# 更新日志

本文件遵循 Keep a Changelog 结构，日期使用 Asia/Shanghai。

## [v2.4.1] - 2026-08-18

### 移除

- 移除不再被引用的历史规划/设计文档（`docs/superpowers/`）、根目录会话记录文件（`plan.md`、`design.md`、`review.md`、`findings.md`、`progress.md`、`task_plan.md`）、历史审计/自检文档与 `INDEX_AND_DEDUPE.md`。
- 移除无生产调用方的死代码：`response_policy.py`、`backend/semantic_caption.py`、`backend/semantic_cleanup.py` 兼容层、`application/web_routes.py` 测试专用副本，以及 `backend/models.py` 中 8 个旧版表情 CRUD 函数；同步删除/精简对应测试。
- 移除 `mixins/event_handlers.py` 中已不可达的旧语义搜索/回复分支（含引用不存在符号 `search_memes` 等的历史代码），并清理 `manager_base.py` 中因此孤立的 `_semantic_mode_active` 与各模块未使用导入。

### 修复

- /偷取 群聊图片下载改用插件级安全下载器：仅允许 HTTPS、固定已校验的公网 DNS 结果（阻断 DNS 重绑定）、禁止重定向、分块限流并校验真实图片格式；下载失败日志只记录 host，不再输出完整 URL。相关修复替代了此前未应用的 `_patch.py`。
- WebUI 导出表情包改为 POST 预生成 + 一次性下载凭证：`packs/export/prepare`（受 WebUI 写操作保护）生成归档并返回 32 位随机 token，`packs/export/download` 凭 token 下载一次后清理会话；1 小时内未下载的会话会自动过期清理。前端「导出当前资源包」同步改为新流程。
- 表情包详情接口不再向前端返回本机绝对路径（`pack_dir`），避免泄露服务器目录结构。

### 验证

- `python -m unittest discover -s tests`：364 项通过，1 项既有兼容性用例跳过。
- `python -m compileall -q .`、`python scripts/generate_conf_schema.py --check`、`python scripts/check_architecture.py`、全部页面 JavaScript `node --check` 与 `git diff --check`：通过。
- 本地环境缺少 `bandit`/`pip-audit`，依赖安全扫描由 CI 的 security job 执行。

## [v2.4.0] - 2026-08-18

### 新增

- 重复图片自动进入插件级 `capture_auto_blacklist.json`，记录来源资源包和文件名；来源图片删除后自动移除对应记录。
- 打开表情索引工作台或开始新一轮采集时，自动迁移旧的“重复待去重”记录，不再把重复项放入待分类队列。

### 变更

- 表情索引工作台进一步收敛为单页布局：资源包导入/导出工具栏置于表情索引标题下方，表情目录统一展示，并支持在全部、已分类、未分类之间切换。
- 统一页面排版、字号、间距和状态文案，减少重复元素；重复项不再作为用户需要手动处理的常规状态展示。
- 分离自动重复黑名单与手动永久黑名单，自动项不会污染全量索引或运行时黑名单恢复逻辑。
- 更新捕获去重、活动记录迁移、资源包工作区和删除回收的回归测试与说明文档。

### 验证

- `python -m unittest discover -s tests -p "test_*.py"`：368 项通过，1 项既有兼容性用例跳过。
- `python -m compileall -q .`、`python scripts/check_architecture.py`、全部页面 JavaScript `node --check` 与 `git diff --check`：通过。

## [v2.3.0] - 2026-08-17

### 移除

- 移除「设置中心」「资源广场」WebUI 页面及其专属前端资源。
- 移除只被这两页使用的 Web API：`settings/rules`、`settings/targets`、`settings/backup/export`、`settings/backup/import`、`community/index/fetch`、`community/index/cache`、`community/install`，以及旧的 `packs/export`、`packs/import` 单步接口。
- 移除对应 mixin handler 与不再使用的辅助（社区索引、选择规则、运行时备份、导出结果脱敏等）。

### 新增

- 表情索引页工具栏新增「导出当前资源包」：支持分享版与带向量自用备份，带向量模式仅在当前资源包具备完整向量时可选。
- 表情索引页工具栏新增「导入资源包」：选择 zip 后预检格式/图片/分类/向量状态，确认导入时可设为默认。

### 变更

