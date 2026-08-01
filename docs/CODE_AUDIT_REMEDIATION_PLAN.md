# 本地代码安全与失效功能修复指南

审计日期：2026-08-01  
审计范围：backend/、mixins/、pages/、tests/、配置与依赖文件  
关联流程：SELF_CHECK_WORKFLOW.md

## 结论摘要（修复前基线）

当前代码可以通过现有编译、单元测试、配置 schema 和前端语法检查，但测试覆盖主要集中在 stub 和静态路径，不能证明真实上传、下载、导入、卸载及 WebUI 权限边界安全。

建议健康度暂评为 71/100：

- P1：2 项已确认的安全风险：pack ID 路径穿越/破坏性卸载；消息图片下载器关闭 TLS 校验、允许降级 HTTP 且无大小上限。
- P2：5 项高优先级可靠性或失效功能问题：三个缺失 self、语义化 UI/死代码残留、WebUI 上传缺少大小与内容校验、远程 pack 下载边界弱、备份输出路径缺少边界控制。
- P3：依赖未锁定、语义化模块残留等维护性问题。
- WebUI 鉴权/CSRF 暂列为“待宿主确认”，不能仅凭插件代码断言为漏洞。

本文件记录发现、证据、修复顺序和验收标准；后续实施结果见“本轮已实施修复”。

## 本轮已实施修复

本轮已在业务代码中完成并通过回归测试的批次：

- pack ID 统一校验和解析边界，详情、默认 pack、导出和卸载入口拒绝路径穿越。
- 消息图片下载改为 HTTPS、公网 DNS、禁止重定向、分块限流、真实格式验证和原子写入。
- 修复 WebAPI mixin 中三个缺失 self 的实例方法。
- 删除管理页旧语义化预览控件、向量重建占位函数和 removed 请求；阻断旧 backend provider 调用。
- WebUI 上传增加 10 MB 限制、Pillow 内容校验、扩展名匹配和原子写入。
- 备份输出目录限制在 BACKUP_DIR；GitHub 来源字段和归档响应增加结构/大小校验。
- 修复 WebUI 页面跳转未携带静态资源令牌的问题，避免表情索引、资源管理和设置页面误报“未授权”。
- 加固选择规则与运行时 pack 解析器的 `pack_id` 边界；导入清单类别和聊天上传目录使用统一安全目录解析。
- 为运行时备份 Base64、上传归档和 `registry.json`、`selection_rules.json`、`community_cache.json` 增加大小限制。
- 导出 JSON 响应移除本机绝对归档路径，仅保留归档文件名。

当前仍未在本地自动确认的项目：AstrBot 宿主实际提供的管理员鉴权与 CSRF 防护、DNS 重绑定场景，以及完整依赖环境中的真实网络集成测试。

## 复测结果（2026-08-01）

- 全量单元测试：144/144 通过。
- Python 编译、配置 schema、页面 JavaScript 语法和 `git diff --check`：通过。
- 新增安全回归覆盖：选择规则绝对/父级路径、运行时 pack 解析、导入类别目录、聊天上传目录、归档 JSON 大小、Base64 大小和导出路径脱敏。
- 初检中记录的三个缺失 `self` 已在前一批修复中关闭；当前 `web_api.py` 的上传保存、导入凭证和响应状态方法均可通过实例调用。
- `bandit`、`pip-audit` 当前解释器未安装，依赖漏洞扫描仍需在完整 CI/部署环境执行。

## 依赖与调用关系

~~~mermaid
flowchart LR
    Pages[WebUI pages] --> Main[main.py / plugin entry]
    Main --> Manager[manager_base.py]
    Manager --> WebAPI[mixins/web_api.py]
    Manager --> PackAPI[mixins/pack_api.py]
    Manager --> EmojiAPI[mixins/emoji_api.py]
    Manager --> Events[mixins/event_handlers.py]
    Manager --> Capture[capture.py]
    WebAPI --> Storage[backend/pack_storage.py]
    PackAPI --> Storage
    EmojiAPI --> Models[backend/models.py]
    Events --> Storage
    Events --> Capture
    Storage --> Protocol[backend/pack_protocol.py]
    Storage --> Repo[backend/repository.py]
    Storage --> Files[backend/file_utils.py]
    Models --> Index[backend/catalog_index.py]
    Storage --> Config[backend/config.py]
