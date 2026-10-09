import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { findingLabel } from "../../lib/detectionVocabulary";
import { cn } from "../../lib/utils";
import {
  drillDownFailed,
  drillDownHeading,
  drillDownLoading,
  type ExceptionTab,
  NOT_EXAMINED,
  noMatch,
  noReceiverSentence,
  noTrackSentence,
  QUIET_HOUR,
  shownCount,
  UNFILTERED,
} from "../../lib/viewVocabulary";
import type { AircraftTrack, OperationalPicture, RFSensor, TimelineEvent } from "../../types/operationalPicture";
import { altitude, cell, headCell, position, simulatedInstant } from "./rowFormat";

/**
 * The whole of one tab's collection for one hour. spec: op-005.
 *
 * The exception panel shows what the view admits; this shows everything, with
 * room, a sort and a find (FR-709). It is reached only from the panel's footer
 * and is an overlay, not a screen: no route, no navigation entry (FR-701).
 *
 * **"All" means all, or nothing.** The table is fetched once, unfiltered, for
 * the hour the panel showed when it was opened, through the loader the seam
 * hands down — the endpoint the panel already reads, so no new data source. An
 * answer for another hour or under another view is refused as a failure rather
 * than shown, and a failure never falls back to the panel's rows, which are
 * filtered and would sit under a heading saying *all*.
 *
 * **Not polled.** The hour does not change under it; the picture underneath
 * goes on polling and the table stays on the hour it was opened for, which its
 * heading names.
 *
 * **Columns are the panel's**, worded by the same helpers: a field nothing
 * produces is no more real at full width.
 */

type Load = (runId: number) => Promise<OperationalPicture>;

type Loaded = { status: "loading" } | { status: "failed" } | { status: "loaded"; picture: OperationalPicture };

type Direction = 1 | -1;

interface Column<Row> {
  title: string;
  render: (row: Row) => ReactNode;
  className: string;
  compare: (a: Row, b: Row) => number;
  // Rows that sort last whichever way the column runs: an altitude not
  // reported is not lower than every altitude, and not higher either.
  last?: (row: Row) => boolean;
}

interface TableSpec<Row> {
  columns: readonly Column<Row>[];
  // The column the table opens sorted on, ascending.
  initial: number;
  key: (row: Row) => string;
  // Ties go to the identifier, so equal rows never swap between renders.
  identity: (a: Row, b: Row) => number;
  // What a find matches: what the row is called, never a field it does not show.
  findable: (row: Row) => readonly string[];
}

const byText = (a: string, b: string): number => a.localeCompare(b);

// Out of nominal first, nominal next, unexamined last: the default order puts
// what the panel would have shown at the top.
const receiverRank = (health: string): number => (health === "nominal" ? 1 : health === "unknown" ? 2 : 0);
const TRACK_RANK: Record<AircraftTrack["state"], number> = { interrupted: 0, nominal: 1, unknown: 2 };

const RECEIVERS: TableSpec<RFSensor> = {
  columns: [
    { title: "Receiver", render: (s) => s.id, className: "font-mono", compare: (a, b) => byText(a.id, b.id) },
    { title: "Station", render: (s) => s.stationName, className: "text-[#4cd7f6]", compare: (a, b) => byText(a.stationName, b.stationName) },
    { title: "Band", render: (s) => s.signalId, className: "font-mono", compare: (a, b) => byText(a.signalId, b.signalId) },
    {
      title: "State",
      render: (s) => s.health,
      className: "font-mono text-[#ffb786]",
      compare: (a, b) => receiverRank(a.health) - receiverRank(b.health),
    },
  ],
  initial: 3,
  key: (s) => s.id,
  identity: (a, b) => byText(a.id, b.id),
  findable: (s) => [s.id, s.stationName],
};

