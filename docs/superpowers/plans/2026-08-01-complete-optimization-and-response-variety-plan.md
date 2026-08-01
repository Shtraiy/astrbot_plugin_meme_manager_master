# 表情包管理大师完整优化与回复去模板化实施指南

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复固定发送句式、存储一致性、批量扫描、配置漂移、退役语义功能残留和核心模块过大问题，同时保持现有 AstrBot 兼容行为与资源包数据兼容。

**Architecture:** 先用纯函数明确“成功发送时如何组织文字与图片”，再把所有 pack 文件写入收口到可加锁、原子提交、失败回滚的仓储层。随后以能力开关隔离向量语义功能，并逐步拆分 Web API、捕获流程和管理页；每一步都有独立回归测试，避免一次性重写。

**Tech Stack:** Python 3、AstrBot 插件 API、`asyncio`、`threading`、`unittest`、原生 HTML/CSS/JavaScript、Pillow、aiohttp；FAISS 仅作为可选向量语义依赖。

## Global Constraints

- 保持插件 ID `meme_manager_master`、命令名称、WebUI 核心 URL、pack 目录结构和现有 JSON 字段向后兼容。
- 显式要求表情包时默认只发送图片，不再附加“找到了一个合适的表情包，发给你”一类成功套话。
- 自动发表情时保留模型原始可见回复；不得为了宣布发送而替换正文。
- 只有失败状态使用确定性提示文字；成功状态不得新增额外模型调用。
- 不用随机模板池掩盖重复句式问题，因为随机模板仍会形成另一组可预测套话。
- 所有 JSON 状态写入必须采用同目录临时文件、`flush`、`fsync`、`os.replace`。
- 同一 pack 的图片、目录、索引和元数据变更必须在同一写锁内完成。
- 批量操作每个受影响分类最多 reconcile 一次，不允许每张图片触发全库扫描。
- `faiss-cpu` 不再是核心安装依赖；未启用向量语义能力时不得注册向量任务 API。
- 每个任务先增加失败测试，再进行最小实现，最后运行完整测试和 `git diff --check`。
- 不自动提交 Git；下列 commit 命令是建议的阶段性提交边界。

---

## 一、已确认问题与目标行为

### 1. 固定句式根因

固定句式不是模型偶然复用，而是 `capture.py` 的三条硬编码路径：

- `_restore_forced_meme_result()` 用固定文字重建最终结果。
- `_handle_explicit_meme_request()` 直接返回固定文字加图片。
- `on_decorating_result()` 在 `force_send=True` 时用固定文字覆盖原回复。

改造后的统一规则：

| 场景 | 改造后输出 |
|---|---|
| 用户明确说“发个表情包”且选图成功 | 只发送图片 |
| 用户的普通问题触发自动表情 | 保留机器人原回复，正文完成后追加图片 |
| Agent continuation 覆盖了已选图片结果 | 恢复图片，不恢复固定成功文案 |
| 明确索图但图库无匹配 | `本地表情包库暂时没有找到合适的表情包。` |
| 管理器不可用 | `本地表情包管理器当前不可用，暂时无法发送表情包。` |
| 回复声称已发送但没有发送凭证 | `我还没有成功发送表情包。` |

失败文案可以固定，因为它们表达确定状态；成功时图片本身就是完成反馈，不需要再声明“发给你啦”。

### 2. 改造顺序

1. 先修复固定句式并增加行为测试。
2. 再统一原子写入和活动日志并发锁。
3. 再迁移分类、图片和批量操作到仓储层。
4. 然后统一配置定义。
5. 隔离退役的向量语义功能和可选依赖。
6. 最后拆分大文件并升级测试结构。

前四步直接修复用户可见或数据风险问题；后续步骤降低未来继续扩展时的回归成本。

---

## 二、目标文件结构

完成本指南后，新增或重构为以下职责边界：

```text
meme_manager_master/
├── capture.py                         # AstrBot 钩子和流程编排，不保存底层文件细节
├── response_policy.py                 # 成功/失败回复文字策略，纯 Python
├── runtime_config.py                  # 类型化配置、默认值、旧键迁移
├── storage.py                         # MemeStore 查询和单分类索引兼容门面
├── capture_activity.py                # 有锁的 bounded activity 日志
├── backend/
│   ├── atomic_io.py                   # 原子字节/JSON 写入
│   ├── pack_repository.py             # pack 事务、分类与图片变更
│   ├── pack_storage.py                # 导入、导出、备份和资源包生命周期
│   ├── catalog_index_service.py       # 图片描述和目录索引
│   ├── vector_semantic_service.py     # 可选向量能力
│   └── ...
├── mixins/
│   ├── web_api.py                     # 路由装配和通用响应包装
│   ├── web_routes.py                  # 声明式路由表与 capability
│   ├── emoji_api.py                   # 表情和分类接口
│   ├── pack_api.py                    # pack、社区、备份接口
│   └── semantic_api.py                # 索引复审；向量路由按 capability 注册
├── pages/a_manage/
│   ├── script.js                      # 页面入口
│   ├── api.js                         # fetch、错误解析、请求取消
│   ├── state.js                       # 页面状态和选择状态
│   ├── emoji-view.js                  # 分类与图片渲染
│   ├── pack-view.js                   # pack 管理
│   └── dialogs.js                     # 确认、进度和通知
├── scripts/generate_conf_schema.py    # 从 runtime_config 生成 schema
├── requirements.txt                   # 核心依赖
├── requirements-semantic.txt          # FAISS 可选依赖
└── tests/
    ├── test_response_policy.py
    ├── test_capture_dispatch_behavior.py
    ├── test_atomic_io.py
    ├── test_capture_activity_concurrency.py
    ├── test_pack_repository.py
    ├── test_batch_reconcile.py
    ├── test_runtime_config.py
    ├── test_web_route_capabilities.py
    └── test_web_api_behavior.py
```

