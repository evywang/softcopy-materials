---
name: softcopy-materials
description: >
  从真实项目生成中国软件著作权申请资料（软著）。当用户提到 软件著作权、软著、
  软著申请、操作手册、技术方案文档、申请表信息、架构图/图纸、合规审查/审查报告
  或需要为软著登记准备 Word/TXT 材料时使用。流程为：环境探测 → 项目分析 → 业务理解 →
  代码选择与抽取 → 申请表与文档草稿（图纸由 DOT 渲染，宿主架构图技能如 archify 的
  产图可优先采用）→ 用户门禁确认 → OfficeCLI 生成正式 Word/TXT → 合规审查出具审查报告
  → 第八道门禁确认审查结论。
  适用于任何支持本地 skill 的 coding agent。
---

# 软著材料生成

本 skill 产出可审阅、可追溯的软件著作权申请资料。核心原则：

- 输出目录固定为当前工作目录下的 `软著/`；正式 Word/TXT 只写入 `软著/申请资料/`，不写临时目录。
- 代码材料只能来自真实项目源码，禁止 AI 编造代码；按完整文件抽取，去注释与空行后确定性折行。
- 脚本只收集证据、校验结构与执行门禁；行业判断、功能取舍、文档正文一律由模型阅读项目后撰写，脚本对正文原文引用、零改写。
- 涉及用户选择或确认的阶段必须停止，把 STOP_FOR_USER 与 NEXT_ACTION 告知用户后等待输入；禁止“用户未选择则默认继续”。
- 每个门禁记录内容指纹；草稿在确认后被修改，对应门禁立即失效。第八道门禁（审查确认）的指纹覆盖 `申请资料/` 与 `审查/审查报告.md`：正式交付物在审查确认后被改动即失效，必须重新审查。
- 软件分两类：有界面的生成操作手册（operation），无界面的生成技术方案文档（design）；类型由模型判定并经用户确认。
- 没有 OfficeCLI 时只推进 Markdown/TXT 草稿，不伪造成 DOCX；没有 graphviz 时图纸降级为中文文本框线图，不伪造 PNG。

## 通用约定

从当前已加载的 SKILL.md 位置取得本 skill 的绝对目录记为 `<SKILL_DIR>`，找到 Python 3.10+ 解释器记为 `<PYTHON>`；命令中的尖括号是必须替换的占位符，不依赖任何 agent 专属环境变量。脚本输出为 UTF-8 中文，Windows 控制台异常时可重定向到文件查看。

按阶段阅读参考文档，不要一次全部加载：

- 填申请表前读 [references/fields.md](references/fields.md)
- 研判业务前读 [references/business.md](references/business.md)
- 选择与抽取代码前读 [references/code-material.md](references/code-material.md)
- 写操作手册前读 [references/manual.md](references/manual.md)
- 写技术方案文档前读 [references/design.md](references/design.md) 与 [references/figures.md](references/figures.md)
- 截图前读 [references/shots.md](references/shots.md)
- 正式生成前读 [references/docx.md](references/docx.md)
- 做合规审查前读 [references/review.md](references/review.md)
- 合规审查前读 [references/review.md](references/review.md)

## 安装自检与 OfficeCLI 安装

各 agent 没有统一的安装钩子，把本 skill 复制进 skill 目录后，可在会话中立即执行一次只读自检（也可作为环境探测前的准备步骤）：

```bash
<PYTHON> "<SKILL_DIR>/scripts/setup_officecli.py"
```

状态非 ready 时脚本以 STOP_FOR_USER 停止并给出建议。OfficeCLI 缺失且用户明确同意安装时，才由 agent 传入 `--install` 执行官方全局安装器并复读状态：

```bash
<PYTHON> "<SKILL_DIR>/scripts/setup_officecli.py" --install --out 软著/OfficeCLI安装.json
```

约束：`--install` 只在用户明确同意后使用，任何情况下不得静默安装；版本要求为「不低于 `1.0.151` 且主版本为 `1`」，官方安装器装的最新版满足该要求时可直接用 `--install` 修复缺失或版本过旧，不满足（如主版本升级到 2.x）时提示用户手动选择版本；安装成功但 PATH 未刷新时脚本报告 restart_required，需重启 coding agent 后重新自检确认 ready。

## 能力与宿主技能探测

启动时先枚举当前 agent 可用的技能与工具（浏览器控制、PDF/DOCX 阅读、视觉/图像理解、联网搜索、Playwright CLI 等），把名称通过 `--host-tools` 传给探测脚本登记，并主动利用它们提升质量：

