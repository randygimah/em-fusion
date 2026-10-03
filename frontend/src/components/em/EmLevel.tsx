import type { Level } from "../../types/operationalPicture";

interface Props {
  label: string;
  value: Level;
}

/** STUB — ui-001 not implemented. */
export const EmLevel = ({ label, value }: Props) => (
  <span>
    {label}: {String(value)}
  </span>
);
