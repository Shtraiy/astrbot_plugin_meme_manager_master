# 配置说明

运行时配置统一由 `runtime_config.PluginConfig` 定义，并由
`scripts/generate_conf_schema.py` 生成 `_conf_schema.json`。

## 公开配置

| 配置项 | 类型 | 默认值 | 作用 |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | 启用插件 |
| `group_whitelist` | list[string] | `[]` | 群组白名单 |
| `vision_provider_id` | string | `""` | 图片识别模型 |
| `scene_provider_id` | string | `""` | 分类/情景判断模型 |
| `only_capture_memes` | bool | `true` | 仅采集表情包 |
| `meme_rejection_confidence` | float | `0.7` | 识别拒绝阈值 |
| `max_images_per_message` | int | `2` | 单次最多处理图片数 |
| `max_concurrent` | int | `2` | 并发模型请求数 |
| `max_image_size_mb` | int | `10` | 图片大小上限 |
| `download_timeout` | float | `20` | 下载超时秒数 |
| `auto_send_enabled` | bool | `true` | 启用情景判断后的自动发送 |
| `auto_send_probability` | float | `50` | 普通自动发送概率 |
| `auto_send_cooldown` | float | `30` | 自动发送冷却秒数 |
| `auto_send_candidate_limit` | int | `8` | 候选图片数量 |
| `meme_repeat_window` | float | `300` | 图片重复抑制窗口 |
| `meme_follow_up_window` | float | `300` | 后续消息关联窗口 |
| `proactive_send_after_steal` | bool | `false` | 采集后主动选择并发送 |
| `perceptual_dedupe_enabled` | bool | `true` | 启用感知去重 |
| `perceptual_duplicate_threshold` | int | `6` | 感知重复阈值 |
| `library_index_enabled` | bool | `false` | 启用后台目录索引 |
| `library_index_provider_id` | string | `""` | 目录索引模型 |
| `library_index_batch_size` | int | `6` | 索引批次大小 |
| `library_index_progress_step` | int | `5` | 索引进度步长 |
| `library_index_rename_files` | bool | `true` | 允许目录索引整理文件名 |
| `health_check_interval` | float | `300` | 健康检查间隔 |
| `fallback_category` | string | `"confused"` | 无法判断时使用的分类 |
| `local_image_roots` | list[string] | `[]` | 可选的本地图片根目录 |

图片选择使用情景判断和分类规则，不依赖 FAISS、Embedding 或图片语义化任务。
旧版本中的语义配置仍可能被兼容读取，但不会启动旧任务；启动时只清理
`semantic_metadata.json` 和 `semantic_indexes`，不会删除图片、分类、目录索引或选择规则。

迁移表情包时，分类目录中的 `index.json` 和 `README.md` 会一并复制。
