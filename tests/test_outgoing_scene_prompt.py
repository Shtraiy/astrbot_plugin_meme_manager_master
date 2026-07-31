import re
import unittest

import collector


class OutgoingScenePromptTests(unittest.TestCase):
    def test_explicit_request_is_not_required_for_proactive_send(self):
        prompt = str(getattr(collector, "OUTGOING_CATEGORY_PROMPT", ""))
        compact = re.sub(r"\s+", "", prompt)

        self.assertIn("普通聊天可以主动发送表情包，不需要用户明确索要", prompt)
        self.assertIn("explicit_request=false", prompt)
        self.assertIn("不代表禁止发送", prompt)
        self.assertIn("不得仅以“用户未明确索要表情包”为理由拒绝发送", prompt)
        self.assertIn("惊讶", prompt)
        self.assertNotIn('{"should_send":false', compact)
        self.assertIn("explicit_request=true", prompt)
        self.assertIn("必须发送", prompt)


if __name__ == "__main__":
    unittest.main()