迁移期间允许旧模块调用新模块，但新模块不得反向调用 `backend/models.py` 或 `backend/category_manager.py`。最终删除无调用方的重复写路径。

---

### Task 1: 去除成功发送的固定套话

**Files:**

- Create: `response_policy.py`
- Create: `tests/test_response_policy.py`
- Create: `tests/test_capture_dispatch_behavior.py`
- Modify: `capture.py:268-301`
- Modify: `capture.py:535-580`
- Modify: `capture.py:888-977`
- Modify: `tests/test_explicit_meme_dispatch.py`

**Interfaces:**

- Produces: `success_reply_text(existing_text: str | None = None) -> str`
- Consumes: AstrBot `Comp.Image` only在 `capture.py` 中创建；`response_policy.py` 不导入 AstrBot。

- [ ] **Step 1: 写入纯策略失败测试**

  新建 `tests/test_response_policy.py`：

  ```python
  import unittest

  from response_policy import success_reply_text


  class ResponsePolicyTests(unittest.TestCase):
      def test_explicit_image_success_has_no_announcement(self):
          self.assertEqual(success_reply_text(), "")

      def test_existing_agent_reply_is_preserved_verbatim(self):
          original = "当然可以，今天也要开心。"
          self.assertEqual(success_reply_text(original), original)

      def test_whitespace_only_reply_is_treated_as_empty(self):
          self.assertEqual(success_reply_text(" \n\t "), "")


  if __name__ == "__main__":
      unittest.main()
  ```

- [ ] **Step 2: 运行测试确认 RED**

  Run: `python -m unittest tests.test_response_policy -v`

  Expected: FAIL，错误为 `ModuleNotFoundError: No module named 'response_policy'`。

- [ ] **Step 3: 实现无额外模型调用的成功回复策略**

  新建 `response_policy.py`：

  ```python
  """User-visible reply policy for successful meme dispatches."""

  from __future__ import annotations


  def success_reply_text(existing_text: str | None = None) -> str:
      """Preserve meaningful Agent text and emit no canned success caption."""
      value = str(existing_text or "")
      return value if value.strip() else ""
  ```

- [ ] **Step 4: 修改三条显式成功路径**

  在 `capture.py` 导入 `success_reply_text`。增加一个只负责组装组件的私有方法：

  ```python
  @staticmethod
  def _explicit_success_chain(image_path: Path, existing_text: str = "") -> list:
      chain = []
      visible_text = success_reply_text(existing_text)
      if visible_text:
          chain.append(Comp.Plain(visible_text))
      chain.append(Comp.Image.fromFileSystem(str(image_path)))
      return chain
  ```

  按以下规则替换现有实现：

  - `_restore_forced_meme_result()` 使用 `self._explicit_success_chain(image_path)`。
  - `_handle_explicit_meme_request()` 使用 `self._explicit_success_chain(image_path)`。
  - `on_decorating_result()` 删除 `confirmation = ...` 和覆盖 `component.text` 的循环；已有 `chain` 保持原样，图片仍通过 `meme_manager_master_auto_send_path` 在正文完成后发送。
  - 删除所有“找到一个合适的表情包，发给你啦～”和“找到了一个合适的表情包，发给你～”字面量。

- [ ] **Step 5: 增加调度行为测试**

  `tests/test_capture_dispatch_behavior.py` 使用最小 fake result/component 验证：

  ```python
  import unittest
  from pathlib import Path
  from tempfile import TemporaryDirectory

  from response_policy import success_reply_text


  class CaptureDispatchBehaviorTests(unittest.TestCase):
      def test_explicit_success_does_not_generate_fixed_text(self):
          self.assertEqual(success_reply_text(None), "")

      def test_auto_send_keeps_the_original_visible_reply(self):
          reply = "这也太离谱了哈哈。"
          self.assertEqual(success_reply_text(reply), reply)

      def test_success_policy_never_uses_legacy_copy(self):
          values = [success_reply_text(), success_reply_text("原回复")]
          legacy = ("找到一个合适的表情包", "找到了一个合适的表情包")
          self.assertTrue(all(marker not in value for value in values for marker in legacy))
  ```

  同时把 `tests/test_explicit_meme_dispatch.py` 中纯字符串布局断言逐步替换为可执行的策略或 fake event 行为断言。保留一条源码禁用断言，用于保证旧文案不会重新出现：

  ```python
  def test_legacy_success_copy_is_absent(self):
      source = (ROOT / "capture.py").read_text(encoding="utf-8")
      self.assertNotIn("找到一个合适的表情包", source)
      self.assertNotIn("找到了一个合适的表情包", source)
  ```

