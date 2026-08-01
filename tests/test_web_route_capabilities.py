import unittest

from mixins.web_routes import enabled_route_specs


DEFAULT_CAPABILITIES = {"core", "catalog_index"}
VECTOR_ROUTES = (
    "semantic/start",
    "semantic/pause",
    "semantic/resume",
    "semantic/retry",
    "semantic/rebuild-index",
    "semantic/clear-local-state",
    "semantic/delete-all",
    "semantic/status",
    "semantic/save_image_and_vector",
)
CATALOG_ROUTES = (
    "semantic/capture-workspace",
    "semantic/capture-index",
    "semantic/reviews",
    "semantic/confirm_category",
    "semantic/propose_image_revision",
    "semantic/save_image",
    "semantic/restore_image_auto",
    "semantic/items",
)


class WebRouteCapabilityTests(unittest.TestCase):
    def test_default_surface_registers_catalog_routes(self):
        paths = {
            spec.path for spec in enabled_route_specs(DEFAULT_CAPABILITIES)
        }
        for route in CATALOG_ROUTES:
            self.assertIn(route, paths, f"default surface must register {route}")

    def test_default_surface_hides_vector_task_routes(self):
        paths = {
            spec.path for spec in enabled_route_specs(DEFAULT_CAPABILITIES)
        }
        for route in VECTOR_ROUTES:
            self.assertNotIn(route, paths, f"default surface must hide {route}")

    def test_vector_capability_registers_vector_routes(self):
        paths = {
            spec.path
            for spec in enabled_route_specs(DEFAULT_CAPABILITIES | {"vector_semantic"})
        }
        for route in VECTOR_ROUTES:
            self.assertIn(route, paths)

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
