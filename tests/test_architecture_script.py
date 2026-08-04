import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ArchitectureScriptTests(unittest.TestCase):
    def test_architecture_guard_passes_for_current_tree(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_architecture.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("architecture checks passed", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