- [ ] **Step 6: 验证固定句式修复**

  Run:

  ```text
  python -m unittest tests.test_response_policy tests.test_capture_dispatch_behavior tests.test_explicit_meme_dispatch -v
  rg -n "找到一个合适的表情包|找到了一个合适的表情包" capture.py
  ```

  Expected: 所有测试 PASS；`rg` 无输出并以“未找到匹配”结束。

- [ ] **Step 7: 建议提交边界**

  ```text
  git add response_policy.py capture.py tests/test_response_policy.py tests/test_capture_dispatch_behavior.py tests/test_explicit_meme_dispatch.py
  git commit -m "fix: remove canned meme success replies"
  ```

---

### Task 2: 统一原子文件写入并保护活动日志并发更新

**Files:**

- Create: `backend/atomic_io.py`
- Create: `tests/test_atomic_io.py`
- Create: `tests/test_capture_activity_concurrency.py`
- Modify: `capture_activity.py`
- Modify: `utils.py`
- Modify: `backend/pack_storage.py`
- Modify: `storage.py`

**Interfaces:**

- Produces: `atomic_write_bytes(path: Path, content: bytes) -> None`
- Produces: `atomic_write_json(path: Path, data: Mapping[str, Any]) -> None`

- [ ] **Step 1: 为原子写入增加失败测试**

  `tests/test_atomic_io.py` 覆盖：写入成功、覆盖成功、序列化异常时旧文件不变、临时文件被清理。

  ```python
  import json
  import tempfile
  import unittest
  from pathlib import Path

  from backend.atomic_io import atomic_write_json


  class AtomicIoTests(unittest.TestCase):
      def test_failed_json_serialization_preserves_existing_file(self):
          with tempfile.TemporaryDirectory() as temp_dir:
              path = Path(temp_dir) / "state.json"
              path.write_text('{"version": 1}', encoding="utf-8")
              with self.assertRaises(TypeError):
                  atomic_write_json(path, {"bad": object()})
              self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 1})
              self.assertEqual(list(path.parent.glob(".state.json.*.tmp")), [])
  ```

- [ ] **Step 2: 实现唯一原子写入模块**

  `backend/atomic_io.py` 的核心实现：

  ```python
  from __future__ import annotations

  import json
  import os
  import tempfile
  from pathlib import Path
  from typing import Any, Mapping


  def atomic_write_bytes(path: Path, content: bytes) -> None:
      target = Path(path)
      target.parent.mkdir(parents=True, exist_ok=True)
      fd, temp_name = tempfile.mkstemp(
          prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
      )
      try:
          with os.fdopen(fd, "wb") as handle:
              handle.write(content)
              handle.flush()
              os.fsync(handle.fileno())
          os.replace(temp_name, target)
      finally:
          if os.path.exists(temp_name):
              os.unlink(temp_name)


  def atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
      payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
      atomic_write_bytes(Path(path), payload)
  ```

- [ ] **Step 3: 迁移所有通用 JSON 写入**

  - `utils.save_json()` 改为调用 `atomic_write_json()`，保留原有 `bool` 返回契约。
  - `backend.pack_storage._save_json()` 改为薄包装，避免改变内部调用方。
  - `storage.MemeStore._atomic_write()` 和 `_atomic_write_json()` 委托给新模块。
  - `capture_activity._write_atomic()` 委托给新模块。
  - 不改变 JSON 缩进、UTF-8 编码或尾部换行，避免无意义数据 diff。

- [ ] **Step 4: 给 activity 的读—改—写增加进程内锁**

  在 `capture_activity.py` 增加按规范化文件路径分配的 `threading.RLock`：

  ```python
  import threading

  _LOCKS_GUARD = threading.Lock()
  _PATH_LOCKS: dict[str, threading.RLock] = {}


  def _lock_for(pack_dir: Path) -> threading.RLock:
      key = str(_path(pack_dir).resolve())
      with _LOCKS_GUARD:
          return _PATH_LOCKS.setdefault(key, threading.RLock())
  ```

  `record_capture_event()` 和 `mark_capture_events_indexed()` 必须在同一把锁内部完成 load、mutate、write；只锁 write 不能防止 lost update。

- [ ] **Step 5: 增加并发回归测试**

  `tests/test_capture_activity_concurrency.py` 用 `ThreadPoolExecutor(max_workers=8)` 并发写入 100 个唯一 digest，最后断言 100 条事件都存在且 JSON 可解析：

  ```python
  from concurrent.futures import ThreadPoolExecutor
  import tempfile
  import unittest
  from pathlib import Path

  from capture_activity import load_capture_activity, record_capture_event


  class CaptureActivityConcurrencyTests(unittest.TestCase):
      def test_parallel_events_are_not_lost(self):
          with tempfile.TemporaryDirectory() as temp_dir:
              pack_dir = Path(temp_dir)
              def write(index: int) -> None:
                  record_capture_event(
                      pack_dir,
                      category="happy",
                      filename=f"{index}.png",
                      digest=f"digest-{index}",
                      status="pending",
                  )
              with ThreadPoolExecutor(max_workers=8) as executor:
                  list(executor.map(write, range(100)))
              events = load_capture_activity(pack_dir)["events"]
              self.assertEqual(len(events), 100)
              self.assertEqual({item["sha256"] for item in events}, {f"digest-{i}" for i in range(100)})
  ```

