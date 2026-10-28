# 业务理解规则

申请表与文档不能只看代码结构泛泛生成，必须先让模型理解软件业务，再由脚本校验结构。

## 文档类型判定

模型研判时先判定软件是否存在面向用户的图形界面，并在模型稿中写 `manual_kind`：

- `operation`：有用户可见页面或图形界面（Web、桌面、移动端），生成操作手册，必须填写 `manual_modules`。
- `design`：无界面软件（嵌入式固件、驱动、库、后端服务、命令行工具），生成技术方案文档，必须填写 `design_spec`，且不得填写 `manual_modules`、`system_requirements`、`faq`、`glossary`。

文档类型在业务确认门禁中由用户确认；判定错误可改回另一种并重新生成。

## 证据收集

脚本只登记证据：README、docs 下的 PRD/BRD/架构文档、DOCX/ODT 自动提取正文、PDF 在有 pypdf 时提取（否则登记路径，由 agent 用宿主 PDF 阅读技能读取）、DOC/WPS 登记路径。证据只是候选，行业、功能、结构判断一律由模型阅读后作出。

## 模型稿硬性要求

- `industry`、`application_purpose` 各不超过 50 字；`technical_characteristics` 不超过 100 字；`main_functions` 为 500~1300 个非空白字符，不满足直接拒绝，脚本不会扩写。
- operation 模式每个 `manual_modules` 条目必须包含 title、purpose、usage（或 usage_scenario）、entry、operation_steps、feedback，以及 `paragraphs`：至少两段模型亲写的自然段，每段不少于 80 个非空白字符。段落会原文进入操作手册，脚本不做任何改写、替换或句式生成；结构化字段用于追溯与自检。
- design 模式的 `design_spec` 中 requirements、conditions、architecture、modules、overview、functions、api_groups、error_handling 必填；每个接口的 signature、description、returns 三项均为必填，params 表可空。
- 不得把测试项目或范本的名称、流程、文案写成通用内容；不得编造项目不存在的功能、模块或接口。
- 外部调研（搜索工具）只用于理解行业表达，结论写入 `external_research_notes` 并与项目证据区分。
