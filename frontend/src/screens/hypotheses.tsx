import { type ReactNode, useEffect, useRef, useState } from "react";
import { EmLevel } from "../components/em/EmLevel";
import { EmStatusPill } from "../components/em/EmStatusPill";
import { MapView } from "../components/map/MapView";
import { affectedAreaBounds, matchZone } from "../lib/affectedArea";
import { HypothesisNotFoundError } from "../lib/api";
import { evidenceLabel } from "../lib/detectionVocabulary";
import {
  CITATION_GROUNDING_COPY,
  centreLabel,
  citationGroundingLabel,
  instantLabel,
  provenance,
  SCREEN_COPY,
  STORED_GROUNDING_COPY,
  windowLabel,
} from "../lib/hypothesisVocabulary";
import { cn } from "../lib/utils";
import { hypothesisHash } from "../routes";
import type { HypothesisDetail, HypothesisList } from "../types/hypotheses";
import type { OperationalPicture } from "../types/operationalPicture";

/**
 * The Hypotheses screen. spec: hyp-001, hyp-002, hyp-003 (amended 2026-10-11).
 *
 * The design's skeleton (assets/Design/Hypothesis_analysis_v2/) with its
 * invented content replaced by what is stored (qa.md 157): a list to choose
 * from, the explanation the address names, its evidence with each citation's
 * check re-run on read, its doubts as two sections, and the affected area on a
 * map zoomed to it, drawn flat because nothing measures intensity between the
 * receivers (qa.md 164).
 *
 * Data arrives through the loaders App.tsx hands down, fetched when the address
 * changes and never polled. It names each explanation's generator, so it must
 * not be shown to the second rater before their scoring is done.
 */

interface Props {
  hypothesisId: number | null;
  loadList: () => Promise<HypothesisList>;
  loadDetail: (id: number) => Promise<HypothesisDetail>;
  loadPicture: (runId: number) => Promise<OperationalPicture>;
}

type Outcome<T> = { state: "loading" } | { state: "ready"; value: T } | { state: "failed"; error: unknown };

/**
 * What a loader answered for `key`, or loading. An answer for a key no longer
 * asked for is dropped, and one held for another key is never returned, so a
 * new address never shows the previous explanation.
 */
function useLoaded<T>(key: string | null, load: () => Promise<T>): Outcome<T> {
  const [held, setHeld] = useState<{ key: string; outcome: Outcome<T> } | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    if (key === null) return;
    let live = true;
    loadRef.current().then(
      (value) => live && setHeld({ key, outcome: { state: "ready", value } }),
      (error: unknown) => live && setHeld({ key, outcome: { state: "failed", error } }),
    );
    return () => {
      live = false;
    };
  }, [key]);
  return key !== null && held?.key === key ? held.outcome : { state: "loading" };
}

const PANEL = "border border-[#424754] bg-[#1d2027] p-4";
const HEADING = "font-mono text-xs uppercase tracking-wide text-[#c2c6d6]";
const NOTE = "text-sm text-[#8c909f]";

const HypothesesScreen = ({ hypothesisId, loadList, loadDetail, loadPicture }: Props) => {
  const list = useLoaded("list", loadList);
  const detail = useLoaded(hypothesisId === null ? null : String(hypothesisId), () =>
    loadDetail(hypothesisId as number).then((answer) => {
      // An answer about another explanation is refused, never shown under this address.
      if (answer.id !== hypothesisId) throw new Error(`asked for explanation ${hypothesisId}, answered ${answer.id}`);
      return answer;
    }),
  );
  const runId = detail.state === "ready" ? detail.value.bundle.runId : null;
  const picture = useLoaded(runId === null ? null : String(runId), () => loadPicture(runId as number));

  return (
    <main className="min-h-screen bg-[#0b0e15] p-6 text-[#e1e2ec]">
      <h1 className="text-xl font-semibold">Hypotheses</h1>
      <div className="mt-4 grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <ExplanationList
          list={list}
          openId={hypothesisId}
        />
        {hypothesisId === null ? (
          <p className={NOTE}>{SCREEN_COPY.choose}</p>
        ) : detail.state === "loading" ? (
          <p className={NOTE}>{SCREEN_COPY.loading(hypothesisId)}</p>
        ) : detail.state === "failed" ? (
          <p className={detail.error instanceof HypothesisNotFoundError ? NOTE : "text-sm text-[#ffb4ab]"}>
            {detail.error instanceof HypothesisNotFoundError ? SCREEN_COPY.notFound(hypothesisId) : SCREEN_COPY.failed(hypothesisId)}
          </p>
        ) : (
          <Detail
            detail={detail.value}
            picture={picture}
          />
        )}
      </div>
    </main>
  );
};

