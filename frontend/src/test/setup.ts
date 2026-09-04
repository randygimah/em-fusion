import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest here runs without `globals`, so Testing Library's own auto-cleanup
// never registers itself. Without this, renders accumulate across the tests in
// a file and every query that should match one element matches several — which
// reads as a duplicate-element bug in the component rather than as a missing
// teardown in the harness.
afterEach(cleanup);
