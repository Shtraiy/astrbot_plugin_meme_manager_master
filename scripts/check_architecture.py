"""Fast, dependency-free architecture guard for local development and CI."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_FILES = (
    "manager_base.py",
    "backend/pack_resolver.py",
    "backend/category_manager.py",
    "backend/pack_repository.py",
    "backend/pack_storage.py",
    "mixins/event_handlers.py",
)
FORBIDDEN_DOMAIN_IMPORTS = ("astrbot", "quart", "PIL", "requests", "aiohttp")
FORBIDDEN_SEMANTIC_PREFIXES = ("backend.semantic_models", "backend.semantic_query", "backend.semantic_storage", "backend.semantic_index")


def imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    return imports


def check() -> list[str]:
    violations: list[str] = []
    for path in (ROOT / "domain").glob("*.py"):
        for module in imports_for(path):
            if module in {"json", "os", "shutil", "subprocess"} or module.startswith(FORBIDDEN_DOMAIN_IMPORTS):
                violations.append(f"domain import forbidden: {path.relative_to(ROOT)} -> {module}")

    for relative in CORE_FILES:
        path = ROOT / relative
        for module in imports_for(path):
            if module in FORBIDDEN_SEMANTIC_PREFIXES:
                violations.append(f"core semantic import forbidden: {relative} -> {module}")

    return violations


def main() -> int:
    violations = check()
    if violations:
        print("architecture checks failed")
        print("\n".join(f"- {item}" for item in violations))
        return 1
    print("architecture checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
