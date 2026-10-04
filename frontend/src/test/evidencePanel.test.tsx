import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmEvidencePanel } from "../components/em/EmEvidencePanel";
import type {
  EvidenceAccount,
  EvidenceGroup,
  EvidenceStatement,
  ExplainedClaim,
  KnownUncertainty,
} from "../types/evidence";

// spec: op-010 — the conclusion says why.
//
// The screen states a conclusion and gives no route to what it rests on, which
// is the one thing this project claims to be about. The account comes from
// api-015 already grouped and already factored, so this panel renders what it
// is given: the grouping is server-side, inside the coverage gate, and a second
// implementation here is the duplication this repository has recorded over
// distance once already.
//
// Three things it has to get right, and all three are about ABSENCE:
//   - a conclusion the store holds no evidence for says so in words. On the
//     real store that is 140 of the 240 claim-bearing hours and every hour the
//     selector offers first, so it is the common case rather than the edge.
//   - a measurement and a judgement are visibly different things. A nominal
//     neighbour is in the bundle *precisely because* nothing was raised for it,
//     and rendered unmarked beside a deviation it reads as a second deviation —
//     which inverts the fault verdict it is evidence for.
//   - the three kinds of not-knowing stay three sentences. Collapsed here,
//     evb-001's organising rule is undone at the last boundary before a person.

const statement = (over: Partial<EvidenceStatement> = {}): EvidenceStatement => ({
  text: "power_dbm deviated by 8.40 dB at its peak",
  count: 1,
  sources: ["RF-06:4"],
  ...over,
});

const group = (over: Partial<EvidenceGroup> = {}): EvidenceGroup => ({
  ruleId: "RF-NOISE",
  findingType: "rf_noise_deviation",
  grounding: "observed",
  dataMode: "synthetic",
  count: 1,
  observedFrom: "2022-06-27T12:31:22+00:00",
  observedTo: "2022-06-27T12:36:52+00:00",
  sources: ["RF-06:4"],
  statements: [statement()],
  ...over,
});

const explained = (over: Partial<ExplainedClaim> = {}): ExplainedClaim => ({
  bundleId: 248,
  ruleId: "FUSION-SPATIAL",
  findingType: "possible_interference_zone",
  subject: "RF-06, RF-07",
  observedFrom: "2022-06-27T12:31:22+00:00",
  observedTo: "2022-06-27T12:36:52+00:00",
  lat: 51.5,
  lon: 6.0,
  channels: [4],
  dataModes: ["replayed", "synthetic"],
  evidence: [group()],
  uncertainties: [],
  superseded: [],
  ...over,
});

const account = (over: Partial<EvidenceAccount> = {}): EvidenceAccount => ({
  runId: 102,
  explained: [],
  unexplained: [],
  unclaimed: [],
  ...over,
});

const panel = () => screen.getByRole("region", { name: "Evidence" });

// Every finding type the bundle builder can emit. Held against the builder's
// own output by a test in the BACKEND suite, where the TypeScript parser lives:
// a type with no sentence written for it would reach an analyst as the raw
// token, which is the defect op-003 removed from the summary panel.
const EVERY_TYPE = [
  "rf_noise_deviation",
  "track_continuity_gap",
  "track_rate_excess",
  "neighbour_nominal",
  "channel_adjacency",
  "possible_sensor_fault",
  "possible_interference_zone",
];

