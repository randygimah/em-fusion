import type { ViewSelection } from "../types/operationalPicture";

/**
 * The view filter's words, in one module. spec: op-007.
 *
 * The server filters (api-007), so whatever a view withholds never arrives and
 * the screen cannot count it. Everything a view can empty therefore says what
 * it withheld, from `view.suppressed`, and an unexamined hour says it was not
 * examined rather than that it is clean. op-004's exception panel uses them,
 * which is why they live here rather than in the screen.
 */

/** Every visit starts here (US-A1): the analyst sees the exceptions first. */
export const DEFAULT_VIEW: ViewSelection = "anomalous";

/** In the order the control offers them. */
export const VIEW_OPTIONS: readonly { value: ViewSelection; label: string }[] = [
  { value: "anomalous", label: "Anomalous only" },
  { value: "nominal", label: "Nominal only" },
  { value: "all", label: "All" },
];

export const viewLabel = (view: ViewSelection): string => VIEW_OPTIONS.find((option) => option.value === view)?.label ?? view;

/**
 * What the screen is showing, named from the view the payload was SERVED under.
 * Between a click and its answer the rows belong to the previous view, so the
 * control's own state is never the label.
 */
export const showingSentence = (served: ViewSelection, selected: ViewSelection): string =>
  served === selected
    ? `Showing ${viewLabel(served).toLowerCase()}`
    : `Switching to ${viewLabel(selected).toLowerCase()} — still showing ${viewLabel(served).toLowerCase()}`;

export const NOT_EXAMINED = "This hour has not been examined, so nothing on it is anomalous or nominal yet.";

/** An examined hour whose receivers the view emptied. */
export const noReceiverSentence = (view: ViewSelection): string =>
  view === "anomalous" ? "No receiver is out of nominal." : view === "nominal" ? "No receiver is nominal." : "No receivers in the layout.";

/** The exception panel's three tabs (op-004), in the order they are offered. */
export type ExceptionTab = "rf" | "tracks" | "events";

const TAB_TITLE: Record<ExceptionTab, string> = { rf: "RF", tracks: "Tracks", events: "Events" };

/** What a row out of nominal is called on each tab: a track's finding is that its reporting broke. */
const ANOMALOUS_WORD: Record<"rf" | "tracks", string> = { rf: "anomalous", tracks: "interrupted" };

/**
 * A tab's label (op-004 (1)). The number is the rows the tab shows; the word
 * names what those rows are, so it follows the view. On an unexamined hour no
 * row has a state, and under All the rows are mixed, so neither carries a word.
 */
export const tabLabel = (tab: ExceptionTab, shown: number, view: ViewSelection, examined: boolean): string => {
  if (tab === "events" || !examined || view === "all") return `${TAB_TITLE[tab]} (${shown})`;
  return `${TAB_TITLE[tab]} (${shown} ${view === "anomalous" ? ANOMALOUS_WORD[tab] : "nominal"})`;
};

const plural = (n: number, one: string, many: string): string => (n === 1 ? one : many);

/**
 * What the view withheld from the open tab, named by what those rows are
 * (op-004 (2)). From `view.suppressed`, never from the rows: they never arrived.
 * On an unexamined hour the withheld rows are neither nominal nor anomalous.
 */
export const footerSentence = (tab: ExceptionTab, hidden: number, view: ViewSelection, examined: boolean): string => {
  if (hidden === 0) return "This view hides nothing.";
  if (tab === "events") return `+${hidden} ${plural(hidden, "conclusion", "conclusions")} hidden by this view`;
  if (!examined) {
    const noun = tab === "rf" ? plural(hidden, "receiver", "receivers") : "aircraft";
    return `+${hidden} ${noun} hidden by this view — choose All to see them.`;
  }
  return `+${hidden} ${view === "nominal" ? ANOMALOUS_WORD[tab] : "nominal"} hidden by this view`;
};

/** An examined hour whose aircraft the view emptied (op-004 (3)). */
export const noTrackSentence = (view: ViewSelection): string =>
  view === "anomalous"
    ? "No aircraft's reporting broke."
    : view === "nominal"
      ? "No aircraft is nominal."
      : "No aircraft in the final five minutes of this hour.";

/** Under Nominal only the Events tab is always empty, and says why rather than that nothing happened. */
export const EVENTS_ARE_ANOMALOUS = "Conclusions are anomalous by definition, so this view shows none.";

export const QUIET_HOUR = "No events in this hour. Nothing the detectors reported reached the analyst.";

/** The disabled View all link's reason (decided 2026-10-06; op-005). */
export const VIEW_ALL_REASON = "The drill-down tables are not built yet.";
