import type { ViewSelection } from "../types/operationalPicture";

/**
 * The view filter's words, in one module. spec: op-007.
 *
 * The server filters (api-007), so whatever a view withholds never arrives and
 * the screen cannot count it. Everything a view can empty therefore says what
 * it withheld, from `view.suppressed`, and an unexamined hour says it was not
 * examined rather than that it is clean. op-004's panel inherits these
 * sentences, which is why they live here rather than in the screen.
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

/**
 * How many receivers the view withheld, or null when it withheld none. On an
 * unexamined hour the withheld rows are neither nominal nor anomalous, so they
 * are named only as hidden.
 */
export const receiversHiddenSentence = (view: ViewSelection, hidden: number, examined: boolean): string | null => {
  if (hidden === 0) return null;
  if (!examined) return `${hidden} ${hidden === 1 ? "receiver" : "receivers"} hidden by this view — choose All to see them.`;
  return `${hidden} ${view === "nominal" ? "out of nominal" : "nominal"} hidden by this view`;
};

/** How many conclusions the view withheld from the timeline. */
export const eventsHiddenSentence = (hidden: number): string =>
  `${hidden} ${hidden === 1 ? "conclusion" : "conclusions"} hidden by this view — choose Anomalous only or All to see ${hidden === 1 ? "it" : "them"}.`;
