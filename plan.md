# 实施计划

## Session 2026-08-17：移除表情包管理页面与死接口

1. [x] 确认范围：表情包管理页与表情索引页功能重叠，完全移除管理页，保留索引。
2. [x] 编写设计文档 `docs/superpowers/specs/2026-08-17-remove-meme-manage-page-design.md`。
3. [x] 路由契约测试先行：声明被删路由不注册（红 → 绿）。
4. [x] 页面/前端资产测试收敛到剩余三页（表情索引、设置中心、资源广场）。
5. [x] 删除后端路由与 handler：`emoji/*`、`emotions`、`category/*`、`sync/*`、
   `meme_image`、`packs/default`、`packs/uninstall`、`community/install_official_first`。
6. [x] 删除前端管理页与顶层旧版副本，入口重定向改为表情索引。
7. [x] 更新 README、CHANGELOG、版本号（v2.2.0）与工作记录。
8. [x] 运行全量验证门禁（350 项测试通过、compile/schema/architecture/Node/diff 全绿）。
9. [ ] 本地 git 提交（沙箱审批通道故障，需用户批准）。
