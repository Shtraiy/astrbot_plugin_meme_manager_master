# Filter 分段完成后发表情联动设计

## 目标

当 `astrbot_plugin_filter` 把机器人回复拆成多条消息发送时，
`meme_manager_master` 必须等待全部文本分段发送完成，最后再发送自动表情包。
没有分段时，自动表情包仍在正文主消息发送完成后立即发送。

## 根因

Filter 在 `on_decorating_result` 中为会话创建并持有一个 `asyncio.Lock`。
存在后续分段时，独立任务 `_send_followups_and_release` 负责逐段发送文本，并在
`finally` 中调用 `_finish_reply` 释放该锁。表情插件的 `after_message_sent`
只知道主消息已经发送，不知道 Filter 的后续任务仍在运行，因此会提前发表情。

Filter 的会话阀门与回复锁能够准确表示分段生命周期，但该锁目前只保存在 Filter
插件实例的私有 `_reply_locks` 中，其他插件无法通过稳定接口取得。

## 方案

采用事件级共享回复锁：

1. Filter 在获得当前会话的 `reply_lock` 后，通过 `AstrMessageEvent.set_extra`
   写入固定键 `astrbot_plugin_filter_reply_lock`。
2. 锁仍由 Filter 独占管理；表情插件不负责释放 Filter 原先持有的锁。
3. 主消息发送完成后，表情插件读取该事件附带的锁：
   - 若锁已释放，立即继续发送表情；
   - 若锁仍占用，等待取得一次锁，随后立即释放自己取得的锁，再发送表情。
4. Filter 的 `_send_followups_and_release` 在所有文本分段结束后释放原锁，
   因而表情插件恰好在最后一个文本分段之后恢复。
5. 等待设置 30 秒保护超时。超时时记录警告并继续发送，避免 Filter 异常导致
   表情永久丢失。
6. 若 Filter 未安装、版本较旧、事件不支持 extra，表情插件保持原行为。

## 执行顺序

```text
Filter 获取 reply_lock
→ Filter 拆分正文并启动后续发送任务
→ 表情插件完成选图并记录待发送图片
→ AstrBot 发送第一条正文
→ 表情插件在 after_message_sent 等待 reply_lock
→ Filter 发送第 2..N 条正文
→ Filter 释放 reply_lock
→ 表情插件取得并释放 reply_lock
→ 表情插件发送自动表情包
```

## 边界与错误处理

- 不轮询 Filter 私有字段，也不依赖 AstrBot 内部插件实例注册结构。
- 不使用固定睡眠时间估计分段结束。
- 不改变 Filter 阻止新对话进入的 gate 行为。
- 不改变表情插件的情景选择、概率、冷却或明确请求逻辑。
- Filter 分段任务即使发送失败，也会在 `finally` 中释放锁。
- 等待超时或读取到非 `asyncio.Lock` 对象时，不阻止自动表情发送。
- 插件终止导致外层任务取消时，保留取消语义，不强行继续发送。

## 测试

表情插件的纯异步辅助函数覆盖：

- 没有共享锁时立即返回；
- 已释放锁时立即返回；
- 锁占用期间不返回，释放后才返回；
- 超时后返回且不会释放 Filter 原先仍持有的锁。

Filter 参考代码覆盖：

- `on_decorating_result` 获取回复锁后将同一锁写入事件 extra；
- 原有分段发送与 `_finish_reply` 释放逻辑保持不变。

完整验收同时运行表情插件的 `unittest`、Filter 参考代码的测试套件、
Python 编译检查和差异格式检查。
