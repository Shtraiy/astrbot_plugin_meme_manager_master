import unittest

from mixins.web_routes import enabled_route_specs


DEFAULT_CAPABILITIES = {"core", "catalog_index"}
class WebRouteCapabilityTests(unittest.TestCase):
    def test_default_surface_registers_ordinary_catalog_routes(self):
        paths = {
            spec.path for spec in enabled_route_specs(DEFAULT_CAPABILITIES)
        }
        for route in (
            "emoji",
            "emotions",
            "packs",
            "packs/import",
            "settings/rules",
            "capture/workspace",
            "capture/index",
        ):
            self.assertIn(route, paths, f"default surface must register {route}")

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
        for route in ("emoji", "emoji/add/<category>", "packs", "settings/rules"):
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
