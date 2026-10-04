import { Fragment } from "react";
import {
  absenceLabel,
  evidenceLabel,
  findingLabel,
  groundingLabel,
} from "../../lib/detectionVocabulary";
import type {
  EvidenceAccount,
  EvidenceGroup,
  ExplainedClaim,
  UnclaimedBundle,
  UnexplainedClaim,
} from "../../types/evidence";

/**
 * Why this hour's conclusions were reached. spec: op-010.
 *
 * The screen states a conclusion and, until this panel, gave no route to what
 * it rests on — which is the one thing this project claims to be about.
 *
 * **It renders what it is given and groups nothing.** The grouping, the
 * collapsing of identical wording and the counts are all `api-015`'s, done once
 * on the server inside the coverage gate. A second implementation here is the
 * duplication this repository has recorded over distance already.
 *
 * **Four states, four sentences.** No answer at all is the client having none;
 * `null` is the server saying no pass examined this hour; three empty lists is
 * a quiet hour, which is a correct non-detection and 160 of the 400 hours in
 * the store; and a claim with no bundle is a gap in the pipeline, which is 140
 * of the 240 claim-bearing hours and every hour the selector offers first. The
 * four are different facts and the panel never falls silent: a panel that
 * disappears cannot be told from one with nothing to say.
 */

// The instant in the simulated time it happened at, sliced from the ISO string
// rather than formatted through `Date` — these are instants in a replayed 2022
// hour and a local format shifts them by the viewer's offset. The same choice
// the timeline strip makes, for the same recorded reason.
const clock = (iso: string): string => iso.slice(11, 19);

const span = (from: string, to: string): string => `${clock(from)}–${clock(to)}`;

const findings = (count: number): string =>
  `${count} ${count === 1 ? "finding" : "findings"}`;

const channels = (indices: readonly number[]): string =>
  indices.length === 1 ? `channel ${indices[0]}` : `channels ${indices.join(", ")}`;

// Which halves of the picture this claim draws on. A fusion claim spans both by
// definition, which is why the mode is per item on the wire.
const MODES: Record<string, string> = {
  synthetic: "synthetic RF",
  replayed: "replayed tracks",
};
const modes = (spanned: readonly string[]): string =>
  spanned.map((mode) => MODES[mode] ?? mode).join(" and ");

const MUTED = "font-mono text-xs text-[#8c909f]";

// The group carrying the claim's own conclusion. It is a real evidence item —
// the rule's reasoning in its own words — but labelled with `evidenceLabel` it
// repeats the heading two centimetres above it, which reads as a bug. Named for
// what it is instead. Found by looking at the running screen.
const VERDICT = "The rule's own reasoning";

const Group = ({ group, verdict }: { group: EvidenceGroup; verdict: boolean }) => (
  <li className="border-l-2 border-[#424754] pl-3">
    <p className="flex flex-wrap items-baseline gap-2">
      {/* Measured or concluded, in words rather than in styling, so the
          distinction survives a screenshot and a test can assert on it. */}
      <span className="font-mono text-xs uppercase tracking-[0.05em] text-[#4cd7f6]">
        {groundingLabel(group.grounding)}
      </span>
      <span className="text-sm">{verdict ? VERDICT : evidenceLabel(group.findingType)}</span>
    </p>
    {/* The count leads. "Nine aircraft stopped reporting inside the zone" is
        the claim an analyst can weigh; the identifiers are traceability. */}
    <p className={`mt-1 ${MUTED}`}>
      {findings(group.count)} · {span(group.observedFrom, group.observedTo)} ·{" "}
      {modes([group.dataMode])}
    </p>
    {group.statements.map((statement) => (
      <p className="mt-1 text-sm text-[#c2c6d6]" key={statement.text}>
        {statement.text}
        <span className={`ml-2 ${MUTED}`}>
          {statement.count > 1 ? `×${statement.count} · ` : ""}
          {statement.sources.join(", ")}
        </span>
      </p>
    ))}
  </li>
);

