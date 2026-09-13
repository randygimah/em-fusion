import { cn } from "../../lib/utils";
import type { ScreenRoute } from "../../routes";

interface Props {
  screens: ScreenRoute[];
  currentId: string;
  collapsed: boolean;
  onToggle: () => void;
}

// Chevron pointing the way the rail will move.
const CHEVRON_LEFT = "M14 6l-6 6 6 6";
const CHEVRON_RIGHT = "M10 6l6 6-6 6";

interface GlyphProps {
  path: string;
  className?: string;
}

const Glyph = ({ path, className }: GlyphProps) => (
  <svg
    aria-hidden="true"
    className={cn("shrink-0", className)}
    fill="none"
    stroke="currentColor"
    strokeLinecap="round"
    strokeLinejoin="round"
    strokeWidth={1.6}
    viewBox="0 0 24 24"
  >
    <path d={path} />
  </svg>
);

/**
 * The left navigation shell. spec: nav-001, nav-003, FR-701.
 *
 * Dumb: it renders the list it is given and marks one entry. It knows nothing
 * about which screens exist, so the closed set stays in one place.
 *
 * The entries are anchors rather than buttons because they are navigation:
 * they have addresses, they can be opened in a new tab, and `aria-current`
 * belongs on a link. A button styled as a link would take all three away.
 *
 * The collapse control is the exact inverse and is a button for the same
 * reason read backwards: it has no address and goes nowhere, so it carries
 * `aria-expanded` instead. Collapsing hides the labels and never the entries —
 * all three stay in the DOM with their accessible names, so the rail reads
 * identically to assistive technology at either width.
 */
export const EmNavRail = ({ screens, currentId, collapsed, onToggle }: Props) => (
  <nav
    aria-label="Screens"
    className={cn(
      // No width transition. One was written here and removed: animating
      // between 280px and a token-derived width left the rail stuck at its old
      // used width when toggled, while mounting already-collapsed rendered at
      // 56px correctly. The rail is the thing; the animation is not (nav-003
      // scopes it out), so it goes rather than being debugged.
      "flex shrink-0 flex-col border-r border-[#424754] bg-[#10131a] p-3",
      collapsed ? "w-14" : "w-[280px]",
    )}
  >
    <div className={cn("flex items-center py-3", collapsed ? "justify-center" : "justify-between px-2")}>
      {!collapsed && (
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.05em] text-[#8c909f]">EM Fusion</p>
      )}
      <button
        aria-expanded={!collapsed}
        className="rounded p-1 text-[#8c909f] hover:bg-[#191b23] hover:text-[#e1e2ec]"
        onClick={onToggle}
        type="button"
      >
        <Glyph
          className="h-4 w-4"
          path={collapsed ? CHEVRON_RIGHT : CHEVRON_LEFT}
        />
        <span className="sr-only">{collapsed ? "Expand navigation" : "Collapse navigation"}</span>
      </button>
    </div>

    <ul className="space-y-1">
      {screens.map((screen) => {
        const current = screen.id === currentId;
        return (
          <li key={screen.id}>
            <a
              aria-current={current ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded border-l-2 py-2 text-[14px] no-underline",
                collapsed ? "justify-center px-0" : "px-3",
                current
                  ? "border-[#4d8eff] bg-[#00285d] font-semibold text-[#d8e2ff]"
                  : "border-transparent text-[#c2c6d6] hover:bg-[#191b23] hover:text-[#e1e2ec]",
              )}
              href={screen.hash}
              title={collapsed ? screen.label : undefined}
            >
              <Glyph
                className="h-5 w-5"
                path={screen.iconPath}
              />
              {/* Visually hidden rather than removed: the entry count and every
                  accessible name are identical in both states (FR-701). */}
              <span className={collapsed ? "sr-only" : undefined}>{screen.label}</span>
            </a>
          </li>
        );
      })}
    </ul>
  </nav>
);
