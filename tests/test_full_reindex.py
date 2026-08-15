import asyncio
import tempfile
import unittest
from pathlib import Path

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

from meme_manager_master.capture import CaptureMixin
from meme_manager_master.indexing import full_reindex_entry_is_current
from meme_manager_master.runtime_config import PluginConfig
from meme_manager_master.storage import MemeStore


class FullReindexContractTests(unittest.TestCase):
    def test_full_reindex_requires_current_v4_sha_primary_and_semantic_fields(self):
        complete = {
            "indexed": True,
            "index_version": 4,
            "index_prompt_version": "library-semantic-primary-v1",
            "index_provider_id": "old-provider",
            "sha256": "a" * 64,
            "primary_category": "尴尬",
            "primary_category_status": "ready",
            "semantic_summary": "承认自己说错话，表情窘迫。",
            "visible_text": "但是不是你自己发的吗",
            "text_meaning": "带自嘲的反问。",
            "use_cases": ["承认口误"],
            "avoid_cases": ["真诚赞同"],
            "classification_confidence": 0.92,
            "semantic_tags": ["认错"],
        }

        self.assertTrue(
            full_reindex_entry_is_current(
                complete,
                "a" * 64,
                index_version=4,
                prompt_version="library-semantic-primary-v1",
            )
        )
        self.assertFalse(
            full_reindex_entry_is_current(
                {**complete, "index_version": 3},
                "a" * 64,
                index_version=4,
                prompt_version="library-semantic-primary-v1",
            )
        )
        self.assertFalse(
            full_reindex_entry_is_current(
                {key: value for key, value in complete.items() if key != "text_meaning"},
                "a" * 64,
                index_version=4,
                prompt_version="library-semantic-primary-v1",
            )
        )
        self.assertFalse(
            full_reindex_entry_is_current(
                {**complete, "primary_category": "工作"},
                "a" * 64,
                index_version=4,
                prompt_version="library-semantic-primary-v1",
            )
        )


class FullReindexRuntimeTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _make_instance(store, *, batch_size=6, provider_id="provider"):
        instance = CaptureMixin.__new__(CaptureMixin)
        instance.store = store
        instance.runtime_config = PluginConfig.from_mapping(
            {
                "library_index_provider_id": provider_id,
                "library_index_batch_size": batch_size,
            }
        )
        instance._library_lock = asyncio.Lock()
        instance._save_lock = asyncio.Lock()
        instance._library_retry_key = None
        instance._library_retry_at = 0.0
        instance._library_completed_key = None
        return instance

    @staticmethod
    def _state():
        return {
            "status": "idle",
            "processed": 0,
            "total": 0,
            "classified": 0,
            "skipped": 0,
            "reindexed": 0,
            "errors": 0,
            "message": "尚未开始全量语义重索引",
        }

    @staticmethod
    def _complete_entry(filename, digest):
        return {
            "id": Path(filename).stem,
            "filename": filename,
            "indexed": True,
            "index_version": 4,
            "index_prompt_version": "library-semantic-primary-v1",
            "index_provider_id": "old-provider",
            "sha256": digest,
            "primary_category": "尴尬",
            "primary_category_status": "ready",
            "semantic_summary": "承认自己说错话，表情窘迫。",
            "visible_text": "但是不是你自己发的吗",
            "text_meaning": "带自嘲的反问。",
            "use_cases": ["承认口误"],
            "avoid_cases": ["真诚赞同"],
            "classification_confidence": 0.92,
            "semantic_tags": ["认错"],
            "tags": ["尴尬"],
        }

    @staticmethod
    def _model_entry(path):
        return {
            "id": path.stem,
            "filename": path.name,
            "indexed": True,
            "primary_category": "尴尬",
            "primary_category_status": "ready",
            "semantic_summary": "模型重新整理后的尴尬语义。",
            "description": "尴尬反应",
            "emotion": "尴尬",
            "visible_text": "但是不是你自己发的吗",
            "text": "但是不是你自己发的吗",
            "text_meaning": "带自嘲的反问。",
            "use_cases": ["承认口误"],
            "avoid_cases": ["真诚赞同"],
            "classification_confidence": 0.91,
            "semantic_tags": ["认错"],
            "tags": ["尴尬"],
        }

    async def test_complete_v4_entry_is_skipped_and_marked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            path = store.save_image(b"complete", "尴尬", ".png", perceptual_threshold=None).path
            digest = store.image_digest(path)
            store.write_catalog(
                [self._complete_entry(path.name, digest)],
                {
                    "index_version": 4,
                    "index_prompt_version": "library-semantic-primary-v1",
                    "index_provider_id": "old-provider",
                    "classification_index_complete": True,
                },
            )
            instance = self._make_instance(store)
            state = self._state()

            async def fail_if_called(*_args, **_kwargs):
                self.fail("complete v4 entries must not call the vision model")

            instance._describe_library_batch = fail_if_called
            instance._describe_library_single = fail_if_called

            await instance._ensure_flat_library_index(
                target_store=store,
                progress_state=state,
                full_reindex=True,
            )

            entry = store.load_catalog()["items"][0]

        self.assertEqual(entry["full_reindex_status"], "skipped_current")
        self.assertGreater(entry["full_reindex_checked_at"], 0)
        self.assertEqual(state["processed"], 1)
        self.assertEqual(state["skipped"], 1)
        self.assertEqual(state["reindexed"], 0)
        self.assertEqual(state["errors"], 0)
        self.assertEqual(state["status"], "completed")

    async def test_complete_v4_entries_skip_without_a_configured_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            path = store.save_image(b"complete-without-provider", "尴尬", ".png", perceptual_threshold=None).path
            digest = store.image_digest(path)
            store.write_catalog(
                [self._complete_entry(path.name, digest)],
                {
                    "index_version": 4,
                    "index_prompt_version": "library-semantic-primary-v1",
                    "index_provider_id": "old-provider",
                    "classification_index_complete": True,
                },
            )
            instance = self._make_instance(store, provider_id="")
            state = self._state()

            async def fail_if_called(*_args, **_kwargs):
                self.fail("a complete catalog should not need a provider")

            instance._describe_library_batch = fail_if_called
            instance._describe_library_single = fail_if_called

            await instance._ensure_flat_library_index(
                target_store=store,
                progress_state=state,
                full_reindex=True,
            )

        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["skipped"], 1)
        self.assertEqual(state["errors"], 0)

    async def test_stale_entries_are_reindexed_and_marked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            paths = [
                store.save_image(f"image-{index}".encode(), "尴尬", ".png", perceptual_threshold=None).path
                for index in range(3)
            ]
            entries = [self._complete_entry(path.name, store.image_digest(path)) for path in paths]
            entries[0]["index_version"] = 3
            entries[1]["sha256"] = "b" * 64
            entries[2]["semantic_summary"] = ""
            store.write_catalog(entries, {"classification_index_complete": True})
            instance = self._make_instance(store, batch_size=3)
            state = self._state()
            called_paths = []

            async def batch(_event, batch_paths, _category, _provider):
                called_paths.extend(batch_paths)
                return {path: self._model_entry(path) for path in batch_paths}

            async def unexpected_single(*_args, **_kwargs):
                self.fail("valid batch results should not need single-image fallback")

            instance._describe_library_batch = batch
            instance._describe_library_single = unexpected_single

            await instance._ensure_flat_library_index(
                target_store=store,
                progress_state=state,
                full_reindex=True,
            )

            result_entries = store.load_catalog()["items"]

        self.assertEqual(set(called_paths), set(paths))
        self.assertEqual(state["reindexed"], 3)
        self.assertEqual(state["skipped"], 0)
        self.assertEqual(state["errors"], 0)
        self.assertTrue(all(item["full_reindex_status"] == "reindexed" for item in result_entries))

    async def test_interrupted_reindex_checkpoints_completed_batches_for_resume(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            paths = [
                store.save_image(f"image-{index}".encode(), "尴尬", ".png", perceptual_threshold=None).path
                for index in range(2)
            ]
            store.reindex_flat_catalog()
            catalog = store.load_catalog()
            store.write_catalog(
                [
                    {
                        **entry,
                        "index_version": 3,
                        "primary_category": "尴尬",
                        "primary_category_status": "ready",
                    }
                    for entry in catalog["items"]
                ],
                {"classification_index_complete": True},
            )
            current_paths = [store.memes_dir / item["filename"] for item in store.load_catalog()["items"]]
            first_path, second_path = current_paths
            instance = self._make_instance(store, batch_size=1)
            state = self._state()
            call_count = 0

            async def interrupt_after_first_batch(_event, batch_paths, _category, _provider):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return {path: self._model_entry(path) for path in batch_paths}
                raise asyncio.CancelledError()

            instance._describe_library_batch = interrupt_after_first_batch
            instance._describe_library_single = interrupt_after_first_batch

            with self.assertRaises(asyncio.CancelledError):
                await instance._ensure_flat_library_index(
                    target_store=store,
                    progress_state=state,
                    full_reindex=True,
                )

            checkpoint = {
                item["filename"]: item
                for item in store.load_catalog()["items"]
            }
            self.assertEqual(checkpoint[first_path.name]["full_reindex_status"], "reindexed")
            persisted_state = store.load_reindex_state()
            self.assertEqual(persisted_state["status"], "running")
            self.assertEqual(persisted_state["processed"], 1)
            self.assertEqual(persisted_state["reindexed"], 1)
            self.assertTrue(
                full_reindex_entry_is_current(
                    checkpoint[first_path.name],
                    store.image_digest(first_path),
                    index_version=4,
                    prompt_version="library-semantic-primary-v1",
                ),
                checkpoint[first_path.name],
            )
            self.assertFalse(checkpoint[second_path.name].get("indexed"))

            store.reindex_flat_catalog()
            after_flatten = {
                item["filename"]: item for item in store.load_catalog()["items"]
            }
            self.assertTrue(
                full_reindex_entry_is_current(
                    after_flatten[first_path.name],
                    store.image_digest(first_path),
                    index_version=4,
                    prompt_version="library-semantic-primary-v1",
                ),
                after_flatten[first_path.name],
            )

            resumed_paths = []
            resumed = self._make_instance(store, batch_size=1)
            resumed_state = self._state()

            async def resume_batch(_event, batch_paths, _category, _provider):
                resumed_paths.extend(batch_paths)
                return {path: self._model_entry(path) for path in batch_paths}

            resumed._describe_library_batch = resume_batch
            resumed._describe_library_single = resume_batch
            await resumed._ensure_flat_library_index(
                target_store=store,
                progress_state=resumed_state,
                full_reindex=True,
            )

        self.assertEqual(resumed_paths, [second_path])
        self.assertEqual(resumed_state["skipped"], 1)
        self.assertEqual(resumed_state["reindexed"], 1)
        self.assertEqual(resumed_state["errors"], 0)

    async def test_failed_reindex_marks_one_image_without_blocking_catalog_rebuild(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            path = store.save_image(b"stale", "尴尬", ".png", perceptual_threshold=None).path
            store.write_catalog(
                [{
                    **self._complete_entry(path.name, "c" * 64),
                    "index_version": 3,
                    "send_count": 4,
                }],
                {"classification_index_complete": True},
            )
            instance = self._make_instance(store, batch_size=1)
            state = self._state()

            async def fail(*_args, **_kwargs):
                raise RuntimeError("vision unavailable")

            instance._describe_library_batch = fail
            instance._describe_library_single = fail

            await instance._ensure_flat_library_index(
                target_store=store,
                progress_state=state,
                full_reindex=True,
            )

            entry = store.load_catalog()["items"][0]
            tag_index = store._load_tag_index(store.load_catalog())

        self.assertEqual(state["status"], "completed_with_errors")
        self.assertEqual(state["processed"], 1)
        self.assertEqual(state["errors"], 1)
        self.assertEqual(entry["full_reindex_status"], "error")
        self.assertFalse(entry["indexed"])
        self.assertEqual(entry["primary_category_status"], "needs_reindex")
        self.assertEqual(entry["send_count"], 4)
        self.assertNotIn(entry["id"], tag_index["by_primary_category"].get("尴尬", []))


if __name__ == "__main__":
    unittest.main()