- WebUI 收敛为单一页面（表情索引），页面导航与跨页链接移除；AstrBot 插件页入口链路保持不变。
- 表情包导出/导入流程从设置中心迁移至表情索引，功能不损失。
- 统一插件清单与运行时注册版本为 v2.3.0。
- 表情索引页面资源缓存版本升级为 `20260817-transfer-1`。

### 验证

- `python -m unittest discover -s tests`：全量通过。
- `python -m compileall -q .`、`python scripts/generate_conf_schema.py --check`、`python scripts/check_architecture.py`、全部页面 JavaScript `node --check` 与 `git diff --check`：通过。

## [v2.2.1] - 2026-08-17

### 修复

- 恢复 AstrBot 插件页面入口：重建 `pages/a_manage/index.html` 作为轻量跳转页，打开插件页面后直接进入表情索引工作台；修复 v2.2.0 移除管理页后 `pages/` 下无可发现页面导致 WebUI 无法打开的问题。
- 插件页入口重定向恢复为一级路径 `/#/plugin-page/meme_manager_master/a_manage`。

### 验证

- `python -m unittest discover -s tests`：全量通过。
- `python -m compileall -q .`、`python scripts/generate_conf_schema.py --check`、`python scripts/check_architecture.py`、全部页面 JavaScript `node --check` 与 `git diff --check`：通过。

## [v2.2.0] - 2026-08-17

### 移除

- 移除表情包管理 WebUI 页面及其专属前端资源（`pages/a_manage/` 下的管理页、`state.js`、`api.js`、`dialogs.js`、`emoji.js`、`pack.js`、`script.js` 与配套样式/字体）。
- 移除顶层旧版页面副本 `pages/semantic/`、`pages/settings/`、`pages/catalog/`，页面只保留 `pages/a_manage/` 一套。
- 移除只被管理页使用的 Web API：`emoji/*`、`emotions`、`category/*`、`sync/*`、`meme_image`、`packs/default`、`packs/uninstall`、`community/install_official_first`。
- 移除对应 mixin handler（`EmojiAPIMixin` 仅保留图片预览接口）与相关回归测试；底层后端函数、聊天命令与共享接口全部保留。

### 变更

- WebUI 入口改为直接进入表情索引工作台；表情索引、设置中心、资源广场的导航不再包含管理页链接。
- 手动上传、分类改名/描述编辑、默认包切换等操作改由聊天命令提供（`/添加表情`、`/查看图库`、`/恢复默认表情包`、`/清空指定类型`、`/图库统计`）。
- 统一插件清单与运行时注册版本为 v2.2.0。
- 三份页面资源缓存版本升级为 `20260817-remove-manage-1`。

### 验证

- `python -m unittest discover -s tests`：全量通过。
- `python -m compileall -q .`、`python scripts/generate_conf_schema.py --check`、`python scripts/check_architecture.py`、全部页面 JavaScript `node --check` 与 `git diff --check`：通过。
- 路由契约、页面导航、捕获索引页、pack 行为与语义移除专项回归：通过。

## [v2.1.8] - 2026-08-16

### 新增

- 新增插件级精确 SHA-256 永久捕获黑名单；手动忽略或从表情索引工作台删除的图片在识图前和保存前都会被拦截，且所有资源包共享。
- 表情索引工作台新增选择索引和当前资源包一键忽略全部待处理/待忽略记录，并支持跨已整理分页保留选择。
- 全量运行时备份包含捕获黑名单；恢复旧备份保留当前黑名单，恢复新备份与当前值取并集。
- 表情索引工作台新增 v4 健康面板，以环形完整率和状态气泡展示 v4 完整、需重建、待分类及重复待忽略数量。
- 点击 v4 状态气泡即可筛选当前资源包中的对应条目；原有缩略图预览、分类气泡、分页和处置操作继续保留。

### 修复

- 修复表情索引页删除后只刷新统计而不重绘卡片，导致当前页出现空位且后一页表情未补齐的问题。
- 将已整理分页条移动到已整理区和待处理区之间，摘要仅统计已整理表情；页数缩减时自动回退到有效页。
- 修复全量语义重索引占用整包处置锁的问题；模型请求期间删除/忽略可立即执行，提交时会校验最新文件指纹并避免旧结果复活已处置图片。
- 收紧自动偷取和 `/偷取` 的视觉筛选：截图、聊天截图、网页/UI、文档、海报、普通照片和低置信度结果默认拒绝。
- 收紧表情包偷取识别：视觉模型必须输出 0–100 的 meme_score，低于 70 或属于普通照片、截图、信息图等非表情包图片时直接拒绝保存。
- 修复 v4 健康面板下方隐藏兼容摘要被样式覆盖而重复显示的问题。
- 修复 v4 完整率圆环进度变量写入错误，避免 100% 时仍显示为空环。

