"""Nothing in the API layer touches storage directly. Spec: db-006.

The enforcement half of `FR-904`. `db-003` is the repository existing and being
correct; this is nothing going around it. The two fail at different times and
that is why they are separate items: a broken repository fails at write time
against a populated database, while a query leaked into a handler fails review
and nothing else -- it works perfectly, right up until the day someone needs to
change how data is read and finds two places doing it.

**Parsed, not grepped.** Every assertion here reads the abstract syntax tree.
A substring search over the source is satisfied by an example inside a
docstring, which is how the equivalent check in `dal-004` passed vacuously
once already (`docs/qa.md` section 38) and how a `compose.yaml` test matched
its own explanatory comment during `adp-007`. Comments never reach the tree at
all; docstrings do, and are identified and skipped. Both halves are asserted
below against synthetic modules rather than assumed, because a check that
cannot tell a rule from a description of the rule is the failure this file
exists to prevent, one level up.

**The rule is stated at the import graph wherever possible.** "No SQL in a
handler" is the requirement, but "the API layer does not import a storage
engine" is the same property expressed where it cannot be argued about, and it
is the form `db-003` already uses one layer down for the DAL.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = BACKEND_ROOT / "app" / "api"

#: A storage engine imported anywhere in the API layer. `alembic` is included
#: because a migration run from a request handler is the same mistake wearing a
#: different hat.
STORAGE_PACKAGES = ("sqlalchemy", "geoalchemy2", "psycopg", "alembic")

#: The only two storage modules the API may name. `repository` is the port
#: `FR-904` requires everything to go through; `session` supplies the
#: dependency and the type alias for it. Anything else under `app.db` is the
#: implementation, and a handler that reaches for it has gone around the port.
ALLOWED_STORAGE_MODULES = {"app.db.repository", "app.db.session"}

#: Enough of a SQL statement to be a SQL statement. Anchored on a keyword
#: followed by whitespace so that a route path or a tag cannot trip it.
SQL = re.compile(
    r"\b(select|insert|update|delete|create|drop|alter|truncate)\b\s", re.IGNORECASE
)

#: PostGIS spells its functions `ST_Something`, without exception.
POSTGIS = re.compile(r"\bst_[a-z]", re.IGNORECASE)

#: Constructing any of these in the API layer means the handler has built its
#: own connection to the database rather than being handed one.
CONSTRUCTORS = frozenset(
    {"sessionmaker", "create_engine", "Session", "scoped_session", "text", "connect"}
)


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """The identity of every docstring constant in the tree.

    Docstrings are ordinary string expressions once parsed, so they have to be
    found and excluded deliberately. Comments need no such handling: the parser
    discards them, which is the whole reason this is a parser.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add(id(first.value))
    return found


def _called_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def violations(source: str) -> list[tuple[str, str]]:
    """Every way one module breaks the rule, as (kind, detail).

    Returned rather than asserted so the same function serves the real modules
    and the synthetic ones below, and so a failure names what it found.
    """
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    found: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for module in modules:
                if module.split(".")[0] in STORAGE_PACKAGES:
                    found.append(("storage-engine", module))
                elif (
                    module.startswith("app.db")
                    and module not in ALLOWED_STORAGE_MODULES
                ):
                    found.append(("past-the-repository", module))

        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            if SQL.search(node.value):
                found.append(("sql", node.value.strip()[:60]))
            if POSTGIS.search(node.value):
                found.append(("postgis", node.value.strip()[:60]))

        elif isinstance(node, ast.Call):
            name = _called_name(node)
            if name in CONSTRUCTORS:
                found.append(("constructs-storage", name))
            if POSTGIS.match(name):
                found.append(("postgis", name))

    return found


def _modules() -> list[Path]:
    return sorted(API_ROOT.rglob("*.py"))


def _kind(kind: str) -> list[str]:
    offences: list[str] = []
    for path in _modules():
        for found, detail in violations(path.read_text(encoding="utf-8")):
            if found == kind:
                offences.append(f"{path.relative_to(BACKEND_ROOT)}: {detail}")
    return offences


# ------------------------------------------------------------------ the guard


def test_the_check_covers_the_modules_it_claims_to() -> None:
    """An empty file list would make every assertion below pass.

    That is not hypothetical: this item was deliberately held back from
    `db-003` because there was no data-serving route to assert over, and a
    check written then would have reported a clean API layer containing one
    health endpoint and nothing else.
    """
    # spec: db-006
    names = {path.name for path in _modules()}

    assert "operational_picture.py" in names
    assert "health.py" in names


# ------------------------------------------------------------------ the rules


