import re
import unittest

import collector


class OutgoingScenePromptTests(unittest.TestCase):
    def test_explicit_request_is_not_required_for_proactive_send(self):
        prompt = str(getattr(collector, "OUTGOING_CATEGORY_PROMPT", ""))
        compact = re.sub(r"\s+", "", prompt)

        self.assertIn("普通聊天可以主动发送表情包", prompt)
        self.assertIn("生成自拍", prompt)
        self.assertIn("外部图片", prompt)
        self.assertIn("只输出一个 JSON", prompt)
        self.assertNotIn('{"should_send":false', compact)
        self.assertIn("recent_context", prompt)
        self.assertIn("fixed phrase", prompt)
        self.assertNotIn("explicit_request=true", prompt)


if __name__ == "__main__":
    unittest.main()