- 浏览器控制技能：可作为 `agent-browser` 截图方式，替代 Playwright CLI 安装。
- PDF / DOCX 阅读技能：读取无法自动提取正文的证据文档，要点写入业务理解模型稿。
- 视觉能力：逐张查看渲染后的图纸，确认中文无乱码、无遮挡后再交用户确认。
- 架构图技能（如 archify）：可为技术方案文档的图纸插槽生成图片，落盘到 `软著/图纸原始/`（文件名 `01-插槽名.png`，插槽名 architecture/key_N/function_N），figures.py 优先采用并登记图纸清单。
- 联网搜索：仅用于行业表达调研，不得编造项目不存在的功能。
- OfficeCLI 仍是对一 DOCX 写入器，宿主 docx 技能用于预览与复核，不替代生成。

```bash
<PYTHON> "<SKILL_DIR>/scripts/probe_env.py" --out-dir 软著 --host-tools "browser,pdf-reader"
```

输出 `软著/环境探测.{md,json}`，包含 OfficeCLI 路径与版本、graphviz 渲染链、无头浏览器、Playwright CLI、中文字体与宿主工具使用建议。OfficeCLI 缺失、待重启或版本不满足要求（不低于 `1.0.151` 且主版本为 `1`）时会打印 STOP_FOR_USER：由用户决定全局安装（安装后须重启 coding agent 再重新探测）、切换版本，或明确承担风险（正式生成时传 `--allow-untested-officecli`）。用户决定后记录门禁：

```bash
<PYTHON> "<SKILL_DIR>/scripts/confirm_gate.py" --workdir 软著 --stage environment --note "<用户选择>"
```

## 工作流

### 1. 定位项目

扫描当前目录找项目根（避开本 skill、`软著/`、node_modules、构建产物、隐藏目录）。多个候选时停止让用户选择并记录 `project` 门禁。

### 2. 分析项目

```bash
<PYTHON> "<SKILL_DIR>/scripts/analyze_project.py" --project <项目目录> --out 软著/analysis/project.json
```

得到框架、语言、源码文件数与总行数、入口/页面/接口分类、路由与运行命令候选。

### 3. 形成业务理解

先收集证据并生成模型稿模板：

```bash
<PYTHON> "<SKILL_DIR>/scripts/business_context.py" --project <项目目录> --analysis 软著/analysis/project.json --software-name "<软件全称>" --out-dir 软著/草稿
```

模型阅读 `业务理解证据.md/json`、README、需求文档（必要时用宿主阅读技能）、页面文案、路由与必要源码，自行判断并撰写模型稿 JSON：`manual_kind`（operation/design）、行业、目标用户、核心价值、业务功能与说明、典型流程、申请口径（开发目的 ≤50 字、行业 ≤50 字、主要功能 500~1300 字、技术特点 ≤100 字）、`manual_modules`（含每页至少两段亲写段落）或 `design_spec`（模块、功能、接口、出错处理、可选 DOT 图纸）。然后用 `--model-context` 生成 `业务理解.md/json` 并停止，等用户确认（含文档类型）；确认后记录 `business` 门禁。

### 4. 确认代码选择

```bash
<PYTHON> "<SKILL_DIR>/scripts/code_selection.py" --project <项目目录> --out-dir 软著/草稿
```

模型阅读候选清单与必要源码，在 `代码文件选择.json` 中填写 `selected` 与 `model_reason`（优先入口、页面、核心组件、数据交互；不足 60 页再补后端等源码），交用户确认后记录 `code-selection` 门禁。

### 5. 抽取代码材料

```bash
<PYTHON> "<SKILL_DIR>/scripts/extract_code.py" --project <项目目录> --selection 软著/草稿/代码文件选择.json --software-name "<软件全称>" --version "<版本号>" --out-dir 软著/草稿
```

已选不足 60 页且候选有富余时脚本会停止要求补充；否则生成 `代码.md`（前30+后30 合并或全部）与 `代码提取清单.{md,json}`。

### 6. 生成申请表草稿

```bash
<PYTHON> "<SKILL_DIR>/scripts/application_info.py" --analysis 软著/analysis/project.json --code-manifest 软著/草稿/代码提取清单.json --business-context 软著/草稿/业务理解.json --software-name "<软件全称>" --version "<版本号>" --out-dir 软著/草稿
```

用户补全软件全称、版本号、著作权人、日期、发表状态等字段后记录 `application-fields` 门禁（脚本校验枚举、日期、长度、字数窗口）。

### 7. 生成文档草稿与图纸

```bash
<PYTHON> "<SKILL_DIR>/scripts/manual_draft.py" --business-context 软著/草稿/业务理解.json --software-name "<软件全称>" --version "<版本号>" --out-dir 软著/草稿
```

design 模式且声明了图纸时，先渲染图纸再生成文档：

```bash
<PYTHON> "<SKILL_DIR>/scripts/figures.py" --workdir 软著
```

