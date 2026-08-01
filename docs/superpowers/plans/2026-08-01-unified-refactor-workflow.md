# Meme Manager Unified Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持现有 AstrBot 命令、pack 数据和独立运行能力的前提下，统一修复 WebUI、恢复可解释的语义选图能力、消除重复发送与数据一致性风险，并通过公开适配层与 `astrbot_plugin_private_companion` 形成双向协作。

**Architecture:** 以“语义决策 → 候选检索 → 发送编排 → 发送回执”为唯一运行时主链；以 Catalog/Pack Repository 为唯一数据写入口；以 WebUI capability 和 Private Companion Adapter 为两个可选边界。Private Companion 只负责主动时机、关系和场景上下文，本插件负责表情语义、图片选择、去重和发送，任一插件不可用时另一方仍可独立工作。

**Tech Stack:** Python 3、AstrBot 4.x 插件 API、`asyncio`、`threading`、`unittest`、原生 HTML/CSS/JavaScript、Pillow、aiohttp；FAISS/向量模型只作为可选语义加速器，不作为核心功能依赖。

## Global Constraints

- 保持插件 ID `meme_manager_master`、现有命令、核心 WebUI URL、pack 目录结构和已有 JSON 字段兼容。
- 明确索图成功时默认只发送图片；自动发表情时保留机器人原始正文，不添加固定成功套话。
- 普通情绪对话可以主动发表情；`explicit_request=false` 只表示不是强制请求，不表示禁止发送。
- 明确请求继续绕过自动发送概率；普通自动发送仍受情景判断、冷却、概率和会话锁约束。
- Private Companion 为软依赖：未安装、未加载、API 版本不兼容或调用失败时，本插件必须降级运行，不能阻塞普通消息处理。
- 不让两个插件各自独立调度同一类主动表情；主动时机由 Private Companion 统一编排，图片能力由本插件提供。
- 所有 JSON 状态写入必须使用同目录临时文件、`flush`、`fsync` 和 `os.replace`；同一 pack 的相关变更必须在同一写锁内完成。
- 批量操作每个受影响分类最多 reconcile 一次；不允许逐张图片触发全库扫描。
- 核心语义能力不依赖 `faiss-cpu`；未显式启用向量能力时不得注册向量任务 API 或启动向量重建。
- 不通过随机模板池掩盖回复问题；成功状态由图片或原始正文表达，固定文案只用于确定性失败状态。
- 不直接读取 Private Companion 私有字段，不直接修改对方数据文件，不依赖对方插件的内部定时器。
- 每项代码改动按 RED → GREEN → 回归测试执行；每个阶段有独立提交边界。
- 本文是统一重构流程；执行前先创建隔离 worktree，并在每个阶段完成后执行验证门禁。

---

## 1. 当前基线与问题定义

当前仓库已经具备若干基础模块：`backend/atomic_io.py`、`backend/catalog_index_service.py`、`backend/pack_repository.py`、`mixins/web_routes.py`、`pages/a_manage/*`、`pages/semantic/*` 和一批回归测试。但这些能力仍存在“模块存在、运行链不一致”的问题，后续必须以运行时行为为准重新收口。

### 1.1 WebUI 问题

- 路由表已经有 capability 概念，但“核心目录语义能力”和“可选向量能力”仍容易混为一个开关，导致语义页面或接口在向量依赖缺失时不可用。
- 管理页面由多个脚本组成，但入口、状态、API、弹窗和渲染之间仍有隐式全局状态；请求竞态、重复刷新、失败后状态回滚和空数据展示需要统一。
- 分类、图片、pack、设置和语义复核页面的响应字段缺少统一 envelope，前端需要猜测不同接口的成功/失败结构。
- 上传、批量移动、删除、重命名和索引任务缺少一致的 loading、取消、冲突和错误提示。
- 图片预览、分类列表、语义标签和状态消息需要使用稳定的可访问结构；用户应能看见当前 pack、当前任务、失败原因和可恢复动作。
- 前端写入用户或图片元数据时必须避免把外部内容直接作为 HTML 解释；静态模板可以使用 `innerHTML`，动态值统一使用 `textContent`、`value` 或属性 setter。

### 1.2 语义能力问题

本插件的“语义化”应分成两层，不能再把它们混称：

1. **运行时语义选图：** 根据用户消息、机器人回复、关系/场景和图片语义标签选择合适表情包。
2. **图库语义管理：** 为图片建立可复核的分类、情绪、关键词、场景、描述和置信度，并在 WebUI 中查看、修正和重建。

当前代码中存在旧向量语义字段、手动语义接口和新的场景分类路径并存的情况；`semantic_enabled=False` 也不能等价于“语义能力已经完成”。目标是让目录语义和场景决策成为核心，让向量检索只作为可选加速器。

### 1.3 发送与生命周期问题

- 明确发送、普通自动发送、Agent continuation 和 `after_message_sent` 之间存在多条路径，容易出现重复发送、固定成功文案覆盖原回复或发送时机早于 Filter 分段结束。
- 发送声明必须有真实 receipt 支持；没有 receipt 时不能让模型继续声称已经发送成功。
- 已退役的旧语义启动 hook 不能继续被 AstrBot 生命周期扫描和调用。
- 采集、索引、分类、发送和 WebUI 写操作需要共享一致的存储边界，不能让不同入口分别修改同一份 pack 元数据。

