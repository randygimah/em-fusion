// The three screens, declared once. spec: nav-001, FR-701.
//
// One list rather than one per consumer: the rail renders it, the workspace
// switches on it, and the test that says there are exactly three asserts
// against it. Two lists would be two places to add a fourth entry, and only
// one of them would be tested.
//
// Drill-down tables and system health are deliberately absent. They are views
// over the same data reached from panel footers (FR-709), and health is a
// strip in the shell rather than a destination.
export interface ScreenRoute {
  id: string;
  label: string;
  hash: string;
  // The entry's icon, as SVG path data rather than a component. spec: nav-003.
  //
  // It lives here, on the one declaration of the three screens, so that adding
  // a fourth cannot land somewhere that has no icon — the single-list rule
  // nav-001 settled. Path data rather than JSX keeps this file plain data, so
  // it stays a `.ts` the tests can import without a renderer.
  iconPath: string;
}

export const SCREENS: ScreenRoute[] = [
  {
    id: "operational-picture",
    label: "Operational Picture",
    hash: "#/operational-picture",
    // A target: rings and a centre, for the picture being watched.
    iconPath:
      "M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18Z M12 8.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Z M12 2v3 M12 19v3 M2 12h3 M19 12h3",
  },
  {
    id: "hypotheses",
    label: "Hypotheses",
    hash: "#/hypotheses",
    // A lamp: a proposed explanation, not a settled one.
    iconPath: "M12 3a6 6 0 0 0-3.5 10.9V16h7v-2.1A6 6 0 0 0 12 3Z M9.5 19h5 M10.5 21.5h3",
  },
  {
    id: "scenario-control",
    label: "Scenario Control",
    hash: "#/scenario-control",
    // Sliders: the dials a run is configured from.
    iconPath:
      "M4 7h16 M4 12h16 M4 17h16 M9 5a2 2 0 1 1 0 4 2 2 0 1 1 0-4Z M15 10a2 2 0 1 1 0 4 2 2 0 1 1 0-4Z M8 15a2 2 0 1 1 0 4 2 2 0 1 1 0-4Z",
  },
];

// The route the analyst lands on, and the one an unrecognised address resolves
// to. A hash naming no screen renders the Operational Picture rather than an
// empty workspace: a blank page under a working nav rail reads as a broken
// application rather than as a bad link.
export const DEFAULT_SCREEN: ScreenRoute = SCREENS[0];

// Where the address bar points: a screen, and on the Hypotheses screen
// optionally one explanation (nav-004). The id is a parameter of an entry, not
// a fourth one.
export interface Route {
  screen: ScreenRoute;
  hypothesisId: number | null;
}

const HYPOTHESES_HASH = "#/hypotheses";
// A positive integer with no leading zero: anything else is no explanation,
// never a guessed or truncated one.
const HYPOTHESIS_ADDRESS = /^#\/hypotheses\/([1-9][0-9]*)$/;

// One explanation's address. Built here, beside the parser, so a card's link
// and the parser cannot disagree on the shape (nav-004).
export const hypothesisHash = (id: number): string => `${HYPOTHESES_HASH}/${id}`;

export const routeFromHash = (hash: string): Route => {
  const exact = SCREENS.find((screen) => screen.hash === hash);
  if (exact) return { screen: exact, hypothesisId: null };
  if (hash.startsWith(`${HYPOTHESES_HASH}/`)) {
    const id = HYPOTHESIS_ADDRESS.exec(hash)?.[1];
    const hypotheses = SCREENS.find((screen) => screen.hash === HYPOTHESES_HASH) as ScreenRoute;
    return { screen: hypotheses, hypothesisId: id === undefined ? null : Number(id) };
  }
  return { screen: DEFAULT_SCREEN, hypothesisId: null };
};

export const screenFromHash = (hash: string): ScreenRoute => routeFromHash(hash).screen;
