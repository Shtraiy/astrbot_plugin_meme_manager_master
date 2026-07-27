# Configuration

The settings page exposes the core options below; advanced runtime options are also available:

| Setting | Purpose |
| --- | --- |
| `enabled` | Enable or pause automatic collection |
| `group_whitelist` | Restrict collection to selected groups |
| `vision_provider_id` | Model used to recognize incoming images |
| `scene_provider_id` | Model used to choose a meme category |
| `only_capture_memes` | Skip ordinary photos and non-meme images |
| `auto_send_enabled` | Allow automatic meme replies |
| `library_index_enabled` | Allow background library indexing (off by default) |
| `library_index_batch_size` | Number of images sent to the vision model per indexing batch; range 1-12, default 6 |

Download limits, deduplication thresholds, concurrency, and candidate counts remain supported as advanced runtime keys. Existing configurations continue to work after upgrading.

Advanced keys can still be kept in the plugin configuration file when needed, such as `max_concurrent`, `download_timeout`, `auto_send_probability`, and `local_image_roots`.