### 变更

- 统一插件清单与运行时注册版本为 v2.1.8，避免 AstrBot WebUI 显示或更新检测使用旧版本号。
- 已整理项执行“删除并拉黑”；普通待分类项执行“忽略、删除并拉黑”；重复项执行“忽略并拉黑但保留已有图片”。普通表情管理页原有删除语义保持不变。
- 批量选择时，点击已选整理卡片的处置按钮仍会批量删除整理项；待处理和重复卡片改为只处理当前卡片，避免误忽略其他选择项。新增“选择索引”只提交选中的普通待处理项。
- “一键忽略全部待处理和待忽略”按当前资源包全量处理，不受分类筛选和分页影响；重复图片保留文件，普通待处理图片删除并统一加入黑名单。
- 表情索引工作台现在会在当前页面内复用已经加载的缩略图；刷新记录、忽略或删除后的重绘、筛选以及返回已浏览分页时不再整批重复加载，只有首次出现的新图片需要请求。缓存随资源包切换、成功重索引或页面重新加载安全失效。
- 捕获工作区 API 新增 `summary.v4` 摘要与 `v4_status` 筛选参数，保留旧摘要字段以兼容现有页面和调用方。
- 两份 WebUI 页面资源缓存版本升级为 `20260816-v4-health-2`，避免插件重装后继续加载旧版界面。

### 验证

- 捕获工作台 API、双页面契约/运行时、全量重索引和偷取筛选专项回归：通过。
- `python -m unittest discover -s tests -v`：运行 369 项，1 项既有兼容性用例跳过。
- `python -m compileall -q .`、`python scripts/generate_conf_schema.py --check`、`python scripts/check_architecture.py`、全部页面 JavaScript `node --check` 和 `git diff --check`：通过。
- 自动化页面回归已覆盖删除后补齐、页码回退、跨页选择、部分失败保留与缩略图缓存边界/失效；当前环境无法访问局域网 AstrBot WebUI，长页面滚动与真实浏览器交互仍需人工复核。
- v4 摘要、双页面结构/脚本契约、Node 语法和运行时回归测试通过。

## [v2.1.7] - 2026-08-15

### 修复

- 全量语义重索引现在按批次写入 catalog 检查点；任务中断、插件重载或离开 WebUI 后，已完成的图片可以被识别为当前条目并跳过。
- 将全量任务状态持久化到资源包的 `reindex_state.json`；重新打开语义索引页面会恢复进度并自动继续暂停或遗留的任务。
- 修复多图片目录整理时错误复用其他图片 SHA 的问题，避免已完成条目被误判为内容变化。
- 重新进入语义索引页面时恢复 URL 中的资源包选择，避免查询错误资源包而看不到实际任务进度。

### 验证

- 新增中断后检查点续跑、持久化状态恢复和资源包回选回归测试。

## [v2.1.6] - 2026-08-15

### 新增

- 将表情索引页“重索引”升级为“全量语义重索引”：先整理旧分类目录和 flat 文件名，再检查当前资源包中的全部图片。
- 完整 v4 语义索引会跳过视觉模型；v3、SHA 变化、主分类无效或语义字段不完整的图片会重新调用视觉模型。
- 每张图片记录 `full_reindex_status` 和 `full_reindex_checked_at`，并在页面进度中分别显示跳过、重新识别和失败数量。

### 修复

- 修复旧版目录整理后因 catalog SHA 被刷新而误判为“已完成”的问题；目录整理会保留前一次 SHA，确保内容变化仍会触发语义重索引。
- 单批或单图视觉识别失败时继续处理其他图片；失败条目标记为 `needs_reindex`，不会进入主分类自动发送候选。

### 兼容

- 保留 `capture/reindex` 和 `capture/reindex/status` API；“分类索引待处理项”仍只处理后台发现的待分类图片。
- 全量任务与待分类索引互斥，旧 `tags`、`text` 和现有 tag index 继续保留兼容读取。

### 验证

- 新增完整 v4 跳过、旧索引重建、SHA 变化、失败标记、API 计数和双页面进度回归测试。

## [v2.1.5] - 2026-08-15

### 变更

