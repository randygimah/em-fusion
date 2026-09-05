"""The backend serves HTTP and nothing else. Spec: api-003.

The sibling of `frontend/src/test/transport.test.ts`, and the split is not
tidiness: neither container can see the whole repository, so "no push transport
anywhere" is asserted twice, each half over what it can actually read. The
frontend suite scans `src/` and `package.json`; this scans `app/` and
`pyproject.toml`.

`FR-807` puts it plainly -- the frontend polls, and no WebSocket or push
transport exists in v1. The reason is that a replay-based prototype does not
need push infrastructure, and polling is one sentence to defend in a viva
rather than a component to operate. The trap this guards is that FastAPI ships
WebSocket support built in: there is no dependency to add, so nothing would
stop a handler appearing except a rule nobody is checking.

Parsed rather than grepped, for the reason `db-006` sets out at length.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

#: Packages that exist to push. `sse_starlette` is included because
#: server-sent events are push wearing an HTTP-shaped hat.
PUSH_PACKAGES = (
    "websockets",
    "socketio",
    "python_socketio",
    "sse_starlette",
    "aiohttp",
)

#: FastAPI needs no dependency for this: `@router.websocket("/live")` is
#: available the moment the framework is installed.
PUSH_DECORATORS = ("websocket", "websocket_route")


def _modules() -> list[Path]:
    return sorted(APP_ROOT.rglob("*.py"))


def _trees() -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in _modules()]


def test_the_check_covers_the_modules_it_claims_to() -> None:
    # spec: api-003 -- an empty file list passes every assertion below
    names = {path.name for path in _modules()}

    assert {"main.py", "operational_picture.py"} <= names


def test_no_push_transport_is_imported_anywhere_in_the_backend() -> None:
    # spec: api-003, FR-807
    offences: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if any(part in PUSH_PACKAGES for part in module.split(".")):
                    offences.append(f"{path.name}: {module}")

    assert offences == []


def test_no_handler_is_registered_as_a_websocket() -> None:
    """The one that needs no dependency, and so needs a test.

    `@router.websocket("/live")` requires nothing to be installed. An import
    check alone would report a clean backend serving a WebSocket.
    """
    # spec: api-003, FR-807
    offences: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                call = decorator.func if isinstance(decorator, ast.Call) else decorator
                if isinstance(call, ast.Attribute) and call.attr in PUSH_DECORATORS:
                    offences.append(f"{path.name}: {node.name}")

    assert offences == []


def test_no_push_transport_is_declared_as_a_dependency() -> None:
    # spec: api-003 -- the dependency tree half of the failure case. A package
    # that is installed is a package someone will eventually import.
    config = tomllib.loads(
        (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    declared = list(config["project"]["dependencies"])
    for group in config.get("dependency-groups", {}).values():
        declared.extend(item for item in group if isinstance(item, str))

    offences = [
        name
        for name in declared
        if any(package.replace("_", "-") in name.lower() for package in PUSH_PACKAGES)
    ]

    assert offences == []
