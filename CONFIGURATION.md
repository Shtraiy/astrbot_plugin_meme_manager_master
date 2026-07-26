# Configuration

The settings page now exposes only the options needed for normal use:

| Setting | Purpose |
| --- | --- |
| `enabled` | Enable or pause automatic collection |
| `group_whitelist` | Restrict collection to selected groups |
| `vision_provider_id` | Model used to recognize incoming images |
| `scene_provider_id` | Model used to choose a meme category |
| `only_capture_memes` | Skip ordinary photos and non-meme images |
| `auto_send_enabled` | Allow automatic meme replies |
| `library_index_enabled` | Allow background library indexing (off by default) |

Download limits, deduplication thresholds, concurrency, candidate counts, and indexing batch sizes remain supported as advanced runtime keys, but are no longer shown in the normal settings page. Existing configurations continue to work after upgrading.

Advanced keys can still be kept in the plugin configuration file when needed, such as `max_concurrent`, `download_timeout`, `auto_send_probability`, and `library_index_batch_size`.
