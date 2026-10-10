import type { Level } from "../../types/operationalPicture";

interface Props {
  /** The row's name, kept on screen even when the value is refused. */
  label: string;
  value: Level;
}

const ALLOWED: readonly string[] = ["Low", "Medium", "High"];

/**
 * The one way a level reaches a screen. spec: ui-001, FR-715, AC-11.
 *
 * Three call sites: the anomaly level, signal integrity, and a hypothesis card's
 * confidence. The card's severity went with api-019: nothing produced it.
 *
 * **The guard is a runtime one, and that is the whole point of the component.**
 * The contract declares `Level` as exactly Low | Medium | High, so TypeScript
 * refuses a number at the call site — but the payload is *cast* from JSON, so a
 * backend regression delivers `87` at runtime with nothing between it and the
 * screen. A compile-time type cannot see that.
 *
 * What a refusal does, decided rather than read off the item:
 *
 * - **No value is rendered**, so no number, percentage or decimal reaches an
 *   analyst in any form.
 * - **The label stays**, so the row reads as visibly incomplete rather than
 *   silently absent. A row with a name and no value looks like a fault, which
 *   is what it is.
 * - **The value is reported through `console.error`**, whose audience is the
 *   developer who caused it. This is the one place in this project where an
 *   absence deliberately gets no composed sentence: an invalid level is not a
 *   state the system is allowed to be in, so there is nothing honest to say to
 *   an analyst about it.
 * - **It never throws.** A primitive that raises during render takes down a
 *   whole screen over one bad badge, which is a larger failure than the one
 *   being prevented.
 *
 * It renders no typed absence of its own. A missing count and a rule that does
 * not exist are both dashes (`op-003`), and both are facts about a *producer*
 * rather than levels; routing them through here would make "no rule exists" and
 * "the backend sent a number" render identically.
 */
export const EmLevel = ({ label, value }: Props) => {
  const valid = typeof value === "string" && ALLOWED.includes(value);

  if (!valid) {
    console.error(
      `${label}: refused a value outside Low|Medium|High (${typeof value}: ${JSON.stringify(value)}). ` +
        "This is a defect upstream — the payload is cast from JSON, so the type did not catch it.",
    );
  }

  // A definition list row, because that is what a label and its value are —
  // and because the panel's existing tests read the value as the `dd` beside
  // the label, which is behaviour this item has no business changing. The
  // caller supplies the surrounding `<dl>`.
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-[#c2c6d6]">{label}</dt>
      {valid && <dd className="font-mono text-[#4cd7f6]">{value}</dd>}
    </div>
  );
};