describe("an explained conclusion", () => {
  it("is headed by the conclusion's own sentence and never its raw type", () => {
    // spec: op-010, op-003 — the wording comes from the one vocabulary module
    render(<EmEvidencePanel account={account({ explained: [explained()] })} />);

    expect(
      within(panel()).getByText(/Possible interference across several receivers/),
    ).toBeInTheDocument();
    expect(panel()).not.toHaveTextContent("possible_interference_zone");
  });

  it("names the receivers the bundle names and the window it covers", () => {
    // spec: op-010, api-015 — the bundle's subject, which is its own record of
    // which receivers deviated together; the claim's representative receiver
    // already reaches the screen through the timeline
    render(<EmEvidencePanel account={account({ explained: [explained()] })} />);

    expect(panel()).toHaveTextContent("RF-06, RF-07");
    expect(panel()).toHaveTextContent("12:31:22");
    expect(panel()).toHaveTextContent("12:36:52");
  });

  it("tells a measurement and a judgement apart", () => {
    // spec: op-010, evb-001 — the declaration is the one part of a bundle that
    // cannot be inferred from the rest
    render(
      <EmEvidencePanel
        account={account({
          explained: [
            explained({
              evidence: [
                group(),
                group({
                  ruleId: "SENSOR-FAULT",
                  findingType: "neighbour_nominal",
                  grounding: "derived",
                  statements: [statement({ text: "RF-02 was measured and stayed within 2.0 dB" })],
                }),
              ],
            }),
          ],
        })}
      />,
    );

    const items = within(panel()).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(/measured/i);
    expect(items[1]).toHaveTextContent(/concluded/i);
  });

  it("renders the rule's own sentences verbatim", () => {
    // spec: op-010, api-011 — the backend sends facts; these ARE the facts
    render(<EmEvidencePanel account={account({ explained: [explained()] })} />);

    expect(panel()).toHaveTextContent("power_dbm deviated by 8.40 dB at its peak");
  });

  it("shows one sentence for nine findings that said the same thing", () => {
    // spec: op-010, eval-007 — measured on run 102: nine discontinuities
    // across eight aircraft, one wording. Nine identical lines is a wall.
    const collapsed = group({
      ruleId: "TRACK-GAP",
      findingType: "track_continuity_gap",
      dataMode: "replayed",
      count: 9,
      sources: ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5", "AC-6", "AC-7", "AC-8"],
      statements: [
        statement({
          text: "reporting from this aircraft broke during the window",
          count: 9,
          sources: ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5", "AC-6", "AC-7", "AC-8"],
        }),
      ],
    });

    render(
      <EmEvidencePanel account={account({ explained: [explained({ evidence: [collapsed] })] })} />,
    );

    expect(
      within(panel()).getAllByText(/reporting from this aircraft broke during the window/),
    ).toHaveLength(1);
    expect(panel()).toHaveTextContent("9");
  });

  it("leads with the count rather than the list of aircraft", () => {
    // spec: op-010, NFR-405, NFR-202 — the claim an analyst can weigh is "nine
    // aircraft stopped reporting inside the zone"; the pseudonyms are
    // traceability beneath it
    const collapsed = group({
      ruleId: "TRACK-GAP",
      findingType: "track_continuity_gap",
      dataMode: "replayed",
      count: 9,
      sources: ["AC-48089ab4e5a9", "AC-aaaa1111"],
      statements: [statement({ text: "reporting broke", count: 9, sources: ["AC-48089ab4e5a9"] })],
    });
    render(
      <EmEvidencePanel account={account({ explained: [explained({ evidence: [collapsed] })] })} />,
    );

    const text = panel().textContent ?? "";
    expect(text.indexOf("9")).toBeLessThan(text.indexOf("AC-48089ab4e5a9"));
  });

  it("renders every aircraft as the pseudonym the store holds", () => {
    // spec: op-010, NFR-405 — the substitution happened at ingest, so nothing
    // here reverses it and a screenshot of this panel carries no real identifier
    const collapsed = group({
      ruleId: "TRACK-GAP",
      findingType: "track_continuity_gap",
      dataMode: "replayed",
      count: 1,
      sources: ["AC-48089ab4e5a9"],
      statements: [statement({ text: "reporting broke", sources: ["AC-48089ab4e5a9"] })],
    });
    render(
      <EmEvidencePanel account={account({ explained: [explained({ evidence: [collapsed] })] })} />,
    );

    expect(panel()).toHaveTextContent("AC-48089ab4e5a9");
  });

  it("renders no percentage anywhere", () => {
    // spec: op-010, FR-715, AC-11 — a deviation in dB is a measurement and
    // carries its unit; what is forbidden is a score dressed as a number
    render(<EmEvidencePanel account={account({ explained: [explained()] })} />);

    expect(panel().textContent ?? "").not.toContain("%");
  });

  it("groups nothing itself, so two groups of one pair both render", () => {
    // spec: op-010, api-015 — the grouping is the endpoint's. A panel that
    // merged them would be a second implementation of it, free to drift.
    render(
      <EmEvidencePanel
        account={account({
          explained: [
            explained({
              evidence: [
                group({ statements: [statement({ text: "first sentence" })] }),
                group({ statements: [statement({ text: "second sentence" })] }),
              ],
            }),
          ],
        })}
      />,
    );

    expect(within(panel()).getAllByRole("listitem")).toHaveLength(2);
  });

  it("writes a sentence for every finding type the builder can emit", () => {
    // spec: op-010, op-003 — the exhaustiveness guarantee, behaviourally: a
    // type with no wording reaches an analyst as the raw token
    render(
      <EmEvidencePanel
        account={account({
          explained: [
            explained({
              evidence: EVERY_TYPE.map((findingType) => group({ findingType })),
            }),
          ],
        })}
      />,
    );

    for (const findingType of EVERY_TYPE) {
      expect(panel()).not.toHaveTextContent(findingType);
    }
  });
});

