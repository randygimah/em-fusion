import { useCallback, useState } from "react";

/**
 * Whether the analyst has collapsed the navigation rail. spec: nav-003.
 *
 * This is a preference, not a location, and the distinction is why it does not
 * live in the URL alongside the route (nav-001). The hash answers *where you
 * are*, so a screen can be linked to and named in a fault report; rail width
 * answers *how one person likes their chrome*. In the hash it would give a
 * single screen two addresses and make every shared link impose one analyst's
 * layout on the next reader.
 *
 * So: `localStorage`, which is per-viewer and survives a reload, which is the
 * whole point of a preference.
 */
export const RAIL_COLLAPSED_KEY = "em-fusion:nav-collapsed";

const COLLAPSED = "collapsed";
const EXPANDED = "expanded";

/**
 * Read the stored preference, resolving anything unexpected to expanded.
 *
 * Guarded because this genuinely throws: a private window with site data
 * blocked raises on access rather than returning null. And the value is
 * compared against one known string rather than parsed, so a leftover from an
 * older build — or anything else that has been written to this key — resolves
 * to expanded instead of to nothing. The rail degrades toward showing more
 * rather than less.
 */
const read = (): boolean => {
  try {
    return window.localStorage.getItem(RAIL_COLLAPSED_KEY) === COLLAPSED;
  } catch {
    return false;
  }
};

const write = (collapsed: boolean): void => {
  try {
    window.localStorage.setItem(RAIL_COLLAPSED_KEY, collapsed ? COLLAPSED : EXPANDED);
  } catch {
    // A preference that cannot be saved is a preference that lasts one visit.
    // That is a worse experience and not a failure, so nothing is surfaced.
  }
};

export const useRailCollapsed = (): [boolean, () => void] => {
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
