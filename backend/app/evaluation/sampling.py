"""Drawing the twenty packages the campaign is asked about. Spec: eval-004.

The **first** of that item's two passes, and they happen at different times:
this one before any scored request is made and committed as an artefact, the
export of rendered pairs after `ai-012` has run. Nothing in the backlog owned
producing the sample until the amendment gave it here -- the kind of gap that
only appears when something finally needs it.

**The order matters more than the draw.** "The instrument provably predates
the results" is worth nothing if the corpus does not. A sample chosen after
seeing how the first few packages turned out is a sample chosen to produce an
answer, and no amount of pre-registering a rubric repairs that. So: the draw
is reproducible from one number, the population it drew from is recorded
beside it, and `ai-012` refuses to invent a sample of its own.

**The strata are a constant, not an argument.** Five scenario types produce
two kinds of bundle, and one anomalous type produces none at all -- which is
why the plan's "five bundles from each of four anomalous types" describes a
corpus that cannot exist. Making the strata configurable would let the
pre-registered stratification change without anybody arguing for it, so they
are fixed here and read off the rules' own declarations rather than spelled
again. A bundle of an unrecognised kind is **refused rather than ignored**:
an unknown kind means a third rule has begun producing bundles, and the
stratification then needs revisiting rather than quietly outliving the corpus
it was written for.

**The scenario type is recorded beside the sample and never inside a
bundle.** It is ground truth -- `api-009` keeps it away from the detection
engine and `evb-001` from the model -- but the author's record of which
sample came from where has a different audience, and `eval-002`'s amendment
needs it so the two fault-producing scenario types stay comparable
afterwards without having been stratified on.

**What is recorded is the ingredients, not a sentence describing them.** A
prose "rule" field is a second copy of the code and drifts from it; the seed
plus the exact ordered population lets a reader re-run the draw instead of
taking its word.

Nothing here touches a database. The bundles arrive already read, which is
what lets the corpus decision be checked without Docker and without a corpus.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import zip_longest
from typing import Any, Mapping, Sequence

from app.ai.service import ConfigurationError
from app.detection.bundle import EvidenceBundle
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT

#: The two kinds the corpus really produces, read off the rules that declare
#: them. Two spellings of one vocabulary eventually differ by a letter, and
#: the sample would then lose a whole stratum without saying so.
STRATA: tuple[str, ...] = (INTERFERENCE, FAULT)

#: Ten of each, keeping the pre-registered 20 bundles and 40 hypotheses.
#: Balancing by kind also hands a scorer roughly equal numbers of long and
#: short documents, where stratifying by scenario type would have given
#: three-quarters short ones -- interference bundles are about 3.2x larger.
PER_KIND = 10


@dataclass(frozen=True, slots=True)
class SampleEntry:
    """One drawn package, and the two facts about it worth keeping."""

    bundle_id: int
    bundle: EvidenceBundle
    #: The bundle's own `anomaly_type`, which is what it was stratified on.
    kind: str
    #: Ground truth, held **here** and not on the bundle. Recorded so the
    #: rf-sensor-fault against ambiguous-mixed-evidence split can be looked
    #: at afterwards without having been stratified on.
    scenario_type: str


@dataclass(frozen=True, slots=True)
class BundleSample:
    """The corpus, fixed before the campaign runs, and how it was fixed."""

    entries: tuple[SampleEntry, ...]
    seed: int
    per_kind: int
    #: Every bundle id that was available, per kind, in the order the draw
    #: saw them. With the seed, this is enough to re-run the draw exactly --
    #: which is the whole claim, and is stronger than a sentence about it.
    population: Mapping[str, tuple[int, ...]]

    @property
    def for_campaign(self) -> tuple[tuple[int, EvidenceBundle], ...]:
        """The shape `ai-012` takes, which is `evb-002`'s reader's shape.

        Handed over whole rather than rebuilt by the caller: `ai-012`
        refuses to invent a sample, so the one thing between the two of them
        should be as close to nothing as it can be.
        """
        return tuple((entry.bundle_id, entry.bundle) for entry in self.entries)

    def as_json(self) -> dict[str, Any]:
        """The artefact, committed before the first scored request.

        **Ids, kinds and scenario types only.** The bundles themselves stay
        in the database: they carry pseudonymised aircraft identifiers, and
        NFR-405 keeps those out of anything committed or published.
        """
        return {
            "seed": self.seed,
            "per_kind": self.per_kind,
            "strata": list(STRATA),
            "entries": [
                {
                    "bundle_id": entry.bundle_id,
                    "kind": entry.kind,
                    "scenario_type": entry.scenario_type,
                }
                for entry in self.entries
            ],
            "population": {
                kind: list(ids) for kind, ids in sorted(self.population.items())
            },
        }


def draw_sample(
    available: Sequence[tuple[int, EvidenceBundle]],
    *,
    scenario_types: Mapping[int, str],
    seed: int,
    per_kind: int = PER_KIND,
) -> BundleSample:
    """Draw the pre-registered corpus, reproducibly, and record how.

    `available` is `evb-002`'s reader's output, in whatever order the store
    returned it. `scenario_types` maps a scenario run id to the type that
    produced it -- taken as an argument rather than queried, so this stays a
    pure function and so the join that reaches ground truth happens in the
    caller, in the open.
    """
    if per_kind < 1:
        raise ConfigurationError(
            f"the sample was configured for {per_kind} bundle(s) per kind. A "
            "sample of nothing is drawable and reproducible and is not a "
            "corpus."
        )

    population: dict[str, list[tuple[int, EvidenceBundle]]] = {k: [] for k in STRATA}
    seen: set[int] = set()
    # Sorted by bundle id **before** anything is drawn. The store returns
    # rows in whatever order it finds them, and a draw seeded consistently
    # but fed an inconsistent population is reproducible only by accident --
    # the unordered-result failure this repository has recorded three times.
    for bundle_id, bundle in sorted(available, key=lambda pair: pair[0]):
        if bundle_id in seen:
            raise ConfigurationError(
                f"bundle {bundle_id} appears in the available set more than "
                "once. Drawn twice it would be counted twice in every "
                "per-arm figure while looking like two bundles."
            )
        seen.add(bundle_id)
        if bundle.anomaly_type not in population:
            raise ConfigurationError(
                f"bundle {bundle_id} is a {bundle.anomaly_type!r}, which is "
                f"not one of the stratified kinds {list(STRATA)}. Ignoring it "
                "would keep a stratification the corpus has outgrown, "
                "silently -- a third kind means a third rule has begun "
                "producing bundles and docs/scoring_rubric.md needs "
                "revisiting rather than quietly outliving its corpus."
            )
        if bundle.scenario_run_id not in scenario_types:
            raise ConfigurationError(
                f"bundle {bundle_id} comes from run {bundle.scenario_run_id}, "
                "for which no scenario type was given. An entry recording no "
                "scenario type is one the afterwards-comparison cannot use, "
                "and nineteen usable entries and a blank is worse than a "
                "sample that refused to be drawn."
            )
        population[bundle.anomaly_type].append((bundle_id, bundle))

    entries: list[SampleEntry] = []
    for kind in STRATA:
        pool = population[kind]
        if len(pool) < per_kind:
            raise ConfigurationError(
                f"only {len(pool)} of {kind!r} are available and {per_kind} "
                "were pre-registered. Drawing fewer is a corpus quietly "
                "smaller than the one the instrument was written for, and it "
                "would be discovered, if at all, when the counts were "
                "reported."
            )
        # One generator per kind, seeded the same way, so adding a stratum
        # later does not renumber the draw for the ones beside it.
        for bundle_id, bundle in random.Random(seed).sample(pool, per_kind):
            entries.append(
                SampleEntry(
                    bundle_id=bundle_id,
                    bundle=bundle,
                    kind=kind,
                    scenario_type=scenario_types[bundle.scenario_run_id],
                )
            )

    return BundleSample(
        # Sorted, because the sample is a *set* and its order is not a
        # variable this experiment should introduce. The order a scorer sees
        # is randomised separately by `eval-004`'s export, which is the order
        # blinding actually depends on.
        entries=tuple(sorted(entries, key=lambda entry: entry.bundle_id)),
        seed=seed,
        per_kind=per_kind,
        population={
            kind: tuple(bundle_id for bundle_id, _ in pool)
            for kind, pool in population.items()
        },
    )


#: The second rater's ten packs (`eval-011`), declared in the spec before the
#: draw. A different number from the sample's seed and the pack's label seed,
#: so knowing one says nothing about the others.
SUBSET_SEED = 20261010

#: Five interference and five fault, so the pre-registered kind balance holds.
#: The clean sensor-fault case gets the extra fault pack, because the
#: mixed-evidence packs' cause correctness is reported separately anyway.
SUBSET_QUOTA: Mapping[str, int] = {
    "gnss-degradation": 5,
    "rf-sensor-fault": 3,
    "ambiguous-mixed-evidence": 2,
}


def draw_rater_subset(
    entries: Sequence[Mapping[str, Any]],
    quota: Mapping[str, int],
    seed: int,
) -> tuple[int, ...]:
    """The second rater's packs, in the order they are read. Spec: eval-011.

    `entries` are the committed sample's own (`bundle_id`, `kind`,
    `scenario_type`). Nothing else goes in -- no score sheet and no arm key --
    because the first rater has seen their scores, and a rule that could see
    them would not be a neutral one.

    The kinds alternate so no two look-alike packs sit side by side: the
    first rater met them in blocks of ten because the pack is sorted by id.
    """
    kind_of = {int(e["bundle_id"]): str(e["kind"]) for e in entries}
    by_kind: dict[str, list[int]] = {}
    for scenario_type, k in quota.items():
        ids = sorted(
            int(e["bundle_id"]) for e in entries if e["scenario_type"] == scenario_type
        )
        if not ids:
            raise ConfigurationError(
                f"the quota names {scenario_type!r}, which is not in the sample"
            )
        if k > len(ids):
            raise ConfigurationError(
                f"the quota asks {k} of {scenario_type!r} and the sample "
                f"holds {len(ids)}"
            )
        for bundle_id in random.Random(f"{seed}:{scenario_type}").sample(ids, k):
            by_kind.setdefault(kind_of[bundle_id], []).append(bundle_id)

    rng = random.Random(seed)
    groups = [by_kind[kind] for kind in sorted(by_kind)]
    for group in groups:
        rng.shuffle(group)
    sizes = sorted(len(group) for group in groups)
    if len(groups) != 2 or sizes[1] - sizes[0] > 1:
        raise ConfigurationError(
            f"the quota gives kinds of sizes {sizes}, which cannot alternate: "
            "some packs of one kind would sit side by side"
        )
    lead, follow = groups
    # The larger kind leads; with equal sizes the seed decides.
    if len(follow) > len(lead) or (len(follow) == len(lead) and rng.random() < 0.5):
        lead, follow = follow, lead
    return tuple(b for pair in zip_longest(lead, follow) for b in pair if b is not None)


__all__ = [
    "PER_KIND",
    "STRATA",
    "SUBSET_QUOTA",
    "SUBSET_SEED",
    "BundleSample",
    "SampleEntry",
    "draw_rater_subset",
    "draw_sample",
]
