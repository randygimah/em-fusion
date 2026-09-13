import { useId, useState } from "react";
import { EmButton } from "../components/em/EmButton";
import {
  DEFAULT_CONFIGURATION,
  type ScenarioConfiguration,
  type ScenarioControl,
  type ScenarioRunRecord,
  type ScenarioTypeId,
  SEED_MAX,
  type SpectralExtent,
} from "../types/scenarioControl";

// The batch's own bounds. Fewer than twenty runs cannot carry a per-type rate
// worth reporting; more than thirty is more than the scoring campaign can take
// by hand. Refused here so the analyst learns it from the form rather than
// from a run that never started.
const MIN_RUNS = 20;
const MAX_RUNS = 30;

interface Props {
  control: ScenarioControl;
  // Optional on purpose (spec: scn-004). The scenario endpoints do not exist,
  // and a control wired to nothing would be the screen claiming a capability
  // the system does not have. Absent means disabled and said so, never hidden.
  onStart?: (configuration: ScenarioConfiguration) => void;
  onReset?: () => void;
  // Takes the record rather than the form's values. The form cannot express
  // everything a row holds — the baseline values and the derived window are
  // not dials — so replaying through it would quietly drop them.
  onReplay?: (run: ScenarioRunRecord) => void;
}

// The form holds strings, not numbers: an empty seed field has to stay empty
// rather than become a zero, and a value read back has to be the value typed.
interface Form {
  scenarioType: ScenarioTypeId;
  baseSeed: string;
  runs: string;
  durationSeconds: string;
  incidentOffsetS: string;
  incidentDurationS: string;
  radiusKm: string;
  elevationDb: string;
  spectralExtent: SpectralExtent;
}

const asForm = (configuration: ScenarioConfiguration): Form => ({
  scenarioType: configuration.scenarioType,
  baseSeed: configuration.baseSeed === null ? "" : String(configuration.baseSeed),
  runs: String(configuration.runs),
  durationSeconds: String(configuration.durationSeconds),
  incidentOffsetS: String(configuration.incidentOffsetS),
  incidentDurationS: String(configuration.incidentDurationS),
  radiusKm: String(configuration.radiusKm),
  elevationDb: String(configuration.elevationDb),
  spectralExtent: configuration.spectralExtent,
});

type Validated = { configuration: ScenarioConfiguration; error: null } | { configuration: null; error: string };

const validate = (form: Form): Validated => {
  const entered = form.baseSeed.trim();
  const baseSeed = entered === "" ? null : Number(entered);

  if (baseSeed !== null && (!Number.isInteger(baseSeed) || baseSeed < 0 || baseSeed > SEED_MAX)) {
    return {
      configuration: null,
      error: `A seed must be a whole number between 0 and ${SEED_MAX}. The run record stores it as a 32-bit signed integer, and a seed it cannot hold is a run nobody can repeat.`,
    };
  }

  const runs = Number(form.runs);
  if (!Number.isInteger(runs) || runs < MIN_RUNS || runs > MAX_RUNS) {
    return {
      configuration: null,
      error: `A batch is between ${MIN_RUNS} and ${MAX_RUNS} runs. Fewer cannot carry a per-type rate worth reporting, and more is more than the scoring campaign can take by hand.`,
    };
  }

  return {
    error: null,
    configuration: {
      scenarioType: form.scenarioType,
      baseSeed,
      runs,
      durationSeconds: Number(form.durationSeconds),
      incidentOffsetS: Number(form.incidentOffsetS),
      incidentDurationS: Number(form.incidentDurationS),
      radiusKm: Number(form.radiusKm),
      elevationDb: Number(form.elevationDb),
      spectralExtent: form.spectralExtent,
    },
  };
};

const LABEL = "block font-mono text-[10px] font-bold uppercase tracking-[0.05em] text-[#8c909f]";
// The same type as a field label, at the display a <caption> needs. `block`
// takes a caption out of the table's caption box, and the browser then stops
// hoisting it above the table: it lands in normal flow, under the column
// headers. Invisible to the tests, which read the accessible name the caption
// gives the table and never its box.
const CAPTION = LABEL.replace("block", "table-caption");
const INPUT =
  "mt-1 w-full rounded border border-[#424754] bg-[#0b0e15] px-2 py-1.5 font-mono text-[13px] text-[#e1e2ec] focus:border-[#4d8eff] focus:outline-none";

