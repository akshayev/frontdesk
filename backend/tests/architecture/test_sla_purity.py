"""A-2: nothing in app/sla imports fastapi / sqlalchemy or reads the system clock."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SLA_DIR = Path(__file__).resolve().parents[2] / "app" / "sla"
SLA_FILES = sorted(SLA_DIR.glob("*.py"))
FORBIDDEN_TOP_LEVEL = {"fastapi", "starlette", "sqlalchemy", "alembic", "psycopg"}
FORBIDDEN_IMPORTS = FORBIDDEN_TOP_LEVEL | {"time"}  # stdlib clock module (time.time etc.)
CLOCK_ATTRS = {"now", "utcnow", "today"}


def _imported_modules(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_sla_files_found() -> None:
    assert {p.name for p in SLA_FILES} >= {"__init__.py", "calendar.py", "policy.py"}


@pytest.mark.parametrize("path", SLA_FILES, ids=lambda p: p.name)
def test_a2_no_framework_imports(path: Path) -> None:
    """A-2: no FastAPI/SQLAlchemy (or DB driver); app imports only from app.sla itself."""
    modules = _imported_modules(ast.parse(path.read_text()))
    for module in modules:
        assert module.split(".")[0] not in FORBIDDEN_IMPORTS, f"{path.name} imports {module}"
        if module.split(".")[0] == "app":
            assert module.startswith("app.sla"), f"{path.name} imports {module}"


@pytest.mark.parametrize("path", SLA_FILES, ids=lambda p: p.name)
def test_a2_no_clock_reads(path: Path) -> None:
    """A-2: no datetime.now / utcnow / today or date.today anywhere (the `time` module is
    banned by test_a2_no_framework_imports)."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in CLOCK_ATTRS, f"{path.name}:{node.lineno} uses .{node.attr}"


def test_a2_importing_sla_loads_no_framework() -> None:
    """A-2 (transitive): importing app.sla in a clean interpreter loads no framework module."""
    code = (
        "import sys, app.sla.calendar, app.sla.policy\n"
        f"banned = {sorted(FORBIDDEN_TOP_LEVEL)!r}\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in banned)\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=SLA_DIR.parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == ""
