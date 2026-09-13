import type { ScreenRoute } from "../../routes";

interface Props {
  screens: ScreenRoute[];
  currentId: string;
}

/**
 * The left navigation shell. spec: nav-001, FR-701.
 *
 * Dumb: it renders the list it is given and marks one entry. It knows nothing
 * about which screens exist, so the closed set stays in one place.
 *
 * The entries are anchors rather than buttons because they are navigation:
 * they have addresses, they can be opened in a new tab, and `aria-current`
 * belongs on a link. A button styled as a link would take all three away.
 */
export const EmNavRail = ({ screens, currentId }: Props) => (
  <nav
    aria-label="Screens"
    className="w-[280px] shrink-0 border-r border-[#424754] bg-[#10131a] p-3"
  >
    <p className="px-2 py-3 font-mono text-[10px] font-bold uppercase tracking-[0.05em] text-[#8c909f]">EM Fusion</p>
    <ul className="space-y-1">
      {screens.map((screen) => {
        const current = screen.id === currentId;
        return (
          <li key={screen.id}>
            <a
              aria-current={current ? "page" : undefined}
              className={`block rounded border-l-2 px-3 py-2 text-[14px] no-underline ${
                current
                  ? "border-[#4d8eff] bg-[#00285d] font-semibold text-[#d8e2ff]"
                  : "border-transparent text-[#c2c6d6] hover:bg-[#191b23] hover:text-[#e1e2ec]"
              }`}
              href={screen.hash}
            >
              {screen.label}
            </a>
          </li>
        );
      })}
    </ul>
  </nav>
);