const TRACKS: TableSpec<AircraftTrack> = {
  columns: [
    { title: "Aircraft", render: (t) => t.name, className: "font-mono", compare: (a, b) => byText(a.name, b.name) },
    {
      title: "Altitude",
      render: (t) => altitude(t.altitudeFt),
      className: "font-mono",
      compare: (a, b) => (a.altitudeFt ?? 0) - (b.altitudeFt ?? 0),
      last: (t) => t.altitudeFt === null,
    },
    { title: "Position", render: position, className: "font-mono", compare: (a, b) => a.lat - b.lat || a.lon - b.lon },
    {
      title: "State",
      render: (t) => t.state,
      className: "font-mono text-[#ffb786]",
      compare: (a, b) => TRACK_RANK[a.state] - TRACK_RANK[b.state],
    },
  ],
  initial: 3,
  key: (t) => t.id,
  identity: (a, b) => byText(a.name, b.name),
  findable: (t) => [t.name],
};

const EVENTS: TableSpec<TimelineEvent> = {
  columns: [
    {
      title: "Time",
      render: (e) => simulatedInstant(e.time),
      className: "font-mono text-[#8c909f]",
      compare: (a, b) => byText(a.time, b.time),
    },
    {
      title: "Conclusion",
      render: (e) => findingLabel(e.event),
      className: "text-[#e1e2ec]",
      compare: (a, b) => byText(findingLabel(a.event), findingLabel(b.event)),
    },
    { title: "Source", render: (e) => e.source, className: "font-mono text-[#4cd7f6]", compare: (a, b) => byText(a.source, b.source) },
  ],
  initial: 0,
  key: (e) => e.id,
  identity: (a, b) => byText(a.id, b.id),
  findable: (e) => [e.source, findingLabel(e.event)],
};

const sorted = <Row,>(rows: readonly Row[], spec: TableSpec<Row>, column: number, direction: Direction): Row[] => {
  const { compare, last } = spec.columns[column];
  return [...rows].sort((a, b) => {
    const lastA = last?.(a) ?? false;
    const lastB = last?.(b) ?? false;
    if (lastA !== lastB) return lastA ? 1 : -1;
    return direction * (compare(a, b) || spec.identity(a, b));
  });
};

