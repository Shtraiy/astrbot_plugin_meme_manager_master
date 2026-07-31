# Proactive Scene Meme Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让普通情绪对话无需用户明确索要也能通过情景分析主动发表情，同时保留明确请求强制发送、概率门控和冷却机制。

**Architecture:** 将情景分类提示词从依赖 AstrBot 的 `capture.py` 移到纯 Python 模块 `collector.py`，由 `capture.py` 导入使用。只调整模型决策契约，不修改候选选择、冷却、概率、发送队列或生命周期逻辑。

**Tech Stack:** Python 3、`unittest`、AstrBot 插件

## Global Constraints

- 不恢复已经退役的向量语义启动任务。
- 不取消情景模型判断。
- 不修改普通消息的概率门控与冷却机制。
- `explicit_request=true` 继续强制发送。
- 不自动提交 Git；当前任务只修改工作区。

---

## Task 1: 修正普通对话主动发表情的情景判断契约

**Files:**

- Create: `tests/test_outgoing_scene_prompt.py`
- Modify: `collector.py`
- Modify: `capture.py`

- [x] **Step 1: 写入失败的回归测试**

  新测试直接导入无 AstrBot 依赖的 `collector.py`，验证情景提示词同时表达以下行为：

  - 普通聊天可以主动发送，不要求用户明确索要；
  - `explicit_request=false` 不代表禁止发送；
  - 不得仅因“用户未明确索要表情包”拒绝；
  - 惊讶等明显社交情绪优先发送；
  - 不使用固定 `should_send=false` 的 JSON 示例；
  - `explicit_request=true` 仍然必须发送。

- [x] **Step 2: 运行定向测试并确认 RED**

  Run: `python -m unittest tests.test_outgoing_scene_prompt -v`

  Expected: FAIL，因为 `collector.py` 尚未提供修正后的 `OUTGOING_CATEGORY_PROMPT`。

- [x] **Step 3: 最小实现提示词修复**

  在 `collector.py` 定义 `OUTGOING_CATEGORY_PROMPT`，使用字段约束代替固定 false 示例；在 `capture.py` 导入该常量并删除旧的本地定义。

- [x] **Step 4: 运行定向测试并确认 GREEN**

  Run: `python -m unittest tests.test_outgoing_scene_prompt -v`

  Expected: PASS。

- [x] **Step 5: 运行完整验证**

  Run:

  - `python -m unittest discover -s tests -v`
  - `python -m compileall -q .`
  - `git diff --check`

  Expected: 全部通过，且没有空白错误。

- [x] **Step 6: 检查最终差异和运行时验收路径**

  确认 `capture.py` 的实际情景分析调用使用导入的新提示词，且发送概率、冷却和明确请求分支没有变化。运行时可临时使用 `auto_send_probability=100`、`auto_send_cooldown=0` 验证普通情绪场景。
