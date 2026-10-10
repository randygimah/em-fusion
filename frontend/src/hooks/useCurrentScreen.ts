import { useEffect, useState } from "react";
import { type Route, routeFromHash } from "../routes";

/**
 * The screen the address bar is asking for. spec: nav-001.
 *
 * The route lives in the URL rather than in component state, so a reload
 * returns the analyst to the screen they chose and a screen can be linked to
 * or named in a bug report. It lives in the *hash* rather than the path
 * because the frontend is served as a static bundle: a path-based route would
 * need the server to rewrite unknown paths onto index.html, which is a
 * deployment concern taken on for nothing at three destinations.
 *
 * A router library would do this and more. The more is nested routes, route
 * parameters, loaders and guards. The one parameter that exists, an
 * explanation's id on the Hypotheses screen (nav-004), is parsed in routes.ts.
 */
export const useCurrentScreen = (): Route => {
  const [current, setCurrent] = useState<Route>(() => routeFromHash(window.location.hash));

  useEffect(() => {
    const update = () => setCurrent(routeFromHash(window.location.hash));

    // Read once on mount as well as on change: the hash may already name a
    // screen when the app starts, which is what makes a link into the
    // application work.
    update();
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);

  return current;
};
