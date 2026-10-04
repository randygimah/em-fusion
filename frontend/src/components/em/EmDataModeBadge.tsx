import { cn } from "../../lib/utils";

interface Props {
  /** Layout only. See the note below on why this is not an input. */
  collapsed?: boolean;
}

/**
 * The standing claim that this system is not live. spec: op-001, NFR-303, FR-703.
 *
 * **It reads nothing.** No payload, no poll, no fetched value, no prop that
 * carries data — `collapsed` is the rail's width and not a fact about the
 * system. That is what makes it unconditional in the strongest sense available:
 * there is nothing here that can be absent, so a failed request, an empty
 * store, a screen with no data and a backend that is down all leave the badge
 * exactly where it was. A badge derived from `scenario.dataMode` would be a
 * badge a backend failure can remove, which is the named failure case.
 *
 * It lives in the rail rather than on a screen because the requirement is a
 * badge on *every* screen, and the rail is the only component on all three.
 * Putting it on the Operational Picture means two screens without one — which
 * is the state the project was actually in until this item — and hoisting the
 * picture's five-second poll to reach every screen is what `nav-001`
 * deliberately avoided.
 *
 * **The wording is the requirement's own.** FR-703 says the badge states the
 * environment is synthetic *or* replayed and NFR-303 says synthetic *and*
 * replayed; the corpus's aircraft tracks are real recorded transponder data,
 * pseudonymised but recorded, so `SYNTHETIC ENVIRONMENT DATA` — this item's
 * original wording — understates their provenance in the other direction.
 *
 * Collapsed it reads **NOT LIVE**: the claim itself rather than an abbreviation
 * of the words, because an abbreviation is cryptic and the claim is the thing
 * that must not be lost. The full wording stays as the accessible name at
 * either width, so the badge reads identically to assistive technology — the
 * same rule `nav-003` applies to the entries.
 */
export const STANDING_CLAIM = "SYNTHETIC & REPLAYED DATA";
const COLLAPSED_CLAIM = "NOT LIVE";

export const EmDataModeBadge = ({ collapsed = false }: Props) => (
  <div
    aria-label={STANDING_CLAIM}
    className={cn(
      "flex items-center border border-[#4d8eff]/40 bg-[#00285d]/60 py-1",
      // The collapsed rail is 56px wide with 12px of padding each side, which
      // leaves 32px. Found by looking at the running screen: with the dot and
      // the expanded padding, NOT LIVE wrapped and the E overflowed the rail's
      // own border. No test could have caught it — the text was in the DOM and
      // the accessible name was correct, which is the third kind of blind spot
      // this project has recorded. So the dot goes, the padding tightens, and
      // the two words centre on two lines.
      collapsed ? "justify-center px-0.5" : "gap-2 px-2",
    )}
    role="status"
    title={STANDING_CLAIM}
  >
    {!collapsed && (
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#4cd7f6]"
      />
    )}
    <span
      className={cn(
        "font-mono text-[9px] font-bold uppercase leading-tight tracking-[0.05em] text-[#d8e2ff]",
        collapsed && "text-center",
      )}
    >
      {collapsed ? COLLAPSED_CLAIM : STANDING_CLAIM}
    </span>
  </div>
);
