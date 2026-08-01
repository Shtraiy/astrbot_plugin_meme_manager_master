# 配置说明

运行时配置统一由 `runtime_config.PluginConfig` 定义（类型、默认值、边界），
并由 `scripts/generate_conf_schema.py` 生成 `_conf_schema.json`，避免 schema
漂移。`_conf_schema.json` 与代码不一致时，`--check` 会以退出码 1 报错。

## 公开配置

| 配置项 | 类型 | 默认值 | 边界 | 产生模型调用 |
| --- | --- | --- | --- | --- |
| `enabled` | bool | `true` | - | 否 |
| `group_whitelist` | list[string] | `[]` | - | 否 |
| `vision_provider_id` | string | `""` | - | 是（视觉识别） |
| `scene_provider_id` | string | `""` | - | 是（分类/情景识别） |
| `reply_scene_provider_id` | string | `""` | - | 是（回复情景识别） |
| `only_capture_memes` | bool | `true` | - | 否 |
| `meme_rejection_confidence` | float | `0.7` | `0–1` | 否 |
| `max_images_per_message` | int | `2` | `1–6` | 否（限制调用次数） |
| `max_concurrent` | int | `2` | `1–8` | 否（限制并发调用） |
| `max_image_size_mb` | int | `10` | `1–50` | 否 |
| `download_timeout` | float | `20` | `5–120` | 否 |
| `auto_send_enabled` | bool | `true` | - | 是（自动发送判定） |
| `auto_send_probability` | float | `50` | `0–100` | 是（按概率触发判定） |
| `auto_send_cooldown` | float | `30` | `0–3600` | 否 |
| `auto_send_candidate_limit` | int | `8` | `2–16` | 否 |
| `meme_repeat_window` | float | `300` | `0–86400` | 否 |
| `meme_follow_up_window` | float | `300` | `10–1800` | 否 |
| `proactive_send_after_steal` | bool | `false` | - | 是（偷取后主动选图） |
| `perceptual_dedupe_enabled` | bool | `true` | - | 否 |
| `perceptual_duplicate_threshold` | int | `6` | `0–16` | 否 |
| `library_index_enabled` | bool | `false` | - | 是（后台索引） |
| `library_index_provider_id` | string | `""` | - | 是（后台索引） |
| `library_index_batch_size` | int | `6` | `1–12` | 否（限制索引批大小） |
| `library_index_progress_step` | int | `5` | `1–50` | 否 |
| `library_index_rename_files` | bool | `true` | - | 否 |
| `health_check_interval` | float | `300` | `10–600` | 否 |
| `fallback_category` | string | `"confused"` | - | 否 |
| `local_image_roots` | list[string] | `[]` | - | 否 |
| `vector_semantic_enabled` | bool | `false` | - | 是（向量 embedding/重建） |

数值超界会被 clamp 到边界内；类型非法时回退默认值。列表字段（
`group_whitelist`、`local_image_roots`）支持字符串（以逗号或换行分隔）或
数组两种写法，运行时统一转换为只读元组。旧版嵌套键（如
`semantic.vision_provider_id`）在没有对应 flat key 时仍会被兼容读取，每次
启动最多记录一次迁移提示。

`vector_semantic_enabled` 默认关闭：未安装 `faiss-cpu` 或未开启时，默认路由面
不暴露向量任务操作（`semantic/start`、`rebuild-index`、`clear-local-state`、
`delete-all` 等）；目录索引、人工复审和 capture workspace 始终可用。安装
`requirements-semantic.txt` 并开启后，向量路由才会注册。

参考插件迁移来的高级配置仍可被运行时兼容读取，但不再显示在设置页；这包括
旧版标记解析、语义索引和旧版提示词等。图床同步相关配置和代码已移除。

迁移表情包时，分类目录中的 `index.json` 和 `README.md` 会一并复制。若此前
已经生成过空的目标索引，插件启动时会自动用原目录中的非空索引修复，不需要
删除迁移标记。
