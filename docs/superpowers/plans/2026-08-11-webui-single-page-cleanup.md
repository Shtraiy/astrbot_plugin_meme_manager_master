# WebUI 单页化与功能清理实施计划

1. 先增加页面发现、hash 导航、初始化幂等、分页位置和功能清理回归测试，并确认旧实现失败。
2. 将索引和设置标记合并进 `pages/a_manage/index.html`，把脚本与样式移动到同一静态资源作用域。
3. 增加 `router.js`，保留 `managed_pack_id` 查询参数和浏览器历史行为。
4. 移除资源广场与批量选择前端，收窄管理脚本并保留单项操作。
5. 调整索引分页摘要和设置中心保留模块，删除旧 Page 目录。
6. 更新 README 与 CHANGELOG，运行项目完整验证门禁和代码审查。
7. 仅暂存本任务文件，创建本地提交 `fix: simplify and stabilize webui navigation`，不推送。
