# Disable Retired Semantic Startup Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop AstrBot v4.26.8 from registering and invoking the retired unbound semantic-index startup hook.

**Architecture:** Treat the retired automatic vector rebuild as a removed startup integration, while preserving the independently invoked manual semantic-index APIs. Add a registration-behavior regression test, remove the decorator first to establish green, then delete the newly unreachable scheduling chain as a refactor.

**Tech Stack:** Python 3, `unittest`, Python AST/descriptor execution, AstrBot v4.26.8 plugin lifecycle conventions.

## Global Constraints

- Keep `self.semantic_enabled = False`.
- Do not register a replacement `on_astrbot_loaded` hook.
- Preserve manual `semantic_task_manager.rebuild_index()` Web API behavior.
- Preserve `SemanticTaskManager.close()` during plugin termination.
- Do not change message sending, scene analysis, collection, or pack selection code.
- Do not create a git commit automatically; this workspace exposes `.git` read-only and the user requested the source repair rather than repository integration.

---

### Task 1: Remove the retired startup lifecycle registration

**Files:**
- Create: `tests/test_lifecycle_hook_registration.py`
- Modify: `manager_base.py`

**Interfaces:**
- Consumes: AstrBot lifecycle decorators expressed as `@filter.on_astrbot_loaded()`.
- Produces: A plugin module set that registers zero `on_astrbot_loaded` handlers.

- [x] **Step 1: Write the failing registration-behavior test**

```python
import ast
import copy
import unittest
from pathlib import Path


class _RecordingFilter:
    def __init__(self):
        self.handlers = []

    def on_astrbot_loaded(self):
        def decorator(handler):
            self.handlers.append(handler)
            return handler

        return decorator


def _registered_startup_handlers(path: Path, module_name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        methods = []
        for statement in node.body:
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            startup_decorators = [
                decorator
                for decorator in statement.decorator_list
                if isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "on_astrbot_loaded"
            ]
            if not startup_decorators:
                continue
            method = copy.deepcopy(statement)
            method.body = [ast.Pass()]
            method.decorator_list = startup_decorators
            methods.append(method)
        if methods:
            classes.append(
                ast.ClassDef(
                    name=node.name,
                    bases=[],
                    keywords=[],
                    body=methods,
                    decorator_list=[],
                )
            )

    recording_filter = _RecordingFilter()
    namespace = {"__name__": module_name, "filter": recording_filter}
    registration_module = ast.fix_missing_locations(
        ast.Module(body=classes, type_ignores=[])
    )
    exec(compile(registration_module, str(path), "exec"), namespace)
    return recording_filter.handlers


class LifecycleHookRegistrationTests(unittest.TestCase):
    def test_plugin_registers_no_astrbot_loaded_handlers(self):
        root = Path(__file__).parents[1]
        handlers = []
        handlers.extend(
            _registered_startup_handlers(
                root / "manager_base.py",
                "meme_manager_master.manager_base",
            )
        )
        handlers.extend(
            _registered_startup_handlers(
                root / "main.py",
                "meme_manager_master.main",
            )
        )

        self.assertEqual(handlers, [])


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m unittest tests.test_lifecycle_hook_registration -v
```

Expected: FAIL because `manager_base.py` registers one
`_schedule_semantic_initial_rebuild` handler.

- [x] **Step 3: Remove only the lifecycle decorator**

Delete `@filter.on_astrbot_loaded()` from
`MemeSender._schedule_semantic_initial_rebuild`, leaving the method temporarily
in place.

- [x] **Step 4: Run the test and verify GREEN**

Run:

```powershell
python -m unittest tests.test_lifecycle_hook_registration -v
```

Expected: PASS with one test.

- [x] **Step 5: Refactor the unreachable automatic-startup chain**

Delete:

```python
import asyncio
self._semantic_initial_rebuild_task = None
async def _schedule_semantic_initial_rebuild(...)
async def _auto_rebuild_initial_pack(...)
```

Also delete the `_semantic_initial_rebuild_task` cancellation block from
`MemeSender.terminate()`. Keep `semantic_task_manager.close()` and the manual
Web API rebuild path unchanged.

- [x] **Step 6: Re-run the targeted test after refactoring**

Run:

```powershell
python -m unittest tests.test_lifecycle_hook_registration -v
```

Expected: PASS with one test.

- [x] **Step 7: Run complete verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
git diff --check
rg -n "on_astrbot_loaded|_schedule_semantic_initial_rebuild|_semantic_initial_rebuild_task|_auto_rebuild_initial_pack" manager_base.py main.py
```

Expected:

- All tests pass.
- Compilation exits with code 0.
- `git diff --check` exits with code 0.
- `rg` finds no retired startup hook or task symbols in production plugin source.