const ExplanationList = ({ list, openId }: { list: Outcome<HypothesisList>; openId: number | null }) => (
  <nav
    aria-label="Explanations"
    className={cn(PANEL, "self-start")}
  >
    <p className={HEADING}>Explanations</p>
    {list.state === "loading" && <p className={cn(NOTE, "mt-3")}>Loading the list of explanations.</p>}
    {list.state === "failed" && <p className="mt-3 text-sm text-[#ffb4ab]">{SCREEN_COPY.listFailed}</p>}
    {list.state === "ready" && list.value.hypotheses.length === 0 && (
      <>
        <p className={cn(NOTE, "mt-3")}>{SCREEN_COPY.emptyList}</p>
        {list.value.unreviewableBundles > 0 && <p className={cn(NOTE, "mt-2")}>{SCREEN_COPY.unreviewable(list.value.unreviewableBundles)}</p>}
      </>
    )}
    {list.state === "ready" && list.value.hypotheses.length > 0 && (
      <ul className="mt-3 space-y-1">
        {list.value.hypotheses.map((hypothesis) => (
          <li key={hypothesis.id}>
            <a
              aria-current={hypothesis.id === openId ? "page" : undefined}
              className={cn(
                "block border-l-2 border-transparent p-2 hover:bg-[#272a31] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#adc6ff]",
                hypothesis.id === openId && "border-[#adc6ff] bg-[#272a31]",
              )}
              href={hypothesisHash(hypothesis.id)}
            >
              <span className="block text-sm">{hypothesis.hypothesisTitle}</span>
              <span className="mt-1 flex flex-wrap items-center gap-2">
                <EmStatusPill status={hypothesis.status} />
                <span className="font-mono text-xs text-[#8c909f]">{windowLabel(hypothesis.windowStart, hypothesis.windowEnd)}</span>
              </span>
            </a>
          </li>
        ))}
      </ul>
    )}
  </nav>
);

const Section = ({ title, children, className }: { title: string; children: ReactNode; className?: string }) => (
  <section className={cn(PANEL, className)}>
    <h3 className={HEADING}>{title}</h3>
    {children}
  </section>
);

const Sentences = ({ sentences }: { sentences: string[] }) =>
  sentences.length === 0 ? (
    <p className={cn(NOTE, "mt-3")}>{SCREEN_COPY.noneRecorded}</p>
  ) : (
    <ul className="mt-3 list-disc space-y-2 pl-5 text-sm">
      {sentences.map((sentence) => (
        <li key={sentence}>{sentence}</li>
      ))}
    </ul>
  );

