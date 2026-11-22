"""A-1 (LEAK-2, D-022): customer-facing modules never import the notes model or mention the
notes table — checked on the syntax tree (imports, names, attributes) and on the raw text."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
CUSTOMER_FILES = [APP / "schemas" / "customer.py", APP / "api" / "customer.py",
                  APP / "api" / "public.py"]
MODEL = "InternalNote"
TABLE = "internal_notes"


def _names(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.update(alias.name for alias in node.names)
            found.update(alias.asname for alias in node.names if alias.asname)
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.update(node.value.split())
    return found


@pytest.mark.parametrize("path", CUSTOMER_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_a1_customer_modules_never_touch_notes(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    names = _names(ast.parse(source))
    assert MODEL not in names, f"{path.name} references {MODEL}"
    assert TABLE not in source, f"{path.name} mentions the {TABLE} table"
    assert MODEL not in source, f"{path.name} mentions {MODEL}"


def test_a1_check_would_catch_a_violation() -> None:
    """The checker itself works (guards against a vacuous test)."""
    assert MODEL in _names(ast.parse("from app.models import InternalNote as N\nN"))
    assert MODEL in _names(ast.parse("import app.models as m\nm.InternalNote"))
