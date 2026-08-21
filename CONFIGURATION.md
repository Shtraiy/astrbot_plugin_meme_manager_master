# 配置说明

运行时配置统一由 `runtime_config.PluginConfig` 定义，AstrBot Web 设置 schema 由
`scripts/generate_conf_schema.py` 从同一份定义生成。

## Web 中的日常设置

| 配置项 | 类型 | 默认值 | 作用 |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | 启用插件 |
| `group_whitelist` | list[string] | `[]` | 群聊白名单；留空表示允许所有群 |
| `vision_provider_id` | string | `""` | 图片识别模型；留空使用当前会话模型 |
| `scene_provider_id` | string | `""` | 情景判断模型；留空使用当前会话模型 |
| `only_capture_memes` | bool | `true` | 只保存被识别为表情包的图片 |
| `auto_send_enabled` | bool | `true` | 启用最终回复阶段的情景判断和自动追加 |
| `auto_send_probability` | float | `50` | 情景模型决定发送后的概率控制 |
| `auto_send_cooldown` | float | `30` | 自动发送之间的冷却秒数 |
| `llm_tool_enabled` | bool | `true` | 允许 LLM 调用 `send_meme` 工具自动选图并发送 |

情景模型会参考当前用户消息、机器人回复和最近 3 轮文本上下文。生图、自拍、插画、
视频等外部视觉请求不会被当成本地表情包请求；当前回复已经包含外部媒体时也不会追加
本地表情包。

`send_meme` LLM 工具在 AstrBot 智能体调用时独立发送一张表情包，不受
`auto_send_probability` 概率抽样影响；发送成功后会在事件上打上去重标记并记录冷却，
同一轮回复不会重复追加表情包。

## 高级运行配置

图片大小、下载超时、并发数、候选数量、重复抑制、感知去重、后台目录索引、采集后主动
发送、本地图片目录和健康检查间隔等参数仍由 `PluginConfig` 读取，以兼容已有配置文件，
但不再暴露在 AstrBot Web 日常设置中。

旧版本的 `fallback_category` 也会继续兼容读取，但它不再作为实际回退分类使用；模型
失败时插件保留原回复并跳过本地表情包发送。

运行 schema 同步检查：

```powershell
python scripts\generate_conf_schema.py --check
```
