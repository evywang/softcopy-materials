# my-experts · 个人专家市场

面向软件著作权等实用场景的专家包市场。

## 插件列表

| 插件名 | 版本 | 分类 | 描述 |
|--------|------|------|------|
| **software-copyright-expert** | 1.2.0 | 法务安全 | 依据真实项目源码编写中国软著登记全套资料（申请表字段、代码鉴别材料、操作手册 / 技术方案文档），再以软著审查专员视角复核最终交付物并出具合规审查报告，以审查结论作为提交门禁 |

## 安装

### 方式一：交互式安装（推荐）

```bash
# 1. 添加市场（GitHub 仓库写 owner/repo；或直接给 zip 的 HTTP 地址）
/plugin marketplace add <owner>/<repo>

# 2. 浏览市场
/plugin

# 或直接安装
/plugin install software-copyright-expert@softcopy-materials
```

### 方式二：项目配置自动安装

在项目的 `.codebuddy/settings.json` 中添加，团队成员启动时会自动装好：

```json
{
  "extraKnownMarketplaces": {
    "softcopy-materials": {
      "source": {
        "source": "github",
        "repo": "<owner>/<repo>"
      }
    }
  },
  "enabledPlugins": {
    "software-copyright-expert@softcopy-materials": true
  }
}
```

### 方式三：命令行安装

```bash
codebuddy plugin marketplace add <owner>/<repo>
codebuddy plugin install software-copyright-expert@softcopy-materials
```

## 使用示例

```
帮我为当前项目生成软件著作权申请材料
这个项目该生成操作手册还是技术方案文档？
以审查专员视角复核已生成的材料并给出合规审查报告
```

## 安全提示

> 市场中的插件包含可执行脚本（Python）与文件读写能力。CodeBuddy 无法控制插件内
> 包含的文件或程序，也无法验证它们是否按预期工作。安装前请确认你信任该插件。

`software-copyright-expert` 的全部脚本均为纯标准库 Python，只在当前工作目录下
`软著/` 内读写文件；正式生成 DOCX 依赖本机安装的 OfficeCLI。