### 1.4 Private Companion 联动问题

上游插件当前提供公开扩展 API，包括主动能力注册、场景上下文、实时上下文、外部活动状态和主动对话桥接。[扩展 API 源码](https://raw.githubusercontent.com/menglimi/astrbot_plugin_private_companion/main/main.py#L269-L525)

联动目标不是把两个插件揉成一个大模块，而是建立以下职责边界：

```text
Private Companion：关系、状态、场景、主动时机、主动消息配额
        │  request / context / activity
        ▼
Meme Manager：语义解析、候选检索、重复降权、图片发送、发送回执
        │
        └── 无 Companion 时仍可独立处理命令、自动发送和 WebUI
```

---

## 2. 目标运行时流程

### 2.1 普通对话自动发表情

```text
收到消息
  → 生成机器人正文
  → 读取当前会话/用户的 Companion 场景（可选）
  → 情景模型判断是否适合发表情
  → 不适合：只发送原正文
  → 适合：检查冷却
  → 检查自动发送概率
  → 获取会话发送锁
  → 按场景、情绪、分类和最近发送记录选择候选
  → 锁定图片
  → 等待正文及 Filter 后续分段全部发送
  → 发送图片并写入 receipt、活动状态和索引权重
```

### 2.2 明确索图

```text
识别明确索图意图
  → 强制进入语义选图
  → 忽略普通自动发送概率
  → 成功：只发送图片或保留已有正文，不增加成功套话
  → 失败：返回确定性失败状态
```

### 2.3 Private Companion 主动发图

```text
Private Companion 判断适合主动联系用户
  → 选择 meme_manager_master 的外部主动能力
  → 传入 user_id / session_id / purpose / scene
  → Meme Manager 获取 Companion 实时上下文并执行语义选图
  → 通过当前会话发送图片
  → 回传 sent / skipped / failed 和原因
  → Companion 记录主动行为，不再重复触发同一次表情
```

### 2.4 WebUI 数据流

```text
浏览器
  → 统一 api client（请求 ID、超时、取消、错误 envelope）
  → 稳定 Web route
  → capability 检查
  → service / repository
  → 原子写入与索引更新
  → 返回统一结果
  → state reducer 更新页面
  → toast / inline error / empty state
```

---

## 3. 目标文件结构与职责

以下是重构完成后的职责边界。迁移期间可以由旧模块调用新模块，但新模块不能反向依赖旧的巨型入口。

```text
meme_manager_master/
├── main.py                              # AstrBot 注册、生命周期和公开命令
├── capture.py                           # 事件编排、发送锁、发送回执
├── meme_selection.py                    # 语义决策和候选选择门面
├── collector.py                          # 场景提示词、收集协议、文本清洗
├── response_policy.py                    # 成功/失败可见回复策略
├── runtime_config.py                     # 类型化配置和旧配置迁移
├── integrations/
│   ├── __init__.py
│   └── private_companion.py              # Private Companion 公开 API 适配器
├── backend/
│   ├── atomic_io.py                      # 唯一原子文件写入实现
│   ├── pack_repository.py                # pack 级事务、锁和回滚
│   ├── catalog_index_service.py          # 目录语义索引和 reconcile
│   ├── semantic_models.py                # 语义记录、决策和复核状态
│   ├── semantic_query.py                 # 关键词/标签/向量可插拔检索
│   ├── semantic_task.py                  # 可选后台语义任务
│   └── vector_semantic_service.py        # FAISS 可选加速器
├── mixins/
│   ├── web_api.py                        # API 组合门面
│   ├── web_routes.py                     # 声明式路由与 capability
│   ├── emoji_api.py                      # 图片、分类和预览接口
│   ├── pack_api.py                       # pack、导入、导出、备份接口
│   └── semantic_api.py                   # 核心语义管理与向量可选接口
├── pages/
│   ├── a_manage/                         # 统一管理台
│   ├── semantic/                         # 语义复核和任务页
│   ├── catalog/                          # 目录浏览
│   └── settings/                         # 配置页
└── tests/
    ├── test_private_companion_integration.py
    ├── test_semantic_selection.py
    ├── test_webui_state_contract.py
    ├── test_web_api_behavior.py
    └── ...
```

---

## 4. 分阶段实施流程

### Task 0: 建立隔离分支、基线和回滚点

**Files:**

- Create: 独立 git worktree，不修改当前工作目录
- Read: `README.md`、`CONFIGURATION.md`、`metadata.yaml`、`_conf_schema.json`
- Verify: `tests/`、`pages/`、`backend/`、`mixins/`

**Interfaces:**

- Produces: 基线测试报告、工作区状态记录和阶段分支。
- Consumes: 当前仓库已有测试和配置，不改变业务代码。

- [ ] **Step 1: 记录当前状态**

  ```text
  git status --short
  git branch --show-current
  python -m unittest discover -s tests -v
  python -m compileall -q .
  git diff --check
  ```

- [ ] **Step 2: 创建隔离 worktree**

  使用 `using-git-worktrees` skill 创建以 `codex/` 开头的工作分支。若当前目录存在未提交用户改动，先保留，不使用 reset、checkout 或覆盖操作。

- [ ] **Step 3: 固定验证门禁**

  后续每个 Task 完成后都运行：

  ```text
  python -m unittest discover -s tests -v
  python -m compileall -q .
  git diff --check
  git status --short
  ```

- [ ] **Step 4: 提交基线记录**

  只提交新增的流程记录或在工作分支上保留基线结果，不提交用户已有的无关改动。

### Task 1: 固化发送行为和回复策略

**Files:**

- Create/Modify: `response_policy.py`
- Modify: `capture.py`
- Modify: `collector.py`
- Modify: `meme_selection.py`
- Test: `tests/test_response_policy.py`
- Test: `tests/test_capture_dispatch_behavior.py`
- Test: `tests/test_outgoing_scene_prompt.py`
- Test: `tests/test_explicit_meme_dispatch.py`

**Interfaces:**

- `success_reply_text(existing_text: str | None = None) -> str`
- `failure_reply_text(reason: str) -> str`
- `SceneDecision(should_send: bool, category: str, confidence: float, reason: str)`
- 明确请求、普通自动发送、Private Companion 主动发送都必须进入同一图片发送门面。

- [ ] **Step 1: 为成功和失败状态写 RED 测试**

  覆盖：明确索图成功无固定套话；自动发送保留原正文；图库为空、管理器不可用、无发送凭证分别返回确定性失败状态；发送声明无 receipt 时被拦截。

- [ ] **Step 2: 修正情景提示词契约**

  在 `collector.py` 保留以下规则：

  ```text
  explicit_request=true 时必须发送。
  explicit_request=false 只表示不是强制请求，不表示禁止发送。
  惊讶、开心、赞叹、调侃、吐槽、安慰、尴尬、无奈等明显社交情绪可以主动发送。
  纯事实、错误提示、长篇严肃内容和完全无情绪内容可以不发送。
  ```

  移除固定为 `should_send=false` 的示例，避免模型照抄默认拒绝。

- [ ] **Step 3: 统一成功输出策略**

  显式成功路径只返回图片组件或原有正文加图片；删除“找到了一个合适的表情包，发给你啦”类硬编码成功句式。失败文案集中在 `response_policy.py`，不额外调用模型生成成功说明。

- [ ] **Step 4: 修正自动发送顺序**

  正常回复必须先经过情景判断，再依次经过冷却、概率、发送锁和选图；明确请求仍绕过普通概率。场景判断失败时保持不发送并记录原因。

- [ ] **Step 5: 运行行为测试并提交**

  ```text
  python -m unittest tests.test_response_policy tests.test_capture_dispatch_behavior tests.test_outgoing_scene_prompt tests.test_explicit_meme_dispatch -v
  git diff --check
  git add response_policy.py capture.py collector.py meme_selection.py tests/test_response_policy.py tests/test_capture_dispatch_behavior.py tests/test_outgoing_scene_prompt.py tests/test_explicit_meme_dispatch.py
  git commit -m "fix: unify meme dispatch response policy"
  ```

### Task 2: 收口原子写入、活动日志和 pack 事务

**Files:**

- Modify: `backend/atomic_io.py`
- Modify: `backend/pack_repository.py`
- Modify: `backend/pack_storage.py`
- Modify: `storage.py`
- Modify: `capture_activity.py`
- Modify: `utils.py`
- Test: `tests/test_atomic_io.py`
- Test: `tests/test_capture_activity_concurrency.py`
- Test: `tests/test_pack_repository.py`
- Test: `tests/test_batch_reconcile.py`

**Interfaces:**

- `atomic_write_bytes(path: Path, content: bytes) -> None`
- `atomic_write_json(path: Path, data: Mapping[str, Any]) -> None`
- `PackRepository` 负责分类、图片、metadata 和 index 的事务边界。
- `BatchMutationResult` 统一描述 succeeded、missing、conflicting。

- [ ] **Step 1: 注入原子写入失败并写 RED 测试**

  验证序列化失败、磁盘写失败和替换失败时旧文件仍可读，临时文件被清理。

- [ ] **Step 2: 为同一 pack 建立 RLock**

  分类重命名、删除、图片替换、批量移动/复制/删除和 metadata 写入必须使用同一 pack 锁；活动日志按规范化目录路径使用独立 RLock，读—改—写全过程在锁内完成。

- [ ] **Step 3: 实现可回滚 mutation**

  先校验安全路径和目标冲突，再执行同盘临时移动或原子替换；metadata 保存失败时恢复旧目录、旧图片和旧索引状态。

- [ ] **Step 4: 限制 reconcile 次数**

  批量操作只对源分类和目标分类各 reconcile 一次；单张图片不能触发全库扫描。

- [ ] **Step 5: 运行并发和故障注入测试**

  ```text
  python -m unittest tests.test_atomic_io tests.test_capture_activity_concurrency tests.test_pack_repository tests.test_batch_reconcile -v
  git add backend/atomic_io.py backend/pack_repository.py backend/pack_storage.py storage.py capture_activity.py utils.py tests/test_atomic_io.py tests/test_capture_activity_concurrency.py tests/test_pack_repository.py tests/test_batch_reconcile.py
  git commit -m "fix: make pack state writes atomic and transactional"
  ```

### Task 3: 重建核心语义模型和运行时选图链

**Files:**

- Modify: `backend/semantic_models.py`
- Modify: `backend/catalog_index_service.py`
- Modify: `backend/semantic_query.py`
- Modify: `meme_selection.py`
- Modify: `collector.py`
- Modify: `capture.py`
- Modify: `runtime_config.py`
- Modify: `_conf_schema.json`
- Create: `tests/test_semantic_selection.py`
- Modify: `tests/test_runtime_config.py`

**Interfaces:**

- `SemanticMemeRecord`：`id`、`pack_id`、`category`、`filename`、`description`、`keywords`、`emotions`、`scenes`、`confidence`、`review_state`、`updated_at`。
- `SceneDecision`：`should_send`、`category`、`candidate_id`、`confidence`、`reason`、`source`。
- `SemanticQuery.search(query, *, category, limit, exclude_ids) -> list[SemanticMemeRecord]`。
- `MemeSelectionService.choose(event, response_text, force_send, context) -> SelectionResult`。

- [ ] **Step 1: 为语义记录和兼容读取写 RED 测试**

  覆盖旧 `index.json` 的 `images`、`entries`、`memes`、`data` 顶层结构、BOM、缺省字段和不存在的语义标签；读取后统一投影为 `SemanticMemeRecord`，写回时保持旧字段兼容。

- [ ] **Step 2: 定义目录语义为核心能力**

  目录索引至少保存分类、情绪、关键词、场景、简短描述、来源和复核状态。没有 FAISS 时仍能使用关键词、标签、分类和最近发送降权完成语义选择。

- [ ] **Step 3: 统一决策顺序**

  `explicit_request`、场景模型、Companion 上下文、分类候选、重复窗口和发送概率必须由一个 service 编排；旧的 legacy 单次多模态路径只能作为兼容 fallback，不得与新路径并行发送。

- [ ] **Step 4: 恢复“有语义但不依赖向量”的默认行为**

  默认 `vector_semantic_enabled=false` 时：目录语义、场景识别、候选标签和 WebUI 语义复核可用；仅向量重建、向量查询和 FAISS 任务不注册。

- [ ] **Step 5: 接入发送反馈**

  发送成功后更新 `send_count`、`last_sent_at` 和 receipt；发送失败不更新成功权重。最近图片必须降权，不能简单随机选图。

- [ ] **Step 6: 验证语义场景**

  ```text
  python -m unittest tests.test_semantic_selection tests.test_runtime_config tests.test_outgoing_scene_prompt -v
  python -m compileall -q .
  ```

- [ ] **Step 7: 提交**

  ```text
  git add backend/semantic_models.py backend/catalog_index_service.py backend/semantic_query.py meme_selection.py collector.py capture.py runtime_config.py _conf_schema.json tests/test_semantic_selection.py tests/test_runtime_config.py
  git commit -m "feat: restore catalog semantic selection pipeline"
  ```

### Task 4: 修复 WebUI 路由 capability 和统一 API 协议

**Files:**

- Modify: `mixins/web_routes.py`
- Modify: `mixins/web_api.py`
- Modify: `mixins/emoji_api.py`
- Modify: `mixins/pack_api.py`
- Modify: `mixins/semantic_api.py`
- Modify: `manager_base.py`
- Create/Modify: `tests/test_web_route_capabilities.py`
- Create/Modify: `tests/test_web_api_behavior.py`

**Interfaces:**

- Capability 集合至少区分 `core`、`catalog_semantic`、`vector_semantic`、`private_companion`。
- 所有 API 返回统一 envelope：`{ok: bool, data: object|null, error: {code, message, retryable}|null, request_id: string}`。
- 非法路径返回 400/403，资源不存在返回 404，冲突返回 409，过大预览返回 413，能力未启用返回 503 或明确的 capability 错误。

- [ ] **Step 1: 写 capability RED 测试**

  默认没有 FAISS 时断言核心语义路由仍注册；向量任务路由不注册。Private Companion 缺失时不影响核心路由。

- [ ] **Step 2: 保持旧 URL，重构内部 handler**

  继续保留现有前端使用的路径；只统一 envelope、参数校验和错误码，不让前端承担旧新字段兼容判断。

- [ ] **Step 3: 统一文件安全策略**

  category、filename、pack_id 必须经过单路径段校验和根目录约束；图片 API 只允许读取图片文件；任何异常响应不得泄漏绝对路径或 traceback。

- [ ] **Step 4: 增加语义管理 API**

  核心接口包括语义状态、条目列表、单条复核、分类确认、描述保存、capture workspace；向量重建、暂停、恢复、重试和清理接口仅在 `vector_semantic` 开启时注册。

- [ ] **Step 5: 验证**

  ```text
  python -m unittest tests.test_web_route_capabilities tests.test_web_api_behavior tests.test_image_preview_policy -v
  ```

- [ ] **Step 6: 提交**

  ```text
  git add mixins/web_routes.py mixins/web_api.py mixins/emoji_api.py mixins/pack_api.py mixins/semantic_api.py manager_base.py tests/test_web_route_capabilities.py tests/test_web_api_behavior.py
  git commit -m "fix: separate core semantic and vector web capabilities"
  ```

### Task 5: 重构 WebUI 状态、请求和语义化界面

**Files:**

- Modify: `pages/a_manage/api.js`
- Modify: `pages/a_manage/state.js`
- Modify: `pages/a_manage/dialogs.js`
- Modify: `pages/a_manage/emoji.js`
- Modify: `pages/a_manage/pack.js`
- Modify: `pages/a_manage/script.js`
- Modify: `pages/a_manage/index.html`
- Modify: `pages/a_manage/style.css`
- Modify: `pages/semantic/index.html`
- Modify: `pages/semantic/script.js`
- Modify: `pages/semantic/style.css`
- Create: `tests/test_webui_state_contract.py`

**Interfaces:**

- `window.MemeManagerUI` 是唯一前端命名空间。
- `apiRequest(path, options) -> Promise<{ok, data, error, request_id}>` 负责超时、取消、JSON 解析和错误归一化。
- State 至少包含 `loading`、`error`、`currentPack`、`categories`、`items`、`semanticStatus`、`pendingMutation` 和 `selection`。

- [ ] **Step 1: 先写前端契约测试**

  静态检查脚本加载顺序、统一命名空间、动态内容不直接拼接 HTML、API 失败能进入 error state、重复点击同一 mutation 不会重复提交。

- [ ] **Step 2: 统一 API client**

  所有 fetch 通过一个 client；每个请求生成 request ID；支持 `AbortController`、超时、取消、非 JSON 错误和服务器 envelope；旧响应字段只在 client 适配一次。

- [ ] **Step 3: 统一状态和竞态处理**

  以 request token 或 AbortController 丢弃过期响应；保存/删除/移动期间锁定相关控件；成功后只刷新受影响 pack/分类，不做全页盲目 reload。

- [ ] **Step 4: 修复 WebUI 可见问题**

  为空列表、加载中、失败、部分成功、冲突和无语义条目提供明确状态；所有 destructive 操作有确认弹窗；批量操作展示成功、缺失、冲突三类结果。

- [ ] **Step 5: 恢复语义管理体验**

  语义页展示分类、情绪、关键词、场景、描述、置信度、来源、复核状态和最后更新时间；用户可批量确认/修改语义；向量未启用时页面仍可使用目录语义功能，并明确显示“向量加速未启用”。

- [ ] **Step 6: 改善 HTML 语义和可访问性**

  使用 `main`、`nav`、`section`、`form`、`button`、`label`、`table` 或明确的列表结构；表单控件有 label；状态变化写入 `aria-live`；图片预览有 alt；动态用户内容使用 `textContent` 或属性 setter。

- [ ] **Step 7: 验证**

  ```text
  python -m unittest tests.test_webui_state_contract tests.test_capture_index_page -v
  node --check pages/a_manage/api.js
  node --check pages/a_manage/state.js
  node --check pages/a_manage/dialogs.js
  node --check pages/a_manage/emoji.js
  node --check pages/a_manage/pack.js
  node --check pages/a_manage/script.js
  node --check pages/semantic/script.js
  ```

- [ ] **Step 8: 提交**

  ```text
  git add pages/a_manage/api.js pages/a_manage/state.js pages/a_manage/dialogs.js pages/a_manage/emoji.js pages/a_manage/pack.js pages/a_manage/script.js pages/a_manage/index.html pages/a_manage/style.css pages/semantic/index.html pages/semantic/script.js pages/semantic/style.css tests/test_webui_state_contract.py
  git commit -m "fix: stabilize semantic management WebUI"
  ```

### Task 6: 建立 Private Companion 双向适配层

**Files:**

- Create: `integrations/__init__.py`
- Create: `integrations/private_companion.py`
- Modify: `main.py`
- Modify: `manager_base.py`
- Modify: `capture.py`
- Modify: `meme_selection.py`
- Modify: `runtime_config.py`
- Modify: `_conf_schema.json`
- Create: `tests/test_private_companion_integration.py`

**Interfaces:**

- `PrivateCompanionAdapter(context, logger) -> adapter`
- `adapter.available -> bool`
- `await adapter.get_context(user_id, purpose) -> CompanionContext`
- `adapter.register_meme_ability(handler) -> bool`
- `adapter.unregister_meme_ability() -> None`
- `await adapter.notify_activity_started(...)`
- `await adapter.notify_activity_ended(...)`
- `await adapter.execute_meme_ability(request) -> MemeAbilityResult`

本插件对外注册的主动能力使用稳定名称 `meme_manager_master.send_reaction_image`，描述明确包括：根据当前场景从本地表情包库选择并发送一张图片；不生成新图片；失败时返回原因；调用方不得重复发送同一结果。能力 spec 至少包含 `name`、`label`、`description`、`source_plugin`、`handler`、`when`、`avoid`，由 adapter 映射到上游当前版本接受的字典结构。

- [ ] **Step 1: 为未安装、加载失败和 API 缺失写 RED 测试**

  fake context 没有 Companion 时，adapter 返回 unavailable；fake API 缺少某个方法时只关闭对应能力，不影响本插件普通命令、场景选图和 WebUI。

- [ ] **Step 2: 只依赖公开发现方式**

  适配器按以下顺序寻找已加载插件的公开 API：AstrBot 注册插件对象上的 `extension_api`；插件模块公开的 `get_private_companion_api()`；都不可用时返回 unavailable。不得读取 `_external_proactive_abilities`、`_plugin` 或其他私有字段。

- [ ] **Step 3: 注册外部主动能力**

  插件初始化完成后异步或延迟注册 `meme_manager_master.send_reaction_image`；卸载时调用 `unregister_proactive_ability`。注册失败只记录一次 warning，并标记联动不可用，避免每条消息重复刷日志。

- [ ] **Step 4: 读取 Companion 上下文**

  在语义选图前调用 `get_realtime_context(user_id, purpose="meme_reaction")`；只把返回的场景、关系、情绪、边界和共同活动作为内部决策输入，不把后台字段原样发送给用户。调用超时或异常时使用空上下文。

- [ ] **Step 5: 实现 Companion → Meme Manager**

  外部能力请求必须包含 `user_id`、`session_id`、`purpose`、`query`、`force` 和可选 `context`。handler 使用统一 `MemeSelectionService`，成功通过当前会话发送图片并返回 `sent=true`、图片 ID、category 和 reason；无候选返回 `sent=false` 和可重试原因。

- [ ] **Step 6: 实现 Meme Manager → Companion**

  图片选择/发送开始时通知外部活动，成功或失败时结束活动；活动 metadata 只包含 activity_id、user_id、category、meme_id、source 和结果，不包含图片绝对路径或敏感原文。

- [ ] **Step 7: 防止双重主动发送**

  当事件来源为 Companion external proactive 时，跳过本插件自己的普通主动概率链；使用统一会话锁、冷却和 receipt。若同一请求已有图片 receipt，外部能力返回已有结果而不再发送第二张。

- [ ] **Step 8: 配置联动开关**

  增加 `private_companion_integration_enabled`、`private_companion_proactive_ability_enabled`、`private_companion_context_enabled` 和 `private_companion_activity_enabled`。默认开启“可发现但不强制依赖”，主动能力和上下文读取可分别关闭。

- [ ] **Step 9: 验证**

  ```text
  python -m unittest tests.test_private_companion_integration tests.test_capture_dispatch_behavior tests.test_runtime_config -v
  ```

  测试必须覆盖：未安装、API 异常、注册失败、上下文超时、成功发送、无候选、重复请求和卸载清理。

- [ ] **Step 10: 提交**

  ```text
  git add integrations/__init__.py integrations/private_companion.py main.py manager_base.py capture.py meme_selection.py runtime_config.py _conf_schema.json tests/test_private_companion_integration.py
  git commit -m "feat: integrate private companion through public adapter"
  ```

### Task 7: 修复 Filter 分段、生命周期和发送回执

**Files:**

- Modify: `main.py`
- Modify: `capture.py`
- Modify: `tests/test_filter_followup_lock.py`
- Modify: `tests/test_lifecycle_hook_registration.py`
- Modify: `tests/test_legacy_tag_dispatch.py`

**Interfaces:**

- 事件 extra key：`astrbot_plugin_filter_reply_lock`。
- 发送回执 key：`meme_manager_master_send_receipt`。
- `wait_for_reply_segments(event, timeout=30.0) -> None`。

- [ ] **Step 1: 测试共享回复锁**

  覆盖无锁、已释放锁、占用后释放、超时和取消；表情插件只能等待和释放自己取得的锁，不能释放 Filter 原来持有的锁。

- [ ] **Step 2: 让 Filter 传递事件级锁**

  Filter 获得会话锁后通过 `event.set_extra` 暴露同一对象；表情插件只通过事件 extra 读取，不轮询 Filter 私有字段，不使用固定 sleep 猜测分段结束。

- [ ] **Step 3: 调整发送顺序**

  `after_message_sent` 先等待所有后续文本分段，再发送自动图片；超时记录 warning 后继续，插件终止或任务取消时保留取消语义。

- [ ] **Step 4: 清理退役语义启动 hook**

  删除未绑定的旧 `on_astrbot_loaded` 语义重建注册、只服务该任务的字段和 cleanup；保留手动语义任务接口和正常关闭逻辑。不得在 `MemeManager` 中添加替代的未绑定启动 hook。

- [ ] **Step 5: 验证**

  ```text
  python -m unittest tests.test_filter_followup_lock tests.test_lifecycle_hook_registration tests.test_legacy_tag_dispatch -v
  python -m compileall -q .
  ```

- [ ] **Step 6: 提交**

  ```text
  git add main.py capture.py tests/test_filter_followup_lock.py tests/test_lifecycle_hook_registration.py tests/test_legacy_tag_dispatch.py
  git commit -m "fix: serialize segmented replies and remove retired startup hook"
  ```

### Task 8: 拆分核心模块并替换源码字符串测试

**Files:**

- Create: `capture_pipeline.py`
- Create: `meme_selection_service.py`
- Create: `mixins/web_routes_core.py`
- Create: `mixins/web_routes_semantic.py`
- Create: `pages/a_manage/view_state.js`
- Modify: `capture.py`
- Modify: `meme_selection.py`
- Modify: `mixins/web_api.py`
- Modify: `pages/a_manage/script.js`
- Modify: `tests/test_module_boundaries.py`
- Modify: `tests/fakes.py`

**Interfaces:**

- `CapturePipeline.process_batch(event, sources, message_text, outline) -> list[str]`
- `MemeSelectionService.choose(event, response_text, force_send, context) -> SelectionResult`
- `WebApiRouter.register(spec: WebRouteSpec) -> None`
- 前端所有共享对象挂载到 `window.MemeManagerUI`，不再新增散落的隐式全局变量。

- [ ] **Step 1: 先增加模块边界测试**

  断言：`capture_pipeline.py` 不注册 AstrBot filter；`meme_selection_service.py` 不导入 WebUI request/jsonify；API 模块不直接执行 `shutil` 删除或 JSON 写入；页面入口不直接实现所有 API 请求。

- [ ] **Step 2: 提取 CapturePipeline**

  将采集、批处理、视觉识别和分类结果回填移入 pipeline；`capture.py` 只保留事件过滤、任务生命周期、发送锁和结果绑定。

- [ ] **Step 3: 提取 MemeSelectionService**

  将场景决策、候选限制、语义检索、重复降权和 Companion context 合并为纯服务；返回结构化 `SelectionResult`，不直接修改 AstrBot event。

- [ ] **Step 4: 拆分 Web API 与管理页入口**

  保持 URL 和外部字段兼容，按 core/pack/semantic 分离 handler；页面按 api/state/dialog/view 拆分，每一步后运行页面语法检查。

- [ ] **Step 5: 用行为测试替换关键源码测试**

  Fakes 只实现生产代码实际读取的属性和方法，缺失属性必须抛 `AttributeError`。源码断言只保留禁止旧成功文案、禁止退役 hook、禁止私有 Companion 字段访问和模块边界规则。

- [ ] **Step 6: 验证并提交**

  ```text
  python -m unittest tests.test_module_boundaries tests.test_log_noise tests.test_web_api_behavior -v
  python -m unittest discover -s tests -v
  git diff --check
  git add capture_pipeline.py meme_selection_service.py mixins/web_routes_core.py mixins/web_routes_semantic.py pages/a_manage/view_state.js capture.py meme_selection.py mixins/web_api.py pages/a_manage/script.js tests/test_module_boundaries.py tests/fakes.py
  git commit -m "refactor: split capture selection and WebUI boundaries"
  ```

### Task 9: 完整验收、文档和兼容性回归

**Files:**

- Modify: `README.md`
- Modify: `CONFIGURATION.md`
- Modify: `CHANGELOG.md`
- Modify: `_conf_schema.json`
- Modify: `metadata.yaml`（仅在实际最低版本验证通过后）
- Create: `docs/private-companion-integration.md`
- Create: `docs/webui-semantic-guide.md`
- Create: `tests/test_acceptance_matrix.py`

**Interfaces:**

- README 必须说明：核心语义与向量语义的区别、Private Companion 为可选依赖、联动开关、降级行为和调试方式。
- 配置 schema、运行时读取、WebUI 表单和文档中的键名必须一致。

- [ ] **Step 1: 运行完整自动化验证**

  ```text
  python -m unittest discover -s tests -v
  python -m compileall -q .
  python scripts/generate_conf_schema.py --check
  git diff --check
  ```

- [ ] **Step 2: 执行 WebUI 手动验收**

  在真实 AstrBot WebUI 中验证：pack 切换、分类浏览、图片预览、上传、批量移动/复制/删除、分类重命名、语义复核、设置保存、失败重试和任务状态刷新。

- [ ] **Step 3: 执行消息链手动验收**

  验证：明确索图、普通惊讶/开心/吐槽场景、中性事实说明、图库为空、重复窗口、自动发送冷却、Filter 分段、无发送 receipt 的声明拦截和插件终止。

- [ ] **Step 4: 执行 Companion 联动验收**

  分别验证：未安装、已安装但未启用、API 注册成功、上下文成功、API 超时、主动能力成功、无候选、重复请求、卸载清理。检查日志中不出现重复发送，也不出现绝对路径或隐私原文。

- [ ] **Step 5: 验证可选依赖矩阵**

  | 环境 | 预期 |
  |---|---|
  | 未安装 FAISS、未安装 Companion | 核心 WebUI、命令、采集、目录语义和自动发送可用 |
  | 未安装 FAISS、已安装 Companion | 双向 Companion 联动可用，向量任务不注册 |
  | 安装 FAISS、向量开关关闭 | 核心语义可用，向量任务不启动 |
  | 安装 FAISS、向量开关开启 | 向量路由和后台任务可用，失败可重试 |
  | Companion API 异常 | 本插件降级独立运行，并记录一次可诊断 warning |

- [ ] **Step 6: 完成提交前检查**

  ```text
  git status --short
  git diff --stat
  git diff --check
  rg -n "找到一个合适的表情包|找到了一个合适的表情包" .
  rg -n "_external_proactive_abilities|_plugin|_private_companion_plugin" integrations main.py capture.py meme_selection.py
  ```

  第一条旧文案搜索必须无业务代码命中；第二条只能出现合法的适配器兼容说明或测试 fake，不得出现对方私有字段读取。

- [ ] **Step 7: 标记版本和发布说明**

  只有真实 AstrBot 运行验收通过后才更新最低版本或插件版本；不为了联动强行提高版本约束。

---

## 5. 验收矩阵

### 5.1 发送行为

| 场景 | 预期 |
|---|---|
| `发一个猫猫表情包` | 成功时只发送匹配图片，不出现成功套话 |
| 普通惊讶/开心/吐槽回复 | 情景模型可允许主动发送，保留原正文 |
| 纯事实说明 | 不发送图片，只保留正文 |
| `auto_send_probability=0` 的明确索图 | 仍发送，因为明确请求绕过普通概率 |
| 最近发送过同图 | 重复降权或换候选，不重复发同图 |
| Filter 分段回复 | 等全部文本分段发送后再发图片 |
| 无发送 receipt 但正文声称已发送 | 改写为未成功发送的确定性状态 |

### 5.2 WebUI

| 场景 | 预期 |
|---|---|
| 空图库/空分类 | 显示 empty state，不显示空白页面或 JS 异常 |
| API 超时/网络断开 | 显示可读错误和重试，不锁死页面 |
| 并发刷新 | 旧响应不会覆盖新 pack/分类状态 |
| 非法文件名/路径 | 400/403，不访问根目录外文件 |
| 批量冲突 | 返回 409 和逐项结果，不丢失其他成功项 |
| 无 FAISS | 核心语义页可用，向量任务明确显示未启用 |
| 动态文本含 HTML | 以文本显示，不执行脚本或改变页面结构 |

### 5.3 Companion

| 场景 | 预期 |
|---|---|
| Companion 未安装 | 本插件完全独立工作 |
| Companion 已安装但 API 不可用 | 联动关闭，核心功能不受影响 |
| Companion 主动触发表情 | 只由统一 handler 发送一次图片 |
| 本插件读取 Companion 场景失败 | 使用本地消息和默认语义，不阻塞发送 |
| Companion 请求重复提交 | 由 request/session lock/receipt 去重 |
| 本插件卸载 | 注销主动能力，清理活动，不留下后台任务 |

---

## 6. 完成定义

以下条件全部满足才算完成统一重构：

- WebUI 核心路由、语义路由和向量路由按 capability 正确区分。
- 语义选择在无 FAISS 时仍可用，且语义条目可在 WebUI 中查看、复核和修正。
- 明确索图、普通自动发送、Companion 主动发送共用同一个选择和发送门面。
- 没有重复主动发送、固定成功套话、无 receipt 成功声明或 Filter 分段提前发送。
- 所有 pack/活动 JSON 写入原子化，并发和故障注入测试稳定通过。
- 批量 mutation 不逐图全库 reconcile，失败可回滚，旧 pack 数据无需迁移即可读取。
- Private Companion 通过公开 API 适配器联动，不读取私有字段，不修改对方数据，不成为硬依赖。
- `capture.py`、`mixins/web_api.py`、`pages/a_manage/script.js` 的职责完成拆分，模块边界测试通过。
- `unittest`、`compileall`、schema check、JavaScript 语法检查和 `git diff --check` 全部通过。
- 真实 AstrBot 中完成 WebUI、消息发送、Filter 分段、可选依赖和 Companion 联动验收。
- README、配置文档、联动说明和变更日志与实际功能一致。

---

## 7. 执行顺序与停靠点

推荐按以下顺序执行，不把所有改动压成一次大重写：

```text
Task 0 基线
  → Task 1 发送行为
  → Task 2 存储事务
  → Task 3 核心语义
  → Task 4 WebUI API/capability
  → Task 5 WebUI 页面
  → Task 6 Companion 联动
  → Task 7 生命周期/Filter
  → Task 8 模块拆分
  → Task 9 完整验收
```

每个箭头处都应完成测试和提交。若某一阶段失败，只回滚该阶段提交，不跨阶段修改已经验证过的存储协议和发送回执契约。

## 8. 外部参考

- [Private Companion 仓库](https://github.com/menglimi/astrbot_plugin_private_companion)
- [Private Companion `main.py` 扩展 API](https://raw.githubusercontent.com/menglimi/astrbot_plugin_private_companion/main/main.py#L269-L525)
- [Private Companion README 的第三方插件桥接说明](https://raw.githubusercontent.com/menglimi/astrbot_plugin_private_companion/main/README.md#L364-L411)
- 本仓库现有设计：`docs/superpowers/specs/2026-07-31-proactive-scene-meme-decision-design.md`
- 本仓库现有设计：`docs/superpowers/specs/2026-07-31-auto-send-scene-design.md`
- 本仓库现有设计：`docs/superpowers/specs/2026-07-31-filter-followup-lock-integration-design.md`
- 本仓库现有设计：`docs/superpowers/specs/2026-07-31-disable-retired-semantic-startup-hook-design.md`