- [ ] **Step 6: 验证并建议提交**

  Run:

  ```text
  python -m unittest tests.test_atomic_io tests.test_capture_activity tests.test_capture_activity_concurrency -v
  python -m unittest discover -s tests -v
  git diff --check
  ```

  Suggested commit: `fix: make plugin state writes atomic and serialized`

---

### Task 3: 建立 pack 仓储事务并消除危险图片替换

**Files:**

- Create: `backend/pack_repository.py`
- Create: `tests/test_pack_repository.py`
- Modify: `backend/models.py`
- Modify: `backend/category_manager.py`
- Modify: `mixins/web_api.py`
- Modify: `storage.py`

**Interfaces:**

- Produces: `PackRepository(pack_dir: Path)`
- Produces: `rename_category(old_name: str, new_name: str) -> bool`
- Produces: `delete_category(category: str) -> bool`
- Produces: `replace_image(category: str, old_name: str, new_name: str, content: bytes) -> Path`
- Produces: `move_images(source: str, target: str, filenames: Sequence[str]) -> BatchMutationResult`
- Produces: `copy_images(source: str, target: str, filenames: Sequence[str]) -> BatchMutationResult`
- Produces: `delete_images(category: str, filenames: Sequence[str]) -> BatchMutationResult`

  `BatchMutationResult` 在 `backend/pack_repository.py` 中定义为稳定的内部返回类型：

  ```python
  from dataclasses import dataclass


  @dataclass(frozen=True, slots=True)
  class BatchMutationResult:
      succeeded: tuple[str, ...] = ()
      missing: tuple[str, ...] = ()
      conflicting: tuple[str, ...] = ()
  ```

  `backend/models.py` 的兼容门面负责把它映射回当前 Web API 使用的
  `moved_files`、`copied_files`、`deleted_files`、`missing_files` 和
  `conflicting_files` 字段，避免前端协议变化。

- [ ] **Step 1: 先写事务失败与回滚测试**

  必须覆盖以下实际风险：

  - 分类目录已经重命名，但元数据保存失败时恢复旧目录和旧元数据。
  - 删除分类时先移动到同盘临时回收目录；元数据保存失败时恢复。
  - 新图片扩展名非法时旧图片仍存在。
  - 新图片写入失败时旧图片仍存在。
  - 成功替换使用 `os.replace`，调用方不会观察到半写文件。

  用 `unittest.mock.patch("backend.pack_repository.atomic_write_json", side_effect=OSError("disk full"))` 注入失败，不需要真实填满磁盘。

- [ ] **Step 2: 实现 pack 级同步锁**

  `backend/pack_repository.py` 使用线程锁，因为 Web API 已经通过 `asyncio.to_thread()` 运行文件操作：

  ```python
  import threading
  from pathlib import Path

  _LOCKS_GUARD = threading.Lock()
  _PACK_LOCKS: dict[str, threading.RLock] = {}


  def pack_lock(pack_dir: Path) -> threading.RLock:
      key = str(Path(pack_dir).resolve())
      with _LOCKS_GUARD:
          return _PACK_LOCKS.setdefault(key, threading.RLock())
  ```

  所有公开 mutation 方法进入同一 `pack_lock(self.pack_dir)`；查询方法不持有写锁，但必须只读取原子替换后的文件。

- [ ] **Step 3: 实现可回滚的分类重命名**

  精确顺序：

  1. 校验旧、新分类均为安全单路径段。
  2. 加载并复制旧 metadata。
  3. 检查目标目录和目标 metadata 名称均不存在。
  4. `os.rename(old_path, new_path)`。
  5. 构建新的 metadata 字典并原子保存。
  6. 保存失败时 `os.rename(new_path, old_path)`，重新抛出原异常。
  7. 成功后只 reconcile 新分类一次，并使语义元数据失效。

  不得先修改共享的 `self.descriptions` 再尝试磁盘操作；事务使用局部副本，提交成功后再替换内存视图。

- [ ] **Step 4: 实现可恢复删除**

  删除流程使用 pack 内同文件系统的 `.trash`：

  ```text
  packs/<pack_id>/.trash/category-<uuid>/
  ```

  精确顺序：加锁 → 原目录移动到 `.trash` → 原子保存不含该分类的新 metadata → 成功后删除 trash；保存失败则把 trash 移回原目录。启动时可清理超过 24 小时且不对应活动事务的 `.trash` 项。

- [ ] **Step 5: 修复危险图片替换**

  删除 `backend.models.update_emoji_in_category()` 当前“先删旧图再验证新图”的实现。新实现先完成：

  1. 安全文件名和扩展名校验。
  2. 内容非空、图片大小上限检查。
  3. 写入目标目录临时文件并 `fsync`。
  4. Pillow `Image.verify()` 验证图片内容。
  5. `os.replace(temp_path, target_path)`。
  6. 当目标文件名不同于旧文件名时，成功替换后再删除旧文件。

  任一步失败都清理临时文件并保留旧图。

