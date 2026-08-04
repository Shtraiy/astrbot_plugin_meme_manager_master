import unittest

from application.web_routes import WebRouteRegistry, WebRouteSpec


class WebRouteRegistryTests(unittest.TestCase):
    def test_register_keeps_route_order_and_rejects_duplicates(self):
        registry = WebRouteRegistry()
        first = WebRouteSpec("GET", "/packs", "list_packs")
        registry.register(first)
        self.assertEqual(registry.routes(), (first,))
        with self.assertRaises(ValueError):
            registry.register(WebRouteSpec("GET", "/packs", "other_handler"))


if __name__ == "__main__":
    unittest.main()