const Explained = ({ claim }: { claim: ExplainedClaim }) => (
  <article className="mt-4 border-t border-[#424754] pt-4 first:mt-0 first:border-0 first:pt-0">
    {/* The conclusion in the words the summary and the timeline use, from the
        one vocabulary module (op-003). */}
    <h3 className="text-lg font-semibold text-[#adc6ff]">{findingLabel(claim.findingType)}</h3>
    <p className={`mt-1 ${MUTED}`}>
      {claim.subject} · {span(claim.observedFrom, claim.observedTo)} · {channels(claim.channels)} ·{" "}
      {modes(claim.dataModes)}
    </p>

    <ul aria-label="Supporting evidence" className="mt-3 space-y-3">
      {/* Keyed on the pair, which is the grouping key `api-015` guarantees
          unique within a bundle — so there is no index to fall back on and no
          duplicate for React to resolve arbitrarily. */}
      {claim.evidence.map((group) => (
        <Group
          group={group}
          key={`${group.ruleId}:${group.findingType}`}
          verdict={group.findingType === claim.findingType}
        />
      ))}
    </ul>

    {claim.uncertainties.length > 0 && (
      <div className="mt-4 border-t border-[#424754] pt-3">
        <h4 className="font-mono text-xs uppercase tracking-[0.05em] text-[#8c909f]">
          What this does not know
        </h4>
        <dl className="mt-2 space-y-2">
        {claim.uncertainties.map((absence) => (
          <Fragment key={`${absence.kind}:${absence.subject}:${absence.statement}`}>
            <dt className="font-mono text-xs uppercase tracking-[0.05em] text-[#ffb786]">
              {absenceLabel(absence.kind)}
              {absence.count > 1 ? ` ×${absence.count}` : ""}
            </dt>
            {/* Verbatim and untruncated: the kind says what sort of
                not-knowing it is, the statement is the only part a person can
                weigh. */}
            <dd className="text-sm text-[#c2c6d6]">{absence.statement}</dd>
          </Fragment>
        ))}
        </dl>
      </div>
    )}

    {claim.superseded.length > 0 && (
      // Named a region rather than given `role="group"`: Biome rejects that in
      // favour of `<fieldset>`, which means form controls, and a suppression
      // does not work in JSX attribute position.
      <section aria-label="Ruled out" className="mt-4 border-t border-[#424754] pt-3">
        <h4 className="font-mono text-xs uppercase tracking-[0.05em] text-[#8c909f]">
          Ruled out for this zone
        </h4>
        {claim.superseded.map((loser) => (
          <p className="mt-1 text-sm text-[#c2c6d6]" key={`${loser.ruleId}:${loser.anomalyType}`}>
            {findingLabel(loser.anomalyType)}
            <span className={`ml-2 ${MUTED}`}>
              {loser.claimedBy} claimed it first — {loser.reason}
            </span>
          </p>
        ))}
      </section>
    )}
  </article>
);

const Unexplained = ({ claim }: { claim: UnexplainedClaim }) => (
  <p className="mt-4 border-t border-[#424754] pt-4 text-sm first:mt-0 first:border-0 first:pt-0">
    <span className="text-[#adc6ff]">{findingLabel(claim.findingType)}</span>
    <span className={`ml-2 ${MUTED}`}>
      {claim.subject} · {span(claim.observedFrom, claim.observedTo)}
    </span>
    <span className="mt-1 block text-[#8c909f]">
      The store holds no evidence for this conclusion. The hour was examined and the finding
      recorded; the account of what it rests on was built and not kept.
    </span>
  </p>
);

const Unclaimed = ({ bundle }: { bundle: UnclaimedBundle }) => (
  <p className="mt-2 text-sm text-[#8c909f]">
    Stored evidence for {findingLabel(bundle.findingType)} on {bundle.subject}, covering{" "}
    {span(bundle.observedFrom, bundle.observedTo)}, does not match any conclusion this hour
    reports. It is held back rather than shown, because evidence put under a conclusion it was
    not built for is worse than evidence withheld.
  </p>
);

export const EmEvidencePanel = ({
  account,
}: {
  account: EvidenceAccount | null | undefined;
}) => (
  <section
    aria-label="Evidence"
    className="border border-[#424754] bg-[#1d2027] p-4"
  >
    <h2 className="font-mono text-sm uppercase tracking-[0.05em] text-[#c2c6d6]">Evidence</h2>

    {account === undefined ? (
      <p className="mt-4 text-sm text-[#8c909f]">
        The evidence for this hour could not be loaded. This says nothing about the hour — only
        that the request for it did not arrive.
      </p>
    ) : account === null ? (
      <p className="mt-4 text-sm text-[#8c909f]">
        This hour has not been examined, so there is nothing to explain yet.
      </p>
    ) : account.explained.length + account.unexplained.length === 0 ? (
      <p className="mt-4 text-sm text-[#8c909f]">
        Nothing was reported for this hour, so there is nothing to explain. The detectors looked
        and found no conclusion to draw.
      </p>
    ) : (
      <div className="mt-4">
        {account.explained.map((claim) => (
          <Explained claim={claim} key={claim.bundleId} />
        ))}
        {account.unexplained.map((claim) => (
          <Unexplained
            claim={claim}
            key={`${claim.ruleId}:${claim.findingType}:${claim.observedFrom}`}
          />
        ))}
      </div>
    )}

    {/* Outside the branch above: a stale bundle is a fact about the hour
        whatever its conclusions look like, and dropped silently the hour reads
        as fully explained while some of its evidence was discarded. */}
    {account?.unclaimed.map((bundle) => (
      <Unclaimed bundle={bundle} key={bundle.bundleId} />
    ))}
  </section>
);
