import type { Connectivity, Service, SystemHealth } from "../../hooks/useSystemHealth";
import { cn } from "../../lib/utils";

interface Props extends SystemHealth {
  collapsed?: boolean;
}

// What each state says, and the colour that goes with it. Words only: the
// item's named failure case is a percentage, and the design reference itself
// renders "99.9% UPTIME" in this panel, so the failure case is not
// hypothetical (FR-715, AC-11).
const CONNECTIVITY: Record<Connectivity, { label: string; tone: string }> = {
  unknown: { label: "Checking", tone: "bg-[#8c909f]" },
  up: { label: "Connected", tone: "bg-[#4cd7f6]" },
  down: { label: "No connection", tone: "bg-[#ff6b6b]" },
};

// "Healthy" is earned here in a way it would not have been on the picture
// payload: something has actually checked. `ops-005` compares the database's
// migration revision against the one the code expects on every probe, so this
// row reports a check rather than an assumption.
const SERVICE: Record<Service, { label: string; tone: string }> = {
  unknown: { label: "Checking", tone: "bg-[#8c909f]" },
  healthy: { label: "Healthy", tone: "bg-[#4cd7f6]" },
  // Distinct from the row below, and kept distinct on purpose: a database at
  // the wrong revision is a misconfiguration somebody can fix with one command.
  refusing: { label: "Schema behind code", tone: "bg-[#df7412]" },
  // An outage is not a misconfiguration. The backend answered and could not
  // reach its database, which says nothing about whether the schema is current.
  "cannot-tell": { label: "Database unreachable", tone: "bg-[#df7412]" },
};

interface RowProps {
  name: string;
  label: string;
  tone: string;
  collapsed: boolean;
}

// Collapsed, the row becomes its dot and the words move into the accessible
// name. `nav-003`'s rule is that collapsing hides labels and never entries, so
// neither row is dropped and both read identically to assistive technology at
// either width.
const Row = ({ name, label, tone, collapsed }: RowProps) => (
  <div
    aria-label={`${name}: ${label}`}
    className={cn("flex items-center font-mono text-[11px]", collapsed ? "justify-center" : "justify-between")}
    role="status"
  >
    {!collapsed && <span className="text-[#8c909f]">{name}</span>}
    <span className="flex items-center gap-1.5">
      {!collapsed && <span className="text-[#c2c6d6]">{label}</span>}
      <span aria-hidden="true" className={cn("h-1.5 w-1.5 shrink-0 rounded-full", tone)} />
    </span>
  </div>
);

/**
 * The system-status strip in the nav footer. spec: nav-002, FR-702.
 *
 * A strip and not a screen and not a fourth nav entry: `nav-001` fixes the rail
 * at exactly three entries, and health is chrome rather than a destination.
 *
 * **The container carries no role**, which was arrived at rather than assumed.
 * `role="group"` reads correctly and the linter rejects it in favour of
 * `<fieldset>`, which means *a group of form controls* and is wrong here; the
 * other native option, a labelled `<section>`, makes a small strip inside the
 * nav into a `region` landmark, and overusing landmarks is its own
 * accessibility problem. The role turned out to be unnecessary either way: each
 * row is a `status` carrying its own name and state, which is what a screen
 * reader user needs, and an invented container role on top of that adds nothing.
 */
export const EmSystemStatus = ({ connectivity, service, collapsed = false }: Props) => (
  <div className="flex flex-col gap-2 border border-[#424754] bg-[#191b23] p-2">
    {!collapsed && (
      <p className="font-mono text-[9px] font-bold uppercase tracking-[0.05em] text-[#8c909f]">
        System status
      </p>
    )}
    <Row collapsed={collapsed} name="Connectivity" {...CONNECTIVITY[connectivity]} />
    <Row collapsed={collapsed} name="Service" {...SERVICE[service]} />
  </div>
);
