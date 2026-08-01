# 安全与失效功能修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 修复审计中确认的路径、下载、上传、调用绑定和失效语义化功能问题，并为每项建立回归测试。

**Architecture:** 先在 backend 建立可复用的 pack ID/目录边界校验，再在 mixin 入口重复校验，形成纵深防御。图片下载和上传都采用有限流、真实格式验证、临时文件和原子替换；语义化按当前产品方向彻底移除残留 UI 与不可达代码。

**Tech Stack:** Python 3.9+、unittest、Pillow、aiohttp、requests、Quart、原生 JavaScript。

## Global Constraints

- 不改变现有 pack 数据格式和普通导入导出契约。
- 任何用户输入的 pack_id、URL、上传文件和输出目录都必须在入口与 backend 公共函数校验。
- 生产代码变更前必须有能复现原问题的失败测试。
- 默认拒绝不安全 URL、重定向、超大响应、伪图片和目录边界外路径。
- 语义化当前产品方向是移除；不得通过恢复半残路由或保留 removed 占位请求来掩盖失败。
- 不提交用户已有的 docs/SELF_CHECK_WORKFLOW.md 或审计文档之外的无关文件。

## 当前进度

- [x] Task 1：pack ID 与目录边界
- [x] Task 2：消息图片安全下载
- [x] Task 3：缺失 self 的真实绑定错误
- [x] Task 4：移除已失效的语义化 UI 和死代码
- [x] Task 5：WebUI 图片上传保护
- [x] Task 6：备份输出目录、GitHub 来源与归档响应上限
- [x] Task 7：最终交付前的审计文档回写与完整验证
- [x] Follow-up：选择规则、运行时 pack 解析、类别目录和运行时备份边界加固
- [x] Follow-up：导出响应路径脱敏与 WebUI 静态资源令牌回归验证

## 最终复测记录（2026-08-01）

- 全量测试：144/144 通过。
- Python 编译、schema、页面 JavaScript 语法和 `git diff --check`：通过。
- 新增回归覆盖：绝对/父级 `pack_id`、运行时解析器、导入类别名、聊天上传目录、归档 JSON/Base64 大小和导出路径脱敏。
- 未完成宿主集成验证：AstrBot 实际管理员鉴权/CSRF、DNS 重绑定和完整依赖环境的网络测试。

---

### Task 1: pack ID 与目录边界

**Files:**
- Modify: backend/pack_protocol.py
- Modify: backend/pack_storage.py
- Modify: mixins/pack_api.py
- Test: tests/test_pack_protocol.py
- Test: tests/test_pack_storage_runtime.py

**Interfaces:**
- 产生 validate_pack_id(value, label="pack_id") -> str 的统一 ID 校验。
- 产生 resolve_pack_directory(pack_id, require_exists=False) -> Path 的目录边界校验。
- get_pack_detail、set_default_pack、export_pack_archive、uninstall_pack 均使用上述接口。

- [ ] Step 1: 写失败测试，覆盖 ..、.、a/b、反斜杠、绝对路径、编码穿越和合法 ID。
- [ ] Step 2: 只运行新增测试，确认失败原因是当前函数接受非法路径。
- [ ] Step 3: 实现严格 ID 正则、resolve/relative_to 边界检查和直接子目录检查。
- [ ] Step 4: 在四个 backend 公共入口和 WebAPI 入口接入校验。
- [ ] Step 5: 运行 pack protocol/storage 相关测试，再运行全量测试。
- [ ] Step 6: 复查卸载测试中的 sentinel，确认边界外文件保持存在。

---

### Task 2: 消息图片安全下载

**Files:**
- Modify: mixins/event_handlers.py
- Modify: capture.py 或新增 backend/image_io.py（仅在复用现有逻辑确实需要时）
- Test: tests/test_event_handlers.py（若不存在则创建）
- Test: tests/test_collector_requests.py

**Interfaces:**
- 下载器只接受 HTTPS 和经过 DNS 公网地址检查的目标。
- 请求禁止自动重定向，检查 2xx 状态、Content-Length 和分块总字节数。
- 下载成功必须经过 Pillow/现有图片格式识别，只允许 png、jpg、jpeg、gif、webp。

