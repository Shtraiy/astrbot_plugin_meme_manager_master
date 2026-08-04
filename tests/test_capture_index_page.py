import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CaptureIndexPageTests(unittest.TestCase):
    def test_capture_index_page_is_available(self):
        page = ROOT / "pages" / "semantic" / "index.html"
        self.assertTrue(page.is_file())
        source = page.read_text(encoding="utf-8")
        self.assertIn("表情索引", source)
        self.assertIn("capture-indexed-items", source)
        self.assertIn("capture-pending-items", source)
        self.assertIn("capture-reindex-button", source)
        self.assertIn("capture-category-filters", source)
        self.assertIn("sections-stack", source)

    def test_nested_capture_index_page_has_the_same_vertical_workspace_contract(self):
        page = ROOT / "pages" / "a_manage" / "semantic" / "index.html"
        source = page.read_text(encoding="utf-8")
        script = page.with_name("script.js").read_text(encoding="utf-8")
        style = page.with_name("style.css").read_text(encoding="utf-8")
        self.assertIn("capture-reindex-button", source)
        self.assertIn("capture-category-filters", source)
        self.assertIn("sections-stack", source)
        self.assertIn('size: "preview"', script)
        self.assertIn('apiPost("capture/reindex"', script)
        self.assertIn(".sections-stack", style)

    def test_reindex_button_is_not_silently_disabled_by_model_index_state(self):
        for script_path in (
            ROOT / "pages" / "semantic" / "script.js",
            ROOT / "pages" / "a_manage" / "semantic" / "script.js",
        ):
            script = script_path.read_text(encoding="utf-8")
            self.assertNotIn(
                'reindexButton.disabled = state.status === "running";',
                script,
            )
            self.assertIn("正在重索引表情文件", script)

    def test_reindex_progress_contract_exists_in_both_page_copies(self):
        for page_dir in (ROOT / "pages" / "semantic", ROOT / "pages" / "a_manage" / "semantic"):
            source = (page_dir / "index.html").read_text(encoding="utf-8")
            script = (page_dir / "script.js").read_text(encoding="utf-8")
            style = (page_dir / "style.css").read_text(encoding="utf-8")
            self.assertIn("capture-reindex-progress", source)
            self.assertIn("capture-reindex-progress-bar", source)
            self.assertIn('apiGet("capture/reindex/status"', script)
            self.assertIn("setTimeout", script)
            self.assertIn("reindex-progress", style)

    def test_reindex_progress_hidden_state_is_not_rendered_by_display_rule(self):
        for page_dir in (ROOT / "pages" / "semantic", ROOT / "pages" / "a_manage" / "semantic"):
            style = (page_dir / "style.css").read_text(encoding="utf-8")
            self.assertIn(".reindex-progress[hidden]", style)

    def test_index_polling_does_not_rebuild_thumbnail_cards(self):
        for script_path in (
            ROOT / "pages" / "semantic" / "script.js",
            ROOT / "pages" / "a_manage" / "semantic" / "script.js",
        ):
            script = script_path.read_text(encoding="utf-8")
            self.assertIn("loadWorkspace({ renderItems: false })", script)
            self.assertIn("renderItems = true", script)

    def test_reindex_progress_is_outside_the_resource_toolbar(self):
        for page_dir in (ROOT / "pages" / "semantic", ROOT / "pages" / "a_manage" / "semantic"):
            source = (page_dir / "index.html").read_text(encoding="utf-8")
            toolbar_end = source.index("</section>", source.index('class="toolbar panel"'))
            progress_row = source.index('class="capture-progress-row"')
            self.assertGreater(progress_row, toolbar_end)

    def test_manual_index_polls_until_the_backend_task_finishes(self):
        for script_path in (
            ROOT / "pages" / "semantic" / "script.js",
            ROOT / "pages" / "a_manage" / "semantic" / "script.js",
        ):
            script = script_path.read_text(encoding="utf-8")
            self.assertIn('apiPost("capture/index"', script)
            self.assertIn("pollIndexStatus", script)
            self.assertIn('setTimeout(() => void pollIndexStatus(), 500)', script)
            self.assertIn('["queued", "running"]', script)
            self.assertIn('state.message !== "没有待索引图片"', script)

    def test_progress_page_assets_use_a_cache_busting_script_version(self):
        for page_dir in (ROOT / "pages" / "semantic", ROOT / "pages" / "a_manage" / "semantic"):
            source = (page_dir / "index.html").read_text(encoding="utf-8")
            self.assertRegex(source, r'<script type="module" src="\./script\.js\?v=[^"]+"')

    def test_capture_index_page_uses_non_semantic_capture_routes(self):
        source = (ROOT / "pages" / "semantic" / "script.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('"capture/workspace"', source)
        self.assertIn('"capture/index"', source)
        self.assertNotIn('"semantic/capture-workspace"', source)
        self.assertNotIn('"semantic/capture-index"', source)

    def test_index_cards_have_pack_local_delete_actions_in_both_pages(self):
        for script_path in (
            ROOT / "pages" / "semantic" / "script.js",
            ROOT / "pages" / "a_manage" / "semantic" / "script.js",
        ):
            script = script_path.read_text(encoding="utf-8")
            self.assertIn("deleteIndexedItem", script)
            self.assertIn('apiPost("emoji/delete"', script)
            self.assertIn("managed_pack_id: packSelect.value", script)
            self.assertIn('className = "card-preview"', script)
            self.assertIn('className = "card-delete"', script)
            self.assertIn('document.createElement("article")', script)
            self.assertNotIn('const card = document.createElement("button")', script)

    def test_interaction_assets_use_a_fresh_cache_busting_version(self):
        for page_dir in (ROOT / "pages" / "semantic", ROOT / "pages" / "a_manage" / "semantic"):
            source = (page_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('style.css?v=20260804-capture-index-2', source)
            self.assertIn('script.js?v=20260804-capture-index-2', source)
            self.assertNotIn("20260803-", source)

    def test_delete_control_is_a_corner_icon_with_success_feedback(self):
        for page_dir in (ROOT / "pages" / "semantic", ROOT / "pages" / "a_manage" / "semantic"):
            script = (page_dir / "script.js").read_text(encoding="utf-8")
            style = (page_dir / "style.css").read_text(encoding="utf-8")
            self.assertIn("card-delete-icon", script)
            self.assertIn('button.setAttribute("aria-busy", "true")', script)
            self.assertIn("已删除", script)
            self.assertIn("position: relative", style)
            self.assertIn(".card-actions { position: absolute", style)
            self.assertIn(".card-delete-icon", style)
            self.assertIn("@media (prefers-reduced-motion: reduce)", style)

    def test_index_actions_use_an_embedded_confirmation_dialog(self):
        for page_dir in (ROOT / "pages" / "semantic", ROOT / "pages" / "a_manage" / "semantic"):
            source = (page_dir / "index.html").read_text(encoding="utf-8")
            script = (page_dir / "script.js").read_text(encoding="utf-8")
            self.assertIn("capture-confirm-mask", source)
            self.assertIn("capture-confirm-cancel", source)
            self.assertIn("capture-confirm-confirm", source)
            self.assertIn("requestConfirmation", script)
            self.assertNotIn("window.confirm(", script)

    def test_reindex_error_state_stops_polling_without_refreshing_workspace(self):
        for script_path in (
            ROOT / "pages" / "semantic" / "script.js",
            ROOT / "pages" / "a_manage" / "semantic" / "script.js",
        ):
            script = script_path.read_text(encoding="utf-8")
            self.assertIn('if (state.status === "error")', script)
            self.assertIn('showError(new Error(state.message', script)
            self.assertIn('if (state.status === "completed")', script)

    def test_index_stats_render_dynamic_values_without_inner_html(self):
        for script_path in (
            ROOT / "pages" / "semantic" / "script.js",
            ROOT / "pages" / "a_manage" / "semantic" / "script.js",
        ):
            script = script_path.read_text(encoding="utf-8")
            self.assertNotIn("item.innerHTML", script)
            self.assertIn("valueElement.textContent", script)


if __name__ == "__main__":
    unittest.main()
