import { useCallback, useState } from "react";

/**
 * Whether the analyst has collapsed the evidence panel. spec: op-010.
 *
 * The same kind of thing as the rail's width (nav-003): a preference about the
 * analyst's chrome, not a location, so it lives in `localStorage` and never in
 * the hash nav-001 owns. Every read and write is guarded, because storage throws
 * in a private window with site data blocked.
 *
 * **Anything unexpected resolves to expanded**, which is the same safe default
 * as the rail and for a different reason. The rail shows more by default so
 * nothing is hidden from a first-time visitor; this panel shows more because it
 * is the project's own subject, and one that opened collapsed would be one
 * nobody opens.
 */
export const EVIDENCE_COLLAPSED_KEY = "em-fusion:evidence-collapsed";

const COLLAPSED = "collapsed";
const EXPANDED = "expanded";

const read = (): boolean => {
  try {
    return window.localStorage.getItem(EVIDENCE_COLLAPSED_KEY) === COLLAPSED;
  } catch {
    return false;
  }
};

const write = (collapsed: boolean): void => {
  try {
    window.localStorage.setItem(EVIDENCE_COLLAPSED_KEY, collapsed ? COLLAPSED : EXPANDED);
  } catch {
    // A preference that cannot be saved lasts one visit. Not a failure to surface.
  }
};

export const useEvidenceCollapsed = (): [boolean, () => void] => {
  const [collapsed, setCollapsed] = useState<boolean>(read);

  const toggle = useCallback(() => {
    setCollapsed((previous) => {
      const next = !previous;
      write(next);
      return next;
    });
  }, []);

  return [collapsed, toggle];
};
