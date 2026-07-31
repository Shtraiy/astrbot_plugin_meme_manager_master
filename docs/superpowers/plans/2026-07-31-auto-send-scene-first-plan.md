# 情景优先自动发送 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每条启用自动发送的正常回复先经过情景模型判断，再由冷却时间和自动发送概率控制最终发送。

**Architecture:** 保留现有 `CaptureMixin._choose_outgoing_meme_from_index()` 作为唯一情景判断入口，只调整 `CaptureMixin.on_decorating_result()` 中“情景选择、冷却、概率、抢占发送锁”的顺序。明确索取表情包的强制路径不变。

**Tech Stack:** Python 3.12、`unittest`、AstrBot 事件钩子、现有 LLM JSON 解析器。

## Global Constraints

- 每条启用自动发送的正常回复都先经过情景模型判断。
- 情景模型判断“不适合发送”时不发送表情包。
- 情景模型判断“适合发送”后才检查冷却和自动发送概率。
- 明确索取表情包继续绕过自动发送概率。
- 不改变表情包偷取、索引、分类和 WebUI 逻辑。

---

### Task 1: 添加情景优先顺序回归测试

**Files:**
- Modify: `tests/test_explicit_meme_dispatch.py`
- Test: `tests/test_explicit_meme_dispatch.py`

**Interfaces:**
- Consumes: `capture.py` 中 `CaptureMixin.on_decorating_result()` 的源代码。
- Produces: 一个防止概率判断重新移动到情景判断之前的回归约束。

- [ ] **Step 1: Write the failing test**

在 `ExplicitMemeDispatchTests` 中加入：

```python
    def test_scene_judgment_runs_before_auto_send_probability_gate(self):
        source = (ROOT / "capture.py").read_text(encoding="utf-8")
        decorating = source.index("async def on_decorating_result")
        scene_call = source.index(
            "_choose_outgoing_meme_from_index(", decorating
        )
        probability_gate = source.index(
            "probability = self._float_config(\"auto_send_probability\"",
            decorating,
        )
        self.assertLess(scene_call, probability_gate)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_explicit_meme_dispatch.ExplicitMemeDispatchTests.test_scene_judgment_runs_before_auto_send_probability_gate -v
```

Expected: FAIL because the current method checks `auto_send_probability` before calling `_choose_outgoing_meme_from_index()`.

### Task 2: 调整自动发送流程顺序

**Files:**
- Modify: `capture.py:885-978`
- Test: `tests/test_explicit_meme_dispatch.py`

**Interfaces:**
- Consumes: `_choose_outgoing_meme_from_index(event, response_text, force_send, preferred_categories)`。
- Produces: 情景判断先行、概率和冷却后置的自动发送流程。

- [ ] **Step 1: Write minimal implementation**

在 `CaptureMixin.on_decorating_result()` 中保留基础条件检查，然后将 `_choose_outgoing_meme_from_index()` 调用移动到冷却和概率判断之前；当返回 `None` 时立即清理未验证声明并返回。模型成功选出图片后，再执行原有冷却判断、概率判断和 `_claim_auto_send()`。

目标顺序：

```python
image_path = await self._choose_outgoing_meme_from_index(
    event,
    "\n".join(plain_texts),
    force_send=force_send,
    preferred_categories=marked_categories,
)
if image_path is None:
    self._rewrite_unverified_meme_claim(event, chain)
    return

if not force_send and cooldown and ...:
    self._rewrite_unverified_meme_claim(event, chain)
    return

if not force_send and (probability <= 0 or random.random() * 100 >= probability):
    self._rewrite_unverified_meme_claim(event, chain)
    return

if not await self._claim_auto_send(event, force=force_send):
    self._rewrite_unverified_meme_claim(event, chain)
    return
```

不要修改 `_handle_explicit_meme_request()`，明确请求仍然使用 `force=True` 路径并绕过概率。

- [ ] **Step 2: Run the targeted test**

Run:

```powershell
python -m unittest tests.test_explicit_meme_dispatch -v
```

Expected: PASS.

### Task 3: 全量验证和行为复核

**Files:**
- Test: `tests/`

- [ ] **Step 1: Run all Python tests**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass, including the new ordering regression test.

- [ ] **Step 2: Run syntax and compile checks**

Run:

```powershell
python -m compileall -q .
node --check pages/a_manage/script.js
git diff --check
```

Expected: all commands exit successfully.

- [ ] **Step 3: Review the final diff**

Confirm only the design/plan documents, the regression test, and the intended `capture.py` ordering change are present; do not stage or overwrite unrelated existing worktree modifications.
