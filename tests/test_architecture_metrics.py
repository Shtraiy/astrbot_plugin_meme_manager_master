import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ArchitectureMetricsTests(unittest.TestCase):
    def test_metrics_report_identifies_large_modules(self):
        result = subprocess.run(
            [sys.executable, "scripts/architecture_metrics.py", "--top", "3"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("semantic_storage.py", result.stdout)
        self.assertIn("fanout", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
