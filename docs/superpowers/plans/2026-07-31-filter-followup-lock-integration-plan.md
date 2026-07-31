# Filter Follow-up Lock Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让自动表情在 Filter 的全部文本分段发送完成后才发送。

**Architecture:** Filter 继续拥有并管理现有 `asyncio.Lock`，只通过事件 extra 暴露同一对象。表情插件在主消息发送完成后等待该锁释放，并使用 30 秒超时保证 Filter 异常时不会永久阻塞。

**Tech Stack:** Python 3、`asyncio`、AstrBot 事件 extra、`unittest`、`pytest`

## Global Constraints

- 共享键固定为 `astrbot_plugin_filter_reply_lock`。
- Filter 是锁的唯一原始持有者；表情插件取得等待后的锁时必须立即释放。
- 等待超时固定为 30 秒。
- 不轮询 Filter 私有实例字段。
- 不使用固定睡眠估计分段完成时间。
- 不改变情景选择、概率、冷却、明确请求或 Filter gate 行为。
- Filter 缺失、旧版本或事件不支持 extra 时保持原行为。
- 不自动创建 Git 提交。

---

### Task 1: 表情插件等待 Filter 回复锁

**Files:**

- Create: `tests/test_filter_followup_lock.py`
- Modify: `collector.py`
- Modify: `capture.py`

**Interfaces:**

- Consumes: `event.get_extra("astrbot_plugin_filter_reply_lock")`
- Produces: `async wait_for_filter_reply_lock(event, timeout: float = 30.0) -> str`
- Return values: `"missing"`、`"released"`、`"timeout"`

- [x] **Step 1: 写入失败的异步行为测试**

  测试使用真实 `asyncio.Lock`：

  - extra 缺失时返回 `"missing"`；
  - 已释放锁时返回 `"released"`；
  - 已占用锁在释放前保持等待，释放后返回 `"released"`；
  - 超时返回 `"timeout"` 且不释放 Filter 仍持有的锁。

- [x] **Step 2: 运行测试并确认 RED**

  Run: `python -m unittest tests.test_filter_followup_lock -v`

  Expected: ERROR，因为 `collector.wait_for_filter_reply_lock` 尚不存在。

- [x] **Step 3: 实现最小等待辅助函数**

  在 `collector.py` 中增加：

  ```python
  FILTER_REPLY_LOCK_EXTRA = "astrbot_plugin_filter_reply_lock"

  async def wait_for_filter_reply_lock(event, timeout: float = 30.0) -> str:
      ...
  ```

  使用 `asyncio.wait_for(lock.acquire(), timeout)` 等待；成功取得后立即
  `lock.release()`。`asyncio.CancelledError` 不捕获，保持任务取消语义。

- [x] **Step 4: 接入自动表情发送**

  在 `CaptureMixin.after_message_sent` 的 `auto_path is not None` 分支中，
  调用等待函数后再执行 `context.send_message`。仅 `"timeout"` 记录 warning，
  实际等待完成记录 INFO。

- [x] **Step 5: 运行定向测试并确认 GREEN**

  Run: `python -m unittest tests.test_filter_followup_lock -v`

  Expected: PASS。

---

### Task 2: Filter 在事件上暴露现有回复锁

**Files:**

- Modify: `参考代码/astrbot_plugin_filter/main.py`
- Create: `参考代码/astrbot_plugin_filter/tests/test_reply_lock_unittest.py`

**Interfaces:**

- Consumes: Filter 已有 `reply_lock: asyncio.Lock`
- Produces: `event.set_extra("astrbot_plugin_filter_reply_lock", reply_lock)`

- [x] **Step 1: 写入失败的 Filter 联动测试**

  在多分段测试中让后续发送任务等待测试事件，验证：

  - `on_decorating_result` 返回后，事件 extra 保存的对象就是当前会话锁；
  - 后续发送未完成时锁保持占用；
  - 后续发送完成后锁被 Filter 原有 `finally` 逻辑释放。

- [x] **Step 2: 运行测试并确认 RED**

  Run:

  `python 参考代码/astrbot_plugin_filter/tests/test_reply_lock_unittest.py -v`

  Expected: FAIL，因为事件中尚未发布共享回复锁。

- [x] **Step 3: 实现锁发布**

  在 Filter 中定义同名共享键。取得 `reply_lock` 后调用安全辅助方法：

  ```python
  setter = getattr(event, "set_extra", None)
  if callable(setter):
      setter(FILTER_REPLY_LOCK_EXTRA, reply_lock)
  ```

  不改变 `_send_followups_and_release` 或 `_finish_reply`。

- [x] **Step 4: 运行 Filter 定向测试并确认 GREEN**

  Run:

  `python 参考代码/astrbot_plugin_filter/tests/test_reply_lock_unittest.py -v`

  Expected: PASS。

---

### Task 3: 双插件回归与验收

**Files:**

- Modify: `docs/superpowers/plans/2026-07-31-filter-followup-lock-integration-plan.md`

**Interfaces:**

- Consumes: Task 1 与 Task 2 的共享 extra 契约
- Produces: 已验证的双插件联动实现

- [x] **Step 1: 运行表情插件完整测试**

  Run: `python -m unittest discover -s tests -v`

  Expected: 全部 PASS。

- [x] **Step 2: 运行 Filter 联动集成测试**

  Run: `python 参考代码/astrbot_plugin_filter/tests/test_reply_lock_unittest.py -v`

  Expected: PASS。当前工作区未安装参考项目原测试套件所需的 pytest，
  因而使用不依赖额外包的真实异步集成测试。

- [x] **Step 3: 运行编译和差异检查**

  Run:

  - `python -m compileall -q .`
  - `git diff --check`

  Expected: exit code 0。

- [x] **Step 4: 检查联动顺序**

  确认日志顺序为：

  ```text
  已锁定表情包
  → Filter 第 2..N 条分段发送完成
  → Filter 分段锁等待完成
  → 正文发送完成后发送自动表情包
  ```
