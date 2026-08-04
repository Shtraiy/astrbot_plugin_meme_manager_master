import inspect
import unittest

from ports.contracts import (
    CatalogRepository,
    ImageRepository,
    PackResolver,
    SelectionService,
)


class PortContractTests(unittest.TestCase):
    def test_ports_are_runtime_independent_protocols(self):
        for port in (PackResolver, ImageRepository, CatalogRepository, SelectionService):
            self.assertTrue(getattr(port, "_is_protocol", False))
            self.assertTrue(inspect.isclass(port))

    def test_ports_expose_stable_method_names(self):
        self.assertTrue(hasattr(PackResolver, "resolve"))
        self.assertTrue(hasattr(ImageRepository, "save"))
        self.assertTrue(hasattr(CatalogRepository, "reconcile"))
        self.assertTrue(hasattr(SelectionService, "choose"))


if __name__ == "__main__":
    unittest.main()
