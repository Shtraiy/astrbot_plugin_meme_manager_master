import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "a_manage"


class CaptureIndexPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (PAGE / "index.html").read_text(encoding="utf-8")
        cls.script = (PAGE / "capture-index.js").read_text(encoding="utf-8")
        cls.style = (PAGE / "capture-index.css").read_text(encoding="utf-8")

    def test_capture_index_view_is_embedded_in_the_single_shell(self):
        self.assertIn('data-view="index"', self.html)
        for identifier in (
            "capture-indexed-items",
            "capture-pending-items",
            "capture-reindex-button",
            "capture-ignore-duplicates-button",
            "capture-category-filters",
            "sections-stack",
        ):
            self.assertIn(identifier, self.html)

    def test_reindex_and_index_progress_contract_is_preserved(self):
        self.assertIn("capture-reindex-progress", self.html)
        self.assertIn("capture-reindex-progress-bar", self.html)
        self.assertIn('apiGet("capture/reindex/status"', self.script)
        self.assertIn('apiGet("capture/index/status"', self.script)
        self.assertIn('apiPost("capture/reindex"', self.script)
        self.assertIn('apiPost("capture/index"', self.script)
        self.assertIn("setTimeout", self.script)
        self.assertIn(".reindex-progress[hidden]", self.style)
        self.assertNotIn('reindexButton.disabled = state.status === "running";', self.script)

    def test_capture_routes_do_not_use_retired_semantic_endpoints(self):
        self.assertIn('"capture/workspace"', self.script)
        self.assertIn('"capture/index"', self.script)
        self.assertNotIn('"semantic/capture-workspace"', self.script)
        self.assertNotIn('"semantic/capture-index"', self.script)

    def test_cards_keep_preview_delete_and_duplicate_ignore_actions(self):
        self.assertIn('size: "preview"', self.script)
        self.assertIn('size: "original"', self.script)
        self.assertIn("deleteIndexedItem", self.script)
        self.assertIn('apiPost("emoji/delete"', self.script)
        self.assertIn('apiPost("capture/duplicates/ignore"', self.script)
        self.assertIn('className = "card-preview"', self.script)
        self.assertIn('className = "card-delete"', self.script)
        self.assertIn('className = "card-ignore"', self.script)

    def test_duplicate_batch_selection_ui_is_removed_but_ignore_all_remains(self):
        for identifier in (
            "capture-selection-mode-button",
            "capture-select-visible-duplicates-button",
            "capture-ignore-selected-button",
            "selectedDuplicateDigests",
        ):
            self.assertNotIn(identifier, self.html + self.script)
        self.assertIn("capture-ignore-duplicates-button", self.html)
        self.assertIn("new Set((digests || [])", self.script)

    def test_pagination_belongs_to_indexed_panel_and_pending_items_are_unpaginated(self):
        indexed = self.html.index('id="capture-indexed-items"')
        pagination = self.html.index('id="capture-pagination"')
        pending = self.html.index('id="capture-pending-panel"')
        self.assertLess(indexed, pagination)
        self.assertLess(pagination, pending)
        self.assertIn("params.page = currentPage", self.script)
        self.assertIn("Number(indexed.total || 0)", self.script)
        self.assertNotIn("pagination.pending.total", self.script)

    def test_duplicate_ignore_syncs_metadata_without_rebuilding_all_cards(self):
        self.assertIn("removeCardsForItems", self.script)
        self.assertIn("card.dataset.sha256", self.script)
        self.assertIn("loadWorkspace({ renderItems: false })", self.script)
        self.assertIn("renderWorkspace(data, { renderItems });", self.script)

    def test_index_actions_use_the_embedded_confirmation_dialog(self):
        self.assertIn("capture-confirm-mask", self.html)
        self.assertIn("capture-confirm-cancel", self.html)
        self.assertIn("capture-confirm-confirm", self.html)
        self.assertIn("requestConfirmation", self.script)
        self.assertNotIn("window.confirm(", self.script)

    def test_index_stats_render_dynamic_values_without_inner_html(self):
        self.assertNotIn("item.innerHTML", self.script)
        self.assertIn("valueElement.textContent", self.script)

    def test_capture_view_assets_have_fresh_cache_busters(self):
        self.assertIn("capture-index.css?v=20260811-spa-cleanup-1", self.html)
        self.assertIn("capture-index.js?v=20260811-spa-cleanup-1", self.html)


if __name__ == "__main__":
    unittest.main()
