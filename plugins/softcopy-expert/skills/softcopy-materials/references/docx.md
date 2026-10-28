# OfficeCLI DOCX 后端

## 版本要求与边界

- 版本要求：不低于 `1.0.151` 且主版本为 `1`（允许 1.0.151 及以上同主版本，如 1.0.158）；官方安装器的最新版通常即满足。已实测版本：`1.0.151`、`1.0.158`（Windows + Word 真实生成/校验/分页/预览全链路）。发布页 https://github.com/iOfficeAI/OfficeCLI/releases
- OfficeCLI 必须全局安装（Windows PowerShell：`irm https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.ps1 | iex`；macOS/Linux：`curl -fsSL https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.sh | bash`），安装后重启 coding agent 刷新 PATH。
- 安装自检与经用户同意的安装入口是 `scripts/setup_officecli.py`：不带参数只做只读检查；`--install` 仅在用户明确同意后传入并执行官方安装器，安装后复读状态，PATH 未刷新时提示重启；`probe_env.py` 始终只读。
- 已安装但当前进程 PATH 找不到时报告 restart_required：Windows 检查官方安装目录（`%LOCALAPPDATA%\OfficeCLI`），Linux/macOS 检查 `/usr/local/bin`、`/opt/homebrew/bin`、`~/.local/bin`、`~/bin`，提示重启 coding agent 或新开终端后重新探测。
- 不下载到项目或 skill 目录；不使用 `OFFICECLI_PATH`、`--officecli` 或项目内便携版。
- 运行时设置 `OFFICECLI_SKIP_UPDATE=1` 与 `OFFICECLI_NO_AUTO_RESIDENT=1`，避免版本漂移与后台文件锁。
- Python 只做分析、校验、折行与命令编排；DOCX 的创建、写入、校验、预览全部经 OfficeCLI，Python 不直接解包或改写 DOCX 压缩包。
- 缺失或版本不匹配时停止并交用户选择；用户明确承担风险后正式生成才允许 `--allow-untested-officecli`。没有可用 OfficeCLI 时只推进 Markdown/TXT 草稿，不伪造成 DOCX。

## 写入策略

- 每个 DOCX 先 `create --force --locale zh-CN`，再用一个原子 `batch --stop-on-error` 写入；io_error 自动重试。
- A4 页面、页边距（代码 1.8cm、文档 2.5cm）、默认宋体、黑色文字、页眉（左：软件全称 版本号；右：第 X 页）全部由命令写入，不依赖模板。
- 代码材料：每个物理行一个固定 13pt 行距段落（Consolas 8pt、东亚宋体），连续写入不设分页符，Word 自动分页。
- 操作手册/技术方案文档：先以 Markdown 元素导入，再统一正文格式（宋体 10.5pt、1.5 倍行距、两端对齐、首行缩进 2 字符；标题黑体；截图预留与图预留居中）；本地图片以 picture 元素嵌入，远程图片保留可见提示。

## 校验策略

1. `validate`：OpenXML 结构错误必须为 0，否则生成失败。
2. 主题字体六个槽位统一为 Times New Roman / SimSun 并整体替换主题根节点后复读校验，避免 WPS 因 Calibri、等线提示缺字体。
3. `view issues` 的内容/格式提示写入生成报告，不当作结构校验。
4. 代码文档在 Windows + Word 环境执行 `view stats --page-count` 读取真实页数：前30页+后30页模式必须正好 60 页，否则生成失败并要求重新校准选材量；全部代码模式下实际页数与估算不同时，申请表 TXT 的页数字段按实际页数回写并在报告中说明。
5. 操作手册/技术方案文档同样读取真实页数并执行文档鉴别材料规则（前30+后30、不足 60 页提交全部、每页不少于 30 行）：超过 60 页给出超页警告并写入生成报告，需压缩内容或按前 30 页 + 后 30 页截取后提交；读不到真实页数时提示提交前人工复核。
6. 预览截图可选生成，HTML 渲染不能替代 Word/WPS 最终复核。
