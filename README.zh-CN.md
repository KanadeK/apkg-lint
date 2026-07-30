# apkg-lint

[![CI](https://github.com/KanadeK/apkg-lint/actions/workflows/ci.yml/badge.svg)](https://github.com/KanadeK/apkg-lint/actions/workflows/ci.yml)
[![Security](https://github.com/KanadeK/apkg-lint/actions/workflows/security.yml/badge.svg)](https://github.com/KanadeK/apkg-lint/actions/workflows/security.yml)
[![Python 3.11–3.13](https://img.shields.io/badge/python-3.11%E2%80%933.13-3776AB)](https://www.python.org/)
[![MIT](https://img.shields.io/badge/license-MIT-161616)](LICENSE)

**在学习者遇到坏牌组之前，先把问题找出来。**

`apkg-lint` 是一个完全离线、只读的 Anki `.apkg` 发布前检查器和 CI
工具。它不把牌组导入 Anki，而是直接检查 ZIP、SQLite、笔记、卡片、
Cloze、模板、媒体和误带的学习进度。

```console
> apkg-lint check pharmacology.apkg
FAIL  pharmacology.apkg

  ERROR MEDIA005  Referenced media is absent: 'renal-clearance.png'
    at: notes/1700123456789/fields/1
    fix: Add the media to Anki or remove the stale reference, then re-export.

Summary: files=1, operational_errors=0, errors=1, warnings=0, info=0
```

[English](README.md) ·
[规则目录](docs/RULES.md) ·
[验收命令](docs/ACCEPTANCE.md) ·
[失败修复](docs/TROUBLESHOOTING.md) ·
[HTML 示例报告](examples/broken-report.html)

## 它解决什么

Anki 自带的 **Check Database** 和 **Check Media** 适合检查已经进入某个
用户配置的集合，但不适合对“即将发布的 APKG 成品”做可携带、可复查的
门禁；官方文档还明确说明媒体检查不会扫描正反面模板。

`apkg-lint` 补的是这个空位：

| 层级 | 实际检查 |
| --- | --- |
| 包 | 路径穿越、符号链接、重复成员、ZIP 炸弹、缺失集合、未映射文件 |
| 数据库 | SQLite 完整性、schema 范围、孤儿卡、缺失牌组和笔记类型 |
| 笔记 | 空首字段、规范化重复、字段数量漂移 |
| Cloze | 缺少挖空、范围语法、标记序号与实际卡片不一致 |
| 模板 | 引用已删除字段、正面没有任何有效字段 |
| 媒体 | 缺失引用、缺失成员、zstd 错误、哈希/大小漂移、未使用文件、跨平台重名 |
| 分享 | 分享包误带复习记录或已排程卡片 |

每个结果都有稳定规则 ID、证据、包内位置和修复办法，不是只有一个模糊
红灯。完整规则见 [docs/RULES.md](docs/RULES.md)。

## 安装

从 GitHub 安装：

```bash
pipx install git+https://github.com/KanadeK/apkg-lint.git
```

不长期安装，直接运行：

```bash
uvx --from git+https://github.com/KanadeK/apkg-lint.git apkg-lint check deck.apkg
```

也可从 [最新 Release](https://github.com/KanadeK/apkg-lint/releases/latest)
下载 wheel：

```bash
python -m pip install apkg_lint-0.1.0-py3-none-any.whl
```

支持 Windows、macOS、Linux 上的 Python 3.11–3.13。运行时只有
`zstandard` 一个依赖，用于读取当前 Anki 包格式。

## 使用

```bash
# 单个文件
apkg-lint check deck.apkg

# 递归检查目录里的全部 APKG
apkg-lint check releases/

# JSON / HTML / SARIF
apkg-lint check deck.apkg --format json  -o report.json
apkg-lint check deck.apkg --format html  -o report.html
apkg-lint check deck.apkg --format sarif -o report.sarif

# 这是带进度的个人备份，不按“公开分享包”检查
apkg-lint check backup.apkg --profile backup

# 查看所有规则
apkg-lint rules
```

退出码：

- `0`：没有达到失败阈值的问题；
- `1`：发现达到 `--fail-on` 的规则结果；
- `2`：命令、配置、输入包或报告写入本身失败。

默认阈值是 `warning`，可以改为 `error`、`info` 或 `none`。

## 配置

当前目录的 `apkg-lint.toml` 会自动读取，也可以用 `--config` 指定：

```toml
[apkg_lint]
profile = "shared"
fail_on = "warning"
verify_media = true
ignore = []

[severity]
MEDIA006 = "info"

[limits]
max_members = 100000
max_uncompressed_mb = 4096
max_database_mb = 2048
max_control_mb = 64
max_compression_ratio = 1000
```

未知字段和非法值会以退出码 2 失败，不会悄悄忽略。完整样例在
[examples/apkg-lint.toml](examples/apkg-lint.toml)。

## GitHub Action

```yaml
- uses: actions/checkout@v4
- uses: KanadeK/apkg-lint@v0.1.0
  with:
    path: dist/course.apkg
    profile: shared
    fail-on: warning
    format: sarif
    output: apkg-lint.sarif
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: apkg-lint-report
    path: apkg-lint.sarif
```

高安全要求的工作流应把第三方 Action 固定到不可变 commit SHA；本仓库
自己的工作流已这样做。

## 格式兼容

- 旧版 v1：`collection.anki2`；
- 旧版 v2：`collection.anki21`；
- 当前 v3：`meta` + zstd `collection.anki21b`；
- legacy JSON 与当前 protobuf 的笔记类型、模板和媒体索引；
- collection schema 11–18。

精确边界和 Anki 官方源码依据见
[docs/FORMAT_SUPPORT.md](docs/FORMAT_SUPPORT.md)。

## 隐私与安全

- CLI 不联网；
- 输入只读，不进入真实 Anki 配置；
- SQLite 只释放到临时目录，结束后删除；
- 不按压缩包自带路径解压；
- 在解析前限制成员数、展开体积、数据库大小、控制数据、文件名、
  符号链接和压缩比；
- HTML 报告会转义牌组内容。

报告会包含媒体文件名和少量规范化证据，公开报告前仍应检查是否敏感。

## 开发与验收

```bash
uv sync --all-groups --locked
uv run python scripts/verify.py
uv run python scripts/package_release.py
```

门禁包含格式、静态检查、严格类型、51 个正常/对抗测试、90% 以上分支感知
覆盖率、好坏示例包演练、密钥扫描和打包。最终发布检查还会核对 Git 作者/
提交者/贡献者、禁止 `Co-authored-by`、重复构建字节哈希，以及在干净虚拟
环境里安装 wheel 后再次运行。

逐条验收见 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)，失败后的具体恢复
步骤见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

## 范围

它不是 Anki 替代品、排程器、牌组生成器或 AI 写作点评器；它不会修改
牌组，也不声称一张结构正确的卡片在教学上一定优秀。

本项目独立开发，与 Anki 或 Ankitects 无隶属或背书关系。

## 许可证

[MIT](LICENSE)