- [ ] **Step 6: 将旧写入口改为兼容门面**

  - `CategoryManager` 保留公共方法名称，但内部委托 `PackRepository`。
  - `backend/models.py` 保留 WebUI 当前使用的函数签名，内部解析当前 pack 后委托仓储。
  - `MemeStore` 保留查询、选图和 catalog 读取；分类级 mutation 迁入仓储。
  - 新代码禁止直接调用 `shutil.rmtree(pack_category)`、`os.rename(category)` 或非原子 `save_json()`。

- [ ] **Step 7: 验证并建议提交**

  Run:

  ```text
  python -m unittest tests.test_pack_repository tests.test_pack_storage_runtime -v
  python -m unittest discover -s tests -v
  git diff --check
  ```

  Suggested commit: `refactor: centralize transactional pack mutations`

---

### Task 4: 批量操作只 reconcile 受影响分类一次

**Files:**

- Create: `tests/test_batch_reconcile.py`
- Modify: `backend/pack_repository.py`
- Modify: `backend/models.py:231-489`
- Modify: `storage.py:402-454`
- Modify: `mixins/web_api.py:847-1038`

**Interfaces:**

- Consumes: Task 3 的 `PackRepository` 和 `BatchMutationResult`
- Produces: `reconcile_categories(categories: Iterable[str]) -> int`

- [ ] **Step 1: 写入 reconcile 次数失败测试**

  以 20 张图片批量移动为例，patch `repository.reconcile_categories`，断言只调用一次且参数集合为 `{"source", "target"}`。批量删除只传入源分类；批量复制传入源、目标分类。

- [ ] **Step 2: 给 MemeStore 增加定向 reconcile**

  将 `reconcile_catalogs()` 的单分类主体提取为：

  ```python
  def reconcile_category(self, category: str) -> bool:
      """Repair one category and return whether files were rewritten."""
  ```

  再实现：

  ```python
  def reconcile_categories(self, categories) -> int:
      safe = sorted({str(item) for item in categories if _is_safe_segment(str(item))})
      return sum(1 for category in safe if self.reconcile_category(category))

  def reconcile_catalogs(self) -> int:
      return self.reconcile_categories(self.directory_categories())
  ```

  单分类主体继续保留现有 metadata、description、tags 和 README 行为。

- [ ] **Step 3: 批量 mutation 内禁止调用单项公共 mutation**

  `move_images()`、`copy_images()`、`delete_images()` 在同一锁和循环内直接使用已校验的内部原语。循环结束后统一调用一次 `reconcile_categories()`。单项 API 调用仓储的单项方法，单项方法内部仍只 reconcile 一次。

- [ ] **Step 4: 添加性能保护测试**

  在临时 pack 中创建 50 个分类，每类 20 个小文件；批量移动一个分类中的 20 张图。测试不使用脆弱的毫秒上限，而是通过 mock 断言未调用 `reconcile_catalogs()`，并且 `reconcile_category()` 只针对两个分类执行。

- [ ] **Step 5: 验证并建议提交**

  Run: `python -m unittest tests.test_batch_reconcile tests.test_pack_storage_runtime -v`

  Suggested commit: `perf: reconcile only changed meme categories`

---

### Task 5: 建立类型化配置并消除 schema 漂移

**Files:**

- Create: `runtime_config.py`
- Create: `scripts/generate_conf_schema.py`
- Create: `tests/test_runtime_config.py`
- Modify: `_conf_schema.json`
- Modify: `capture.py`
- Modify: `manager_base.py`
- Modify: `CONFIGURATION.md`

**Interfaces:**

- Produces: `PluginConfig.from_mapping(raw: Mapping[str, Any]) -> PluginConfig`
- Produces: `PluginConfig.to_schema() -> dict[str, Any]`
- Consumes: 现有 flat keys 和 `manager_base.py` 的 legacy/nested keys。

- [ ] **Step 1: 写默认值、边界和兼容键测试**

  测试至少覆盖当前运行时使用的以下配置：

  ```text
  enabled
  group_whitelist
  vision_provider_id
  scene_provider_id
  reply_scene_provider_id
  only_capture_memes
  meme_rejection_confidence
  max_images_per_message
  max_concurrent
  max_image_size_mb
  download_timeout
  auto_send_enabled
  auto_send_probability
  auto_send_cooldown
  auto_send_candidate_limit
  meme_repeat_window
  meme_follow_up_window
  proactive_send_after_steal
  perceptual_dedupe_enabled
  perceptual_duplicate_threshold
  library_index_enabled
  library_index_provider_id
  library_index_batch_size
  library_index_progress_step
  library_index_rename_files
  health_check_interval
  fallback_category
  local_image_roots
  ```

  数值边界必须与现有 `_int_config`、`_float_config` 调用一致；超界值 clamp，非法类型回退默认值。

- [ ] **Step 2: 实现不可变配置对象**

  使用 `@dataclass(frozen=True, slots=True)`。列表字段在构造时转换为 tuple，避免运行期间被 WebUI 或事件处理意外修改。提供 `bool_value`、`int_value`、`float_value` 内部解析函数，但业务代码只访问属性，例如：

  ```python
  config.auto_send_probability
  config.max_images_per_message
  config.group_whitelist
  ```

  `from_mapping()` 同时读取当前 flat key 和已有 nested/legacy key，优先级保持 `primary > legacy path > legacy flat > default`。

