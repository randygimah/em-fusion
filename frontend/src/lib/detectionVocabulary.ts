import type { AbsenceKind, EvidenceFindingType, Grounding } from "../types/evidence";
import type { ReportableFindingType } from "../types/operationalPicture";

/**
 * What each conclusion says to an analyst. spec: op-003, op-006.
 *
 * **One module, read by two panels.** The payload carries each finding type
 * verbatim — `possible_interference_zone` — which is deliberate: the backend
 * sends facts and never prose, so the wording is composed here, where the rest
 * of the screen's wording lives, rather than arriving from a detector.
 *
 * It is one module because the detection summary and the timeline carry the
 * *same* verbatim type. Written inside either panel, the other would need a
 * second copy, and one conclusion would then have two sentences on one screen
 * with nothing to notice when they drifted apart.
 *
 * The keys are the full union, so a new detection rule cannot reach the screen
 * without its sentence being written: a map that misses a member is a type
 * error rather than a token on screen.
 *
 * The wording states the claim and stops there. *Why* a zone was claimed —
 * which receivers deviated together, over what window, how far above normal —
 * is `op-010`'s evidence panel, whose own wording is below: the bundle carries
 * the rule's sentences, and what is written here is only the label for a block
 * of them.
 */
export const REPORTABLE_COPY: Record<ReportableFindingType, string> = {
  // More than one receiver deviated together over one area, which is what the
  // fusion rule concludes rather than what any single receiver reported.
  possible_interference_zone: "Possible interference across several receivers",
  // One receiver abnormal while its measured neighbours were nominal.
  possible_sensor_fault: "Possible receiver fault",
  // Aircraft reporting stopped with no accompanying radio disturbance. The rule
  // that claims this is not built, so the panel shows it with no count.
  possible_data_source_issue: "Possible data-source problem",
};

/**
 * One finding type as a sentence.
 *
 * **Takes a `string`, not the union**, and that is deliberate rather than a
 * loosening. The contract types both call sites as `string` because they match
 * the backend's own declaration field for field — and one of them,
 * `DetectionCount.findingType`, legitimately carries *intermediate* types like
 * `rf_noise_deviation` that are outside the reportable union and that the
 * summary filters out before it gets here. Declaring a frontend type narrower
 * than the payload it mirrors would be a claim rather than a check, since the
 * payload is cast from JSON.
 *
 * The exhaustiveness guarantee is unaffected: it lives on `REPORTABLE_COPY`
 * above, whose keys are the union, so a new rule still cannot reach the screen
 * without its sentence being written.
 *
 * A type with no entry is **named** rather than printed or dropped: printing
 * the token is the defect being removed, and dropping it hides a built
 * detector. Reachable only if the contract and the backend register drift
 * apart, which a parity test refuses — so this is the second guard, not the
 * first.
 */
export const findingLabel = (type: string): string =>
  REPORTABLE_COPY[type as ReportableFindingType] ?? "Unrecognised finding type";

/**
 * What each piece of evidence is, as a block heading. spec: op-010.
 *
 * **The same module as the conclusions above and not a second one**, which is
 * `op-003`'s rule properly applied rather than stretched: the two key sets
 * overlap. A bundle's own verdict appears as an evidence item carrying the
 * conclusion's finding type, so a panel with its own vocabulary would word that
 * item twice — once as the heading of the claim and once inside its evidence —
 * and the two would be free to drift.
 *
 * Five of these never reached the summary panel. They are the working material
 * a conclusion rests on, and the summary deliberately filters them out: a quiet
 * run holds about 138 track discontinuities.
 *
 * **These are labels, not definitions.** `eval-009`'s glossary defines the same
 * seven types for the human marker at length, because the marker is reading
 * prose with no system in front of them. Here the rule's own sentences are
 * directly below the heading, so the heading says what kind of evidence this is
 * and stops. A type present in one and absent from the other is a gap, which is
 * why a test in the backend suite holds both against what the builder emits
 * rather than against each other.
 */
export const EVIDENCE_COPY: Record<EvidenceFindingType, string> = {
  // A run of consecutive readings on one receiver and one channel that sat far
  // enough from that cell's own normal to be recorded as an event.
  rf_noise_deviation: "Readings away from this cell's normal",
  // One aircraft's position reports stopping for longer than the rule allows.
  track_continuity_gap: "Aircraft reporting broke off",
  // How often aircraft dropped out inside the window, against how often they
  // dropped out in the same area outside it.
  track_rate_excess: "Dropouts inside the window against outside it",
  // A receiver near the one under examination that WAS measured and stayed
  // within its normal range — evidence precisely because nothing was raised
  // for it, which is why the panel marks it as a judgement rather than a
  // reading.
  neighbour_nominal: "A neighbour measured and nominal",
  // How many of a receiver's channels the deviation covered, out of the total
  // it watches.
  channel_adjacency: "How much of the band the deviation covered",
  // The two verdicts, worded exactly as the summary and the timeline word
  // them: the same type, so the same sentence.
  possible_sensor_fault: REPORTABLE_COPY.possible_sensor_fault,
  possible_interference_zone: REPORTABLE_COPY.possible_interference_zone,
};

/**
 * One evidence finding type as a heading.
 *
 * Takes a `string` for `findingLabel`'s reason: the contract types
 * `EvidenceGroup.findingType` as `string` because it mirrors the backend's own
 * declaration field for field, and the payload is cast from JSON. The
 * exhaustiveness guarantee lives on `EVIDENCE_COPY`, whose keys are the union.
 *
 * An unrecognised type is **named** rather than printed, the same choice
 * `findingLabel` makes: printing the token is the defect being removed. The
 * rule's own sentences sit beneath the heading either way, so an unfamiliar
 * kind of evidence is still legible — what is lost is only the label.
 */
export const evidenceLabel = (type: string): string =>
  EVIDENCE_COPY[type as EvidenceFindingType] ?? "Unrecognised kind of evidence";

/**
 * Whether a group was measured or concluded. spec: op-010, evb-001.
 *
 * Two words, because the distinction is the one part of a bundle that cannot
 * be inferred from the rest. A nominal neighbour carries no citations
 * *precisely because* no episode was raised for it; rendered unmarked beside a
 * deviation it reads as a second deviation, which inverts the fault verdict it
 * is evidence for.
 */
export const GROUNDING_COPY: Record<Grounding, string> = {
  observed: "Measured",
  derived: "Concluded",
};

export const groundingLabel = (grounding: string): string =>
  GROUNDING_COPY[grounding as Grounding] ?? "Unrecognised kind of claim";

/**
 * The three things an absence can mean. spec: op-010, evb-001.
 *
 * Three sentences and never one. *Never consulted* is a statement about the
 * design — a single-receiver fault verdict has no aircraft side, so there is no
 * track evidence because none was sought. *Consulted and no basis to judge* is
 * a measurement that could not be made. *Looked at and below the bar* is a
 * measurement that was made and came back negative, which is evidence.
 *
 * Collapsed into one, the rule the bundle builder is organised around is undone
 * at the last boundary before a person — and the first of the three would read
 * as an admission of ignorance the system does not have.
 */
export const ABSENCE_COPY: Record<AbsenceKind, string> = {
  not_applicable: "Not consulted, by design",
  not_measurable: "Consulted, with no basis to judge",
  measured_negative: "Measured, and below the bar",
};

export const absenceLabel = (kind: string): string =>
  ABSENCE_COPY[kind as AbsenceKind] ?? "Unrecognised kind of absence";
