"""Command-line entrypoint for the corpus build. Spec: adp-006.

    python -m app.corpus.build --accept-licence

The one command `adp-005` promises. Before it, that claim was met by a
multi-line `python -c` invocation, which is not a command, cannot go in a
README without inviting transcription error, and carried the download-date
trap this module exists to remove.

Three things are decided here rather than left to whoever types the command,
because each was a way to damage a committed artefact by hand:

* **The download date is derived.** Re-filtering a tarball fetched weeks ago
  must not claim it arrived today. The date advances only when a download
  actually happened, which `is_already_downloaded` decides using the same
  rule `download` uses to skip.
* **A changed content checksum aborts.** The filter is deterministic, so a
  different checksum means the inputs changed, and overwriting would replace
  the corpus behind every measurement already reported. `--replace-corpus`
  is how a deliberate replacement is expressed.
* **The bounding box comes from the manifest.** The manifest is the authority
  on what the corpus covers, so a re-filter cannot quietly apply a different
  box from the one that built the extract it replaces.

The seed is read from the environment and is never a flag: a flag is written
to shell history and shown in a process listing. Only its fingerprint is ever
printed (`dal-004`).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from dotenv import load_dotenv

from app.corpus.extract import BoundingBox
from app.corpus.fetch import (
    ChecksumMismatchError,
    ContentChecksumChanged,
    LicenceNotAcceptedError,
    Opener,
    _urlopen,
    build_corpus,
    is_already_downloaded,
    licence_notice,
    raw_path,
)
from app.dal.pseudonymise import Pseudonymiser

#: Repository root, three levels up from `backend/app/corpus/`.
REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_DATA_DIR = REPO_ROOT / "data" / "opensky"

DEFAULT_ENV_FILE = REPO_ROOT / "backend" / ".env"

DEFAULT_NULL_SAMPLE = 500


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.corpus.build",
        description=(
            "Fetch, verify and filter the OpenSky corpus, then write the "
            "extract, manifest and coverage report."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="directory holding manifest.json (default: %(default)s)",
    )
    parser.add_argument(
        "--accept-licence",
        action="store_true",
        help=(
            "accept the OpenSky terms printed above. Required; there is no "
            "default and it cannot be set from the environment."
        ),
    )
    parser.add_argument(
        "--box",
        nargs=4,
        type=float,
        metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"),
        help="override the bounding box recorded in the manifest",
    )
    parser.add_argument(
        "--null-sample",
        type=int,
        help="rows with a null position to retain (default: from the manifest)",
    )
    parser.add_argument(
        "--replace-corpus",
        action="store_true",
        help=(
            "proceed even though the filtered extract no longer matches the "
            "content checksum in the manifest. This replaces the corpus every "
            "recorded measurement was taken against."
        ),
    )
    return parser


def _box_from(manifest: dict[str, Any], override: list[float] | None) -> BoundingBox:
    if override is not None:
        lat_min, lat_max, lon_min, lon_max = override
        return BoundingBox(
            lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max
        )

    recorded = manifest.get("bounding_box") or {}
    try:
        return BoundingBox(**recorded)
    except TypeError as error:
        raise ValueError(
            f"manifest records no usable bounding_box ({recorded!r}); pass --box"
        ) from error


def _download_date_for(data_dir: Path, manifest: dict[str, Any]) -> str:
    """Today only if a download is actually going to happen.

    The skip is decided by the same checksum rule `download` uses, so the two
    cannot disagree about whether this run fetched anything.
    """
    tarball = raw_path(data_dir, manifest["source_url"])
    if is_already_downloaded(tarball, manifest["original_sha256"]):
        recorded = manifest.get("download_date")
        if recorded:
            return str(recorded)
    return datetime.now(timezone.utc).date().isoformat()


def main(
    argv: Sequence[str] | None = None,
    *,
    opener: Opener = _urlopen,
    env_file: Path | None = DEFAULT_ENV_FILE,
    stdout: TextIO | None = None,
) -> int:
    """Run the build. Returns a process exit code; never raises for an
    expected failure, because a command that reports success on failure
    cannot be used in a script or in CI."""
    out = stdout if stdout is not None else sys.stdout
    args = build_parser().parse_args(argv)

    # The seed lives in backend/.env, so it should not have to be exported by
    # hand. An explicit environment variable still wins.
    if env_file is not None and Path(env_file).is_file():
        load_dotenv(env_file, override=False)

    print(licence_notice(), file=out)
    if not args.accept_licence:
        print(
            "Refusing to continue: pass --accept-licence to accept the terms "
            "above. Acceptance is an explicit act and cannot be set from the "
            "environment.",
            file=sys.stderr,
        )
        return 2

    data_dir = Path(args.data_dir)
    manifest_path = data_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(f"cannot read {manifest_path}: {error}", file=sys.stderr)
        return 2

    try:
        pseudonymiser = Pseudonymiser.from_environment()
        box = _box_from(manifest, args.box)
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    null_sample = args.null_sample
    if null_sample is None:
        null_sample = int(manifest.get("null_sample", DEFAULT_NULL_SAMPLE))

    recorded_content = manifest.get("content_sha256")
    try:
        written = build_corpus(
            data_dir,
            box=box,
            null_sample=null_sample,
            accept_licence=True,
            opener=opener,
            download_date=_download_date_for(data_dir, manifest),
            pseudonymiser=pseudonymiser,
            require_content_sha256=(None if args.replace_corpus else recorded_content),
        )
    except ContentChecksumChanged as error:
        print(
            f"{error}\nPass --replace-corpus only if replacing the corpus is "
            f"what you intend; every reported measurement was taken against "
            f"the recorded one.",
            file=sys.stderr,
        )
        return 1
    except (ChecksumMismatchError, LicenceNotAcceptedError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1

    print("Wrote:", file=out)
    for name in ("opensky_extract.parquet", "manifest.json", "coverage.json"):
        print(f"  {data_dir / name}", file=out)
    print(f"content_sha256:        {written['content_sha256']}", file=out)
    print(f"download_date:         {written['download_date']}", file=out)
    print(f"null_retained:         {written['null_retained']}", file=out)
    print(f"pseudonym_seed_sha256: {written['pseudonym_seed_sha256']}", file=out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