- 将自动选图路由收敛为 12 个稳定主分类：开心、悲伤、尴尬、无奈、疑惑、震惊、愤怒、吐槽、赞同、拒绝、卖萌、围观；旧 `tags` 保留兼容读取，但辅助标签不再参与自动分类。
- 视觉索引新增语义摘要、最多 2 个辅助语义标签、图片可见文字、文字含义、适用场景、避免场景和分类置信度，具体候选判定会综合这些字段。
- 索引版本升级并增加 `by_primary_category` 路由索引；旧目录按确定性规则迁移，无法无歧义推断主分类的条目标记为 `needs_reindex` 并排除自动发送。

### 修复

- 修复带有配字的尴尬/自嘲表情仅按宽泛标签随机抽取、忽略图片文字与回复语境的问题。

### 验证

- 新增主分类归一化、旧目录迁移、主分类路由隔离、语义字段和版本元数据回归测试。

## [v2.1.4] - 2026-08-11

### 修复

- 修复 AstrBot Plugin Page 受限 iframe 中，表情索引、设置中心和资源广场因使用 `target="_top"` 被浏览器拦截、点击无响应的问题。
- 恢复 `a_manage` 页面根目录内的相对导航，并继续保留 `managed_pack_id` 与 `view` 参数。
- 更新相关页面脚本的缓存版本，避免浏览器继续加载失效的旧导航逻辑。

## [v2.1.3] - 2026-08-11

### 修复

- 修复从表情管理、表情索引和资源广场进入设置中心时继续复用旧页面令牌，导致 AstrBot WebUI 显示“Token 过期”的问题。
- 统一设置、表情索引和资源广场的 Dashboard 路由导航，并在切换管理表情包后刷新页面链接参数。
- 更新设置页面资源缓存版本，确保浏览器加载最新导航逻辑。

## [v2.1.2] - 2026-08-06

### 新增

- 捕获索引工作台新增单卡和批量“忽略重复记录”操作：按图片 SHA-256 处理当前 pack 的全部重复事件，隐藏记录但不删除图片、不修改 catalog；后续新产生的重复事件仍会显示。

### 修复

- 批量视觉索引遇到模型思考标签、代码块或尾部说明时，增强 JSON 提取并对格式错误的批量响应最多重试一次；重试仍失败时继续逐图补偿，避免批次因单次非法 JSON 中断。

### 验证

- `python -m unittest discover -s tests -v`：301 项通过，1 项既有兼容性用例跳过。
- `python -m compileall -q .`、`python scripts/generate_conf_schema.py --check`、`python scripts/check_architecture.py`、全部页面 JavaScript `node --check` 和 `git diff --check`：通过。

## [v2.1.1] - 2026-08-05

### Refactor delivery note

- The follow-up repair pass adds bounded `PackRuntime.create()` validation, active-pack rebinding for capture and automatic selection, community/official install service routing, semantic failure diagnostics, and a dependency-free real-image upload smoke test.
- The legacy `storage.py` and `backend/pack_storage.py` implementations remain as compatibility facades during the migration window; full physical extraction of the remaining legacy bodies and live AstrBot host acceptance are still follow-up items.

### 新增

- 增加 `domain`、`ports`、`application`、`capabilities` 和 `infrastructure` 边界，提供 pack、catalog、图片仓储、选择状态和可选语义能力的稳定接口。
- 增加 `CatalogLock`、路径安全策略、pack paths/runtime/transfer/backup/community 边界及对应应用服务。
- 增加架构依赖检查、模块规模指标、存储/pack 契约测试和 WebRouteRegistry 测试。

### 变更

- `MemeStore` 保留旧入口，同时将选择、权重和发送回执迁移到 `SelectionState`；旧 pack facade 继续兼容现有调用方。
- 语义实现继续懒加载；缺少 FAISS 或 provider 时不阻断核心启动和基础上传流程。

### 验证

- 全量 pytest：283 项通过，1 项既有兼容用例跳过；unittest discover：284 项通过，1 项跳过。
- compileall、配置 schema、架构边界检查和全部页面 JavaScript 语法检查通过。
- `bandit` 和 `pip-audit` 尚未执行，当前环境未安装。

### 迁移状态

- `storage.py` 与 `backend/pack_storage.py` 的旧实现尚未完全物理拆除；capture 的活动资源包同步和社区/官方安装路由已接入应用服务，兼容 facade 暂时保留。

## [v2.1.0] - 2026-08-04

