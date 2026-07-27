# 修复复核

## 结果

- 批量索引结果支持规范 ID、文件名/stem、1-based ID、ID 键对象和完整结果顺序。
- 部分结果不会被无依据地顺序错配，缺失项保持“待重新识别”。
- 索引源文件签名未变化时跳过任务；索引内容未变化时跳过 `index.json`/`README.md` 写入。
- 批量失败时先降级为逐图识别；逐图也失败才停止当前索引轮次并按源签名退避，索引期间新增或变更的图片会在下一轮继续处理。
- `meme_image_data` 路由不在本插件仓库内，因此未修改依赖插件 WebUI；本插件只减少可能触发其刷新链路的无意义写入。

## 验证

`python -m unittest discover -s tests -p 'test*.py' -v`：44 项通过，2 项因 Pillow 未安装跳过。

`python -m py_compile main.py collector.py health.py indexing.py storage.py`：通过。

`git diff --check`：通过。