const NumberField = ({ label, value, onChange, hint }: { label: string; value: string; onChange: (value: string) => void; hint?: string }) => {
  const id = useId();
  return (
    <div>
      <label
        className={LABEL}
        htmlFor={id}
      >
        {label}
      </label>
      <input
        className={INPUT}
        id={id}
        inputMode="numeric"
        onChange={(event) => onChange(event.target.value)}
        placeholder={hint}
        value={value}
      />
    </div>
  );
};

const ScenarioControlScreen = ({ control, onStart, onReset, onReplay }: Props) => {
  const [form, setForm] = useState<Form>(() => asForm(DEFAULT_CONFIGURATION));
  const [error, setError] = useState<string | null>(null);
  const libraryHeading = useId();
  const extentField = useId();

  const set = (field: keyof Form) => (value: string) => setForm((current) => ({ ...current, [field]: value }));

  const nameFor = (id: ScenarioTypeId): string => control.library.find((entry) => entry.id === id)?.name ?? id;

  const start = () => {
    const { configuration, error: refusal } = validate(form);
    setError(refusal);
    if (configuration !== null) {
      onStart?.(configuration);
    }
  };

  const replay = (run: ScenarioRunRecord) => {
    const recorded = run.parameters;
    setForm((current) => ({
      ...current,
      scenarioType: run.scenarioType,
      baseSeed: String(run.seed),
      durationSeconds: String(recorded.duration_seconds),
      incidentOffsetS: String(recorded.start_offset_s),
      incidentDurationS: String(recorded.duration_s),
      radiusKm: String(recorded.radius_km),
      elevationDb: String(recorded.elevation_db),
      spectralExtent: recorded.spectral_extent,
    }));
    setError(null);
    onReplay?.(run);
  };

  // The row is the only thing that says whether a run finished, and it says it
  // by absence (db-007). It cannot tell a run still going from one that died,
  // so neither does this.
  const latest = control.runs[0];
  const status =
    latest === undefined
      ? "Idle — no runs recorded"
      : latest.completedAt === null
        ? `Run ${latest.id} incomplete — started and not known to have finished`
        : `Run ${latest.id} complete — ${nameFor(latest.scenarioType)}`;

  return (
    <main className="min-h-screen bg-[#0b0e15] text-[#e1e2ec]">
      <header className="flex items-baseline justify-between border-b border-[#424754] bg-[#1d2027] px-6 py-4">
        <div>
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.05em] text-[#8c909f]">EM Fusion</p>
          <h1 className="text-xl font-semibold">Scenario Control</h1>
        </div>
        <p
          className="font-mono text-[13px] text-[#4cd7f6]"
          role="status"
        >
          {status}
        </p>
      </header>

      <div className="grid gap-4 p-6 lg:grid-cols-[320px_1fr]">
        <section
          aria-labelledby={libraryHeading}
          className="space-y-2 border border-[#424754] bg-[#1d2027] p-3"
        >
          <h2
            className={LABEL}
            id={libraryHeading}
          >
            Scenario library
          </h2>
          {control.library.map((entry) => (
            <button
              aria-pressed={form.scenarioType === entry.id}
              className={`block w-full rounded border p-2 text-left ${
                form.scenarioType === entry.id
                  ? "border-[#4d8eff] bg-[#00285d] text-[#d8e2ff]"
                  : "border-[#424754] bg-[#191b23] text-[#c2c6d6] hover:border-[#8c909f]"
              }`}
              key={entry.id}
              onClick={() => setForm((current) => ({ ...current, scenarioType: entry.id }))}
              type="button"
            >
              <span className="block text-[14px] font-semibold">{entry.name}</span>
              <span className="mt-0.5 block text-[12px] text-[#8c909f]">{entry.description}</span>
            </button>
          ))}
        </section>

        <div className="space-y-4">
          <section className="border border-[#424754] bg-[#1d2027] p-3">
            <h2 className={LABEL}>Run configuration</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <NumberField
                hint="chosen and recorded for you"
                label="Base seed"
                onChange={set("baseSeed")}
                value={form.baseSeed}
              />
              <NumberField
                label="Runs in batch"
                onChange={set("runs")}
                value={form.runs}
              />
              <NumberField
                label="Run duration (s)"
                onChange={set("durationSeconds")}
                value={form.durationSeconds}
              />
              <NumberField
                label="Incident offset (s)"
                onChange={set("incidentOffsetS")}
                value={form.incidentOffsetS}
              />
              <NumberField
                label="Incident duration (s)"
                onChange={set("incidentDurationS")}
                value={form.incidentDurationS}
              />
              <NumberField
                label="Zone radius (km)"
                onChange={set("radiusKm")}
                value={form.radiusKm}
              />
              <NumberField
                label="Noise elevation (dB)"
                onChange={set("elevationDb")}
                value={form.elevationDb}
              />
              <div>
                <label
                  className={LABEL}
                  htmlFor={extentField}
                >
                  Spectral extent
                </label>
                <select
                  className={INPUT}
                  id={extentField}
                  onChange={(event) => setForm((current) => ({ ...current, spectralExtent: event.target.value as SpectralExtent }))}
                  value={form.spectralExtent}
                >
                  <option value="narrowband">Narrowband — the navigation slice</option>
                  <option value="broadband">Broadband — the whole band</option>
                </select>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <EmButton
                disabled={onStart === undefined}
                onClick={start}
              >
                Start batch
              </EmButton>
              <EmButton
                disabled={onReset === undefined}
                onClick={() => onReset?.()}
                variant="ghost"
              >
                Reset
              </EmButton>
            </div>

            {onStart === undefined && (
              <p
                className="mt-3 border-l-2 border-[#df7412] bg-[#191b23] px-3 py-2 text-[12px] text-[#ffb786]"
                role="note"
              >
                Nothing is wired to these controls yet: the scenario endpoints are not built, and the runs listed below are a fixture from a
                recorded batch rather than the database. A batch runs from the command line today —
                <span className="font-mono"> make generate</span> — and this screen is what will drive it.
              </p>
            )}

            {error !== null && (
              <p
                className="mt-3 border-l-2 border-[#ffb4ab] bg-[#191b23] px-3 py-2 text-[12px] text-[#ffb4ab]"
                role="alert"
              >
                {error}
              </p>
            )}
          </section>

          <section className="border border-[#424754] bg-[#1d2027] p-3">
            <table className="w-full border-collapse text-left text-[13px]">
              <caption className={`${CAPTION} mb-2 text-left`}>Recent runs</caption>
              <thead>
                <tr className="border-b border-[#424754] text-[#8c909f]">
                  <th className="py-1 font-mono text-[10px] font-bold uppercase tracking-[0.05em]">Scenario type</th>
                  <th className="py-1 font-mono text-[10px] font-bold uppercase tracking-[0.05em]">Seed</th>
                  <th className="py-1 font-mono text-[10px] font-bold uppercase tracking-[0.05em]">Started</th>
                  <th className="py-1 font-mono text-[10px] font-bold uppercase tracking-[0.05em]">Outcome</th>
                  <th className="py-1 font-mono text-[10px] font-bold uppercase tracking-[0.05em]">Replay</th>
                </tr>
              </thead>
              <tbody>
                {control.runs.map((run) => (
                  <tr
                    className="border-b border-[#32353c]"
                    key={run.id}
                  >
                    <td className="py-1.5">{nameFor(run.scenarioType)}</td>
                    <td className="py-1.5 font-mono text-[#4cd7f6]">{run.seed}</td>
                    <td className="py-1.5 font-mono text-[#c2c6d6]">{run.startedAt.replace("T", " ").replace("Z", "")}</td>
                    <td className="py-1.5">{run.completedAt === null ? "Incomplete" : "Complete"}</td>
                    <td className="py-1.5">
                      <EmButton
                        disabled={onReplay === undefined}
                        onClick={() => replay(run)}
                        size="sm"
                      >
                        Replay
                      </EmButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {control.runs.length === 0 && <p className="mt-2 text-[12px] text-[#8c909f]">No runs recorded yet.</p>}
          </section>
        </div>
      </div>
    </main>
  );
};

export default ScenarioControlScreen;