const DrillTable = <Row,>({ rows, spec, empty }: { rows: readonly Row[]; spec: TableSpec<Row>; empty: string }) => {
  const [sort, setSort] = useState<{ column: number; direction: Direction }>({ column: spec.initial, direction: 1 });
  const [find, setFind] = useState("");

  if (rows.length === 0) return <p className="p-4 text-sm text-[#c2c6d6]">{empty}</p>;

  const needle = find.trim().toLowerCase();
  const matching = needle === "" ? rows : rows.filter((row) => spec.findable(row).some((text) => text.toLowerCase().includes(needle)));
  const shown = sorted(matching, spec, sort.column, sort.direction);

  const sortBy = (column: number) =>
    setSort((current) => ({ column, direction: current.column === column ? (-current.direction as Direction) : 1 }));

  return (
    <>
      <div className="flex flex-wrap items-center gap-3 border-b border-[#424754] px-4 py-2">
        <input
          aria-label="Find"
          className="min-w-0 flex-1 border border-[#424754] bg-[#0b0e15] px-2 py-1 font-mono text-xs text-[#e1e2ec] placeholder:text-[#8c909f]"
          onChange={(event) => setFind(event.target.value)}
          placeholder="Find by name"
          type="search"
          value={find}
        />
        <span className="font-mono text-xs text-[#8c909f]">{shownCount(shown.length, rows.length)}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {shown.length === 0 ? (
          <p className="p-4 text-sm text-[#c2c6d6]">{noMatch(find.trim())}</p>
        ) : (
          <table className="w-full border-collapse text-left text-sm">
            <thead className="sticky top-0 bg-[#1d2027]">
              <tr className="border-b border-[#424754]">
                {spec.columns.map((column, index) => (
                  <th
                    aria-sort={sort.column === index ? (sort.direction === 1 ? "ascending" : "descending") : "none"}
                    className={headCell}
                    key={column.title}
                  >
                    {/* The arrow is drawn by CSS and the order announced by
                        aria-sort, so the header's name stays its title. */}
                    <button
                      className={cn(
                        "uppercase tracking-[0.05em] hover:text-[#e1e2ec]",
                        sort.column === index && "text-[#adc6ff] after:ml-1",
                        sort.column === index && (sort.direction === 1 ? "after:content-['▲']" : "after:content-['▼']"),
                      )}
                      onClick={() => sortBy(index)}
                      type="button"
                    >
                      {column.title}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr
                  className="border-b border-[#424754]/50"
                  key={spec.key(row)}
                >
                  {spec.columns.map((column) => (
                    <td
                      className={`${cell} ${column.className}`}
                      key={column.title}
                    >
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
};

// The answer is the hour asked for, unfiltered, or it is not the table.
const isTheTable = (picture: OperationalPicture, runId: number): boolean =>
  picture.scenario?.id === String(runId) && picture.view.selected === "all";

const total = (picture: OperationalPicture, tab: ExceptionTab): number =>
  tab === "rf" ? picture.rfSensors.length : tab === "tracks" ? picture.aircraftTracks.length : picture.timelineEvents.length;

export const EmDrillDown = ({ tab, runId, load, onClose }: { tab: ExceptionTab; runId: number; load: Load; onClose: () => void }) => {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const headingId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  // The seam hands down a fresh function on every render of the screen, and
  // the screen re-renders on every poll; keyed on it, the table would refetch
  // every five seconds. It is read through a ref and the fetch keyed on the
  // hour and the attempt only.
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` is the retry trigger.
  useEffect(() => {
    let cancelled = false;
    setLoaded({ status: "loading" });
    loadRef.current(runId).then(
      (picture) => {
        if (!cancelled) setLoaded(isTheTable(picture, runId) ? { status: "loaded", picture } : { status: "failed" });
      },
      () => {
        if (!cancelled) setLoaded({ status: "failed" });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [runId, attempt]);

  const body = () => {
    if (loaded.status === "loading") return <p className="p-4 text-sm text-[#c2c6d6]">{drillDownLoading(tab, runId)}</p>;
    if (loaded.status === "failed")
      return (
        <div className="flex flex-wrap items-center gap-3 p-4 text-sm">
          <p className="text-[#ffb4ab]">{drillDownFailed(runId)}</p>
          <button
            className="border border-[#424754] px-3 py-1 font-mono text-xs uppercase tracking-[0.05em] text-[#adc6ff] hover:bg-[#272a31]"
            onClick={() => setAttempt((n) => n + 1)}
            type="button"
          >
            Try again
          </button>
        </div>
      );
    const { picture } = loaded;
    const { examined } = picture.view;
    return (
      <>
        {/* Rows are served on an unexamined hour, each `unknown`: nothing on it is nominal yet. */}
        {!examined && total(picture, tab) > 0 && <p className="px-4 pt-3 text-sm text-[#ffb786]">{NOT_EXAMINED}</p>}
        {tab === "rf" && (
          <DrillTable
            empty={noReceiverSentence("all")}
            rows={picture.rfSensors}
            spec={RECEIVERS}
          />
        )}
        {tab === "tracks" && (
          <DrillTable
            empty={noTrackSentence("all")}
            rows={picture.aircraftTracks}
            spec={TRACKS}
          />
        )}
        {tab === "events" && (
          <DrillTable
            empty={examined ? QUIET_HOUR : NOT_EXAMINED}
            rows={picture.timelineEvents}
            spec={EVENTS}
          />
        )}
      </>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0b0e15]/70 p-4">
      <div
        aria-labelledby={headingId}
        aria-modal="true"
        className="flex max-h-[85vh] w-full max-w-5xl flex-col border border-[#424754] bg-[#1d2027] text-[#e1e2ec] shadow-2xl"
        onKeyDown={(event) => {
          // Stopped here, so the map's own Escape (which closes its pop-up)
          // does not also fire under the table.
          if (event.key !== "Escape") return;
          event.stopPropagation();
          onClose();
        }}
        role="dialog"
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#424754] px-4 py-3">
          <div>
            <h2
              className="font-mono text-sm uppercase tracking-[0.05em]"
              id={headingId}
            >
              {drillDownHeading(tab, runId, loaded.status === "loaded" ? total(loaded.picture, tab) : null)}
            </h2>
            <p className="mt-1 text-xs text-[#8c909f]">{UNFILTERED}</p>
          </div>
          <button
            aria-label="Close"
            className="px-2 text-lg leading-none text-[#c2c6d6] hover:text-[#e1e2ec]"
            onClick={onClose}
            ref={closeRef}
            type="button"
          >
            ×
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col">{body()}</div>
      </div>
    </div>
  );
};