~~~

关键边界是 Pages -> mixins -> backend。目前多个入口在 mixin 层直接把用户提供的 pack_id、URL、输出目录传入存储层；因此不能只在某一个 WebUI handler 上修复，必须在路由入口和 backend 公共函数两侧同时校验。

## 当前基线

| 检查 | 结果 | 说明 |
|---|---:|---|
| python -m compileall -q . | 通过 | Python 文件可编译 |
| python -m unittest discover -s tests -v | 144/144 通过 | 已补充路径、归档大小、类别目录和导出响应回归测试 |
| python scripts/generate_conf_schema.py --check | 通过 | schema 与配置同步 |
| node --check pages/**/*.js | 通过 | 当前 JS 可解析 |
| 路由 handler AST 检查 | 40/40 | 未发现路由缺少 handler |
| 缺失 self AST 检查 | 0 项 | 上传、导入和响应状态方法已恢复正确实例绑定 |
| 未定义实例方法检查 | 1 项 | _resolve_embedding_provider，位于已失效语义化路径 |
| 当前审计解释器依赖导入 | 不完整 | aiohttp 未安装；不是代码漏洞，但运行时集成测试无法在此解释器完成 |

## 修复优先级总表

| 优先级 | 问题 | 主要位置 | 处理目标 |
|---|---|---|---|
| P1 | pack_id 路径穿越与卸载删除边界缺失 | mixins/pack_api.py、backend/pack_storage.py | 先阻断任意目录访问/删除 |
| P1 | 消息图片下载关闭 TLS、降级 HTTP、无大小限制 | mixins/event_handlers.py | 先阻断 SSRF、资源耗尽和非图片落盘 |
| P1 待确认 | WebUI 鉴权与 CSRF 依赖宿主实现 | mixins/web_api.py、pages/a_manage/api.js | 确认 AstrBot 4.5.7 的真实保护，再补插件侧防线 |
| P2 | 三个实例方法缺失 self | mixins/web_api.py | 恢复上传/导入运行时调用 |
| P2 | 语义化 UI 和死函数残留 | pages/a_manage、mixins | 删除已失效功能，避免用户触发必然报错 |
| P2 | WebUI 图片上传无大小/内容/原子写入保护 | backend/models.py | 防止伪图片、超大文件和半成品 |
| P2 | 远程 pack 下载/解压边界弱 | backend/pack_storage.py、backend/pack_protocol.py | 限制来源、压缩包和落盘内容 |
| P2 | 运行时备份允许任意输出目录 | mixins/pack_api.py、backend/pack_storage.py | 限制写入范围，避免越权写文件 |
| P3 | 依赖仅有下限、语义化模块残留 | requirements.txt、backend、mixins | 提高可复现性，完成退役清理 |

## 详细问题与修复方案

### P1-01：pack ID 可构造路径，卸载接口可能删除边界外目录

**当前状态**：已修复并通过选择规则、运行时解析、详情、默认设置、导出和卸载相关回归测试。

**症状**：详情、设置默认、导出、下载和卸载接口都直接接收用户提供的 pack_id；卸载最终直接对拼接出的目录执行 shutil.rmtree。

**证据**：

- mixins/pack_api.py:92-103、:105-123、:125-150、:165-190、:407-429 将原始 pack_id 传给 backend。
- backend/pack_storage.py:473-512、:515-531、:1180-1205、:1297-1313 使用 PACKS_DIR / pack_id；卸载路径仅检查非空，没有统一的 ID 和目录边界校验。
- backend/pack_storage.py:829-833 已有校验逻辑，说明当前实现不一致。
- mixins/capture_index_api.py:19-42 已展示较安全的正则和 resolve().relative_to(...) 模式。