- [ ] **Step 3: 迁移 CaptureMixin 和 MemeSender**

  - 保留 `self.config_raw` 供短期兼容和调试。
  - `self.runtime_config = PluginConfig.from_mapping(config or {})`。
  - 将 `_bool_config()`、`_int_config()`、`_float_config()` 调用逐个替换为属性访问。
  - `configured_provider_id()` 改为接收 `PluginConfig` 或直接读取 provider 属性。
  - 当旧配置键被使用时每次启动最多记录一次迁移提示，不在每条消息中输出日志。

- [ ] **Step 4: 从同一配置定义生成 `_conf_schema.json`**

  `scripts/generate_conf_schema.py` 调用 `PluginConfig.to_schema()`，使用 `json.dumps(..., ensure_ascii=False, indent=2)` 输出。运行：

  ```text
  python scripts/generate_conf_schema.py --check
  python scripts/generate_conf_schema.py --write
  ```

  `--check` 比较内存生成内容与仓库文件，不写磁盘；不一致时退出码为 1。测试套件运行 `--check` 的底层比较函数，保证 schema 不再漂移。

- [ ] **Step 5: 更新配置文档**

  `CONFIGURATION.md` 对每项公开配置写明类型、默认值、边界、是否产生模型调用。内部维护项可以不在 AstrBot UI 展示，但必须仍由 `PluginConfig` 定义，不能继续散落字符串键。

- [ ] **Step 6: 验证并建议提交**

  Run:

  ```text
  python -m unittest tests.test_runtime_config -v
  python scripts/generate_conf_schema.py --check
  python -m unittest discover -s tests -v
  ```

  Suggested commit: `refactor: centralize plugin configuration schema`

---

### Task 6: 隔离退役向量语义能力并改为可选依赖

**Files:**

- Create: `mixins/web_routes.py`
- Create: `backend/catalog_index_service.py`
- Create: `backend/vector_semantic_service.py`
- Create: `requirements-semantic.txt`
- Create: `tests/test_web_route_capabilities.py`
- Modify: `requirements.txt`
- Modify: `manager_base.py:46-80`
- Modify: `mixins/web_api.py:102-392`
- Modify: `backend/semantic_task.py`
- Modify: `README.md`
- Modify: `CONFIGURATION.md`

**Interfaces:**

- Produces: `WebRouteSpec(path, handler_name, methods, description, capability)`
- Produces: capability 值 `core`、`catalog_index`、`vector_semantic`
- Produces: `enabled_route_specs(capabilities: set[str]) -> tuple[WebRouteSpec, ...]`

  路由类型使用以下精确字段：

  ```python
  from dataclasses import dataclass


  @dataclass(frozen=True, slots=True)
  class WebRouteSpec:
      path: str
      handler_name: str
      methods: tuple[str, ...]
      description: str
      capability: str = "core"
  ```

- [ ] **Step 1: 写路由能力失败测试**

  默认能力集合为 `{"core", "catalog_index"}`。测试断言：

  - `semantic/capture-workspace` 和 `semantic/capture-index` 仍注册。
  - `semantic/start`、`pause`、`resume`、`retry`、`rebuild-index`、`clear-local-state`、`delete-all` 不注册。
  - 显式加入 `vector_semantic` 后上述向量路由才注册。

- [ ] **Step 2: 将 290 行路由注册改为声明式路由表**

  `mixins/web_routes.py` 使用不可变 `WebRouteSpec`。`WebAPIMixin._register_web_apis()` 只循环注册：

  ```python
  for spec in enabled_route_specs(self.web_capabilities):
      self._register_webui_api(
          spec.path,
          getattr(self, spec.handler_name),
          list(spec.methods),
          spec.description,
      )
  ```

  这样测试无需启动 AstrBot 即可验证实际 API 面。

- [ ] **Step 3: 拆分目录索引和向量任务职责**

  - `CatalogIndexService` 只负责 caption、分类复审、capture workspace 和 `index.json` 补全。
  - `VectorSemanticService` 负责 embedding、FAISS、向量重建和向量搜索。
  - pack 文件操作锁移入 `PackRepository`，不得再为了获得锁而无条件初始化 `SemanticTaskManager`。
  - `manager_base.py` 默认不创建向量服务；仅当类型化配置明确启用且 FAISS 可用时创建。

- [ ] **Step 4: 调整依赖**

  `requirements.txt` 保留：

  ```text
  aiohttp>=3.9.0
  Pillow>=10.0.0
  requests>=2.31.0
  ```

  `requirements-semantic.txt`：

  ```text
  -r requirements.txt
  faiss-cpu
  numpy
  ```

  `semantic_index.py` 继续保留惰性导入和清晰错误；核心插件启动、收集、分类、WebUI 浏览和自动发送不得依赖 FAISS。

- [ ] **Step 5: 验证默认启动不触达向量模块**

  测试 patch `backend.semantic_index._import_faiss_modules` 令其抛错，默认配置下初始化核心服务仍成功。启用 `vector_semantic` 时返回明确的配置/依赖错误，不以模糊 500 结束。

