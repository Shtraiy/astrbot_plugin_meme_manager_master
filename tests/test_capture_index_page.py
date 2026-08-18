import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SEMANTIC_PAGE = ROOT / "pages" / "a_manage" / "semantic"
ASSET_VERSION = "20260818-workspace-layout-1"


class CaptureIndexPageTests(unittest.TestCase):
    def test_workspace_uses_overview_sections(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="workspace-header"', source)
        self.assertIn('id="capture-catalog-panel"', source)
        self.assertIn('id="capture-items"', source)

    def test_workspace_uses_one_emoji_grid_with_view_filters(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn('id="capture-items"', source)
        self.assertIn('id="capture-view-filters"', source)
        self.assertIn('data-capture-view="classified"', source)
        self.assertIn('data-capture-view="unclassified"', source)
        self.assertNotIn('id="capture-v4-health"', source)
        self.assertNotIn('id="capture-attention-items"', source)
        self.assertNotIn('id="capture-indexed-items"', source)
        self.assertNotIn('id="capture-pending-items"', source)
        self.assertIn("currentView", script)
        self.assertIn("params.view = currentView", script)

    def test_workspace_cache_version_is_polished(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        self.assertIn("20260818-workspace-layout-1", source)

    def test_capture_index_page_is_available(self):
        page = SEMANTIC_PAGE / "index.html"
        self.assertTrue(page.is_file())
        source = page.read_text(encoding="utf-8")
        self.assertIn("表情索引", source)
        self.assertIn("capture-items", source)
        self.assertIn("capture-reindex-button", source)
        self.assertIn("全量语义重索引", source)
        self.assertIn("全部表情", source)
        self.assertNotIn("capture-dispose-selected-button", source)
        self.assertIn("capture-category-filters", source)
        self.assertIn("capture-view-filters", source)

    def test_capture_index_page_has_the_vertical_workspace_contract(self):
        page = SEMANTIC_PAGE / "index.html"
        source = page.read_text(encoding="utf-8")
        script = page.with_name("script.js").read_text(encoding="utf-8")
        style = page.with_name("style.css").read_text(encoding="utf-8")
        self.assertIn("capture-reindex-button", source)
        self.assertIn("全量语义重索引", source)
        self.assertIn("capture-category-filters", source)
        self.assertIn("capture-view-filters", source)
        self.assertIn('size: "preview"', script)
        self.assertIn('apiPost("capture/reindex"', script)
        self.assertIn('apiPost("capture/items/dispose"', script)
        self.assertIn('apiPost("capture/items/ignore-all"', script)
        self.assertIn('apiPost("capture/index"', script)
        self.assertIn(".catalog-panel .cards", style)

    def test_selection_index_and_pack_wide_ignore_controls_exist(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn('id="capture-select-index-button"', source)
        self.assertIn('id="capture-ignore-all-button"', source)
        self.assertIn("indexSelectedItems", script)
        self.assertIn("ignoreAllCaptureItems", script)
        self.assertIn('kind === "pending"', script)
        self.assertIn('item.kind !== "indexed"', script)

    def test_single_catalog_places_view_filters_before_items_and_pagination(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        view_filters = source.index('id="capture-view-filters"')
        categories = source.index('id="capture-category-filters"')
        items = source.index('id="capture-items"')
        pagination = source.index('id="capture-pagination"')
        self.assertLess(view_filters, categories)
        self.assertLess(categories, items)
        self.assertLess(items, pagination)
        self.assertNotIn('id="capture-v4-health"', source)

    def test_catalog_uses_one_card_grid_for_all_views(self):
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        self.assertIn(".catalog-panel .cards", style)
        self.assertNotIn(".attention-items", style)

    def test_reindex_button_is_not_silently_disabled_by_model_index_state(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertNotIn(
            'reindexButton.disabled = state.status === "running";',
            script,
        )
        self.assertIn("正在进行全量语义重索引", script)

    def test_reindex_progress_contract_exists(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        self.assertIn("capture-reindex-progress", source)
        self.assertIn("capture-reindex-progress-bar", source)
        self.assertIn('apiGet("capture/reindex/status"', script)
        self.assertIn("setTimeout", script)
        self.assertIn("reindex-progress", style)

    def test_full_reindex_progress_contract_includes_semantic_counters(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn("skipped", script)
        self.assertIn("reindexed", script)
        self.assertIn("completed_with_errors", script)

    def test_reindex_restores_the_requested_pack_after_page_navigation(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn("preferredPackId", script)
        self.assertIn("window.location?.search", script)

    def test_reindex_progress_hidden_state_is_not_rendered_by_display_rule(self):
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        self.assertIn(".reindex-progress[hidden]", style)

    def test_index_polling_does_not_rebuild_thumbnail_cards(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn('apiGet("capture/index/status"', script)
        self.assertIn("const data = await loadWorkspace();", script)

    def test_reindex_progress_is_outside_the_resource_toolbar(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        toolbar_end = source.index("</section>", source.index('class="toolbar panel"'))
        progress_row = source.index('class="capture-progress-row"')
        self.assertGreater(progress_row, toolbar_end)

    def test_manual_index_polls_until_the_backend_task_finishes(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn('apiPost("capture/index"', script)
        self.assertIn("pollIndexStatus", script)
        self.assertIn('apiGet("capture/index/status"', script)
        self.assertIn("const data = await loadWorkspace();", script)
        self.assertIn("createPollingController", script)
        self.assertIn("indexPolling.schedule", script)
        self.assertIn("setTaskBusy", script)
        self.assertIn('["queued", "running"]', script)

    def test_progress_page_assets_use_a_cache_busting_script_version(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        self.assertRegex(source, r'<script type="module" src="\./script\.js\?v=[^"]+"')

    def test_capture_index_page_uses_non_semantic_capture_routes(self):
        source = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn('"capture/workspace"', source)
        self.assertIn('"capture/index"', source)
        self.assertNotIn('"semantic/capture-workspace"', source)
        self.assertNotIn('"semantic/capture-index"', source)

    def test_index_cards_have_pack_local_delete_actions(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn("disposeCaptureItems", script)
        self.assertIn('apiPost("capture/items/dispose"', script)
        self.assertNotIn('apiPost("emoji/delete"', script)
        self.assertIn('className = "card-preview"', script)
        self.assertIn('className = "card-delete"', script)
        self.assertIn('document.createElement("article")', script)
        self.assertNotIn('const card = document.createElement("button")', script)

    def test_contextual_batch_controls_exist(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn("capture-selection-mode-button", source)
        self.assertIn("capture-select-indexed-page-button", source)
        self.assertIn("capture-select-pending-button", source)
        self.assertIn("capture-clear-selection-button", source)
        self.assertNotIn("capture-dispose-selected-button", source)
        self.assertIn("selectedItems", script)
        self.assertIn("toggleVisibleSelection", script)
        self.assertIn("disposalItemsForAction", script)
        self.assertNotIn("disposeSelectedItems", script)
        self.assertIn('if (item.kind !== "indexed") return [item];', script)

    def test_pagination_and_unique_tag_card_contract_exists(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        self.assertIn("capture-pagination", source)
        self.assertIn("capture-pagination-prev", source)
        self.assertIn("capture-pagination-next", source)
        self.assertIn("pagination", script)
        self.assertIn('params.page = currentPage', script)
        self.assertIn("card-tags", script)
        self.assertIn("card.selected", style)
        self.assertNotIn("card-select", script)
        self.assertNotIn("card-select", style)
        self.assertIn("max-height", style)

    def test_mutations_refetch_and_rerender_cards_to_fill_current_page(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertNotIn("removeCardsForItems", script)
        self.assertNotIn("loadWorkspace({ renderItems: false })", script)
        self.assertIn("await loadWorkspace({ preserveSelection: true })", script)

    def test_batch_disposal_deduplicates_items_before_posting(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn("new Map", script)
        self.assertIn('apiPost("capture/items/dispose"', script)

    def test_interaction_assets_use_a_fresh_cache_busting_version(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        self.assertIn(f"style.css?v={ASSET_VERSION}", source)
        self.assertIn(f"script.js?v={ASSET_VERSION}", source)
        self.assertNotIn("20260803-", source)

    def test_thumbnail_cache_contract_and_asset_version_match(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn("THUMBNAIL_CACHE_MAX_ENTRIES = 512", script)
        self.assertIn("THUMBNAIL_CACHE_MAX_BYTES = 64 * 1024 * 1024", script)
        self.assertIn("dataUrl.length * 2", script)
        self.assertIn("thumbnailRequests", script)
        self.assertIn("if (shouldClearThumbnails) clearThumbnailCache();", script)
        self.assertIn("evictThumbnailFile", script)
        self.assertIn('if (item.kind !== "duplicate")', script)
        self.assertIn('size: "original"', script)
        self.assertIn(f"script.js?v={ASSET_VERSION}", source)

    def test_delete_control_is_a_corner_icon_with_success_feedback(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        self.assertIn("card-delete-icon", script)
        self.assertIn('button?.setAttribute("aria-busy", "true")', script)
        self.assertIn("统一处理完成", script)
        self.assertIn("position: relative", style)
        self.assertIn(".card-actions { position: absolute", style)
        self.assertIn(".card-delete-icon", style)
        self.assertIn("@media (prefers-reduced-motion: reduce)", style)

    def test_index_actions_use_an_embedded_confirmation_dialog(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn("capture-confirm-mask", source)
        self.assertIn("capture-confirm-cancel", source)
        self.assertIn("capture-confirm-confirm", source)
        self.assertIn("requestConfirmation", script)
        self.assertNotIn("window.confirm(", script)

    def test_reindex_error_state_stops_polling_without_refreshing_workspace(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn('if (state.status === "error")', script)
        self.assertIn('showError(new Error(state.message', script)
        self.assertIn('["completed", "completed_with_errors"].includes(state.status)', script)

    def test_index_stats_render_dynamic_values_without_inner_html(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertNotIn("item.innerHTML", script)
        self.assertIn("itemsCount.textContent", script)

    def test_catalog_view_filter_contract_exists(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        self.assertIn('id="capture-view-filters"', source)
        self.assertIn('data-capture-view="classified"', source)
        self.assertIn('data-capture-view="unclassified"', source)
        self.assertIn('aria-pressed="true"', source)
        self.assertIn(".catalog-panel .cards", style)
        self.assertIn(f"style.css?v={ASSET_VERSION}", source)
        self.assertIn(f"script.js?v={ASSET_VERSION}", source)

    def test_workspace_typography_uses_a_consistent_compact_scale(self):
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        self.assertIn(
            'font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", system-ui, sans-serif;',
            style,
        )
        self.assertIn("h1 { font-size: clamp(28px, 4vw, 44px);", style)
        self.assertIn("font-variant-numeric: tabular-nums;", style)

    def test_workspace_removes_repeated_health_detail_and_hides_empty_import_preview(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        self.assertNotIn('id="capture-v4-health-detail"', source)
        self.assertNotIn("v4DetailNodes", script)
        self.assertIn(".transfer-import-preview[hidden]", style)

    def test_catalog_view_runtime_contract_exists(self):
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn("setView", script)
        self.assertIn("currentView", script)
        self.assertIn("params.view = currentView", script)
        self.assertIn("button.dataset.captureView", script)
        self.assertNotIn("renderV4Health", script)
        self.assertNotIn("currentV4Filter", script)
        self.assertNotIn("summary.innerHTML", script)

    def test_export_import_controls_use_transfer_routes(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        script = (SEMANTIC_PAGE / "script.js").read_text(encoding="utf-8")
        self.assertIn("capture-export-button", source)
        self.assertIn("capture-import-button", source)
        self.assertIn('apiGet("packs/export/status"', script)
        self.assertIn('download("packs/export/download"', script)
        self.assertIn('upload("packs/import/stage"', script)
        self.assertIn('apiPost("packs/import/apply"', script)

    def test_workspace_centers_heading_and_places_transfer_controls_below_it(self):
        source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        toolbar_start = source.index('<section class="toolbar panel"')
        toolbar_end = source.index("</section>", toolbar_start)
        transfer_start = source.index('id="capture-transfer-panel"')
        transfer_end = source.index("</section>", transfer_start)
        self.assertIn('class="toolbar-pack-control"', source)
        self.assertIn('class="toolbar-actions"', source)
        self.assertIn('class="export-mode-control"', source)
        self.assertIn('id="capture-export-backup"', source[toolbar_start:toolbar_end])
        self.assertNotIn('id="capture-export-backup"', source[transfer_start:transfer_end])
        self.assertNotIn('class="transfer-export-row"', source)
        self.assertRegex(style, r"\.workspace-header\s*\{[^}]*display:\s*grid;")
        self.assertRegex(style, r"\.page-header-copy\s*\{[^}]*text-align:\s*center;")

    def test_transfer_export_copy_uses_consistent_typography(self):
        style = (SEMANTIC_PAGE / "style.css").read_text(encoding="utf-8")
        self.assertRegex(
            style,
            r"\.transfer-option,\s*\.transfer-hint\s*\{[^}]*font-family:\s*inherit;",
        )
        self.assertRegex(style, r"\.transfer-option\s*\{[^}]*line-height:\s*1\.4;")
        self.assertRegex(style, r"\.transfer-hint\s*\{[^}]*font-size:\s*12px;")


if __name__ == "__main__":
    unittest.main()
