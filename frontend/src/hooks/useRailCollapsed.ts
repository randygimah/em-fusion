/**
 * STUB, written at the test stage. spec: nav-003.
 *
 * Deliberately not the implementation: it consults no storage, writes none,
 * and refuses to toggle. Its only job is to let `navCollapse.test.tsx` load,
 * so every test in that file fails on its own assertion rather than the whole
 * file failing to collect — the distinction between "this fails because
 * nothing is built" and "this cannot fail", which `scn-005` learned the
 * expensive way by skipping this step.
 *
 * Replaced wholesale at the code stage.
 */
export const RAIL_COLLAPSED_KEY = "em-fusion:nav-collapsed";

export const useRailCollapsed = (): [boolean, () => void] => [
  false,
  () => {
    throw new Error("useRailCollapsed: not implemented (nav-003)");
  },
];
