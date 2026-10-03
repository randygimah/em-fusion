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
 * lives in the evidence bundle, which no endpoint serves yet; inventing a
 * reason here would be prose the system cannot support.
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