def test_no_route_module_imports_a_storage_engine() -> None:
    # spec: db-006, FR-904 -- the same assertion `db-003` makes over `app/dal/`,
    # for the same reason: a layer that cannot name a storage engine cannot use
    # one, and that is checkable where "holds no SQL" is arguable
    assert _kind("storage-engine") == []


def test_no_route_module_reaches_past_the_repository() -> None:
    # spec: db-006, FR-904 -- `app.db.repository` and `app.db.session` are the
    # port and the dependency that supplies it. Anything else under `app.db` is
    # the implementation, and importing it is going around the port rather than
    # through it.
    assert _kind("past-the-repository") == []


def test_no_route_module_holds_a_sql_statement() -> None:
    # spec: db-006, FR-904
    assert _kind("sql") == []


def test_no_route_module_names_a_postgis_function() -> None:
    # spec: db-006, FR-904 -- spatial logic is the repository's, and a handler
    # calling ST_DWithin is a second place the distance semantics can be got
    # wrong, in a layer with no test that would notice
    assert _kind("postgis") == []


def test_no_route_module_constructs_a_session_or_an_engine() -> None:
    # spec: db-006, db-005 -- one Engine per process, built in the lifespan. A
    # handler constructing its own builds a second connection pool nobody knows
    # about, which is a resource leak that only shows up under load.
    assert _kind("constructs-storage") == []


# ---------------------------------------------- the check checks what it claims

VIOLATION = 'session.execute(text("SELECT * FROM observations"))'


def test_a_real_violation_is_caught() -> None:
    """Without this, the three tests below prove only that nothing is checked."""
    # spec: db-006 -- the named failure case
    source = f'''"""A handler."""
from sqlalchemy import text


def read():
    {VIOLATION}
'''
    kinds = {kind for kind, _ in violations(source)}

    assert kinds == {"storage-engine", "sql", "constructs-storage"}


def test_a_violation_written_inside_a_docstring_is_not_a_violation() -> None:
    """The second named failure case, and the reason this is a parser.

    A docstring explaining what the module must not do contains the very text a
    search would match. Under a grep, the clearest possible documentation of
    the rule is indistinguishable from breaking it — so the rule ends up
    enforced by nobody writing it down.
    """
    # spec: db-006
    source = f'''"""This module must never do this: {VIOLATION}

    It obtains data by calling a repository function instead.
    """


def read():
    return None
'''
    assert violations(source) == []


def test_a_violation_written_inside_a_comment_is_not_a_violation() -> None:
    # spec: db-006 -- comments never reach the syntax tree, so this passes by
    # construction. Asserted anyway, because "by construction" is a claim about
    # the parser and this is what makes it a checked one.
    source = f"""def read():
    # Never do this: {VIOLATION}
    return None
"""
    assert violations(source) == []


def test_a_docstring_on_a_function_is_skipped_too() -> None:
    # spec: db-006 -- module docstrings are the obvious case and function ones
    # are where a rule is most naturally written down, next to the handler it
    # constrains
    source = f'''def read():
    """Obtains data via the repository, never {VIOLATION}"""
    return None
'''
    assert violations(source) == []


@pytest.mark.parametrize(
    "statement",
    [
        'text("select 1")',
        'connection.execute("DELETE FROM observations")',
        'session.execute("ST_DWithin(location, :point, 20000)")',
    ],
)
def test_each_forbidden_shape_is_recognised(statement: str) -> None:
    # spec: db-006 -- one case per rule, so a regex that stops matching is a
    # named failure rather than a silently emptier check
    assert violations(f"def read():\n    {statement}\n") != []


# Mutation results, 2026-09-05, run in both directions as `db-006` requires.
#
#   * A real query in the handler -- `session.execute(text("SELECT count(*) FROM
#     observations"))` with its import -- turned three tests red at once:
#     the storage-engine import, the SQL statement, and the constructor. One
#     violation tripping three independent rules is the point of stating the
#     same property three ways.
#   * The identical text written inside the module's docstring, as a
#     prohibition ("a handler must never write ..."), left all thirteen green.
#     `grep -c` over the same file at the same moment returned 1. That pair is
#     the whole argument for parsing: the grep-based check would have failed on
#     the clearest possible documentation of the rule it was enforcing, and the
#     rational response to such a check is to stop writing the rule down.
#
# The first assertion here was red on arrival for a real reason, which is rarer
# than it should be for a structural test: `app/api/v1/operational_picture.py`
# imported `sqlalchemy.orm` to annotate a parameter it never constructed. Fixed
# by naming the type in `app/db/session.py` instead.