**后果**：攻击者若能访问这些 API，可能读取、导出、覆盖或删除 PACKS_DIR 之外的目录；..、.、嵌套路径和编码后的路径都必须纳入测试。

**修复**：

1. 在公共模块实现 validate_pack_id() 与 resolve_safe_pack_dir()。
2. ID 只允许 [A-Za-z0-9._-]{2,64}，拒绝空值、.、..、斜杠、反斜杠、控制字符和绝对路径。
3. 对解析结果执行 resolve().relative_to(PACKS_DIR.resolve())，并拒绝 PACKS_DIR 本身和符号链接逃逸。
4. 在所有 WebAPI 入口和 get_pack_detail、set_default_pack、export_pack_archive、uninstall_pack 等 backend 公共函数重复校验。
5. 卸载增加“只能删除 pack 目录的直接子目录”保护，并在删除前再次确认 is_dir() 和边界。

**验收测试**：对详情、默认 pack、导出、下载、卸载分别测试 ..、.、a/b、绝对路径、编码穿越；使用临时 sentinel 目录确认卸载请求不会删除边界外文件。

### P1-02：消息图片下载器禁用 TLS 校验，允许 HTTP 降级且没有资源上限

**当前状态**：已修复并通过 HTTPS、DNS、重定向、大小、真实图片格式和失败清理测试；DNS 重绑定仍需真实网络环境复测。

**症状**：收到偷取流程中的图片消息时，下载器关闭证书与主机名校验；特定域名还从 HTTPS 改成 HTTP；响应一次性读入内存，未限制状态、重定向、大小和真实内容。

**证据**：mixins/event_handlers.py:558-590 设置 CERT_NONE，在 :564-571 做 HTTP 降级，在 :570-577 直接 await resp.read()，在 :586-590 即使识别失败也可能按 .bin 写盘。该流程由 mixins/commands.py:187-192 的 /偷取 状态触发。

**后果**：中间人攻击、恶意重定向、内网地址访问、超大响应导致内存耗尽，以及把任意响应内容当作图片保存。消息组件中的 URL 不能视为可信输入。

**修复**：

1. 删除 CERT_NONE 和 HTTP 降级；默认只允许 HTTPS。
2. 复用 capture.py:1653-1685 的安全下载策略：检查目标地址、拒绝内网/回环地址、关闭自动重定向、检查状态码和 Content-Length。
3. 使用分块读取并设置总字节上限；响应超限立即中止并清理临时文件。
4. 下载后用 Pillow verify() 检查真实图片格式，只允许 PNG/JPEG/GIF/WebP；禁止以 .bin 作为成功结果。
5. 错误日志不要记录完整用户 URL，统一使用 host、状态和错误类型。

**验收测试**：证书异常、HTTP、重定向、内网地址、超大响应、伪图片、扩展名不匹配、有效图片各一例，并确认失败不会留下文件。

### P1-03（待宿主确认）：WebUI 鉴权与 CSRF 边界

**当前状态**：未关闭。当前本地环境未安装 AstrBot，仍需在宿主环境验证 middleware、普通用户、未登录和跨 Origin 请求。

**症状**：mixins/web_api.py:96-123 只注册 handler；pages/a_manage/api.js:89-108 的 fetch 包装器没有显式 CSRF 令牌或 Origin 检查。README 表示安全边界依赖 AstrBot 的 context.register_web_api。

**风险判断**：仅凭插件代码不能确认宿主是否已经强制管理员鉴权和 CSRF 防护，因此暂不把它记为“已确认漏洞”。如果宿主注册的 API 能被普通用户或跨站请求调用，前述导出、导入、卸载风险会进一步扩大。

**修复与验收**：针对当前支持的 AstrBot 版本核实真实 middleware、权限和 CSRF 行为；用普通用户、未登录请求、跨 Origin POST 和无 token POST 做集成测试。若宿主没有完整保护，则在插件侧增加管理员鉴权、CSRF token、Origin/Referer 校验和安全响应头。

### P2-01：三个实例方法缺少 self，真实调用必然参数错误

**当前状态**：已修复；上传保存、导入凭证和响应状态方法均已恢复实例绑定，并有回归测试。