describe("the three kinds of not-knowing", () => {
  const absence = (over: Partial<KnownUncertainty>): KnownUncertainty => ({
    kind: "not_applicable",
    statement: "the aircraft side was not consulted",
    subject: "track",
    ...over,
  });

  it("gets three different sentences", () => {
    // spec: op-010, evb-001 — never consulted, consulted and could not tell,
    // and looked at and found nothing are three different claims
    render(
      <EmEvidencePanel
        account={account({
          explained: [
            explained({
              uncertainties: [
                absence({ kind: "not_applicable", statement: "a" }),
                absence({ kind: "not_measurable", statement: "b" }),
                absence({ kind: "measured_negative", statement: "c" }),
              ],
            }),
          ],
        })}
      />,
    );

    const headings = within(panel())
      .getAllByRole("term")
      .map((node) => node.textContent);
    expect(new Set(headings).size).toBe(3);
  });

  it("renders no kind as its raw token", () => {
    // spec: op-010, ai-002 — the kind crosses the wire by enum member name so
    // nothing launders it; the screen is where it becomes a sentence
    render(
      <EmEvidencePanel
        account={account({
          explained: [
            explained({
              uncertainties: [
                absence({ kind: "not_applicable" }),
                absence({ kind: "not_measurable" }),
                absence({ kind: "measured_negative" }),
              ],
            }),
          ],
        })}
      />,
    );

    for (const kind of ["not_applicable", "not_measurable", "measured_negative"]) {
      expect(panel()).not.toHaveTextContent(kind);
    }
  });

  it("renders each statement untruncated", () => {
    // spec: op-010, evb-001 — the kind says what sort of not-knowing it is and
    // the statement is the only part a person can weigh
    const long =
      "the local discontinuity rate could not be measured: the reference period " +
      "outside the window held no discontinuities at all, so the ratio consists " +
      "of nothing but the smoothing constant";
    render(
      <EmEvidencePanel
        account={account({ explained: [explained({ uncertainties: [absence({ statement: long })] })] })}
      />,
    );

    expect(panel()).toHaveTextContent(long);
  });
});

