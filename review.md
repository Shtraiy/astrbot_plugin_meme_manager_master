# 移植复核

## 本轮复核结果

- 补齐参考实现缺失的 `image_host` 运行目录，修复图床配置 schema 缺少 `items` 导致的插件安装 `KeyError`。
- 去除重复的 `after_message_sent` 注册，避免同一消息被二次处理。
- 统一默认表情包的运行时路径；切换默认包后，选图、分类、上传、WebUI 图片读写和索引维护使用同一目录。
- 兼容旧版 `index.json` 的 BOM、顶层数组、`images`/`entries`/`memes`/`data` 结构，并启动时补齐或清理分类索引。
- 分类名校验支持 Unicode，同时拒绝路径穿越和 Windows 特殊路径字符；图片 API 只允许读取图片文件。

## 验证

- `python -m unittest discover -s tests -v`：16 项通过。
- `python -m compileall -q ...`：通过。
- schema 对象节点检查：全部包含 `items`。
- 相对导入静态检查：未发现缺失模块。
- 参考代码运行文件对照：仅缺少 `.github/img` 文档截图，不影响插件运行。

本地未安装完整 AstrBot 运行时，因此无法在此工作区直接启动 AstrBot、注册真实 WebUI 路由或调用真实 Provider；这些部分已完成静态检查和离线单元测试。
