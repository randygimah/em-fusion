import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import App from "./App";

test("shows the GNSS degradation operational picture for an analyst", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: /active hypotheses/i })).toBeInTheDocument();
  // spec: api-019 — first paint is the mock, and the mock carries no
  // explanation: a made-up card shown before the first poll was an explanation
  // that does not exist reaching an analyst (qa.md 162). Its confidence and
  // free-text evidence went with it.
  expect(screen.getByText(/no active hypotheses/i)).toBeInTheDocument();
  expect(screen.queryByText(/gnss degradation/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/3 synthetic sources/i)).not.toBeInTheDocument();
  // spec: api-002 — no longer a score, because it is no longer a number.
  expect(screen.getByText(/anomaly level/i)).toBeInTheDocument();
});
