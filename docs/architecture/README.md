# C4 Architecture Model

`workspace.dsl` is the source of truth. Everything else in this directory is regenerated and gitignored.

Four views: **L1 System Context**, **L2 Containers**, **L3 Backend Components**, and a **Deployment** view for the local Compose stack. Level 4 (Code) is deliberately skipped — C4 treats it as optional, it rots fastest, and `docs/em_fusion_v2.md` §9 plus the TypeScript/Pydantic types already serve that purpose.

## Viewing and editing

```bash
docker run -it --rm -p 9090:8080 \
  -v "$(pwd)/docs/architecture":/usr/local/structurizr \
  structurizr/structurizr local
```

Run from the repository root. Then open <http://localhost:9090>.

Two things to get right, both of which have bitten:

- **Mount an absolute path that exists.** Docker will not create a missing mount source, and it cannot create one under `/Users`, so a mistyped home directory surfaces as `mkdir ...: permission denied` rather than as "no such directory".
- **Port 9090, not 8080.** The backend dev server (`uvicorn app.main:app --port 8080`) already owns 8080, and Vite proxies `/api` there. The container listens on 8080 internally; only the host side moves.

`structurizr/structurizr local` is the successor to the standalone `structurizr/lite` image — the tooling was consolidated into one image with subcommands (`local`, `validate`, `export`, …). Either still works; `local` is the current form. The hosted structurizr.com workspace remains a fallback, not the default: no account, consistent with the project's stance that the hosted AI generator is the sole hosted dependency.

Edits made in the browser write back to `workspace.dsl`, so they land in git.

## Validating

```bash
docker run --rm -v "$(pwd)/docs/architecture":/usr/local/structurizr \
  structurizr/structurizr validate -workspace /usr/local/structurizr/workspace.dsl
```

Exit 0 and no output means the model parses and every view resolves. Worth running before committing a DSL change — a broken view fails here rather than as an empty diagram later.

## Exporting

Text formats, regenerable and diffable:

```bash
docker run --rm -v "$(pwd)/docs/architecture":/ws \
  structurizr/structurizr export -w /ws/workspace.dsl -f mermaid -o /ws/exports
```

`plantuml`, `mermaid`, `json`, and `dot` all work. **PNG and SVG do not** — the Docker build reports "Exporting to PNG/SVG is not supported in this build". For thesis figures, use the export control on each diagram in the browser UI and save into `exports/`.

## Notes on the model

- **`theme default` is deliberately absent.** It fetches from Structurizr's cloud service, which reaches end of life on 30 September 2026. A diagram that cannot be regenerated after that date is exactly the failure this whole text-based approach exists to avoid. The styles in `workspace.dsl` are self-contained.
- **The local model server sits outside the system boundary**, as an external software system rather than a container. It runs as a host process because Docker Desktop on macOS does not pass Metal through; the deployment view is where that shows, and it is a Compose config value (`host.docker.internal`), never a Compose service.
- **The basemap tile source is modelled as an external system.** It is not named in the original Track 0 checklist, and it qualifies the claim in `em_fusion_v2.md` §10 that the hosted AI generator is the sole hosted dependency — the browser also reaches a tile host. It is tagged `Optional` because `MapView` degrades to a placeholder when no tile URL is configured.
- **Two seams are styled to stand out**, because they carry the RQ1 extensibility argument: the adapter → DAL seam (any source reaches the canonical model one way) and the hypothesis service → generator seam (any generator reaches the analyst through the same interface and the same two guards).