### 验证

- 新增跨事件污染、生图放行、外部媒体跳过、上下文裁剪、提示词边界和 Web schema 兼容回归测试；全量测试 233 项通过，1 项既有兼容用例跳过。

### 新增

- 新增捕获索引工作台、重索引进度反馈和索引卡片交互，覆盖已索引、待分类、重复项和分类筛选。
- 新增 WebUI 写接口安全门回归测试，覆盖缺少认证、缺少同源证据、跨 Origin 和正常同源请求。

### 变更

- 重构表情包发送逻辑：移除自然语言请求的前置抢占和跨事件状态，改为最终回复阶段由情景模型判断是否追加本地表情包。
- 情景判断现在可参考最近 3 轮 user/assistant 文本上下文，并明确区分生图、自拍、插画、视频等外部视觉任务。
- AstrBot Web 设置收敛为日常核心配置；高级运行参数和旧版 `fallback_category` 继续兼容读取但不再公开暴露。
- 重构固定标签、平铺目录和快速标签索引的相关流程，兼容保留原有路由、pack 数据结构和命令行为。
- 抽取共享远程读取策略，图片下载和远程归档共用公网 HTTPS URL、有限流读取与原子写入约束。
- 统一 WebUI 页面副本的动态统计节点构造方式，并移除设置页不可达的历史向量重建逻辑。

### 修复

- 远程归档请求显式禁止 HTTP 重定向，避免下载目标脱离预期安全边界。
- 索引统计动态数据不再进入 `innerHTML`，降低业务数据被当作 HTML 解析的风险。

### 安全

- 图片下载继续校验 HTTPS、公网 DNS、响应大小和真实图片格式；归档写入继续采用有界流和原子替换。
- WebUI 删除、导入、导出、安装及规则保存等写操作在宿主未提供认证用户或同源请求证据时默认拒绝。

### 测试

- 实施前全量 unittest 基线为 205 项通过；本轮新增安全、远程下载和动态 DOM 回归用例，当前全量回归为 215 项通过、1 项历史兼容用例跳过。

## [2026-08-03]

### 变更

- 将单张表情包的固定标签上限从 5 个提高到 6 个。
- 同一图片在不同标签下只保留一个文件，重复采集时合并新识别出的标签和空缺元数据。
- 新增 `memes/tag_index.json`，Bot 按标签选图优先读取派生索引；索引缺失或损坏时自动恢复。

## [2026-08-01]

### 安全

- 修复 WebUI 页面跳转时静态资源令牌未继续传递，导致表情索引、资源管理和设置页面返回“未授权”。
- 统一校验 `pack_id`，拒绝绝对路径、父级路径和非法目录名，覆盖选择规则、运行时解析、导出和卸载路径。
- 校验导入表情包的分类目录，并阻止聊天上传将图片写入 `memes` 目录之外。
- 限制运行时备份的 Base64、上传归档和 JSON 文件大小，降低超大请求导致的内存与磁盘耗尽风险。
- 导出接口不再向 WebUI 返回服务器本机绝对路径，只返回归档文件名。
- 新增路径边界、归档大小、类别安全和导出响应的回归测试；全量测试 144 项通过。

## [v1.4.4] - 2026-07-28

### 变更

- 增加 meme_send_receipt 发送凭证，只有插件记录到真实发送路径时才允许 Agent 声称表情包已发送。
- 在最终消息发送前拦截没有发送凭证的表情包发送幻觉，并改为真实的未发送提示。

## [v1.4.3] - 2026-07-28

### 修复

- 修复“再发一个可爱猫猫标签”等带描述的后续表情请求未被识别、误交给默认 Agent 的问题。
- 对明确的表情请求继续在默认 Agent 前接管；本地没有可发送图片时只返回失败提示，不再允许模型声称已经发送。

## [v1.4.2] - 2026-07-28

### 变更

- 将刚发送的表情包信息注入下一轮 Agent 的临时上下文，避免误引用更早历史图片。
- 保留发送消息链中的实际图片，并补充图片文字字段到上下文描述。

## [v1.4.1] - 2026-07-27

### 修复

- 修复后台索引批量模型返回非法 JSON 时连续重试后续批次的问题。
- 批量识别失败时增加单图识别降级，单图也失败才进入退避重试。
- 修复已有索引结果与图片文件关联不稳定的问题。
- 减少无变化索引对 `index.json` 和 `README.md` 的重复写入。