**症状**：mixins/web_api.py:125 的 _get_webui_response_status、:280-288 的 _save_uploaded_file、:290-298 的 _pack_import_session_paths 定义在 mixin 类中却缺少 self。

**证据与影响**：后两个方法由 mixins/pack_api.py:231、:301、:353、:694 的上传、导入和备份恢复路径调用；现有测试没有覆盖真实绑定调用，因此 112 个测试通过不能排除线上 TypeError。第一个方法当前未找到调用点，应删除或补 self 后补测试。

**修复**：先确认这些方法是否应为实例方法；若是则补 self，若应为静态工具则加 @staticmethod 并统一调用方式。补充真实类实例的同步/异步调用测试、有效/无效 token 测试和 pack 上传/备份导入测试。

### P2-02：图片语义化已经移除，但前端控件、必然抛错函数和 backend 死代码仍在

**当前状态**：主要失效 UI、removed 路由和不可达调用已移除；`_resolve_embedding_provider` 的残留引用仍列为低优先级清理项。

**症状**：产品逻辑已经把语义化关闭，却保留了用户可见控件和调用入口；相关函数一进入就抛出“功能已移除”，后面的旧实现成为不可达代码。

**证据**：

- manager_base.py:285-293 的 _semantic_pack_ready 永远返回 False。
- mixins/event_handlers.py:699-705 和 mixins/web_api.py:180-184 仍调用未定义的 _resolve_embedding_provider；后者前面立即 return {}，属于残留死代码。
- mixins/web_api.py:133-178、:342-350 还有 return {}/return 之后的旧语义化逻辑。
- pages/a_manage/index.html:429-639 注释声称控件已移除，但实际仍包含语义化 DOM 和悬空注释。
- pages/a_manage/emoji.js:632-863、pages/a_manage/pack.js:299-359 的语义化/向量函数会无条件抛错，后面还调用 apiGet/apiPost("removed")。
- tests/test_semantic_removal.py:41-53 只检查少数字符串，未覆盖实际 DOM、removed 路由和无条件抛错。

**后果**：用户点击旧控件会必然失败；静态检查会持续发现未定义方法；维护者无法判断哪些接口仍属于产品契约。

**修复**：当前仓库的明确方向是“移除语义化”，因此删除语义化 DOM、事件绑定、旧响应字段、removed 占位请求和不可达 backend 逻辑；保留必要的一次性数据清理迁移，并在迁移后删除旧模块依赖。若实际产品要恢复语义化，则必须恢复完整 provider、路由、数据模型、权限和测试契约，不能只删除抛错。

**验收测试**：更新静态测试，检查语义化 DOM、功能已移除、apiGet/apiPost("removed") 和未定义 provider 均不存在；通过浏览器 smoke test 验证管理页加载、图片编辑、pack 导入导出和保存流程无旧控件报错。

### P2-03：WebUI 图片上传无大小、内容校验和原子写入

**当前状态**：已修复并通过超限、伪图片、真实格式和原子写入回归测试。

**证据**：backend/models.py:152-165 只做扩展名清理；:178 一次性读取整个 stream；:198-200 直接写目标文件。mixins/emoji_api.py:161-208 将上传直接交给该路径。

**后果**：超大上传会消耗内存，伪图片会进入资源目录，写入中断可能留下损坏文件或半成品索引。

**修复**：限制请求和单文件字节数，分块写入临时文件；写完后用 Pillow 校验格式和尺寸，再用 os.replace 原子替换；失败时清理临时文件并保持 catalog/index 不变。补测超限、伪图片、截断图片、扩展名不匹配和并发上传。

### P2-04：社区/GitHub pack 下载没有响应大小和内容边界

**当前状态**：主要响应、来源、归档和解压边界已加固；DNS 重绑定仍需真实网络环境复测。

**证据**：backend/pack_storage.py:81-107 的 _http_get_with_optional_acceleration 使用 requests.get；:1405-1420 将完整 response.content 写入归档；:1483-1535 的远程安装允许较宽的来源描述，并以 block_executable_scripts=False 解压。backend/pack_protocol.py:67-89 仅做很弱的 repo/subpath 检查。

