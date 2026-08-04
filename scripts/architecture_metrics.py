"""Report code-size and dependency metrics without third-party tooling."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _internal_modules() -> set[str]:
    return {
        _module_name(path)
        for path in ROOT.rglob("*.py")
        if not {".git", ".worktrees", "__pycache__", "tests"}.intersection(path.parts)
    }


def _imports(module: str, tree: ast.AST, known: set[str]) -> set[str]:
    dependencies: set[str] = set()
    parts = module.split(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in known:
                    dependencies.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = parts[:-node.level]
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            if target in known:
                dependencies.add(target)
            for alias in node.names:
                candidate = f"{target}.{alias.name}" if target else alias.name
                if candidate in known:
                    dependencies.add(candidate)
    return dependencies


def collect() -> list[dict[str, int | str]]:
    known = _internal_modules()
    rows: list[dict[str, int | str]] = []
    for path in ROOT.rglob("*.py"):
        if {".git", ".worktrees", "__pycache__", "tests"}.intersection(path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        long_functions = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and getattr(node, "end_lineno", node.lineno) - node.lineno + 1 > 80
        )
        rows.append(
            {
                "file": str(path.relative_to(ROOT)),
                "lines": len(path.read_text(encoding="utf-8").splitlines()),
                "fanout": len(_imports(_module_name(path), tree, known)),
                "long_functions": long_functions,
            }
        )
    return sorted(rows, key=lambda row: (-int(row["lines"]), str(row["file"])))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()
    print("file | lines | fanout | long_functions")
    print("--- | ---: | ---: | ---:")
    for row in collect()[: max(1, args.top)]:
        print(f"{row['file']} | {row['lines']} | {row['fanout']} | {row['long_functions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
