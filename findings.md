# Findings & Decisions

## Requirements
- 避免自动发送带有不合适文字的表情包。
- 针对日志中“分类为尴尬、候选图片上有字、发送时未注意”的链路增加可验证的保护。
- 保持现有自动表情包功能，不因缺少 Filter 回复钩子而绕过图片候选校验。
- 用户批准重构：使用少量稳定主分类，辅助标签不再直接决定自动发送分类；同时更新版本和 CHANGELOG。

## Research Findings
- 日志显示 `meme_selection` 已决定 `category=尴尬` 并返回 `indexed_count=186`。
- 随后 `capture` 直接以路径加入当前消息链：`无 Filter 回复钩子或无可见正文，直接加入当前消息链发送自动表情包`。
- 因此问题至少发生在“候选确定/发送前”的边界，不能仅凭情景分类解决。
- `MemeSelectionService.choose()` 的模型提示只包含每个分类的 `description` 与 `indexed_count`，不包含分类下每张图片的 `description`、`text` 或 `tags`。
- 分类确定后，`SelectionState.pick_indexed()` 仅按标签查找图片并按发送权重随机选择，不读取单图语义字段；这解释了“分类正确但抽到带有不合适配字的图片”。
- 索引识别链路已经保存 `text` 字段：`_library_batch_system_prompt()` 要求视觉模型输出图片文字，`normalize_library_results()` 和 `_catalog_entry_from_vision()` 也会保留该字段。
- 当前 flat tag index 为发送权重服务，只保存 filename/tags/send statistics，不适合作为单图语义候选源；单图语义应从主 catalog 读取。
- 项目已有旧版 `OUTGOING_DECISION_SYSTEM_PROMPT`，其中明确要求模型从候选图片选择 `candidate_id`，但当前 `MemeSelectionService.choose()` 使用的是分类级 `OUTGOING_CATEGORY_PROMPT`，实际未实现单图选择。
- 当前 `backend/tagging.py` 定义了 28 个 canonical tags、最多保留 6 个；采集时会把场景分类和视觉模型标签合并，之后 tag index 会把一张图片加入它的所有标签，因此误标签会污染多个自动发送分类。
- 当前版本为 `v2.1.4`，版本声明位于 `metadata.yaml` 和 `README.md`，日志采用 Keep a Changelog 结构，下一版本应记录为 `v2.1.5`。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 将单图 `description/text/tags` 纳入 outgoing 候选，再由模型选具体图片 | 复用已有索引语义，修复分类后随机抽图造成的误配，不需要运行时 OCR |
| 保留发送权重，但只在模型选定候选集合内加权抽取或直接发送选定候选 | 不破坏已有重复发送抑制，同时让语义选择优先于随机分类内抽样 |
| 待确认 12 个主分类、最多 2 个辅助标签 | 减少标签噪声，避免辅助描述反向改变自动发送分类 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 读取仓库内 `data/.../builtin-default/memes_data.json` 失败，文件不存在 | 该路径不是当前 flat pack 的实际元数据位置；继续依据代码和测试追踪 `index.json` |

## Resources
- `task_plan.md`
- `progress.md`

## Visual/Browser Findings
- 无。

## Refactor Results — 2026-08-15

- `backend/tagging.py` 新增 12 个 `PRIMARY_CATEGORIES`，主分类与旧 28 标签体系分离；`semantic_tags` 最多保留 2 个，不参与自动路由。
- `storage.py` 在读取目录时按“已有合法主分类 > category > 唯一旧主分类标签”迁移；多义条目标记 `primary_category_status=needs_reindex`，不会进入 `by_primary_category`。
- 派生 `tag_index.json` 同时保留旧 `by_tag` 和新的 `by_primary_category`；自动选图优先使用主分类接口，旧接口只作为兼容回退。
- 视觉索引现在持久化 `semantic_summary`、`visible_text`、`text_meaning`、`use_cases`、`avoid_cases` 和 `classification_confidence`，并保留 `text=visible_text` 兼容别名。
- outgoing 候选提示包含单图语义和负向场景；候选 ID 与主分类不一致时不会跨分类选图。
- 索引契约升级为 `LIBRARY_INDEX_VERSION=4` / `library-semantic-primary-v1`，发布版本升级到 v2.1.5。

## Verification Results — 2026-08-15

- 定向回归：30 项通过。
- 全量单元测试：339 项通过，1 项既有兼容性用例跳过。

## Full Reindex Findings — 2026-08-15

- 手动重索引必须以当前表情目录为边界重新检查，而不是只重排旧目录或只重建 tag index。
- “当前条目”的判断采用 `index_version=4`、提示词版本、当前 SHA、合法主分类以及完整语义字段的组合契约；完整条目直接跳过视觉模型。
- 不把 provider ID 纳入跳过条件。只要 v4 语义结果完整且文件未变化，就保持幂等，避免更换模型配置后无意义地重跑全部图片。
- 扁平化会保留旧 SHA 到 `reindex_previous_sha256`，因为迁移阶段会刷新主 `sha256`；这样内容变化仍能被全量检查识别。
- 失败条目显式进入 error/needs_reindex 状态，并排除出 `by_primary_category`，防止旧的错误分类继续参与自动选图。
- API 复用现有任务状态和锁；手动全量重索引与后台 capture/index 互斥，避免两个流程同时覆盖同一份 catalog。
- WebUI 进度只展示跳过、重新识别和失败计数，不展示模型返回的原始文本；完成但有失败时使用 `completed_with_errors`，便于用户继续处理遗留条目。
- 若资源包中的所有条目都已满足 v4 契约，即使当前未配置视觉模型也可以完成全量检查；只有发现需要重新识别的图片时才返回 blocked。