**后果**：恶意或异常大的响应可造成内存/磁盘耗尽；过宽的仓库来源和归档内容会扩大供应链与落盘风险。当前代码没有看到“执行脚本”，但仍不应把远程仓库的任意文件全部当作 pack 内容。

**修复**：限定 HTTPS 和允许的加速域名，使用流式下载并限制响应、压缩包和解压后总大小；严格校验 owner/repo/ref/subpath 和控制字符；校验 manifest、文件扩展名、数量、单文件大小和总大小；能提供时记录哈希/签名并向用户展示来源。解压完成后只复制允许的 manifest、JSON 和图片文件。

### P2-05：运行时备份接受任意输出目录

**当前状态**：已限制在 BACKUP_DIR，并移除导出响应中的本机绝对路径；鉴权/CSRF 联动仍待宿主确认。

**证据**：mixins/pack_api.py:589-603 从请求 JSON 读取 output_dir；backend/pack_storage.py:1678-1687 对其 expanduser().resolve() 并创建目录。

**风险判断**：用户选择导出目录可能是设计需求，但若 API 权限或 CSRF 不可靠，攻击者可诱导服务进程向任意可写路径写入文件。该项应与 P1-03 联动验证。

**修复**：默认使用受控 BACKUP_DIR；若保留自定义路径，只允许配置根目录下的目录，拒绝符号链接、系统目录和 PACKS_DIR 等敏感路径；优先返回下载 token 或归档句柄，不把绝对服务器路径暴露给前端。补测相对路径、绝对路径、符号链接和越界路径。

### P3-01：依赖不可复现，语义化模块未完成退役

**证据**：requirements.txt 只有 aiohttp>=3.9.0、Pillow>=10.0.0、requests>=2.31.0，没有 lock/hash 或 CI 版本矩阵；审计解释器缺少 aiohttp。同时 semantic 相关模块仍被 manager_base.py、event_handlers.py 和 backend 导入。

**修复**：增加受支持 Python/AstrBot 版本的 CI 矩阵，锁定直接依赖并定期升级；在语义化移除完成后删除无调用模块、导入和配置字段。依赖缺失属于环境问题，应在安装/启动阶段给出明确诊断，而不是静默降级。

## 推荐实施顺序

1. 先修复并测试 pack ID 的统一边界校验，尤其是卸载和导出。
2. 抽取安全图片下载器，修复 TLS、协议、重定向、DNS/IP、大小和内容校验。
3. 确认 AstrBot WebAPI 的权限/CSRF 行为；未覆盖时补插件侧保护。
4. 修复三个缺失 self，用真实实例调用测试覆盖上传、导入和备份恢复。
5. 删除语义化残留 UI、死代码和假路由，更新静态与浏览器 smoke test。
6. 加固 WebUI 上传、远程 pack 下载和备份输出目录。
7. 最后整理依赖锁定、CI 矩阵和已退役模块。

## 修复后的验证命令

~~~powershell
python -m compileall -q .
python -m unittest discover -s tests -v
python scripts/generate_conf_schema.py --check
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
git diff --check
~~~

额外的失效功能门禁：

~~~powershell
rg -n 'api(Post|Get)\("removed"|功能已移除|向量语义功能已移除' pages mixins backend
~~~

该命令在修复完成后应无输出，或只命中明确记录在迁移脚本中的兼容代码。

## 完成定义

- 所有 P1 项都有回归测试，并在真实 WebAPI/文件系统边界上验证，而不是只用 mock 返回值。
- 路径、URL、上传文件、远程归档和输出目录都在入口与 backend 两侧校验。
- 语义化移除后，前端不再展示不可用控件，也不再调用 removed 或无条件抛错函数。
- 全量测试、Python 编译、JS 语法、schema 检查和安全专项测试通过。
- CI 能在干净环境安装完整依赖并运行同一套门禁。
- git diff --check 无输出，且审计文档中的每条 P1/P2 都能链接到对应代码、测试或 issue。
