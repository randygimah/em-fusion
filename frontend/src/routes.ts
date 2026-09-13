// Stub. spec: nav-001 — the three screens are declared once, here, so that
// "exactly three entries" is assertable at the source as well as in the DOM.
// Empty until the implementation; the tests are written against it.
export interface ScreenRoute {
  id: string;
  label: string;
  hash: string;
}

export const SCREENS: ScreenRoute[] = [];
