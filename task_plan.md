# Task Plan: 重构表情包主分类与全量语义重索引

## Goal
将当前多标签平铺的表情包索引重构为少量稳定主分类 + 辅助语义信息，并把手动重索引升级为可幂等跳过 v4 条目、增量修复旧条目的全量语义检查，发布 v2.1.6。

## Next Step
完成全项目健康审查，修正元数据/注册版本不一致，并同步发布日志后运行全量验证。

## Current Phase
Phase 6

## Phases

### Phase 1: Requirements & Discovery
- [x] 确认现有主分类、标签规范和版本/日志位置
- [x] 确认用户批准“主分类与辅助标签分离”的方向
- [x] 确认最终主分类集合
- **Status:** complete

### Phase 2: Planning & Structure
- [x] 写入并自检设计文档
- [x] 写入实现计划
- [x] 定义兼容迁移策略
- **Status:** complete

### Phase 3: Implementation
- [x] 先写失败测试
- [x] 实现主分类/辅助语义分离
- [x] 更新版本与 CHANGELOG
- **Status:** complete

### Phase 4: Testing & Verification
- [x] 运行新增和完整测试
- [x] 验证旧索引迁移兼容
- [x] 检查版本、日志和最终 diff
- **Status:** complete

### Phase 5: Delivery
- [x] 汇总修改范围与验证结果
- [x] 更新工作记录
- [x] 创建本地功能 commit
- [ ] 等待用户决定是否推送远端
- **Status:** complete（本地提交已创建，未推送远端）

## Addendum: Full Semantic Reindex Check — 2026-08-15

### Phase A: Contract and tests
- [x] 定义 v4 当前条目判断和 `full_reindex_status` 标记
- [x] 覆盖完整条目跳过、旧条目重识别和单图失败隔离

### Phase B: Runtime and API
- [x] 将全量扫描接入现有扁平化和 catalog 写入流程
- [x] 保留 SHA 变化信息，避免迁移阶段误跳过
- [x] 接入进度计数、任务状态和 capture/index 互斥

### Phase C: UI and release
- [x] 更新两份语义管理页面和脚本缓存版本
- [x] 更新 v2.1.7、README 和 CHANGELOG
- [x] 完成 350 项测试通过、1 项跳过及静态检查

## Addendum: Resumable Full Reindex — 2026-08-15

### Phase D: Root cause and recovery
- [x] 复现并确认末尾写入导致的中断丢失
- [x] 修正多图片扁平化时旧 SHA 错误复用
- [x] 增加批次检查点和资源包级持久化状态
- [x] 接入页面重返、插件重载后的自动恢复
- [x] 完成 350 项全量测试和静态检查

## Key Questions
1. v2.1.5 的主分类是否采用 12 个稳定类别：开心、悲伤、尴尬、无奈、疑惑、震惊、愤怒、吐槽、赞同、拒绝、卖萌、围观？
2. 辅助标签是否最多保留 2 个，并且不参与自动发送分类？
3. 旧索引缺少主分类时是否通过重索引重新生成，而不是根据旧标签硬推断？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 待用户确认后采用少量稳定主分类 | 当前 28 个固定标签存在模型误分和语义重叠，继续增加标签会放大候选污染 |
| 辅助标签只用于语义描述，不作为自动发送分类 | 避免一次误加标签让图片进入错误分类 |
| 版本号从 v2.1.4 递增到 v2.1.5 | 本次属于可见的索引数据契约和选图行为变更 |
| 主分类固定为 12 个中文类别 | 用户已确认，减少主分类噪声并保留语义描述承载细节 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Git 无法读取用户级 ignore 文件 | 1 | 不影响当前工作区状态读取，继续使用显式路径检查 |
| 读取仓库内 `data/.../builtin-default/memes_data.json` 失败 | 1 | 当前 pack 使用 flat `memes/index.json`，继续依据实际代码追踪 |
| 只读代码审查代理在多次 30 秒等待后仍未返回 | 1 | 关闭审查代理；以本地完整测试、编译和 diff 检查作为最终证据，并在交付中明确说明 |
| Git 暂存首次因 `.git/index.lock` 权限被拒绝 | 1 | 使用受限 Git 权限仅暂存并提交设计文档，未包含代码改动 |
| 审查计划文件已存在却被模板初始化覆盖 | 1 | 从 `HEAD` 读取并恢复原文件，再追加本次审查记录 |

## Notes
- 遵循系统调试流程：先复现/追踪根因，再写失败测试和修复。

## Addendum: 2026-08-16 — Project Metadata and Release Audit

### Phase 6: Requirements & Discovery
- [x] 对全项目运行健康审查并记录 R/T 风险
- [x] 对齐 `metadata.yaml` 与 `main.py @register` 版本
- [x] 更新 CHANGELOG/发布元数据并补充一致性测试（README 与 metadata.yaml 已是当前版本，无需改动）
- [x] 完成全量验证并交付审查报告
- **Status:** complete

### Phase 6 Results
- 修复运行时注册版本 2.1.0 与 manifest v2.1.7 不一致的问题。
- 新增版本一致性回归测试，并记录在 CHANGELOG。
- Brooks 健康评分：92/100（0 critical、1 warning、3 suggestions）。
- 全量验证：366 项通过、1 项跳过；compileall、schema、architecture、12 个 JavaScript 文件和 diff 检查通过。

## Addendum: 2026-08-16 — v4 Health Workspace

### Phase 7: Implementation and delivery
- [x] 暴露 `summary.v4` 与 `v4_status` 工作区 API 契约
- [x] 在两份索引页面加入 v4 环形完整率、状态气泡和响应式布局
- [x] 接入状态筛选，同时保留缩略图预览、分类气泡、分页和处置操作
- [x] 对齐 v2.1.8 清单、运行时注册、README、CHANGELOG 和页面缓存版本
- [x] 完成 369 项测试通过、1 项跳过及 compile/schema/architecture/Node/diff 门禁
- **Status:** complete；已创建本地提交，未推送远端

### Local commits
- `eca68f3` — `feat: expose v4 workspace health summary`
- `df9b659` — `feat: add v4 health panel to capture workspace`
- `911888e` — `feat: connect v4 health filters to capture workspace`
- `66e7642` — `chore: release v2.1.8 v4 health workspace`

## Addendum: 2026-08-17 — 移除表情包管理页面与死接口

### Goal
将 WebUI 收敛为表情索引、设置中心、资源广场三页，删除表情包管理页及其专用后端 API 与顶层旧版页面副本，入口改为直接进入表情索引。

### 状态

- [x] 设计文档与实施计划
- [x] 路由/页面测试先行（红 → 绿）
- [x] 后端路由与 handler 删除
- [x] 前端页面与旧版副本删除
- [x] README / CHANGELOG / 版本（v2.2.0）
- [x] 全量验证门禁
- [ ] 本地 git 提交（需用户批准）

## Addendum: 2026-08-17 — 移除设置中心与资源广场（v2.3.0）

### Goal
删除设置中心与资源广场页面,把表情包导出/导入移植到表情索引页;选择规则、运行时备份、社区安装随页面移除。

### 状态

- [x] 设计文档与实施计划
- [x] 路由/页面测试先行（红 → 绿）
- [x] 后端 9 条路由与 handler 删除
- [x] 页面删除与导航收敛
- [x] 表情索引页导出/导入实现
- [x] README / CHANGELOG / 版本（v2.3.0）
- [ ] 全量验证与提交
