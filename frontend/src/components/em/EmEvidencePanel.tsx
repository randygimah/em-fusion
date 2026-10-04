import type { EvidenceAccount } from "../../types/evidence";

/** Stub: `op-010` is specified and unbuilt. */
export const EmEvidencePanel = ({
  account,
}: {
  account: EvidenceAccount | null | undefined;
}) => (
  <section aria-label="Evidence">
    <p>{account === undefined ? "" : ""}</p>
  </section>
);
