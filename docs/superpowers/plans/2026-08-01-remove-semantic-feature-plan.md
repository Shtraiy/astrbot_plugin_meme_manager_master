# Remove Semantic Feature Implementation Plan

Goal: Remove image semanticization, semantic review, and vector indexing while preserving ordinary catalog management, scene-based selection, capture, sending, and Companion behavior.

Architecture: Keep category/catalog and scene-decision paths. Remove semanticization from the active runtime surface: no semantic task manager, vector service, semantic WebUI routes, or semantic controls. Add one idempotent startup cleanup that deletes only legacy semantic metadata files and the plugin-level semantic index directory inside the plugin data root.

## Global Constraints

- Ordinary image files, category directories, pack manifests, selection rules, and send/capture behavior remain intact.
- Cleanup is limited to semantic_metadata.json files under packs/ and the plugin-level semantic_indexes directory.
- No FAISS import or semantic background task is required for plugin startup.
- The WebUI continues to show ordinary pack/category/image management and never requests removed semantic endpoints.
- Do not change plugin minimum-version metadata.

## Task 1: Runtime cleanup and no semantic task startup

Files: backend/semantic_cleanup.py; config.py; manager_base.py; runtime_config.py; tests/test_semantic_removal.py.

- [ ] Write a failing test for exact cleanup scope and absence of vector manager construction.
- [ ] Run the focused test and confirm the expected failure.
- [ ] Implement cleanup with an explicit packs traversal and exact semantic_indexes target; remove vector startup construction and shutdown.
- [ ] Run focused runtime tests.
- [ ] Commit: refactor: remove semantic runtime startup.

## Task 2: Remove semantic WebUI API surface

Files: mixins/web_routes.py; mixins/web_api.py; mixins/emoji_api.py; mixins/pack_api.py; mixins/semantic_api.py; tests/test_web_route_capabilities.py; tests/test_semantic_removal.py.

- [ ] Add failing tests asserting no semantic route registration and no semantic WebUI mixin wiring.
- [ ] Run focused route tests and confirm failure.
- [ ] Remove semantic route specifications, mixin wiring, status/review/edit/vector calls, and semantic import/export options while retaining ordinary catalog locks and pack operations.
- [ ] Run focused WebUI tests.
- [ ] Commit: refactor: remove semantic web APIs.

## Task 3: Remove semantic WebUI controls and page

Files: pages/a_manage/index.html; pages/a_manage/pack.js; pages/a_manage/emoji.js; pages/a_manage/script.js; pages/a_manage/state.js; pages/a_manage/style.css; pages/semantic/index.html; pages/semantic/script.js; tests/test_webui_state_contract.py.

- [ ] Add failing frontend contract tests asserting semantic markup, links, state, and endpoint calls are absent.
- [ ] Run the frontend contract tests and confirm failure.
- [ ] Remove semantic markup, state, listeners, and styles while preserving the Promise.allSettled catalog loading fix.
- [ ] Run Node syntax checks and frontend tests.
- [ ] Commit: refactor: remove semantic web controls.

## Task 4: Documentation, fixture cleanup, and full verification

Files: README.md; CONFIGURATION.md; CHANGELOG.md; requirements-semantic.txt; repository semantic fixtures if present.

- [ ] Remove FAISS/vector setup instructions and semantic WebUI links; document scene-based selection as the active path.
- [ ] Remove semantic fixture data without touching images, categories, manifests, or selection rules.
- [ ] Run the complete unittest, compileall, diff check, and targeted stale-reference searches.
- [ ] Commit: docs: remove semantic feature references.
