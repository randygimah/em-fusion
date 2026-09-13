import type { ScenarioLibraryEntry } from "../types/scenarioControl";

/**
 * The five scenario types, with the copy that describes them. spec: api-010.
 *
 * This is not a mock and no endpoint serves it. It is the closed set of types
 * the generator can produce — already parity-checked against the backend enum
 * by `backend/tests/test_scn_control_contract.py` — with presentation text
 * attached. It moved out of `mocks/scenarioControlMock.ts` when the runs
 * beside it were retired, because deleting that fixture outright would have
 * taken with it the one half nothing else provides.
 *
 * A sixth entry here would put a type on screen that the generator cannot
 * produce (`scn-002`, FR-202): spectral extent is a parameter of two of these
 * rather than a type of its own.
 */
export const SCENARIO_LIBRARY: ScenarioLibraryEntry[] = [
  {
    id: "normal-baseline",
    name: "Normal baseline",
    description: "Real replayed traffic and a quiet radio grid. Nothing staged; the false-positive control.",
  },
  {
    id: "gnss-degradation",
    name: "GNSS signal degradation",
    description: "A raised noise floor over a zone, with the aircraft inside it holding their last position.",
  },
  {
    id: "rf-sensor-fault",
    name: "RF sensor fault",
    description: "One receiver deviating while its neighbours stay nominal. The tracks are untouched.",
  },
  {
    id: "aircraft-coverage-gap",
    name: "Data-source coverage gap",
    description: "Aircraft inside a zone stop reporting, with no radio signature to explain it.",
  },
  {
    id: "ambiguous-mixed-evidence",
    name: "Ambiguous mixed evidence",
    description: "Both signatures at once, so the evidence supports more than one explanation.",
  },
];
