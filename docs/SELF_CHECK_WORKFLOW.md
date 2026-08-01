# 本地代码回归自检流程

本文用于在重构、删除模块、拆分 Mixin、修改 WebUI 路由或出现运行时
`AttributeError` 后，快速检查仓库中是否出现类似“调用仍在，但方法已经被移走/删除”
的回归漏洞。

## 适用场景

- 删除或合并 `semantic`、`web_api`、`emoji_api` 等模块后；
- 新增 WebUI 页面、接口或路由后；
- 修改多继承 Mixin、实例方法、回调注入后；
- 日志出现 `object has no attribute`、`takes 0 positional arguments`、页面空白或
  接口 404/500 后；
- 发布前或合并前的本地回归检查。

## 总流程

```text
确认范围
   ↓
语法/编译检查
   ↓
实例方法绑定检查
   ↓
删除/移动符号检查
   ↓
路由—处理器—页面接口检查
   ↓
单元测试与前端语法检查
   ↓
记录发现、分级、复测
```

所有命令默认在插件仓库根目录执行：

```powershell
Set-Location "E:\代码\astrbot_plugin_meme_stealer1"
```

## 1. 确认检查范围

先确认当前改动，不要把 `.worktrees`、缓存或构建产物当作源码扫描：

```powershell
git status --short
git diff --stat
rg --files -g '!**/.git/**' -g '!**/.worktrees/**' -g '!**/__pycache__/**'
```

如果工作区有用户未提交的修改，只检查和当前问题相关的文件，不要用重置命令覆盖它们。

## 2. 语法与编译检查

```powershell
python -m compileall -q .
```

失败时先修复语法错误，再继续后续检查。编译通过只代表代码能被解析，不能证明运行时
方法存在。

## 3. 检查实例方法是否漏写 `self`

类似本次问题的典型错误是：

```python
class WebAPIMixin:
    def _resolve_context():  # 错误：实例方法缺少 self
        ...
```

使用下面的 AST 检查，只检查类体中的直接方法，避免把嵌套函数误报为类方法：

```powershell
@'
import ast
from pathlib import Path

ROOT = Path('.')
EXCLUDED = {'.git', '.worktrees', '__pycache__', '.pytest_cache'}
errors = []

for path in ROOT.rglob('*.py'):
    if EXCLUDED.intersection(path.parts):
        continue
    try:
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    except (OSError, SyntaxError) as exc:
        errors.append(f'PARSE_ERROR {path}: {exc}')
        continue
    for class_node in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for method in [
            n for n in class_node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]:
            decorators = {
                n.id for n in method.decorator_list
                if isinstance(n, ast.Name)
            }
            if {'staticmethod', 'classmethod'} & decorators:
                continue
            positional = [*method.args.posonlyargs, *method.args.args]
            if not positional or positional[0].arg not in {'self', 'cls'}:
                errors.append(
                    f'MISSING_SELF {path}:{method.lineno} '
                    f'{class_node.name}.{method.name}'
                )

print('\n'.join(errors) if errors else 'MISSING_SELF: none')
raise SystemExit(1 if errors else 0)
'@ | python -
```

注意：`@staticmethod` 和 `@classmethod` 不需要 `self`；带其他名称的实例接收参数仍需人工确认，
不要仅按参数名机械修改。

## 4. 检查删除/移动后仍被调用的内部符号

先找出实例内部调用，再逐项确认定义是否仍存在：

```powershell
rg -n "self\._[A-Za-z0-9_]+\(" . `
  -g '!**/.git/**' -g '!**/.worktrees/**' -g '!**/__pycache__/**'
```

重点核对以下情况：

1. 被删除的旧模块仍被 import；
2. 方法定义从一个 Mixin 移到另一个 Mixin，但组合类没有继承新 Mixin；
3. 辅助函数从 `SemanticMixin` 移出后，`emoji_api.py`、页面接口仍继续调用；
4. 调用的是实例方法，却实际只留下了模块级函数；
5. 名称拼写或参数签名改变，但调用方没有同步更新。

本项目中 `capture_pipeline.py` 的 `_loader`、`_recognize_single`、`_classify_single`、
`_catalog_entry_builder`、`_bind_saved_result`、`_record_capture_event` 是构造函数注入的回调，
它们不是类方法缺失；扫描结果必须区分这类合法依赖和真实的未定义方法。

对每个疑似符号，使用仓库级搜索确认：

```powershell
rg -n "def _目标方法|_目标方法" . `
  -g '!**/.git/**' -g '!**/.worktrees/**' -g '!**/__pycache__/**'
```

若只有调用、没有定义或明确的依赖注入来源，必须记录为待修复项，不能用“当前页面没走到”
作为长期豁免理由。

## 5. 检查路由、处理器和页面接口契约

### 5.1 路由处理器是否存在

`mixins/web_routes.py` 中每条 `WebRouteSpec` 的处理器名，都必须能在当前 Mixin 组合的
源码中找到：