- [ ] Step 1: 写失败测试，验证 CERT_NONE、HTTP、重定向、内网地址、超限和伪图片都会失败。
- [ ] Step 2: 运行测试确认旧 downloader 会接受至少一个危险输入。
- [ ] Step 3: 删除 TLS 禁用和 HTTP 降级，复用 capture.py 的安全目标检查与有限流下载。
- [ ] Step 4: 使用临时文件和真实图片格式验证，失败时删除临时文件。
- [ ] Step 5: 运行新增测试和现有 capture/collector 测试。
- [ ] Step 6: 进行一次静态扫描，确认 event_handlers.py 不再出现 CERT_NONE 或明文图片 URL 降级。

---

### Task 3: 修复缺失 self 的真实绑定错误

**Files:**
- Modify: mixins/web_api.py
- Modify: tests/test_web_api_behavior.py
- Test: tests/test_web_api_behavior.py

**Interfaces:**
- _save_uploaded_file(self, uploaded_file, destination) 保持异步接口。
- _pack_import_session_paths(self, token) 或明确声明为 staticmethod，调用方统一一致。
- _get_webui_response_status 的最终形态由调用关系决定：无调用则删除，有调用则保留正确绑定。

- [ ] Step 1: 写真实类实例调用测试，分别覆盖同步 save、异步 save、合法/非法 token。
- [ ] Step 2: 运行测试确认当前方法绑定会产生 TypeError。
- [ ] Step 3: 采用最小修改补 self 或 staticmethod，并统一调用方。
- [ ] Step 4: 运行 web API 测试和 pack import 相关测试。
- [ ] Step 5: 用 AST 检查所有 mixin 类方法的首参数和静态方法声明。

---

### Task 4: 移除已失效的语义化 UI 和死代码

**Files:**
- Modify: pages/a_manage/index.html
- Modify: pages/a_manage/emoji.js
- Modify: pages/a_manage/pack.js
- Modify: pages/a_manage/script.js
- Modify: pages/a_manage/state.js
- Modify: mixins/web_api.py
- Modify: mixins/event_handlers.py
- Modify: manager_base.py
- Test: tests/test_semantic_removal.py
- Test: tests/test_module_boundaries.py

- [ ] Step 1: 扩展静态失败测试，检查 semantic DOM、功能已移除、removed 请求、无条件抛错和 _resolve_embedding_provider 残留。
- [ ] Step 2: 运行新增测试确认当前旧控件或旧调用仍被命中。
- [ ] Step 3: 删除语义化 DOM、事件绑定、不可达函数体和旧 response 字段；保留必要的一次性清理迁移。
- [ ] Step 4: 更新测试为当前“语义化移除”的明确契约。
- [ ] Step 5: 运行 Python 测试和所有页面 JS 语法检查。

---

### Task 5: WebUI 图片上传保护

**Files:**
- Modify: backend/models.py
- Modify: mixins/emoji_api.py
- Test: tests/test_pack_storage_runtime.py
- Test: tests/test_web_api_behavior.py

- [ ] Step 1: 写失败测试，覆盖空文件、超限文件、伪图片、截断图片和正常 Pillow 图片。
- [ ] Step 2: 运行测试确认旧实现把伪图片写入资源目录。
- [ ] Step 3: 增加单文件大小上限、分块读取、Pillow verify、临时文件和 os.replace。
- [ ] Step 4: 确认校验失败不改变 catalog/index，重复图片行为保持不变。
- [ ] Step 5: 运行上传、catalog 和全量测试。

---

### Task 6: 远程 pack 与备份输出目录

**Files:**
- Modify: backend/pack_storage.py
- Modify: backend/pack_protocol.py
- Modify: mixins/pack_api.py
- Test: tests/test_pack_protocol.py
- Test: tests/test_pack_storage_runtime.py

- [ ] Step 1: 写失败测试，覆盖响应大小、严格来源描述、压缩包总大小、解压后文件类型和 output_dir 越界。
- [ ] Step 2: 运行测试确认旧实现无上限或接受越界目录。
- [ ] Step 3: 实现流式下载上限、严格 HTTPS/来源字段、解压内容白名单和受控备份根目录。
- [ ] Step 4: 保持官方 pack 正常安装、导出和运行时备份流程。
- [ ] Step 5: 运行远程 pack、备份和全量测试。

---

### Task 7: 总体验证与审计文档回写

**Files:**
- Modify: docs/CODE_AUDIT_REMEDIATION_PLAN.md

- [ ] Step 1: 运行 Python 编译、112+ 全量测试、schema、JS 语法和 git diff --check。
- [ ] Step 2: 运行路径、URL、语义化 removed 和未定义方法专项扫描。
- [ ] Step 3: 将已修复项、未完成项和环境限制回写审计文档。
- [ ] Step 4: 检查 git status，只保留本次修复相关变更和用户原有文档。