宿主架构图技能（如 archify）生成的图纸图片放入 `软著/图纸原始/`（文件名 `数字前缀-插槽名.图片扩展名`，如 `01-architecture.png`）后，同一命令会优先采用宿主图片、跳过对应插槽的 DOT 渲染；未匹配已声明插槽的图片会被提示，不会采用。图纸清单与登记的图片纳入最终确认指纹，确认后替换图片会使门禁失效。

自检存在阻断问题时脚本退出并提示：模型修正业务理解或模型稿后重跑，每一轮自检都真实追加到自检记录（含正文摘要）。具备视觉能力时逐张查看渲染图（含宿主技能产图）确认无乱码无遮挡。

### 8. 截图（仅 operation 模式）

让用户在 agent-browser / playwright-cli / user-supplied / skip 中选择并记录门禁（必须显式 `--method`）。取得图片后整理生成清单：

```bash
<PYTHON> "<SKILL_DIR>/scripts/shots.py" --input-dir 软著/截图原始 --out-dir 软著/截图 --method <agent-browser|playwright-cli|user-supplied>
```

skip 时不运行截图工具，保留可见截图预留文字。

### 9. 用户确认 Markdown

```bash
<PYTHON> "<SKILL_DIR>/scripts/confirm_gate.py" --workdir 软著 --stage markdown --note "<用户确认内容>"
```

脚本校验全部上游门禁指纹、草稿完整性与自检清零；任何已确认文件被改过都会被拦下。

### 10. 生成正式 Word/TXT

```bash
<PYTHON> "<SKILL_DIR>/scripts/build_final.py" --workdir 软著 --software-name "<软件全称>" --version "<版本号>"
```

软件名与版本以 `申请表信息.md` 为准；输出 `申请资料/申请表信息.txt`、`<软件全称>-代码.docx`、`<软件全称>_操作手册.docx` 或 `_技术方案文档.docx`、`生成报告.md`。生成后执行三轮验证：文件存在且非空；抽样代码可回溯源码；行业/功能/流程可回溯业务理解；名称版本页数一致，前30+后30 模式实际页数必须正好 60。

### 11. 合规审查（软著审查专员）

对 `申请资料/` 正式生成物做登记合规复核并出具审查报告：

```bash
<PYTHON> "<SKILL_DIR>/scripts/review_final.py" --workdir 软著
```

脚本产出 `软著/审查/合规审查底稿.{md,json}`：按登记口径机械核查正式文件、申请表字段、代码鉴别材料（60 页/每页 50 行/无空行）、代码逐行回溯源码、名称版本一致性、文档骨架、截图、图纸与门禁链，问题分阻断/提示两级并附依据。随后模型以软著审查专员身份阅读底稿与正式文件（有宿主 docx/视觉技能时抽查 DOCX 页眉、标题、截图与图纸乱码），撰写 `软著/审查/审查报告.md`：审查结论（通过/整改后通过/不通过）、逐项合规情况（对应底稿编号）、问题与整改建议（指明回到哪个阶段重跑）、提交前检查清单。脚本阻断项不得降级或省略；整改一律回到对应阶段重新生成并重新确认。手册/技术方案文档同样读取真实页数并执行文档鉴别材料规则（前30+后30、不足 60 页提交全部、每页不少于 30 行）：超过 60 页时给出超页警告，需压缩或按前30+后30截取后提交。

### 12. 第八道门禁：审查确认

审查报告完成后，由用户确认审查结论，记录第八道门禁：

```bash
<PYTHON> "<SKILL_DIR>/scripts/confirm_gate.py" --workdir 软著 --stage review --note "<用户确认内容>"
```

这一道与前七道的关键差别：前七道确认的是**过程产物**（草稿、字段、截图方式），本道确认的是**最终交付物的可提交性**，因此指纹覆盖 `申请资料/` 全部正式文件与 `审查/审查报告.md`。正式材料在审查确认后被改动，门禁立即失效，必须重新审查再确认。

脚本在确认前校验：上游七道门禁仍有效；审查报告存在且在「审查结论」明确写出结论（通过 / 整改后通过 / 不通过）；结论不得为「不通过」——存在阻断项时整改前不允许确认。

## 何时询问用户

- OfficeCLI 缺失/待重启/版本不符：问是否全局安装或承担风险。
- 多个候选项目目录：问选哪个。
- 业务理解草稿：确认用途、行业、用户、核心功能与文档类型。
- 登记字段：软件全称、版本号、著作权人、日期、硬件/系统环境必须用户确认。
- 代码候选清单：确认或修改模型选择。
- 截图方式：四选一（可 skip）。
- Markdown 草稿整体确认后才进入正式生成。
- 合规审查存在阻断项：由用户决定回到对应阶段整改重跑，还是停止提交；审查报告仅供决策，不替代用户判断。
- 审查报告出具后：确认审查结论（第八道门禁）；结论为「不通过」时不得确认，须先整改。
