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
}

export const SCREENS: ScreenRoute[] = [
  { id: "operational-picture", label: "Operational Picture", hash: "#/operational-picture" },
  { id: "hypotheses", label: "Hypotheses", hash: "#/hypotheses" },
  { id: "scenario-control", label: "Scenario Control", hash: "#/scenario-control" },
];

// The route the analyst lands on, and the one an unrecognised address resolves
// to. A hash naming no screen renders the Operational Picture rather than an
// empty workspace: a blank page under a working nav rail reads as a broken
// application rather than as a bad link.
export const DEFAULT_SCREEN: ScreenRoute = SCREENS[0];

export const screenFromHash = (hash: string): ScreenRoute =>
  SCREENS.find((screen) => screen.hash === hash) ?? DEFAULT_SCREEN;
