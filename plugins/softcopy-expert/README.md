# 青砚 · 软件著作权资料编写专家

从**真实项目源码**出发，生成中国软件著作权登记所需的全套申请资料：申请表信息、程序鉴别材料（源代码文档），以及操作手册或技术方案文档，最终经 OfficeCLI 输出为可直接提交前导出 PDF 的正式 Word/TXT。

## 类型

Agent 型（单个 AI 专家）

## 功能

- **真实代码溯源**：程序鉴别材料只来自真实项目源码，按完整文件抽取、去注释空行、确定性折行；行业判断、功能取舍与文档正文由模型阅读项目后撰写，禁止编造项目不存在的功能、模块或接口。
- **双文档类型自动研判**：有界面软件（Web / 桌面 / 移动端）生成操作手册；无界面软件（嵌入式固件、驱动、库、后端服务、命令行）生成技术方案文档，模块表与接口表必须可回溯源码。
- **申请表字段校验**：按官网表单顺序管理 25 个字段，校验枚举值、日期格式、字符长度上限与"主要功能 500~1300 字"窗口；开发环境只填 IDE，源程序量取全项目源码总行数。
- **鉴别材料规则内建**：依据《计算机软件著作权登记办法》第十条组织材料——前后各连续 30 页，不足 60 页提交全部，程序每页不少于 50 行、文档每页不少于 30 行；前 30+后 30 模式实际页数强校验为 60。
- **中文图纸渲染**：DOT 图纸自动注入 CJK 字体与版式默认值渲染 PNG；无 graphviz 或缺中文字体时自动降级为中文文本框线图，任何环境不乱码、不遮挡；宿主架构图技能（如 archify）产图放入 `软著/图纸原始/` 后优先采用。
- **八道诚实门禁**：环境、项目、业务理解、代码选择、申请表字段、截图方式、Markdown 整体确认、**合规审查确认**，全部需用户显式确认；每道门禁记录内容指纹，已确认内容被改动即失效并拦截。第八道确认的是**最终交付物的可提交性**，指纹覆盖 `申请资料/` 与 `审查/审查报告.md`——正式材料在审查确认后被改动，必须重新审查。
- **合规审查（软著审查专员）**：正式生成后切换审查视角，对 `申请资料/` 最终交付物做登记合规复核——正式文件齐备、申请表字段、开发目的、代码鉴别材料（60 页 / 每页 50 行 / 无空行）、**代码逐行回溯源码**、名称版本四处一致、文档骨架、截图、图纸、门禁链指纹；问题分阻断/提示两级并附依据，随后出具审查报告（通过 / 整改后通过 / 不通过）。审查报告不写入提交目录。
- **诚实降级**：没有 OfficeCLI 时只推进 Markdown/TXT 草稿，不伪造成 DOCX；OfficeCLI 版本不匹配须用户明确承担风险才能正式生成。

### 完整工作流程

```text
环境探测 → 定位项目 → 项目分析 → 业务理解（模型撰写+用户确认）
→ 代码选择（模型填写+用户确认）→ 代码抽取 → 申请表草稿（用户补全）
→ 图纸渲染（仅 design）→ 文档草稿+自检 → 截图（仅 operation）
→ Markdown 最终确认 → OfficeCLI 生成正式 Word/TXT → 三轮验证
→ 合规审查（审查专员出具报告）→ 第八道门禁：审查确认
```

输出目录固定为当前工作目录下的 `软著/`，正式 Word/TXT 只写入 `软著/申请资料/`，审查底稿、审查报告与门禁确认写入 `软著/审查/`。

## 使用示例

- 帮我为当前项目生成软件著作权申请材料
- 这个项目该生成操作手册还是技术方案文档？
- 以审查专员视角复核已生成的材料并给出合规审查报告

## 运行要求

- **Python 3.10+**：技能脚本为纯标准库 CLI，Windows / macOS / Linux 通用。
- **OfficeCLI ≥ 1.0.151 且主版本保持为 1**（正式 Word 的唯一后端，缺失时技能仍可推进全部 Markdown/TXT 草稿并明确拒绝伪造成 DOCX）：
  - 版本判定：`1.0.151` 及以上同主版本均可用（如 `1.0.158`、`1.1.0`）；主版本升到 `2.x` 或低于 `1.0.151` 则须用户明确承担风险。
  - Windows PowerShell：`irm https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.ps1 | iex`
  - macOS / Linux：`curl -fsSL https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.sh | bash`
  - 必须全局安装，安装后重启 coding agent 刷新 PATH。
- **可选增强**：graphviz + 中文字体（DOT 图纸渲染 PNG）、Node 18+ 与 `@playwright/cli@0.1.20`（仅 playwright-cli 截图方式）、pypdf（PDF 证据正文提取）。

## 目录结构

```text
softcopy-expert/
├── .codebuddy-plugin/plugin.json
├── agents/softcopy-expert.md      # 专家角色定义与工作流程
├── skills/softcopy-materials/                # 软著材料生成技能（SKILL.md + references + scripts）
├── avatars/expert.png
└── README.md
```

## 头像

头像已自动生成在 `avatars/` 目录下。如需替换为自定义头像，要求：
- 格式：PNG（推荐）或 JPG
- 尺寸：512×512 px
- 大小：单张不超过 500KB

## 安装

将专家包目录放到专家目录下：

```
C:\Users\wange\.workbuddy\plugins\marketplaces\my-experts\plugins/softcopy-expert/
```

然后运行注册命令使其可见：

```bash
python3 scripts/register_expert.py <expert-dir>
```

## 分发给他人

本专家已发布为公开市场仓库：**[evywang/softcopy-materials](https://github.com/evywang/softcopy-materials)**
（仓库根即市场清单 `.codebuddy-plugin/marketplace.json`，专家本体在 `plugins/softcopy-expert/`）。

**给他人使用**（对方无需任何额外配置）：

```bash
# 1. 对方添加市场
/plugin marketplace add evywang/softcopy-materials

# 2. 安装并启用
/plugin install softcopy-expert@softcopy-materials
```

团队批量分发时，在项目 `.codebuddy/settings.json` 里写死市场与插件，成员启动即自动装好：

```json
{
  "extraKnownMarketplaces": {
    "softcopy-materials": {
      "source": { "source": "github", "repo": "evywang/softcopy-materials" }
    }
  },
  "enabledPlugins": { "softcopy-expert@softcopy-materials": true }
}
```

**自己重新打包**（专家更新后重建分发物）：

```bash
# 单个专家包
python scripts/package_expert.py <expert-dir> <输出目录>

# 整个市场包（清单必须在压缩包根）
python scripts/build_marketplace.py \
  --marketplace-dir <市场源目录> \
  --expert-dir <本专家目录> \
  --out <输出目录>/my-experts-marketplace.zip
```

`build_marketplace.py` 会在打包前自检：清单声明的本地插件必须真的在包内，否则直接报错，
避免发出一个装上后是空市场的包。

> **注意**：本机 `~/.workbuddy/plugins/marketplaces/my-experts/` 里的清单由 WorkBuddy 托管，
> 它会自动规范化成最小结构，`owner`、`version`、`description_zh` 等字段会被清掉。
> **分发给别人的市场包要从「市场源目录」构建**（通常是源码仓库里的 `marketplace/`），
> 富元数据以那里为准；本地托管目录只负责让专家在自己机器上可见。

## 许可

内置技能 softcopy-materials 为 MIT 许可（见 `skills/softcopy-materials/LICENSE`）。生成材料是否符合项目实际与版权保护中心官网当前要求，由使用者自行核对；本专家不提供任何法律担保。