```powershell
@'
import ast
from pathlib import Path

ROOT = Path('.')
EXCLUDED = {'.git', '.worktrees', '__pycache__', '.pytest_cache'}
methods = set()
for path in ROOT.rglob('*.py'):
    if EXCLUDED.intersection(path.parts):
        continue
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods.update(
                child.name for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )

routes = ast.parse(Path('mixins/web_routes.py').read_text(encoding='utf-8-sig'))
handler_names = []
for node in ast.walk(routes):
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'WebRouteSpec'
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        handler_names.append(node.args[1].value)

missing = sorted(set(handler_names) - methods)
print(f'ROUTE_HANDLER_COUNT: {len(handler_names)}')
print(f'ROUTE_HANDLER_MISSING: {missing}')
raise SystemExit(1 if missing else 0)
'@ | python -
```

### 5.2 页面请求是否和路由一致

```powershell
rg -n "fetch\(|/meme_manager_master/|meme_image_data|capture/|semantic/" `
  pages mixins tests -g '!**/.worktrees/**'
```

逐项确认：HTTP 方法、路径、请求字段、响应字段和 capability 开关一致。新增页面时至少要有
一个接口成功/失败的测试，不能只检查页面能打开。

## 6. 回归测试

```powershell
python -m unittest discover -s tests -v
python scripts/generate_conf_schema.py --check
git diff --check
```

如果修改了 JavaScript：

```powershell
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object {
    node --check $_.FullName
}
```

本次类似漏洞必须覆盖“错误路径不会再次触发同一个缺失方法”的回归测试。例如预览接口应
同时覆盖：

- 缩略图生成成功时返回 `image/webp` Data URL；
- 缩略图不可用时回退原图 Data URL；
- 文件不存在、类型不支持时返回明确错误，而不是新的 `AttributeError`。

## 7. 发现记录模板

每个未确认的问题都按下面格式记录，直到复测关闭：

```markdown
### [P1/P2/P3] 简短标题

- 症状：用户看到什么，或日志出现什么。
- 证据：文件、行号、调用方与定义方的搜索结果。
- 影响：页面、接口、启动流程或数据处理的影响范围。
- 根因：漏写 self、删除后仍调用、Mixin 未继承、路由失配等。
- 修复：最小修复方案和需要补充的回归测试。
- 状态：待修复 / 已修复待复测 / 已关闭。
```

优先级建议：

- `P1`：启动失败、核心接口全部不可用、可能破坏已有数据；
- `P2`：某个页面或核心功能稳定失败；
- `P3`：当前默认配置不可达，但未来开关打开后会失败，或属于应清理的死代码。

## 本次自检记录（2026-08-01）

检查范围排除了 `.git`、`.worktrees`、`__pycache__` 和测试缓存目录。

| 检查项 | 结果 |
|---|---|
| Python 编译 | 通过 |
| 类体实例方法缺少 `self`/`cls` | 3 项，见下方 P2/P3 |
| WebUI 路由处理器 | 40 条路由，未发现缺失处理器 |
| 注入回调误报 | 6 个，确认是 `capture_pipeline.py` 的合法依赖注入 |
| `_resolve_embedding_provider` | 无定义但仅在已停用语义路径和提前返回代码中出现，见下方 P3 |
| 单元测试 | 112 项通过 |

### 当前自检发现

#### [P2] 上传、导入和备份接口的实例方法缺少 `self`

- 症状：`self._save_uploaded_file(...)`、`self._pack_import_session_paths(...)` 会把实例
  自动作为第一个参数传入，但定义没有 `self`，进入对应接口后会出现参数数量错误或把实例当成
  上传对象/令牌处理。
- 证据：[`mixins/web_api.py:280`](../mixins/web_api.py:280) 和
  [`mixins/web_api.py:290`](../mixins/web_api.py:290)；调用方位于
  [`mixins/pack_api.py:231`](../mixins/pack_api.py:231)、
  [`mixins/pack_api.py:301`](../mixins/pack_api.py:301)、
  [`mixins/pack_api.py:694`](../mixins/pack_api.py:694)。
- 影响：表情包压缩包导入、预检导入和运行时备份上传路径可能失败；现有 112 项测试没有覆盖
  这几个真实上传调用。
- 修复：补上 `self`，并增加异步上传、预检导入和备份导入的接口回归测试；修复后重新执行本流程。
- 状态：待修复。

#### [P3] `_get_webui_response_status` 也缺少 `self`，但当前没有调用方

- 证据：[`mixins/web_api.py:125`](../mixins/web_api.py:125)；仓库搜索未发现调用。
- 影响：当前默认路径不可达，未来恢复调用时会复现同类绑定错误。
- 修复：若确认不再需要则删除；若保留则补上 `self` 或明确标记为 `@staticmethod`，并添加测试。
- 状态：待清理/确认。

### 当前仍需关注的低优先级项

`mixins/event_handlers.py` 和 `mixins/web_api.py` 仍引用 `_resolve_embedding_provider`，但当前仓库
没有对应定义。当前 `_semantic_pack_ready()` 固定返回 `False`，而 `_pack_import_embedding_signature()`
在调用前直接返回，因此本次默认运行路径不会触发它；它仍是重启语义功能或删除提前返回后可能暴露的
潜在 `AttributeError`。后续应二选一：删除残留旧语义代码，或恢复一个有测试覆盖的明确实现。

## 关闭条件

只有同时满足以下条件，才可以把本次自检标记为完成：

1. 编译和 AST 检查通过；
2. 没有未解释的缺失方法、路由处理器或页面接口；
3. 全量测试、配置 schema 检查和 `git diff --check` 通过；
4. 所有 P1/P2 已修复并有回归测试；
5. P3 已记录负责人和后续处理方式。
