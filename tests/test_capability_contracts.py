import unittest

from capabilities.semantic import CapabilityStatus, LazySemanticCapability, Unavailable


class SemanticCapabilityTests(unittest.TestCase):
    def test_disabled_capability_does_not_load_optional_runtime(self):
        calls = []

        def loader():
            calls.append("loaded")
            return object()

        capability = LazySemanticCapability(loader=loader, enabled=False)
        self.assertEqual(capability.status(), CapabilityStatus("semantic", False, "disabled"))
        self.assertIsInstance(capability.query("hello"), Unavailable)
        self.assertEqual(calls, [])

    def test_loader_failure_is_reported_without_breaking_core_path(self):
        capability = LazySemanticCapability(
            loader=lambda: (_ for _ in ()).throw(RuntimeError("missing dependency")),
            enabled=True,
        )
        self.assertEqual(capability.status().available, False)
        result = capability.query("hello")
        self.assertIsInstance(result, Unavailable)
        self.assertIn("missing dependency", result.reason)

    def test_loaded_provider_receives_query(self):
        class Provider:
            def query(self, request):
                return {"request": request, "ok": True}

        capability = LazySemanticCapability(loader=lambda: Provider(), enabled=True)
        self.assertEqual(capability.query("hello"), {"request": "hello", "ok": True})
        self.assertTrue(capability.status().available)


if __name__ == "__main__":
    unittest.main()
