import { cn } from "../../lib/utils";
import type { ReviewStatus } from "../../types/hypotheses";

/**
 * An explanation's review status (op-002, hyp-001): DESIGN.md's dot + text in a
 * tinted pill, New in the primary tint and every other status neutral. The
 * status is shown in its stored words.
 */
export const EmStatusPill = ({ status, className }: { status: ReviewStatus; className?: string }) => (
  <p
    className={cn(
      "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-xs uppercase",
      status === "New" ? "bg-[#4d8eff]/20 text-[#adc6ff]" : "bg-[#32353c] text-[#c2c6d6]",
      className,
    )}
  >
    <span
      aria-hidden="true"
      className={cn("h-1.5 w-1.5 rounded-full", status === "New" ? "bg-[#adc6ff]" : "bg-[#8c909f]")}
    />
    {status}
  </p>
);
