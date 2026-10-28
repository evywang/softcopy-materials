# softcopy-materials 软著材料生成技能

从真实项目生成中国软件著作权登记申请资料的本地 skill：项目分析、业务理解、代码材料抽取、申请表信息、操作手册或技术方案文档，最终经 OfficeCLI 输出可提交前再导出 PDF 的 Word/TXT。适用于 workbuddy、zcode、mimo、trae、qorder、opencode、pi、muse、hermes 等支持本地 skill 目录的 coding agent。

本技能是对开源项目 [Fokkyp/SoftwareCopyright-Skill](https://github.com/Fokkyp/SoftwareCopyright-Skill)（MIT）做功能层面的 clean-room 分析后重新实现的版本，架构与代码均为重写，修复了原实现中的已知缺陷（接口返回结果丢失、章节编号错乱、正文盲替换、自检记录失真、序列图渲染调用错误、演示项目残留等）。

## 能力概览

- 双文档类型：有界面软件生成操作手册；无界面软件（固件、驱动、库、服务、命令行）生成技术方案文档，模块表与接口表必须回溯源码。
- 真实代码：候选发现按内容而非扩展名白名单；模型选择、用户确认后按完整文件抽取，去注释空行、90 列确定性折行、55 行/页估算、Word 自动分页、前30+后30 合并文档实际页数强校验为 60。手册/技术方案文档按文档鉴别材料规则读取真实页数，超过 60 页给出超页警告。
- 中文图纸：DOT 图纸自动注入 CJK 字体与版式默认值，渲染为 PNG；无 graphviz 环境自动降级为中文文本框线图（分层方框 + 连接关系），任何环境无乱码、无遮挡；宿主架构图技能（如 archify）产出的图片放入 `图纸原始/` 后优先于 DOT 渲染并登记图纸清单。
- 诚实门禁：七个阶段全部显式确认，内容指纹失效机制保证已确认文件被改动后必须重新确认；截图方式必须显式选择，不从备注猜测。
- 零改写正文：操作手册段落由模型亲写并原文引用，脚本不做同义词替换、句式生成或填充扩写；自检记录按真实轮次追加并可核对。
- 宿主协作：启动时登记宿主技能并主动利用（浏览器技能截图、PDF 阅读技能读证据、视觉能力审查图纸、搜索技能做行业调研、架构图技能如 archify 直接产图）。
- 合规审查：正式生成后脚本按登记口径机械核查（正式文件、申请表字段、代码 60 页/每页 50 行/无空行、代码逐行回溯源码、名称版本一致性、文档骨架、截图、图纸、门禁链指纹），模型以软著审查专员身份出具审查报告（通过/整改后通过/不通过），阻断项不得降级。

## 架构

```text
第1层
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│probe_env 环境探测│    │  analyze_project │    │  business_context│
└──────────────────┘    └──────────────────┘    └──────────────────┘
第2层
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  code_selection  │───▶│  extract_code    │───▶│ application_info │
└──────────────────┘    └──────────────────┘    └──────────────────┘
第3层
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  figures 图纸渲染│───▶│  manual_draft    │───▶│  shots 截图整理  │
└──────────────────┘    └──────────────────┘    └──────────────────┘
第4层
┌──────────────────┐    ┌──────────────────┐
│  confirm_gate    │───▶│  build_final     │
└──────────────────┘    └──────────────────┘

连接关系：
probe_env ──（门禁：environment）──▶ analyze_project
analyze_project ──（事实）──▶ business_context
business_context ──（业务理解）──▶ code_selection
extract_code ──（代码提取清单）──▶ application_info
business_context ──（design_spec）──▶ figures
figures ──（图纸清单）──▶ manual_draft
confirm_gate ──（七道内容指纹门禁）──▶ build_final
build_final ──（OfficeCLI）──▶ 申请资料 Word/TXT
review_final ──（机械核查底稿 + 审查专员报告）──▶ 审查/合规审查底稿、审查报告
confirm_gate ──（第八道门禁：审查确认）──▶ 审查/合规审查确认.json
```

门禁序列（全部需用户显式确认，指纹失效自动拦截）：

```text
环境确认
  ▼
业务理解（含 operation/design 文档类型）
  ▼
代码文件选择（模型填写 selected/model_reason）
  ▼
申请表字段（枚举/日期/长度/500~1300字窗口校验）
  ▼
截图方式（agent-browser/playwright-cli/user-supplied/skip 四选一）
  ▼
Markdown 最终确认（上游指纹 + 草稿完整性 + 自检清零）
  ▼
正式生成（60 页强校验、真实页数回写、主题字体统一）
  ▼
合规审查（机械核查底稿 + 审查专员报告）
  ▼
审查确认（第八道门禁：结论须明确且不为「不通过」）
```

## 安装到各 agent

把本目录（包含 SKILL.md 的 `out/` 文件夹，可重命名为 `softcopy-materials`）整体复制到所用 agent 的 skill 目录即可；不需要的 `tests/` 可以不复制。各 agent 的 skill 目录位置以其官方文档为准，常见形态：

| 形态 | 说明 |
| --- | --- |
| 用户级目录 | 如 zcode 的 `~/.zcode/skills/`、通用 `~/.agents/skills/` |
| 项目级目录 | agent 支持的 `.zcode/skills/`、`.opencode/`、项目 skills 文件夹等 |
| 配置声明 | 部分 agent 需要在配置文件中登记 skill 路径后重启会话 |

技能不含任何 agent 专属环境变量或产品名，脚本均为纯 Python 3.10+ 标准库 CLI（可选增强：pypdf 提取 PDF、graphviz 渲染 PNG），Windows/macOS/Linux 通用。

复制完成后可立即做一次安装自检（只读；OfficeCLI 缺失时在用户同意后加 `--install` 执行官方全局安装，安装后按提示重启 agent 再自检）：

```bash
python scripts/setup_officecli.py
```

## 运行要求

- Python 3.10+。
- OfficeCLI（正式 Word 的唯一后端；版本要求：不低于 `1.0.151` 且主版本为 `1`，官方安装器的最新版通常即满足；缺失时技能仍可推进全部 Markdown/TXT 草稿并明确拒绝伪造成 DOCX）：

```powershell
irm https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.ps1 | iex
```

- 可选：graphviz + 中文字体（DOT 图纸渲染 PNG；Linux 需安装中文字体如 fonts-noto-cjk，缺失时自动降级中文文本框线图）、Node 18+ 与 `@playwright/cli@0.1.20`（仅 playwright-cli 截图方式）、pypdf（PDF 证据正文提取）。宿主自带架构图技能（如 archify）时无需额外安装：图片放入 `软著/图纸原始/` 即被 figures.py 优先采用。

## 使用

在打开目标项目的 agent 会话中说：

```text
使用 softcopy-materials 为当前项目生成软著材料
```

按流程引导确认信息，材料生成在项目目录 `软著/`（草稿在 `草稿/`，正式 Word/TXT 只写入 `申请资料/`，不写临时目录）。提交前把需要上传的 docx 另存为 PDF，按中国版权保护中心官网要求填报。逐步命令示例（操作手册与技术方案文档两条完整路径，含 archify 宿主产图）见 [使用示例.md](使用示例.md)。

## 测试

```bash
cd out
python -m unittest discover -s tests
```

## 许可

MIT，见 [LICENSE](LICENSE)。使用者需自行核对生成材料是否符合项目实际与官网当前要求；本技能不提供任何法律担保。
