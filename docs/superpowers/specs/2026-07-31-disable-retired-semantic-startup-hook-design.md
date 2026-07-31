# 禁用退役语义索引启动钩子设计

## 目标

消除 AstrBot v4.26.8 启动时调用未绑定
`MemeSender._schedule_semantic_initial_rebuild` 所产生的 `missing self`
异常，同时保持表情发送、情景分析、分类选择和手动语义索引管理行为不变。

## 根因

`MemeSender` 定义在 `manager_base.py`，但实际注册的插件类
`MemeManager` 定义在 `main.py`。AstrBot v4.26.8 的生命周期装饰器按函数
`__module__` 保存 handler，插件加载器只给模块路径与具体插件主模块完全一致的
handler 绑定插件实例。因此基类中的 `@filter.on_astrbot_loaded()` handler
保持为未绑定函数，核心启动时无参数调用它便缺少 `self`。

当前代码又固定设置 `self.semantic_enabled = False`，已有回归测试明确要求旧版
向量语义配置不能启动自动重建。该启动 handler 即使正确绑定也只会立即返回。

## 方案

删除已经退役的自动启动重建链路：

- 删除 `MemeSender._schedule_semantic_initial_rebuild` 上的生命周期注册及方法。
- 删除只供该方法使用的 `_semantic_initial_rebuild_task` 实例字段。
- 删除只供该启动任务调用的 `_auto_rebuild_initial_pack` 方法。
- 删除 `terminate()` 中只负责取消该任务的清理代码。
- 删除因此不再使用的 `asyncio` 导入。

不在 `MemeManager` 中增加替代启动 hook，也不手动注册绑定方法。这样 AstrBot
启动时不会发现该 handler，自然不会调用未绑定函数，也不会为已经退役的功能
创建后台任务。

## 保留行为

- `semantic_enabled` 继续固定为 `False`，不恢复旧版自动向量检索路径。
- 语义管理页面的手动重建接口继续直接调用
  `semantic_task_manager.rebuild_index()`。
- `SemanticTaskManager` 的正常关闭继续由 `MemeSender.terminate()` 执行。
- 表情发送、情景分析、分类目录和表情包收集流程不变。

## 测试

新增回归测试，断言插件源码不再注册 `on_astrbot_loaded`，并且退役的启动调度
方法与任务字段均已删除。先运行测试确认它在现有代码上失败，再删除启动链路并
确认通过。最后运行完整 `unittest` 测试套件和 Python 编译检查。

## 兼容性

方案只使用“没有启动 handler 就不执行启动回调”这一稳定行为，不依赖
AstrBot 内部 handler 注册表、手工绑定或加载顺序，兼容 v4.26.8 的生命周期
实现，也降低后续热重载时残留或重复任务的风险。
