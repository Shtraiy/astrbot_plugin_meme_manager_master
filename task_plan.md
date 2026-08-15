# Task Plan: 重构表情包主分类与全量语义重索引

## Goal
将当前多标签平铺的表情包索引重构为少量稳定主分类 + 辅助语义信息，并把手动重索引升级为可幂等跳过 v4 条目、增量修复旧条目的全量语义检查，发布 v2.1.6。

## Next Step
完成交付前静态检查、提交本地变更，并等待用户决定是否推送远端。

## Current Phase
Phase 5

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

## Notes
- 遵循系统调试流程：先复现/追踪根因，再写失败测试和修复。
