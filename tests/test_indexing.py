import unittest
from pathlib import Path

from indexing import catalog_needs_write, normalize_library_results


class LibraryIndexingTests(unittest.TestCase):
    def setUp(self):
        self.paths = [Path("see_0001.jpg"), Path("see_0002.gif")]

    def test_results_can_be_matched_by_filename(self):
        result = normalize_library_results(
            [
                {"id": "see_0002.gif", "emotion": "surprised"},
                {"id": "see_0001", "emotion": "shy"},
            ],
            self.paths,
        )

        self.assertEqual(result[self.paths[0]]["emotion"], "shy")
        self.assertEqual(result[self.paths[1]]["emotion"], "surprised")
        self.assertTrue(result[self.paths[0]]["indexed"])

    def test_complete_results_without_ids_are_matched_by_order(self):
        result = normalize_library_results(
            [{"emotion": "shy"}, {"emotion": "happy"}],
            self.paths,
        )

        self.assertEqual(result[self.paths[0]]["emotion"], "shy")
        self.assertEqual(result[self.paths[1]]["emotion"], "happy")

    def test_one_based_image_ids_are_supported(self):
        result = normalize_library_results(
            [{"id": "image_2", "emotion": "happy"}, {"id": "image_1", "emotion": "shy"}],
            self.paths,
        )

        self.assertEqual(result[self.paths[0]]["emotion"], "shy")
        self.assertEqual(result[self.paths[1]]["emotion"], "happy")

    def test_id_keyed_object_results_are_supported(self):
        result = normalize_library_results(
            {
                "image_0": {"emotion": "shy"},
                "image_1": {"emotion": "happy"},
            },
            self.paths,
        )

        self.assertEqual(result[self.paths[0]]["emotion"], "shy")
        self.assertEqual(result[self.paths[1]]["emotion"], "happy")

    def test_partial_results_are_not_guessed_for_other_images(self):
        result = normalize_library_results(
            [{"id": "image_0", "emotion": "happy"}],
            self.paths,
        )

        self.assertEqual(set(result), {self.paths[0]})
        self.assertEqual(result[self.paths[0]]["emotion"], "happy")

    def test_tags_are_normalized_and_text_is_bounded(self):
        result = normalize_library_results(
            [{"id": "image_0", "tags": "a, b", "description": "x" * 200}],
            [self.paths[0]],
        )

        self.assertEqual(result[self.paths[0]]["tags"], ["a", "b"])
        self.assertEqual(len(result[self.paths[0]]["description"]), 120)

    def test_unchanged_catalog_does_not_need_a_write(self):
        entries = [{"filename": "see_0001.jpg", "indexed": True}]
        metadata = {"index_version": 3}

        self.assertFalse(
            catalog_needs_write(
                {"items": entries, "index_version": 3, "updated_at": 1},
                entries,
                metadata,
            )
        )
        self.assertTrue(
            catalog_needs_write(
                {"items": entries, "index_version": 2}, entries, metadata
            )
        )


if __name__ == "__main__":
    unittest.main()
