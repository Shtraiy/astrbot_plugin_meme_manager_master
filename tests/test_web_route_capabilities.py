import unittest

from mixins.web_routes import enabled_route_specs


DEFAULT_CAPABILITIES = {"core", "catalog_index"}

REMOVED_MANAGE_ROUTES = (
    "emoji",
    "emoji/<category>",
    "emoji/add/<category>",
    "emoji/delete",
    "emoji/batch_delete",
    "emoji/move",
    "emoji/batch_move",
    "emoji/batch_copy",
    "emoji/clear_all",
    "emotions",
    "category/delete",
    "category/clear",
    "category/restore",
    "category/rename",
    "category/update_description",
    "category/remove_from_config",
    "sync/status",
    "sync/config",
    "meme_image",
    "packs/default",
    "packs/uninstall",
    "community/install_official_first",
    "packs/export",
    "packs/import",
    "community/index/fetch",
    "community/index/cache",
    "community/install",
    "settings/rules",
    "settings/targets",
    "settings/backup/export",
    "settings/backup/import",
)


class WebRouteCapabilityTests(unittest.TestCase):
    def test_default_surface_registers_ordinary_catalog_routes(self):
        paths = {
            spec.path for spec in enabled_route_specs(DEFAULT_CAPABILITIES)
        }
        for route in (
            "packs",
            "packs/import/stage",
            "packs/import/apply",
            "capture/workspace",
            "capture/index",
            "capture/index/status",
            "capture/reindex",
            "capture/reindex/status",
            "capture/duplicates/ignore",
            "capture/items/dispose",
            "capture/items/ignore-all",
            "meme_image_data",
            "packs/export/status",
            "packs/export/download",
        ):
            self.assertIn(route, paths, f"default surface must register {route}")

    def test_removed_manage_routes_are_not_registered(self):
        for capabilities in (DEFAULT_CAPABILITIES, {"core"}):
            paths = {
                spec.path for spec in enabled_route_specs(capabilities)
            }
            for route in REMOVED_MANAGE_ROUTES:
                self.assertNotIn(
                    route,
                    paths,
                    f"{route} must not be registered for {capabilities}",
                )

    def test_semantic_routes_are_removed_from_every_capability_surface(self):
        paths = {
            spec.path
            for spec in enabled_route_specs(DEFAULT_CAPABILITIES | {"vector_semantic"})
        }
        self.assertFalse(
            any(path == "meme_image_semantic" or path.startswith("semantic/") for path in paths)
        )

    def test_core_routes_always_registered(self):
        paths = {
            spec.path for spec in enabled_route_specs({"core"})
        }
        for route in (
            "packs",
            "packs/<pack_id>",
            "packs/export/status",
            "meme_image_data",
        ):
            self.assertIn(route, paths)

    def test_route_specs_are_frozen_and_typed(self):
        spec = enabled_route_specs(DEFAULT_CAPABILITIES)[0]
        self.assertIsInstance(spec.path, str)
        self.assertIsInstance(spec.handler_name, str)
        self.assertIsInstance(spec.methods, tuple)
        self.assertIsInstance(spec.description, str)
        with self.assertRaises(AttributeError):
            spec.path = "changed"


if __name__ == "__main__":
    unittest.main()
