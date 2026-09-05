import { describe, expect, it } from "vitest";

// spec: api-003, FR-807 — the frontend polls. No push transport exists, and
// exactly one module reaches the network.
//
// This is the weaker sibling of the backend's route-purity check, and the
// difference is worth stating: that one parses, this one scrubs. Parsing
// TypeScript would mean adding the compiler as a dependency for a single test,
// so comments and string literals are stripped before matching instead — which
// covers the same failure (a rule *described* being mistaken for a rule
// *broken*) without a parser. Both halves are asserted below rather than
// assumed, and the check is mutation-tested like its sibling.
//
// Sources are read through Vite rather than through node:fs, so the test needs
// no node types in the app's TypeScript project and runs the same way in the
// container as it does locally.
//
// Test files are excluded from the scans: they hold the forbidden names as
// fixtures on purpose, which is exactly the "described, not broken" case, and
// the scrubber's behaviour on them is asserted directly at the foot of this
// file instead.

const modules = import.meta.glob("../**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const manifest = import.meta.glob("../../package.json", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const PUSH_TRANSPORTS = ["WebSocket", "EventSource", "socket.io", "sockjs", "pusher", "signalr"];

// The one module allowed to reach the network.
const FETCH_CALLERS = ["../lib/api.ts"];

const NETWORK_CALLS = [/\bfetch\s*\(/, /\bXMLHttpRequest\b/, /\baxios\b/];

// Block comments, then line comments, then the three kinds of string literal —
// in that order, so a comment containing a quote cannot leave an unterminated
// string behind for the next pass to mangle.
const scrub = (source: string): string =>
  source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/\/\/[^\n]*/g, " ")
    .replace(/`(?:\\.|[^`\\])*`/g, '""')
    .replace(/"(?:\\.|[^"\\])*"/g, '""')
    .replace(/'(?:\\.|[^'\\])*'/g, '""');

const appModules = Object.entries(modules).filter(([path]) => !path.startsWith("../test/"));

describe("transport", () => {
  it("checks the files it claims to check", () => {
    // An empty list would make every assertion below pass, which is the way a
    // structural test most often fails: silently, and green.
    const paths = appModules.map(([path]) => path);

    expect(paths).toContain("../App.tsx");
    expect(paths).toContain("../lib/api.ts");
  });

  it("has no push transport anywhere in the frontend source", () => {
    const offences = appModules.flatMap(([path, source]) => {
      const code = scrub(source);
      return PUSH_TRANSPORTS.filter((name) => code.includes(name)).map((name) => `${path}: ${name}`);
    });

    expect(offences).toEqual([]);
  });

  it("declares no push transport as a dependency", () => {
    const parsed = JSON.parse(Object.values(manifest)[0]);
    const declared = Object.keys({ ...parsed.dependencies, ...parsed.devDependencies });

    const offences = declared.filter((name) =>
      PUSH_TRANSPORTS.some((transport) => name.toLowerCase().includes(transport.toLowerCase())),
    );

    expect(offences).toEqual([]);
  });

  it("reaches the network from exactly one module", () => {
    // A second caller is how a screen quietly becomes coupled to the transport,
    // and how changing the endpoint stops being a one-file change.
    const offenders = appModules
      .filter(([path]) => !FETCH_CALLERS.includes(path))
      .filter(([, source]) => NETWORK_CALLS.some((pattern) => pattern.test(scrub(source))))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  it("ignores a transport named in a comment", () => {
    // The check must not punish writing the rule down — the defect that has now
    // appeared three times on the backend side of this repository.
    const code = scrub("// Never use a WebSocket here.\n/* or an EventSource */\nconst x = 1;");

    expect(PUSH_TRANSPORTS.some((name) => code.includes(name))).toBe(false);
  });

  it("ignores a transport named in a string", () => {
    const code = scrub('const reason = "WebSocket is out of scope";');

    expect(PUSH_TRANSPORTS.some((name) => code.includes(name))).toBe(false);
  });

  it("still catches a real one", () => {
    // Without this, the two above prove only that nothing is being checked.
    const code = scrub('const socket = new WebSocket("/live");');

    expect(PUSH_TRANSPORTS.some((name) => code.includes(name))).toBe(true);
  });

  it("still catches a real fetch", () => {
    const code = scrub('const response = await fetch("/api/v1/operational-picture");');

    expect(NETWORK_CALLS.some((pattern) => pattern.test(code))).toBe(true);
  });
});