const Detail = ({ detail, picture }: { detail: HypothesisDetail; picture: Outcome<OperationalPicture> }) => {
  const writer = provenance(detail);
  const { bundle } = detail;
  const centre = centreLabel(bundle.latitude, bundle.longitude);
  const citations = [...detail.supportingEvidence].sort((a, b) => a.position - b.position);

  // Two columns of their own from xl, so the map sits beside the explanation
  // rather than below the whole list.
  return (
    <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
      <div className="min-w-0 space-y-4">
        <header className={cn(PANEL, "p-5")}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-mono text-xs uppercase text-[#8c909f]">{`Explanation ${detail.id} · Run ${bundle.runId}`}</p>
              <h2 className="mt-1 text-2xl font-semibold">{detail.hypothesisTitle}</h2>
            </div>
            <EmStatusPill status={detail.status} />
          </div>
          {/* Who wrote it (ai-010): a fallback is a warning, never a neutral label. */}
          <p className={cn("mt-2 text-xs", writer.degraded ? "text-[#ffb786]" : "text-[#8c909f]")}>{writer.text}</p>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <EmLevel
              label="Confidence"
              value={detail.confidence}
            />
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-[#c2c6d6]">Time window</dt>
              <dd className="font-mono">{windowLabel(bundle.windowStart, bundle.windowEnd)}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-[#c2c6d6]">Affected area</dt>
              <dd className="font-mono">{bundle.subject}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-[#c2c6d6]">Receivers in the evidence</dt>
              <dd className="font-mono">{`${bundle.receivers.length} named: ${bundle.receivers.join(", ")}`}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-4">
              <dt className="text-[#c2c6d6]">Centre</dt>
              <dd className="font-mono">{centre}</dd>
            </div>
          </dl>
        </header>

        <Section title="Summary">
          <p className="mt-3 text-sm">{detail.summary}</p>
        </Section>
        <Section title="Recommended action">
          <p className="mt-3 text-sm">{detail.recommendedHumanAction}</p>
        </Section>

        {/* hyp-002: every citation shown, a failing one marked and never hidden. */}
        <Section title="Supporting evidence">
          <p className={cn("mt-3 text-xs", detail.grounding === "passed" ? "text-[#8c909f]" : "text-[#ffb786]")}>
            {STORED_GROUNDING_COPY[detail.grounding] ?? "Unrecognised check result"}
          </p>
          <ol className="mt-3 space-y-3">
            {citations.map((citation) => {
              const grounded = citation.grounding === "grounded";
              return (
                <li
                  className="border border-[#424754] bg-[#191b23] p-3"
                  key={citation.position}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="border border-[#424754] px-1.5 py-0.5 font-mono text-xs">{citation.ruleId}</span>
                    <span className="text-xs text-[#c2c6d6]">{evidenceLabel(citation.findingType)}</span>
                    <span className={cn("ml-auto font-mono text-xs", grounded ? "text-[#4cd7f6]" : "text-[#ffb4ab]")}>
                      {grounded ? CITATION_GROUNDING_COPY.grounded : citationGroundingLabel(citation.grounding)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm">{citation.statement}</p>
                </li>
              );
            })}
          </ol>
        </Section>

        {/* hyp-003: two sections, both open, never merged or categorised. */}
        <Section title="Uncertainty and evidence against">
          <Sentences sentences={detail.evidenceAgainstOrUncertainty} />
        </Section>
        <Section title="Alternative explanations">
          <Sentences sentences={detail.alternativeExplanations} />
        </Section>
      </div>

      <div className="min-w-0 space-y-4">
        <AffectedArea
          centre={centre}
          detail={detail}
          picture={picture}
        />
        <Section title="Verdicts">
          {detail.verdicts.length === 0 ? (
            <p className={cn(NOTE, "mt-3")}>{SCREEN_COPY.noVerdict}</p>
          ) : (
            <ol className="mt-3 space-y-2 text-sm">
              {detail.verdicts.map((verdict) => (
                <li key={verdict.createdAt}>
                  <span className="font-mono">{verdict.verdict}</span>
                  {verdict.note !== null && <span className="block">{verdict.note}</span>}
                  <span className="block font-mono text-xs text-[#8c909f]">{instantLabel(verdict.createdAt)}</span>
                </li>
              ))}
            </ol>
          )}
        </Section>
      </div>
    </div>
  );
};

/**
 * hyp-001 (6): the conclusion's hour, only the receivers its evidence names, its
 * zone at the radius recorded with the claim, zoomed to the area. A fault is a
 * claim about one receiver, so it gets no disc; nor does a zone with no
 * recorded radius or one the hour's map does not hold. Never a default radius.
 */
const AffectedArea = ({ detail, picture, centre }: { detail: HypothesisDetail; picture: Outcome<OperationalPicture>; centre: string }) => {
  const { bundle } = detail;
  let body: ReactNode;
  if (picture.state === "loading") body = <p className={cn(NOTE, "mt-3")}>{SCREEN_COPY.mapLoading}</p>;
  else if (picture.state === "failed") body = <p className="mt-3 text-sm text-[#ffb4ab]">{SCREEN_COPY.mapFailed}</p>;
  else {
    const interference = bundle.anomalyType === "possible_interference_zone";
    const zone = interference ? matchZone(bundle, picture.value.interferenceZones) : null;
    const note = !interference
      ? SCREEN_COPY.notAnArea(bundle.subject)
      : zone === null
        ? SCREEN_COPY.unplaced
        : zone.radiusKm === null
          ? SCREEN_COPY.noRadius
          : null;
    const drawn = picture.value.rfSensors.filter((sensor) => bundle.receivers.includes(sensor.id));
    body = (
      <>
        {/* MapView keeps a 320 px minimum; a shorter box lets it cover what follows. */}
        <div className="mt-3 h-80">
          <MapView
            bounds={affectedAreaBounds({ lat: bundle.latitude, lon: bundle.longitude }, zone?.radiusKm ?? null, drawn)}
            key={detail.id}
            sensors={drawn}
            tracks={[]}
            zones={zone === null ? [] : [zone]}
          />
        </div>
        {note !== null && <p className={cn(NOTE, "mt-2")}>{note}</p>}
      </>
    );
  }
  return (
    <section
      aria-labelledby="affected-area-heading"
      className={PANEL}
    >
      <h3
        className={HEADING}
        id="affected-area-heading"
      >
        Affected area
      </h3>
      {body}
      <p className="mt-2 font-mono text-xs text-[#c2c6d6]">{centre}</p>
    </section>
  );
};

export default HypothesesScreen;
