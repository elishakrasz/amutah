"""The domain package stays pure: no I/O, no framework imports. This is what
makes the rules reviewable by non-engineers."""

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[2] / "app" / "domain"
FORBIDDEN = (
    "sqlalchemy",
    "fastapi",
    "pydantic",
    "starlette",
    "app.models",
    "app.services",
    "app.db",
    "app.routers",
    "os",
    "requests",
    "httpx",
    "socket",
    "subprocess",
)


def test_domain_imports_nothing_impure() -> None:
    bad = []
    for path in DOMAIN.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                    bad.append(f"{path.name}: {name}")
    assert bad == []
