import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import App from "./App";

test("shows the GNSS degradation operational picture for an analyst", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: /active hypotheses/i })).toBeInTheDocument();
  expect(screen.getByText(/gnss degradation/i)).toBeInTheDocument();
  // spec: api-002 — the mock said "Medium Confidence", which is not a value
  // the contract admits. Confidence is one of Low, Medium, High (FR-715), and
  // the assertion is scoped to its own term: the same three words are now the
  // vocabulary of every level on the screen, so a bare text match is ambiguous.
  expect(screen.getByText("Confidence").parentElement?.querySelector("dd")).toHaveTextContent(
    "Medium",
  );
  expect(screen.getByText(/3 synthetic sources/i)).toBeInTheDocument();
  // spec: api-002 — no longer a score, because it is no longer a number.
  expect(screen.getByText(/anomaly level/i)).toBeInTheDocument();
});
