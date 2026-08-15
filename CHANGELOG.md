# 更新日志

本文件遵循 Keep a Changelog 结构，日期使用 Asia/Shanghai。

## [Unreleased]

### 新增

- 新增插件级精确 SHA-256 永久捕获黑名单；手动忽略或从表情索引工作台删除的图片在识图前和保存前都会被拦截，且所有资源包共享。
- 表情索引工作台新增已整理、普通待分类和重复记录的统一单项/批量处置，并支持跨已整理分页保留选择。
- 全量运行时备份包含捕获黑名单；恢复旧备份保留当前黑名单，恢复新备份与当前值取并集。

### 修复

- 修复表情索引页删除后只刷新统计而不重绘卡片，导致当前页出现空位且后一页表情未补齐的问题。
- 将已整理分页条移动到已整理区和待处理区之间，摘要仅统计已整理表情；页数缩减时自动回退到有效页。

### 变更

- 已整理项执行“删除并拉黑”；普通待分类项执行“忽略、删除并拉黑”；重复项执行“忽略并拉黑但保留已有图片”。普通表情管理页原有删除语义保持不变。
- 批量选择时，点击任意已选卡片的处置按钮会批量处理同一区域的选择：已整理与待处理互不混入；移除冗余的“统一处理”工具栏按钮，未选卡片仍保持单项处置。
- 表情索引工作台现在会在当前页面内复用已经加载的缩略图；刷新记录、忽略或删除后的重绘、筛选以及返回已浏览分页时不再整批重复加载，只有首次出现的新图片需要请求。缓存随资源包切换、成功重索引或页面重新加载安全失效。

### 验证

- `python -m unittest tests.test_capture_index_runtime tests.test_capture_index_page -v`：25 项通过。
- `python -m unittest discover -s tests -v`：运行 328 项，1 项既有兼容性用例跳过。
- `python -m compileall -q .`、`python scripts/generate_conf_schema.py --check`、`python scripts/check_architecture.py`、全部页面 JavaScript `node --check` 和 `git diff --check`：通过。
- 自动化页面回归已覆盖删除后补齐、页码回退、跨页选择、部分失败保留与缩略图缓存边界/失效；当前环境无法访问局域网 AstrBot WebUI，长页面滚动与真实浏览器交互仍需人工复核。

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
