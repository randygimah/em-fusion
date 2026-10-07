"""The root Makefile as the containerised command surface. Spec: ops-003.

These tests read the Makefile and assert its structure. That is a weaker kind
of evidence than running the targets, and the limit is worth stating: a target
can be well-formed and still fail against a real Docker daemon. What these
catch is the class of defect that has actually occurred in this project --
a target that silently does less than its name claims. `test-backend` ran with
`--no-deps` for weeks, which starts the backend container alone, so every
database test would have skipped while the target reported success.

The Makefile lives at the repository root, which is **not** mounted into the
backend container: Compose mounts `./backend:/app`. Rather than let these skip
in the containerised run -- the one this item calls authoritative -- the
`test-backend` target mounts the file read-only at `/repo/Makefile`, following
the pattern `generate` already uses for `DATA_DIR`. A skip here would be the
same failure mode the tests exist to catch, one level up.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

#: Native checkout, then the read-only mount used inside the container.
CANDIDATE_PATHS = (
    Path(__file__).resolve().parents[2] / "Makefile",
    Path("/repo/Makefile"),
)

#: Enumerated by ops-003. The item's own text says that enumerating them is
#: what makes it the thing to amend whenever one is added -- so this set is the
#: enforcement of that sentence rather than a restatement of it.
REQUIRED_TARGETS = {
    "build",
    "up",
    "down",
    "demo",
    "generate",
    "migrate",
    "db-test-create",
    # spec: adp-007 -- added 2026-09-04 with the replay entrypoint. ops-003's
    # own text makes this set the enforcement of "this item enumerates its
    # targets", so a new target lands here and not only in the Makefile.
    "replay",
    # spec: scn-003 -- added 2026-09-12 with the batch runner. `generate` is
    # the one target that had no build prerequisite, and the pipeline service
    # builds its own image rather than sharing the backend's, so a stale image
    # ran yesterday's dependencies against today's code.
    "build-pipeline",
    "test",
    "test-backend",
    "test-frontend",
    # spec: ops-003 -- added 2026-09-19. Every measurement had been run by
    # hand-writing a compose invocation, which is precisely where the wrong
    # environment variable gets supplied; see ops-004 and docs/qa.md 84.
    "measure",
    # spec: ops-006 -- added 2026-10-07. The frontend service is a static build,
    # so a frontend edit was invisible until an image rebuild while the backend
    # reloaded on save (docs/qa.md 153).
    "dev",
}

#: Tools that would mean the root Makefile needs a host toolchain beyond
#: Docker. Each may appear only inside a compose invocation.
HOST_TOOLCHAIN = ("uv ", "pnpm ", "pytest ", "npm ", "node ", "alembic ", "black ")


def _makefile() -> str:
    for path in CANDIDATE_PATHS:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise AssertionError(  # pragma: no cover -- a broken checkout or mount
        f"root Makefile not found at any of {[str(p) for p in CANDIDATE_PATHS]}. "
        "Skipping is deliberately not an option here: see the module docstring."
    )


def _recipes() -> dict[str, list[str]]:
    """Target name to its recipe lines, with backslash continuations joined."""
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    pending = ""

    for raw in _makefile().splitlines():
        if raw.startswith("\t"):
            if current is None:
                continue
            pending += raw.strip()
            if pending.endswith("\\"):
                pending = pending[:-1] + " "
                continue
            recipes[current].append(pending)
            pending = ""
            continue

        pending = ""
        match = re.match(r"^([A-Za-z0-9_-]+)\s*:(?!=)", raw)
        current = match.group(1) if match else None
        if current is not None:
            recipes.setdefault(current, [])

    return recipes


def _phony_targets() -> set[str]:
    text = _makefile()
    declared: set[str] = set()
    for match in re.finditer(r"^\.PHONY:(.*?)(?=^\S|\Z)", text, re.M | re.S):
        declared.update(match.group(1).replace("\\", " ").split())
    return declared


# ------------------------------------------------------------------- targets


@pytest.mark.parametrize("target", sorted(REQUIRED_TARGETS))
def test_every_enumerated_target_exists(target: str) -> None:
    # spec: ops-003
    assert target in _recipes()


@pytest.mark.parametrize("target", sorted(REQUIRED_TARGETS))
def test_every_enumerated_target_is_phony(target: str) -> None:
    # spec: ops-003 -- without .PHONY, a target sharing a name with a file or
    # directory silently does nothing and reports success
    assert target in _phony_targets()


def test_migrate_applies_the_alembic_revisions() -> None:
    # spec: ops-003, db-001
    recipe = " ".join(_recipes()["migrate"])

    assert "alembic upgrade head" in recipe
    assert "$(COMPOSE)" in recipe


# ----------------------------------------------------- the database tier runs


def test_test_backend_does_not_use_no_deps() -> None:
    # spec: ops-003 -- the named failure case, and a real regression: --no-deps
    # starts the backend container alone, so postgis never comes up and every
    # database test skips while the target reports success
    assert "--no-deps" not in " ".join(_recipes()["test-backend"])


def test_test_backend_supplies_a_test_database_url() -> None:
    # spec: ops-003, db-001 -- without it the database tier skips, which is the
    # second failure case
    assert "TEST_DATABASE_URL" in " ".join(_recipes()["test-backend"])


def test_test_backend_provisions_the_test_database_first() -> None:
    # spec: ops-003 -- the database must exist before the tests address it, and
    # depending on the target is what stops that being a manual step nobody
    # wrote down (AC-12)
    prerequisites = re.search(r"^test-backend\s*:([^\n#]*)", _makefile(), re.M)

    assert prerequisites is not None
    assert "db-test-create" in prerequisites.group(1)


def test_db_test_create_is_idempotent_and_installs_postgis() -> None:
    # spec: ops-003, db-001 -- run twice it must not fail, and the extension is
    # what db-001's migrations assert rather than create
    recipe = " ".join(_recipes()["db-test-create"])

    assert "CREATE EXTENSION IF NOT EXISTS postgis" in recipe
    assert "pg_database" in recipe, "must check for the database before creating it"


# ------------------------------------------------------------ no silent success


def test_no_recipe_ignores_its_own_failures() -> None:
    # spec: ops-003 -- the first failure case. A leading `-` or a trailing
    # `|| true` makes make continue past a failed command, which is precisely
    # "a target that succeeds while the underlying compose command fails".
    offenders = [
        f"{target}: {line}"
        for target, lines in _recipes().items()
        for line in lines
        if line.startswith("-") or "|| true" in line or "; true" in line
    ]

    assert offenders == []


def test_no_target_needs_a_host_toolchain_beyond_docker() -> None:
    # spec: ops-003 -- what makes the demo reproducible on a machine that is
    # not the development one. backend/Makefile is the native equivalent and is
    # deliberately not merged with this file.
    offenders = [
        f"{target}: {line}"
        for target, lines in _recipes().items()
        for line in lines
        if any(tool in line for tool in HOST_TOOLCHAIN)
        and "$(COMPOSE)" not in line
        and "$(MAKE)" not in line
    ]

    assert offenders == []


# ------------------------------------------- the frontend healthcheck, ops-001
#
# These read two files together, because each is individually correct and the
# defect lives only in the relationship between them: nginx binds an address,
# the healthcheck names one, and nothing before this asserted they agree.

COMPOSE_PATHS = (
    Path(__file__).resolve().parents[2] / "compose.yaml",
    Path("/repo/compose.yaml"),
)
NGINX_PATHS = (
    Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf",
    Path("/repo/frontend/nginx.conf"),
)


def _read_first(candidates: tuple[Path, ...]) -> str:
    """Read whichever of these exists. Never skip.

    The repository root is not the backend's build context, so `make
    test-backend` mounts each file this reads at `/repo`. A missing mount must
    fail loudly rather than quietly skip — a skipped structural test is a test
    that passes for the wrong reason, which this file's docstring already
    argues at length.
    """
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise AssertionError(  # pragma: no cover -- a broken checkout or mount
        f"not found at any of {[str(p) for p in candidates]}. Skipping is "
        "deliberately not an option: see the module docstring."
    )


def _nginx_listens() -> list[str]:
    """The `listen` directives nginx actually declares, comments removed."""
    source = "\n".join(
        line
        for line in _read_first(NGINX_PATHS).splitlines()
        if not line.strip().startswith("#")
    )
    return [m.strip() for m in re.findall(r"\blisten\s+([^;]+);", source)]


def _frontend_healthcheck_url() -> str:
    """The URL the frontend service's healthcheck probes."""
    compose = _read_first(COMPOSE_PATHS)
    frontend = compose[compose.index("\n  frontend:") :]
    match = re.search(r"healthcheck:.*?(https?://[^\"'\s\]]+)", frontend, re.S)
    assert match is not None, "the frontend service declares no healthcheck URL"
    return match.group(1)


def test_the_frontend_healthcheck_names_a_port_nginx_listens_on() -> None:
    """A check on the wrong port reports a healthy service as broken."""
    # spec: ops-001
    url = urlparse(_frontend_healthcheck_url())
    ports = {listen.split()[-1].rsplit(":", 1)[-1] for listen in _nginx_listens()}

    assert str(url.port) in ports


def test_the_frontend_healthcheck_names_an_address_nginx_binds() -> None:
    """The defect that left the container permanently unhealthy. Spec: ops-001.

    `listen 8080;` binds IPv4 only. Inside the image `localhost` resolves to
    `::1` first, so the probe was refused while the service answered every real
    request correctly. Verified in the running container: `127.0.0.1` succeeded,
    `[::1]` and `localhost` were both refused.

    A hostname is only safe here once nginx binds IPv6 too, so the assertion is
    conditional on what nginx declares rather than a flat ban — otherwise it
    would forbid the very fix that would make a hostname correct.
    """
    # spec: ops-001
    host = urlparse(_frontend_healthcheck_url()).hostname
    binds_ipv6 = any("[::]" in listen for listen in _nginx_listens())

    if not binds_ipv6:
        assert host == "127.0.0.1", (
            f"nginx binds IPv4 only, so the healthcheck must name 127.0.0.1, "
            f"not {host!r}: a name resolving to ::1 is refused."
        )


def test_measure_never_touches_the_test_database_url() -> None:
    """The one variable a measurement must never carry.

    `measure` reads the database that is already running, which is the
    application's -- the correct target for a measurement and the
    catastrophic one for a test. A command surface offering a second route
    to `TEST_DATABASE_URL` would be a second way to make the mistake
    `ops-004` exists to catch."""
    # spec: ops-003, ops-004
    recipe = " ".join(_recipes()["measure"])
    assert "TEST_DATABASE_URL" not in recipe


def test_measure_does_not_start_the_database() -> None:
    """A measurement reads a corpus that is already there. Letting compose
    bring dependencies up would start an empty database and measure it."""
    # spec: ops-003
    assert "--no-deps" in " ".join(_recipes()["measure"])


# ------------------------------------------------ the frontend dev server, ops-006
#
# The `frontend` service is nginx over a production build frozen when the image
# was built, so an edit is invisible on :8080 until a rebuild. `frontend-dev`
# serves the working tree through Vite. Each assertion below is one of the
# item's failure cases, and every one of them is silent when it happens.

DOCKERFILE_PATHS = (
    Path(__file__).resolve().parents[2] / "frontend" / "Dockerfile",
    Path("/repo/frontend/Dockerfile"),
)


def _service(name: str) -> str:
    """One service's block of compose.yaml, up to the next top-level key."""
    compose = _read_first(COMPOSE_PATHS)
    start = compose.find(f"\n  {name}:\n")
    assert start >= 0, f"compose.yaml declares no {name!r} service"
    block = compose[start + 1 :]
    following = re.search(r"\n  [A-Za-z0-9_-]+:\n|\n[A-Za-z]", block[1:])
    return block if following is None else block[: following.start() + 1]


def _uncommented(block: str) -> str:
    return "\n".join(
        line for line in block.splitlines() if not line.strip().startswith("#")
    )


def test_the_dev_server_is_profiled_out_of_the_ordinary_stack() -> None:
    """`docker compose up`, `make up` and `make demo` stay the nginx path."""
    # spec: ops-006, ops-001, AC-12
    service = _uncommented(_service("frontend-dev"))
    recipes = _recipes()

    assert re.search(r"profiles:\s*\[\s*[\"']dev[\"']\s*\]", service)
    for target in ("up", "demo"):
        assert not any("--profile dev" in line for line in recipes[target])


def test_the_dev_server_serves_the_working_tree_on_1234() -> None:
    # spec: ops-006
    service = _uncommented(_service("frontend-dev"))

    assert re.search(r"[\"']1234:1234[\"']", service)
    assert re.search(r"-\s*\./frontend:/app\s*$", service, re.M)
    assert "pnpm" in service and "dev" in service
    assert "0.0.0.0" in service, "Vite binds localhost only unless told otherwise"


def test_the_containers_node_modules_is_not_the_hosts() -> None:
    """The host's install holds macOS binaries; the mount must not shadow Linux's."""
    # spec: ops-006
    service = _uncommented(_service("frontend-dev"))

    assert re.search(r"-\s*/app/node_modules\s*$", service, re.M)


def test_the_dev_server_forwards_api_to_the_backend_service() -> None:
    """The sharpest failure case: inside the container, localhost is itself.

    Every call would fail, and the picture's first-paint mock would make the
    screen look healthy while showing invented data.
    """
    # spec: ops-006, api-003
    service = _uncommented(_service("frontend-dev"))
    match = re.search(r"API_PROXY_TARGET:\s*[\"']?(\S+?)[\"']?\s*$", service, re.M)

    assert match is not None, "frontend-dev sets no API_PROXY_TARGET"
    assert urlparse(match.group(1)).hostname == "backend"
    assert "VITE_" not in service, "a VITE_ variable is published to the browser"


def test_the_dev_server_does_not_try_to_open_a_browser() -> None:
    # spec: ops-006 -- there is no browser in the container.
    service = _uncommented(_service("frontend-dev"))

    assert re.search(r"BROWSER:\s*[\"']?none[\"']?\s*$", service, re.M)


def test_the_dev_server_starts_from_an_install_that_does_not_type_check() -> None:
    """A tree mid-edit routinely fails `tsc -b`; the dev server must still start.

    So it targets a `deps` stage that installs and builds nothing, and the
    production `build` stage starts from that stage rather than repeating it.
    """
    # spec: ops-006
    service = _uncommented(_service("frontend-dev"))
    dockerfile = _read_first(DOCKERFILE_PATHS)
    stages = dict(
        (alias, base)
        for base, alias in re.findall(r"^FROM\s+(\S+)\s+AS\s+(\S+)", dockerfile, re.M)
    )

    assert re.search(r"target:\s*deps\s*$", service, re.M)
    assert "deps" in stages and stages.get("build") == "deps"
    deps = dockerfile[dockerfile.index("AS deps") : dockerfile.index("AS build")]
    assert "pnpm install --frozen-lockfile" in deps
    assert "pnpm run build" not in deps


def test_make_dev_starts_the_dev_profile_with_a_fresh_node_modules() -> None:
    """An anonymous volume outlives its container.

    After a lockfile change it would go on serving the previous install while
    the image held the new one, so the target renews it every time.
    """
    # spec: ops-006, ops-003
    recipe = " ".join(_recipes()["dev"])

    assert "--profile dev" in recipe
    assert "frontend-dev" in recipe
    assert "--renew-anon-volumes" in recipe
