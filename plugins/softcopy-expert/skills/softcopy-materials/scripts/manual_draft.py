import argparse
import json
import re
from pathlib import Path
from typing import Any
import common as C
TEMPLATE_MARKERS = ("进入方式：", "页面内容：", "操作步骤：", "操作规则：", "操作结果与反馈：")
AI_TONE_MARKERS = ("旨在", "赋能", "一站式", "高效便捷", "显著提升", "强大能力", "丰富功能", "降本增效", "全方位", "多维度", "闭环")
TECH_TERMS = ("React", "Vue", "Vite", "Next.js", "FastAPI", "LangGraph", "Celery", "接口封装", "状态管理", "异步任务", "任务队列", "数据持久化", "组件库", "路由表", "源码", "框架设计")
GUI_WORDS = ("页面", "按钮", "点击", "弹窗", "下拉", "菜单", "登录", "输入框", "截图")
DESIGN_HEADINGS = ("## 一、引言", "## 二、软件总体设计", "### 2.1 软件需求概括", "### 2.2 需求概述", "### 2.3 条件与限制", "### 2.4 总体结构和模块接口设计", "### 2.5 模块功能逻辑关系", "### 2.6 设计和描述", "## 三、软件功能描述", "## 四、接口设计", "### 4.1 软件界面", "### 4.2 API接口", "### 4.3 出错处理设计")
OPERATION_SECTIONS = ("相关文档", "说明", "功能特点", "系统要求", "常见问题解答", "术语表")
def chinese_num(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value <= 0 or value >= 100:
        return str(value)
    if value < 10:
        return digits[value]
    if value == 10:
        return "十"
    if value < 20:
        return "十" + digits[value % 10]
    tens, ones = divmod(value, 10)
    return digits[tens] + "十" + (digits[ones] if ones else "")
def section_body(text: str, title: str) -> str:
    pattern = re.compile(rf"^##\s+[零一二三四五六七八九十百\d]+、\s*{re.escape(title)}\s*$", flags=re.M)
    match = pattern.search(text)
    if not match:
        return ""
    nxt = re.search(r"^##\s+", text[match.end():], flags=re.M)
    return text[match.end(): match.end() + nxt.start()] if nxt else text[match.end():]
def list_issues(lines: list[str]) -> list[str]:
    found = [line.strip()[:40] for line in lines if re.match(r"^(?:[-*+]\s+|\d+\.\s+)", line.strip())]
    return [f"正文出现列表行：{found[0]}"] if found else []
def figure_markup(manifest: dict[str, Any], key: str, title: str, figure_kind: str) -> str:
    for entry in manifest.get("figures") or []:
        if entry.get("key") != key:
            continue
        if entry.get("status") == "ok" and str(entry.get("format") or "").lower() in ("png", "jpg", "jpeg", "webp"):
            return f"![{title}]({entry['path']})"
        if entry.get("status") == "text" and entry.get("format") == "text":
            path = Path(manifest.get("_draft_dir", "")) / entry["path"]
            if path.is_file():
                content = path.read_text(encoding="utf-8").rstrip()
                return f"```text\n{content}\n```"
    return f"【图预留：请在此处插入“{title}”{figure_kind}。】"
def render_operation(business: dict[str, Any], software_name: str, version: str, manifest: dict[str, Any]) -> str:
    lines = [f"# {software_name}操作手册", "", f"## {chinese_num(1)}、相关文档", "", "| 文档名称 | 指向资料 | 说明 |", "| --- | --- | --- |"]
    related = business.get("related_documents") or [{"name": "总体设计", "description": "说明软件整体功能、页面组成与运行边界。"}, {"name": "详细设计", "description": "说明各功能页面的输入输出与处理规则。"}, {"name": "测试案例", "description": "记录主要功能的操作场景与预期结果。"}]
    for item in related:
        name = str(item.get("name") or "").strip()
        desc = str(item.get("description") or "").strip()
        if name:
            lines.append(f"| {name} | 《{name}》 | {desc} |")
    users = "、".join(str(u) for u in business.get("target_users") or [])
    lines.extend(["", f"## {chinese_num(2)}、说明", ""])
    if business.get("product_positioning"):
        lines.extend([str(business["product_positioning"]).strip(), ""])
    if users:
        lines.extend([f"主要使用对象：{users}。", ""])
    if business.get("core_value"):
        lines.extend([str(business["core_value"]).strip(), ""])
    for section in business.get("manual_sections") or []:
        if isinstance(section, dict):
            for para in section.get("paragraphs") or []:
                if str(para).strip():
                    lines.extend([str(para).strip(), ""])
    lines.extend([f"## {chinese_num(3)}、功能特点", ""])
    for feature in business.get("business_features") or []:
        detail = str((business.get("business_feature_details") or {}).get(feature) or "").strip()
        if detail:
            lines.extend([f"{feature}：{detail}", ""])
    lines.extend([f"## {chinese_num(4)}、系统要求", "", "| 系统要求 | 最低配置 | 推荐配置 |", "| --- | --- | --- |"])
    for row in business.get("system_requirements") or []:
        if isinstance(row, dict) and str(row.get("item") or "").strip():
            lines.append(f"| {row.get('item', '')} | {row.get('minimum', '')} | {row.get('recommended', '')} |")
    lines.extend(["", f"以上要求用于保障{software_name}正常打开页面、提交操作与展示结果；实际部署与申请表确认的环境字段不一致时，以申请表为准。", ""])
    index = 5
    for module in business.get("manual_modules") or []:
        title = str(module.get("title") or "").strip()
        if not title:
            continue
        lines.extend([f"## {chinese_num(index)}、{title}", ""])
        for para in module.get("paragraphs") or []:
            if str(para).strip():
                lines.extend([str(para).strip(), ""])
        shot = str(module.get("screenshot") or "").strip() or f"请在此处插入“{title}”页面或操作结果截图"
        lines.extend([f"【截图预留：{shot.rstrip('。')}。】", ""])
        index += 1
    flow = [str(step).strip() for step in business.get("operation_flow") or [] if str(step).strip()]
    if flow:
        lines.extend([f"## {chinese_num(index)}、典型使用流程", "", "；".join(flow) + "。", ""])
        index += 1
    lines.extend([f"## {chinese_num(index)}、常见问题解答", ""])
    for item in business.get("faq") or []:
        if isinstance(item, dict) and item.get("question") and item.get("answer"):
            lines.extend([f"问题：{item['question']}", f"处理方法：{item['answer']}", ""])
    index += 1
    lines.extend([f"## {chinese_num(index)}、术语表", "", "| 术语 | 解释 |", "| --- | --- |"])
    for item in business.get("glossary") or []:
        if isinstance(item, dict) and item.get("term"):
            lines.append(f"| {item['term']} | {item.get('definition', '')} |")
    lines.extend(["", "```text", "STOP_FOR_USER", "NEXT_ACTION: 请整体确认操作手册草稿是否符合真实业务；确认后运行 confirm_gate.py --stage markdown。", "```", ""])
    return "\n".join(lines)
def check_operation(text: str, business: dict[str, Any]) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    advisory: list[str] = []
    modules = [m for m in business.get("manual_modules") or [] if str(m.get("title") or "").strip()]
    for title in OPERATION_SECTIONS:
        if not section_body(text, title):
            blocking.append(f"缺少章节：{title}")
    for marker in TEMPLATE_MARKERS:
        if marker in text:
            blocking.append(f"存在制式字段标题：{marker}")
    body = [line for line in text.splitlines() if not line.strip().startswith("|") and not line.startswith("```")]
    blocking.extend(list_issues(body))
    if text.count("【截图预留：") < len(modules):
        blocking.append("截图预留数量少于页面模块数量")
    for module in modules:
        body_text = section_body(text, str(module["title"]))
        if not body_text:
            blocking.append(f"缺少页面模块章节：{module['title']}")
        elif len(re.sub(r"\s", "", body_text)) < 150:
            blocking.append(f"页面模块章节内容过薄：{module['title']}")
    for marker in AI_TONE_MARKERS:
        if marker in text:
            advisory.append(f"疑似空泛表达：{marker}")
    for term in TECH_TERMS:
        if term in text:
            advisory.append(f"疑似技术化表达：{term}")
    return blocking, advisory
def render_design(business: dict[str, Any], software_name: str, version: str, manifest: dict[str, Any]) -> str:
    spec = business["design_spec"]
    lines = [f"# {software_name}技术方案文档", "", "## 一、引言", "", f"本文档是对{software_name} {version}软件静态和动态形态的描述，是软件编码过程中的指导文档。"]
    if spec.get("intro_note"):
        lines.extend(["", str(spec["intro_note"]).strip()])
    lines.extend(["", "## 二、软件总体设计", "", "### 2.1 软件需求概括", ""])
    if business.get("product_positioning"):
        lines.extend([str(business["product_positioning"]).strip(), ""])
    features = business.get("business_features") or []
    if features:
        lines.append(f"{software_name} {version}主要有以下功能：")
        for i, feature in enumerate(features, start=1):
            lines.append(f"（{i}）{feature}；")
        lines.append("")
    lines.extend(["### 2.2 需求概述", ""])
    for i, item in enumerate(spec.get("requirements") or [], start=1):
        lines.append(f"{i}. {item}")
    lines.extend(["", "### 2.3 条件与限制", "", str(spec.get("conditions") or "").strip(), "", "### 2.4 总体结构和模块接口设计", "", str(spec.get("architecture") or "").strip(), "", figure_markup(manifest, "architecture", "软件整体结构框架图", ""), ""])
    lines.extend(["### 2.5 模块功能逻辑关系", "", "软件模块信息如下表所示：", "", "| 模块名 | 功能描述 |", "| --- | --- |"])
    for module in spec.get("modules") or []:
        lines.append(f"| {module.get('name', '')} | {module.get('description', '')} |")
    if spec.get("module_note"):
        lines.extend(["", str(spec["module_note"]).strip()])
    lines.extend(["", "### 2.6 设计和描述", "", str(spec.get("overview") or "").strip(), ""])
    for i, item in enumerate(spec.get("key_designs") or [], start=1):
        lines.extend([f"#### 2.6.{i} {item['title']}", "", item["description"], "", figure_markup(manifest, f"key_{i}", item["title"], str(item.get("figure") or "图")), ""])
    lines.extend(["## 三、软件功能描述", ""])
    for i, item in enumerate(spec.get("functions") or [], start=1):
        lines.extend([f"### 3.{i} {item['title']}", "", item["description"], "", figure_markup(manifest, f"function_{i}", item["title"], str(item.get("figure") or "图")), ""])
    lines.extend(["## 四、接口设计", "", "### 4.1 软件界面", "", str(spec.get("ui_statement") or "无。").strip(), "", "### 4.2 API接口", ""])
    for gi, group in enumerate(spec.get("api_groups") or [], start=1):
        lines.extend([f"#### 4.2.{gi} {group['title']}", ""])
        if group.get("summary"):
            lines.extend([group["summary"], ""])
        for ii, iface in enumerate(group.get("interfaces") or [], start=1):
            call = re.search(r"([A-Za-z_]\w*)\s*\(", iface["signature"].strip())
            short = call.group(1) if call else iface["signature"].split()[0][:40]
            lines.extend([f"##### 4.2.{gi}.{ii} {short}", "", "**接口名称**", "", iface["signature"], "", "**接口说明**", "", iface["description"], "", "**参数说明**", ""])
            params = iface.get("params") or []
            if params:
                lines.extend(["| 序号 | 参数名称 | 类型 | 取值说明 |", "| --- | --- | --- | --- |"])
                for pi, param in enumerate(params, start=1):
                    lines.append(f"| {pi} | {param.get('name', '')} | {param.get('type', '')} | {param.get('detail', '')} |")
            else:
                lines.append("无。")
            lines.extend(["", "**返回结果**", "", iface["returns"], ""])
    lines.extend(["### 4.3 出错处理设计", ""])
    for i, item in enumerate(spec.get("error_handling") or [], start=1):
        lines.extend([f"#### 4.3.{i} {item['title']}", "", item["description"], ""])
    lines.extend(["```text", "STOP_FOR_USER", "NEXT_ACTION: 请整体确认技术方案文档草稿是否与真实设计一致；确认后运行 confirm_gate.py --stage markdown。", "```", ""])
    return "\n".join(lines)
def check_design(text: str, business: dict[str, Any]) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    advisory: list[str] = []
    spec = business["design_spec"]
    for heading in DESIGN_HEADINGS:
        if heading not in text:
            blocking.append(f"缺少必备章节标题：{heading}")
    hits = sorted({word for word in GUI_WORDS if word in text})
    if hits:
        blocking.append("正文出现界面词汇（" + "、".join(hits) + "）；无界面软件应改写为设备/模块行为")
    for module in spec.get("modules") or []:
        if module["name"] and f"| {module['name']} |" not in text:
            blocking.append(f"模块表缺少模块行：{module['name']}")
    for group in spec.get("api_groups") or []:
        for iface in group.get("interfaces") or []:
            if iface["signature"] not in text:
                blocking.append(f"接口设计缺少签名：{iface['signature'][:40]}")
    if "**返回结果**" not in text:
        blocking.append("接口设计缺少返回结果小节")
    declared = set((spec.get("figures") or {}).keys())
    for key in declared:
        entry = next((e for e in (spec.get("_figure_manifest") or {}).get("figures", []) if e.get("key") == key), None)
        if entry and entry.get("status") == "error":
            advisory.append(f"图纸 {key} 渲染失败，正文保留【图预留】")
        elif entry and entry.get("format") == "text":
            advisory.append(f"图纸 {key} 为中文文本框线图（当前环境无 graphviz）；安装 graphviz 后重跑 figures.py 可得 PNG")
    for leftover in ("待确认", "待填写"):
        if leftover in text:
            blocking.append(f"正文残留占位文字：{leftover}")
    return blocking, advisory
def append_review(review_json: Path, review_md: Path, action: str, blocking: list[str], advisory: list[str], text_digest: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    rounds: list[dict[str, Any]] = []
    if review_json.is_file():
        try:
            rounds = C.load_json(review_json).get("rounds") or []
        except Exception:
            rounds = []
    entry = {"round": len(rounds) + 1, "action": action, "text_sha256": text_digest, "blocking": blocking, "advisory": advisory, "resolved": not blocking}
    if extra:
        entry.update(extra)
    rounds.append(entry)
    data: dict[str, Any] = {"rounds": rounds}
    if extra:
        data.update({k: v for k, v in extra.items() if not isinstance(v, (list, dict))})
    C.save_json(review_json, data)
    lines = ["# 文档自检记录", "", "每一轮记录一次真实生成与校验；上一轮发现的问题需由模型修正业务理解或模型稿后重跑脚本产生下一轮记录。", ""]
    for record in rounds:
        status = "已通过" if record.get("resolved") else "未通过"
        lines.extend([f"## 第 {record['round']} 轮（{record['action']}，{status}）", ""])
        if record.get("blocking"):
            lines.extend(f"- [阻断] {item}" for item in record["blocking"])
        if record.get("advisory"):
            lines.extend(f"- [提示] {item}" for item in record["advisory"])
        if not record.get("blocking") and not record.get("advisory"):
            lines.append("- 未发现问题")
        lines.append("")
    review_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return entry
def require_business(business: dict[str, Any] | None) -> None:
    if business is None:
        C.stop_for_user("文档草稿必须基于已确认的业务理解生成；请先完成业务理解并记录 business 门禁。")
    if business.get("confirmation_required") and not business.get("user_confirmed"):
        C.stop_for_user("业务理解尚未确认；请先记录 business 门禁。")
    if business.get("user_confirmed") and not C.digest_current(business):
        C.stop_for_user("业务理解在确认后被修改；请重新记录 business 门禁。")
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--business-context", required=True)
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--version", default="V1.0")
    parser.add_argument("--out-dir", default=f"{C.ROOT_NAME}/{C.DRAFT_NAME}")
    args = parser.parse_args()
    business = C.load_json(Path(args.business_context))
    require_business(business)
    out_dir = C.ensure_dir(Path(args.out_dir))
    kind = "design" if business.get("manual_kind") == "design" else "operation"
    doc_md, review_json, review_md, _suffix = C.PROSE_FILES[kind]
    manifest: dict[str, Any] = {}
    if kind == "design":
        listing = out_dir / "图纸清单.json"
        if listing.is_file():
            try:
                manifest = C.load_json(listing)
            except Exception:
                manifest = {}
        manifest["_draft_dir"] = str(out_dir)
        business.setdefault("design_spec", {})["_figure_manifest"] = manifest
    text = render_design(business, args.software_name, args.version, manifest) if kind == "design" else render_operation(business, args.software_name, args.version, manifest)
    blocking, advisory = (check_design if kind == "design" else check_operation)(text, business)
    if kind == "design":
        business["design_spec"].pop("_figure_manifest", None)
        manifest.pop("_draft_dir", None)
    (out_dir / doc_md).write_text(text, encoding="utf-8")
    import hashlib
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    entry = append_review(out_dir / review_json, out_dir / review_md, "生成与结构校验", blocking, advisory, digest)
    print(f"OK 文档草稿：{out_dir / doc_md}")
    print(f"自检：阻断 {len(blocking)} 项，提示 {len(advisory)} 项")
    if blocking:
        C.stop_for_user("文档自检存在阻断问题；请修正业务理解/模型稿后重跑本脚本，直到自检通过再交用户确认。")
    C.stop_for_user("请整体确认文档草稿是否符合真实业务；确认后运行 confirm_gate.py --stage markdown。")
if __name__ == "__main__":
    main()
