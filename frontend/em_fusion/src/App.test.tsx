import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import App from "./App";

test("shows the GNSS degradation operational picture for an analyst", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: /active hypotheses/i })).toBeInTheDocument();
  expect(screen.getByText(/gnss degradation/i)).toBeInTheDocument();
  expect(screen.getByText(/medium confidence/i)).toBeInTheDocument();
  expect(screen.getByText(/3 synthetic sources/i)).toBeInTheDocument();
  expect(screen.getByText(/anomaly score/i)).toBeInTheDocument();
});