- [ ] **Step 6: 验证并建议提交**

  Run:

  ```text
  python -m unittest tests.test_web_route_capabilities tests.test_legacy_tag_dispatch -v
  python -m unittest discover -s tests -v
  ```

  Suggested commit: `refactor: make vector semantic support optional`

---

### Task 7: 拆分 Web API、捕获编排和管理页大文件

**Files:**

- Create: `mixins/emoji_api.py`
- Create: `mixins/pack_api.py`
- Create: `mixins/semantic_api.py`
- Create: `capture_pipeline.py`
- Create: `meme_selection.py`
- Create: `pages/a_manage/api.js`
- Create: `pages/a_manage/state.js`
- Create: `pages/a_manage/emoji-view.js`
- Create: `pages/a_manage/pack-view.js`
- Create: `pages/a_manage/dialogs.js`
- Modify: `mixins/web_api.py`
- Modify: `capture.py`
- Modify: `pages/a_manage/script.js`
- Modify: `pages/a_manage/index.html`
- Create: `tests/test_module_boundaries.py`

**Interfaces:**

- `CapturePipeline.process_batch(event, sources, message_text, outline) -> list[str]`
- `MemeSelectionService.choose(event, response_text, force_send, preferred_categories) -> Path | None`
- API mixins 通过 `self.pack_repository`、`self.catalog_index_service` 调用后端，不直接导入文件操作函数。

- [ ] **Step 1: 写模块边界测试**

  使用 AST 读取 import，断言：

  - `mixins/*_api.py` 不导入 `shutil`、`os.remove`、`requests`。
  - `meme_selection.py` 不导入 WebUI request/jsonify。
  - `capture_pipeline.py` 不注册 AstrBot filter。
  - `capture.py` 不直接调用 `json.dump`、`os.replace`、`shutil.rmtree`。

- [ ] **Step 2: 先拆 Web API，不改变 URL**

  按已有方法组移动函数，方法名和 route path 保持不变。`WebAPIMixin` 继续作为组合门面，继承或显式调用三个小 mixin；`main.py` 的 `MemeManager` 继承结构不变。

- [ ] **Step 3: 提取捕获处理管线**

  将 `_process_one`、`_process_batch`、识图与分类调用迁入 `CapturePipeline`。依赖通过构造参数注入：store/repository、provider generate callable、config、activity recorder。`CaptureMixin` 只负责事件过滤、任务生命周期和结果回填。

- [ ] **Step 4: 提取选图服务**

  将 `_choose_outgoing_meme_from_index`、legacy candidate choice、重复降权和候选限制迁入 `MemeSelectionService`。服务返回 `Path | None` 和结构化 decision，不写 event extras；`CaptureMixin` 负责把决策绑定到当前 AstrBot event。

- [ ] **Step 5: 逐个拆管理页脚本**

  顺序固定为：`api.js` → `state.js` → `dialogs.js` → `pack-view.js` → `emoji-view.js`。每抽出一个文件就运行页面 smoke test，避免一次移动 5800 行。

  `index.html` 按依赖顺序加载脚本；共享符号统一挂在单一命名空间 `window.MemeManagerUI`，不新增多个隐式全局变量：

  ```javascript
  window.MemeManagerUI = window.MemeManagerUI || {};
  ```

  用户数据只通过 `textContent`、`value`、属性 setter 写入 DOM；`innerHTML` 只允许静态模板。

- [ ] **Step 6: 每次移动后运行回归测试**

  Run:

  ```text
  python -m unittest tests.test_module_boundaries tests.test_log_noise tests.test_capture_index_page -v
  python -m unittest discover -s tests -v
  ```

  另外在 AstrBot WebUI 手动验证：分类浏览、预览、上传、批量移动、pack 切换、导入导出、设置保存。

- [ ] **Step 7: 建议提交边界**

  分为三个提交，不合并成一次大提交：

  ```text
  refactor: split web api controllers
  refactor: extract capture and selection services
  refactor: modularize meme manager web ui
  ```

---

### Task 8: 用行为测试替换关键源码字符串测试并建立完整验证门禁

**Files:**

- Create: `tests/fakes.py`
- Create: `tests/test_web_api_behavior.py`
- Create: `.github/workflows/test.yml`（若仓库使用 GitHub CI）
- Modify: `tests/test_explicit_meme_dispatch.py`
- Modify: `tests/test_legacy_tag_dispatch.py`
- Modify: `tests/test_capture_index_page.py`
- Modify: `tests/test_lifecycle_hook_registration.py`
- Modify: `README.md`

**Interfaces:**

- Produces: `FakeEvent`、`FakeResult`、`FakeContext`、`FakeProvider`，只实现生产代码实际读取的方法和属性。

- [ ] **Step 1: 建立最小 fake，不使用宽松 MagicMock**

  Fake 对象缺少属性时应抛出 `AttributeError`，防止 mock 自动吞掉生产代码访问错误。事件 fake 至少支持：`get_result`、`set_result`、`get_extra`、`set_extra`、`get_message_str`、`unified_msg_origin`、`stop_event`。

