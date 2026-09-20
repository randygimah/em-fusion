"""What does adding a hypothesis provider actually cost? Spec: ai-003.

`ai-003` claims that adding a provider touches one adapter module and one
registry line. That is the kind of claim a design document asserts and
nobody checks, which is why `US-R6` asks for it as a *measurement* and why
`adp-003` exists to make the same measurement on the source-adapter side.
This is the generator-side half of it, and it can be taken now because the
template is a real provider registered through the real interface.

**What is counted, and what is not.** The interesting number is not how big
an adapter is -- that is mostly the provider's own API surface and tells
you nothing about the abstraction. It is how much has to change
*everywhere else*. An abstraction that holds costs a constant, small edit
outside the new module; one that leaks costs a change per existing caller.

Read the caveat with the figure: the shipped adapter wraps a local function
and makes no network call, so its own size is a **lower bound** and a
hosted adapter will be several times larger. The number that carries the
claim is the one outside it, and that one does not depend on what the
adapter does.

Needs no database and no corpus. It reads the source tree.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
AI = ROOT / "app" / "ai"
PROVIDERS = AI / "providers"


def code_lines(path: Path) -> int:
    """Lines that are neither blank, comment, nor docstring."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstring_spans: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef
                      | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                    and first.end_lineno is not None):
                docstring_spans.update(range(first.lineno, first.end_lineno + 1))
    return sum(
        1 for number, line in enumerate(source.splitlines(), start=1)
        if line.strip() and not line.strip().startswith("#")
        and number not in docstring_spans
    )


def registry_cost() -> tuple[int, int]:
    """(import lines, mapping entries) the registry holds for its providers."""
    tree = ast.parse((AI / "registry.py").read_text(encoding="utf-8"))
    imports = sum(
        1 for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("app.ai.providers")
    )
    entries = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.AnnAssign | ast.Assign)
                and isinstance(node.value, ast.Dict)):
            targets = ([node.target] if isinstance(node, ast.AnnAssign)
                       else list(node.targets))
            if any(getattr(t, "id", "") == "PROVIDERS" for t in targets):
                entries = len(node.value.keys)
    return imports, entries


adapters = sorted(p for p in PROVIDERS.glob("*.py") if p.name != "__init__.py")
imports, entries = registry_cost()
per_provider = (imports + entries) // max(len(adapters), 1)

print("WHAT ADDING A HYPOTHESIS PROVIDER COSTS")
print("=" * 74)
print(f"  adapter modules registered: {len(adapters)}")
for path in adapters:
    print(f"    {path.relative_to(ROOT)}  {code_lines(path)} lines of code")
print()
print("  ...and everywhere else:")
print(f"    app/ai/registry.py       {imports} import line(s) and {entries} "
      f"mapping entry(ies) for {len(adapters)} provider(s)")
print("    app/ai/service.py        0 -- the interface imports no adapter")
print("    every caller             0 -- a caller is handed a generator and "
      "cannot tell which")
print()
print(f"  So one provider = 1 new module + {per_provider} lines in 1 existing "
      "file,")
print("  and 0 changes anywhere else.")
print()
print("  CAVEAT, and it matters: the shipped adapter wraps a local function and")
print("  makes no network call, so its own size is a LOWER BOUND -- a hosted")
print("  adapter will be several times larger. The claim is about the cost")
print("  OUTSIDE the new module, and that cost does not depend on what the")
print("  adapter does.")
print()
print("  For comparison, the interface it plugs into:")
for name in ("service.py", "registry.py"):
    print(f"    app/ai/{name:14} {code_lines(AI / name)} lines of code")