describe("a competing conclusion", () => {
  it("is shown as rejected and never among the support", () => {
    // spec: op-010, ai-008, anom-013 — carried among the support, two rules'
    // disagreement reads as two rules' agreement
    render(
      <EmEvidencePanel
        account={account({
          explained: [
            explained({
              superseded: [
                {
                  ruleId: "SENSOR-FAULT",
                  anomalyType: "possible_sensor_fault",
                  claimedBy: "FUSION-SPATIAL",
                  reason: "an earlier rule claimed this zone",
                },
              ],
            }),
          ],
        })}
      />,
    );

    // `role="group"` is deliberately not used: Biome rejects it in favour of
    // `<fieldset>`, which means form controls, and a suppression does not work
    // in JSX attribute position. A named `<section>` is a region and serves.
    const rejected = within(panel()).getByRole("region", { name: /ruled out/i });
    expect(rejected).toHaveTextContent(/Possible receiver fault/);
    const support = within(panel()).getByRole("list", { name: /supporting evidence/i });
    expect(support).not.toHaveTextContent(/Possible receiver fault/);
  });
});

describe("what the panel says when there is nothing to show", () => {
  it("says a conclusion has no stored evidence rather than rendering an empty block", () => {
    // spec: op-010, op-003 — the state of 140 of 240 claim-bearing hours. A
    // dash meaning "nothing to report" could not be told from a dash meaning
    // "nobody looked", and this is the same correction one layer along.
    render(
      <EmEvidencePanel
        account={account({
          unexplained: [
            {
              ruleId: "FUSION-SPATIAL",
              findingType: "possible_interference_zone",
              subject: "RF-04",
              observedFrom: "2022-06-27T12:31:22+00:00",
              observedTo: "2022-06-27T12:36:52+00:00",
              reason: "not-bundled",
            },
          ],
        })}
      />,
    );

    expect(panel()).toHaveTextContent(/Possible interference across several receivers/);
    expect(panel()).toHaveTextContent(/no (stored )?evidence/i);
  });

  it("names stored evidence that no current conclusion claims", () => {
    // spec: op-010, api-015 — four of 103 bundles on the real store. Dropped
    // silently, the hour would read as fully explained.
    render(
      <EmEvidencePanel
        account={account({
          unclaimed: [
            {
              bundleId: 220,
              ruleId: "SENSOR-FAULT",
              findingType: "possible_sensor_fault",
              subject: "RF-05",
              observedFrom: "2022-06-27T12:45:16+00:00",
              observedTo: "2022-06-27T12:50:36+00:00",
              reason: "no-current-claim",
            },
          ],
        })}
      />,
    );

    expect(panel()).toHaveTextContent(/does not match any conclusion|no current conclusion/i);
    expect(panel()).toHaveTextContent("RF-05");
  });

  it("says a quiet hour had nothing to explain", () => {
    // spec: op-010, anom-008 — a correct non-detection, stated
    render(<EmEvidencePanel account={account()} />);

    expect(panel()).toHaveTextContent(/nothing (was )?reported/i);
  });

  it("says an unexamined hour has not been examined", () => {
    // spec: op-010, api-012, api-015 — null means no pass examined this hour,
    // and it must not read as a quiet hour
    render(<EmEvidencePanel account={null} />);

    expect(panel()).toHaveTextContent(/not been examined/i);
  });

  it("says so when the evidence could not be loaded, and does not call it unexamined", () => {
    // spec: op-010 — the amendment. No answer is the client having none; null
    // is the server saying no pass examined this hour. Reported as the second,
    // a transport failure becomes a fact about the store.
    render(<EmEvidencePanel account={undefined} />);

    expect(panel()).toHaveTextContent(/could not (be )?load/i);
    expect(panel()).not.toHaveTextContent(/not been examined/i);
  });

  it("keeps the section present in every one of those states", () => {
    // spec: op-010 — never silence. A panel that disappears is a panel an
    // analyst cannot tell from one that has nothing to say.
    for (const state of [undefined, null, account()]) {
      const { unmount } = render(<EmEvidencePanel account={state} />);
      expect(screen.getByRole("region", { name: "Evidence" })).toBeInTheDocument();
      unmount();
    }
  });
});
