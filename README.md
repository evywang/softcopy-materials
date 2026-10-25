# softcopy-materials · 中国软著登记材料专家

从**真实项目源码**生成中国软件著作权（软著）登记所需的全套申请资料，并作为
**软著审查专员**复核最终交付物、以审查结论作为提交门禁。

- 专家包：`plugins/software-copyright-expert/`（内含完整技能 `skills/softcopy-materials/`）
- 市场清单：`.codebuddy-plugin/marketplace.json`

## 安装

本仓库同时是**插件市场**和**源码仓库**，添加一次即可使用。

```bash
# 1. 添加市场
/plugin marketplace add evywang/softcopy-materials

# 2. 安装专家
/plugin install software-copyright-expert@softcopy-materials
```

团队批量分发：在项目 `.codebuddy/settings.json` 中写死市场与插件，成员启动即自动装好。

```json
{
  "extraKnownMarketplaces": {
    "softcopy-materials": {
      "source": { "source": "github", "repo": "evywang/softcopy-materials" }
    }
  },
  "enabledPlugins": {
    "software-copyright-expert@softcopy-materials": true
  }
}
```

## 它能做什么

| 能力 | 说明 |
|------|------|
| 真实代码溯源 | 程序鉴别材料只来自真实项目源码，按完整文件抽取、去注释空行、确定性折行；代码逐行回溯校验，杜绝编造 |
| 双文档类型研判 | 有界面软件生成操作手册，无界面软件生成技术方案文档，类型由模型判定并经用户确认 |
| 申请表字段校验 | 25 个字段逐项校验枚举值、日期格式、长度上限与「主要功能 500~1300 字」窗口 |
| 鉴别材料规则内建 | 依据《计算机软件著作权登记办法》第十条：前后各连续 30 页，不足 60 页提交全部，程序每页不少于 50 行、文档每页不少于 30 行 |
| 八道诚实门禁 | 环境、项目、业务理解、代码选择、申请表字段、截图方式、Markdown 最终确认、**合规审查确认**；每道记录内容指纹，改动即失效 |
| 合规审查专员 | 正式生成后切换审查视角，逐项复核并出具审查报告；结论为「不通过」时不得确认提交门禁 |

## 目录结构

```
softcopy-materials/
├── .codebuddy-plugin/marketplace.json   市场清单（CLI 只在仓库根找它）
├── plugins/software-copyright-expert/    专家包
│   ├── .codebuddy-plugin/plugin.json     专家清单
│   ├── agents/                           专家定义（青砚）
│   ├── avatars/                          头像
│   ├── skills/softcopy-materials/        内置技能（完整实现）
│   └── scripts/build_marketplace.py      市场分发打包工具
├── docs/                                 介绍文档与使用示例
├── MARKETPLACE.md                        市场分发与安装说明
├── README.md
└── LICENSE
```

## 单独使用技能（不走专家）

只想用技能、不需要专家人格时，直接取用
`plugins/software-copyright-expert/skills/softcopy-materials/`：

```bash
cp -r plugins/software-copyright-expert/skills/softcopy-materials <你的项目>/.codebuddy/skills/
```

## 环境要求

- **Python 3.10+**：技能脚本为纯标准库，Windows / macOS / Linux 通用
- **OfficeCLI ≥ 1.0.151 且主版本保持为 1**：正式 Word 的唯一后端；缺失时技能仍可推进全部 Markdown/TXT 草稿并明确拒绝伪造成 DOCX
- 可选：graphviz + 中文字体（DOT 图纸渲染 PNG）、Node 18+ 与 `@playwright/cli@0.1.20`（仅 playwright-cli 截图方式）

## 来源与许可

MIT 许可，详见 [LICENSE](LICENSE)。

本项目是对开源项目 [Fokkyp/SoftwareCopyright-Skill](https://github.com/Fokkyp/SoftwareCopyright-Skill)（MIT）
做功能层面的 clean-room 分析后重新实现的版本，架构与代码均为重写，并修复了原实现中的已知缺陷
（接口返回结果丢失、章节编号错乱、正文盲替换、自检记录失真、序列图渲染调用错误、演示项目残留等）。
原项目的 MIT 许可声明保留于 [LICENSE](LICENSE)。

生成材料是否符合项目实际与版权保护中心官网当前要求，由使用者自行核对；本项目不提供任何法律担保。
