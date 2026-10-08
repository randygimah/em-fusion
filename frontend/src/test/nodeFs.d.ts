// The one Node API a frontend test uses (mapBoundary.test.tsx reads the
// committed .env files, which Vite refuses to serve as modules). Declared
// narrowly here rather than adding Node's types to the app's project, which
// would let app code use Node globals without a type error.
declare module "node:fs" {
  export function readFileSync(path: string, encoding: "utf8"): string;
}