- [ ] **Step 2: 将关键源码断言替换为行为断言**

  必须覆盖：

  - 显式索图成功只得到图片组件。
  - 自动发表情保留原回复文本。
  - 没有发送凭证时发送声明被改写。
  - 有凭证时原文字保留。
  - 退役 `search_memes` 工具在请求和工具调用路径中均被阻止。
  - 默认配置不会启动向量重建。
  - `terminate()` 即使 manager cleanup 失败也会取消 capture tasks。

  源码/AST 测试只保留两类：禁止重新出现的遗留 API，以及模块边界规则。

- [ ] **Step 3: 增加 Web API 行为测试**

  使用 fake request/context 覆盖核心成功和失败状态码：

  - 非法 category/filename 返回 400。
  - 路径越界返回 403。
  - 文件不存在返回 404。
  - 超大预览返回 413。
  - pack mutation 冲突返回 409。
  - 后端异常不向客户端泄漏绝对路径和 traceback。

- [ ] **Step 4: 建立验证脚本顺序**

  每个阶段完成时运行：

  ```text
  python -m unittest discover -s tests -v
  python -m compileall -q .
  python scripts/generate_conf_schema.py --check
  git diff --check
  git status --short
  ```

  完整验收还必须在 AstrBot 中手动执行本文末尾的场景矩阵。

- [ ] **Step 5: 建议提交**

  Suggested commit: `test: cover meme dispatch and pack mutations behaviorally`

---

## 三、运行时验收矩阵

### A. 回复去模板化

| 输入 | 设置 | 预期 |
|---|---|---|
| `发一个猫猫表情包` | 默认 | 只发送匹配图片，不出现成功套话 |
| `再来一个` | 最近发送窗口内 | 只发送另一张图片；重复降权有效 |
| 普通聊天触发主动表情 | `auto_send_probability=100` | 原机器人回复完整保留，随后发送图片 |
| 普通聊天未选中表情 | 默认 | 只发送原机器人回复，不附加失败提示 |
| 明确索图但图库为空 | 默认 | 返回“本地表情包库暂时没有找到合适的表情包。” |
| Agent 声称“发给你啦”但发送失败 | 模拟无 receipt | 改写为“我还没有成功发送表情包。” |

### B. 数据一致性

| 操作 | 注入故障 | 预期 |
|---|---|---|
| 重命名分类 | metadata 原子保存失败 | 旧目录和旧 metadata 均保留 |
| 删除分类 | metadata 保存失败 | 分类从 `.trash` 恢复 |
| 替换图片 | 新文件格式非法 | 旧图片仍存在 |
| 替换图片 | 临时写入失败 | 旧图片和 catalog 不变 |
| 并发收集 100 张 | 8 worker | activity 中 100 个唯一事件均存在 |
| 批量移动 20 张 | 50 个分类的 pack | 只 reconcile 源、目标两个分类 |

### C. 能力隔离

| 环境 | 预期 |
|---|---|
| 未安装 FAISS、默认配置 | 插件正常启动，管理、收集、自动发送可用 |
| 未安装 FAISS、请求向量 API | 路由未注册或返回明确的能力未启用提示 |
| 安装 FAISS 且显式启用 | 向量路由注册并可建立索引 |
| 仅使用目录索引 | caption、分类复审和 capture workspace 可用 |

---

## 四、完成定义

以下条件全部满足才算完成整改：

- `capture.py` 不再包含两条旧成功套话，也不以成功文案覆盖 Agent 回复。
- 所有核心 JSON 写入统一通过 `backend.atomic_io`。
- `capture_activity.json` 并发回归测试稳定通过至少 20 次重复运行。
- 分类重命名、删除、图片替换具有故障注入回滚测试。
- 批量移动、复制、删除不存在逐图片全库 reconcile。
- 运行时配置不再通过散落的字符串键读取；schema check 通过。
- 默认安装不依赖 `faiss-cpu`，默认路由面不暴露向量任务操作。
- `web_api.py`、`capture.py`、`pages/a_manage/script.js` 的职责已按目标结构拆分。
- 关键发送和 mutation 测试验证行为，不只检查源码字符串。
- 完整 `unittest`、`compileall`、schema check、`git diff --check` 全部通过。
- AstrBot 手动验收矩阵全部通过，现有 pack 数据无需迁移即可继续使用。

---

## 五、后续功能扩展路线

这些功能应在上述稳定性整改完成后分别设计和实现，不与核心重构混在同一提交中：

1. **重复图片审核中心**：按 SHA256 和感知哈希形成相似组，并排预览、保留最佳版本、合并描述与标签。
2. **自适应选图反馈**：在现有 `send_count`、`last_sent_at` 基础上增加喜欢、不合适、不要再发三类反馈；权重按会话或 persona 隔离。
3. **运行与成本仪表盘**：展示收集成功率、重复率、模型错误、索引积压、图库增长和模型调用量。
4. **隐私与治理**：增加群级退出收集、保留期限、待审核分类和敏感内容过滤。
5. **资源包版本管理**：更新差异预览、增量安装、冲突解决和上一个版本回滚。

推荐下一轮先执行 Task 1 至 Task 4；它们直接解决固定套话、数据一致性和性能问题，并为后续重构提供稳定边界。
