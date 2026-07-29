import ast
from pathlib import Path
import unittest

from collector import drop_empty_text_components


class _Text:
    def __init__(self, text):
        self.text = text


class _Image:
    pass


class LogNoiseRegressionTests(unittest.TestCase):
    def test_blank_text_components_are_removed_but_images_are_preserved(self):
        image = _Image()
        result = drop_empty_text_components([_Text("  "), image, _Text("正文")])

        self.assertEqual(len(result), 2)
        self.assertIs(result[0], image)
        self.assertEqual(result[-1].text, "正文")

    def test_webui_success_wrapper_has_no_per_request_info_logging(self):
        source_path = Path(__file__).parents[1] / "mixins" / "web_api.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        wrapper = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "logged_handler"
        )

        info_calls = []
        for node in ast.walk(wrapper):
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "info"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger"
            ):
                info_calls.append(node)
        self.assertEqual(info_calls, [])


if __name__ == "__main__":
    unittest.main()
