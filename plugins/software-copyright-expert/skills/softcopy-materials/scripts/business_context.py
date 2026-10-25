import argparse
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any
import common as C
MAX_DOC_CHARS = 80000
MAX_DOCS = 40
MAX_DOC_BYTES = 25000000
MAX_XML_BYTES = 5000000
KIND_ALIASES = {"operation": "operation", "操作手册": "operation", "manual": "operation", "design": "design", "技术方案": "design", "技术方案文档": "design", "设计说明书": "design", "design-spec": "design"}
LENGTH_RULES = {"industry": 50, "application_purpose": 50, "technical_characteristics": 100}
MAIN_MIN = 500
MAIN_MAX = 1300
MODULE_PARAGRAPH_MIN = 80
MODULE_PARAGRAPH_COUNT = 2
def nsp(text: str) -> str:
    return re.sub(r"\s+", "", text)
def effective_len(value: str) -> int:
    return len(nsp(str(value or "")))
def require_text(data: dict[str, Any], field: str) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        raise SystemExit(f"模型稿缺少必填字段：{field}")
    return value
def require_list(data: dict[str, Any], field: str) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list):
        raise SystemExit(f"模型稿字段必须是列表：{field}")
    items = [str(item).strip() for item in value if str(item).strip()]
    if not items:
        raise SystemExit(f"模型稿字段不能为空列表：{field}")
    return items
def normalize_kind(model: dict[str, Any]) -> str:
    raw = str(model.get("manual_kind") or "operation").strip()
    key = raw.lower() if raw.isascii() else raw
    if key not in KIND_ALIASES:
        raise SystemExit(f"manual_kind 必须是 operation 或 design，当前为：{raw}")
    return KIND_ALIASES[key]
def zip_xml_text(path: Path, member: str) -> str:
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(member)
        if info.file_size > MAX_XML_BYTES:
            raise ValueError("文档 XML 过大，跳过自动提取")
        data = archive.read(info, MAX_XML_BYTES + 1)
    if len(data) > MAX_XML_BYTES:
        raise ValueError("文档 XML 过大，跳过自动提取")
    root = ET.fromstring(data)
    paragraphs = []
    for node in root.iter():
        if not node.tag.endswith("}p"):
            continue
        text = "".join(child.text or "" for child in node.iter() if child.tag.endswith("}t"))
        if text.strip():
            paragraphs.append(text)
    if paragraphs:
        return "\n".join(paragraphs)[:MAX_DOC_CHARS]
    return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))[:MAX_DOC_CHARS]
def read_document(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    try:
        if suffix in (".docx", ".odt"):
            member = "word/document.xml" if suffix == ".docx" else "content.xml"
            return zip_xml_text(path, member), "已自动提取正文"
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
                return text[:MAX_DOC_CHARS], "已自动提取 PDF 文本"
            except Exception:
                return "", "已登记 PDF；正文未自动提取，请 agent 用宿主 PDF 阅读技能读取后写入模型稿依据"
        if suffix in (".doc", ".wps"):
            return "", f"已登记 {suffix.lstrip('.').upper()} 文档；请 agent 用宿主文档阅读技能读取"
        return C.read_text(path, limit=MAX_DOC_CHARS), "已提取文本"
    except Exception as exc:
        return "", f"已登记文件但读取失败：{type(exc).__name__}"
def collect_documents(root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for path in C.iter_docs(root):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_DOC_BYTES:
            text, note = "", "文件过大未自动提取，请 agent 按需直接阅读"
        else:
            text, note = read_document(path)
        headings = [line.lstrip("#").strip()[:120] for line in text.splitlines() if line.strip().startswith("#")][:24]
        opening = re.sub(r"\s+", " ", re.sub(r"[>#*_`|]", " ", text)).strip()[:900]
        docs.append({"path": C.rel_posix(path, root), "size": size, "format": suffix_name(path), "headings": headings, "opening": opening, "text_extracted": bool(text.strip()), "note": note})
    docs.sort(key=lambda item: (0 if Path(item["path"]).suffix.lower() in {".md", ".txt", ".rst", ".adoc", ".docx", ".pdf"} else 1, item["path"].count("/"), item["path"]))
    return docs[:MAX_DOCS]
def suffix_name(path: Path) -> str:
    return path.suffix.lower().lstrip(".") or "text"
def normalize_api_groups(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise SystemExit("design_spec.api_groups 必须是非空列表")
    groups: list[dict[str, Any]] = []
    for gi, group in enumerate(raw, start=1):
        if not isinstance(group, dict):
            raise SystemExit(f"api_groups 第 {gi} 项必须是对象")
        title = str(group.get("title") or group.get("name") or "").strip()
        if not title:
            raise SystemExit(f"api_groups 第 {gi} 项缺少 title")
        interfaces_raw = group.get("interfaces")
        if not isinstance(interfaces_raw, list) or not interfaces_raw:
            raise SystemExit(f"api_groups「{title}」缺少非空 interfaces")
        interfaces: list[dict[str, Any]] = []
        for ii, iface in enumerate(interfaces_raw, start=1):
            if not isinstance(iface, dict):
                raise SystemExit(f"api_groups「{title}」第 {ii} 个接口必须是对象")
            signature = str(iface.get("signature") or iface.get("name") or "").strip()
            description = str(iface.get("description") or "").strip()
            returns = str(iface.get("returns") or iface.get("result") or "").strip()
            if not signature or not description or not returns:
                raise SystemExit(f"api_groups「{title}」第 {ii} 个接口的 signature、description、returns 都是必填")
            params: list[dict[str, str]] = []
            for pi, param in enumerate(iface.get("params") or [], start=1):
                if not isinstance(param, dict):
                    raise SystemExit(f"接口 {signature} 第 {pi} 个参数必须是对象")
                name = str(param.get("name") or "").strip()
                if not name:
                    raise SystemExit(f"接口 {signature} 第 {pi} 个参数缺少 name")
                params.append({"name": name, "type": str(param.get("type") or "").strip(), "detail": str(param.get("detail") or param.get("description") or "").strip()})
            interfaces.append({"signature": signature, "description": description, "params": params, "returns": returns})
        groups.append({"title": title, "summary": str(group.get("summary") or "").strip(), "interfaces": interfaces})
    return groups
SLOT_FIELD_NAMES = {"key": "key_designs", "function": "functions"}
def normalize_figures(spec: dict[str, Any]) -> dict[str, str]:
    figures = spec.get("figures")
    if figures is None:
        return {}
    if not isinstance(figures, dict):
        raise SystemExit("design_spec.figures 必须是对象")
    normalized: dict[str, str] = {}
    for key, value in figures.items():
        slot = str(key).strip()
        if not C.DOT_SLOT_RE.fullmatch(slot):
            raise SystemExit(f"figures 插槽名只能是 architecture、key_<n>、function_<n>：{slot}")
        dot = str(value or "").strip()
        if not dot:
            raise SystemExit(f"figures.{slot} 不能为空，请填写 DOT 图源或删除该条目")
        normalized[slot] = dot
    for slot in normalized:
        match = re.fullmatch(r"(key|function)_(\d+)", slot)
        if not match:
            continue
        limit = len(spec.get(SLOT_FIELD_NAMES[match.group(1)]) or [])
        if int(match.group(2)) > limit:
            raise SystemExit(f"figures.{slot} 超出 {SLOT_FIELD_NAMES[match.group(1)]} 数量范围")
    return normalized
def normalize_design_spec(model: dict[str, Any]) -> dict[str, Any]:
    spec = model.get("design_spec")
    if not isinstance(spec, dict):
        raise SystemExit("manual_kind 为 design 时必须提供 design_spec 对象，且不要填写 manual_modules")
    def items(field: str, required: bool = True) -> list[dict[str, Any]]:
        raw = spec.get(field)
        if raw is None and not required:
            return []
        if not isinstance(raw, list):
            raise SystemExit(f"design_spec.{field} 必须是列表")
        out: list[dict[str, Any]] = []
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                raise SystemExit(f"design_spec.{field} 第 {index} 项必须是对象")
            title = str(item.get("title") or item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            if not title or not description:
                raise SystemExit(f"design_spec.{field} 第 {index} 项的 title 与 description 均为必填")
            out.append({"title": title, "description": description, "figure": str(item.get("figure") or "").strip()})
        if required and not out:
            raise SystemExit(f"design_spec.{field} 不能为空")
        return out
    return {
        "intro_note": str(spec.get("intro_note") or "").strip(),
        "requirements": require_list(spec, "requirements"),
        "conditions": require_text(spec, "conditions"),
        "architecture": require_text(spec, "architecture"),
        "modules": [{"name": str(m.get("title") or "").strip(), "description": str(m.get("description") or "").strip()} for m in items("modules")],
        "module_note": str(spec.get("module_note") or "").strip(),
        "overview": require_text(spec, "overview"),
        "key_designs": items("key_designs", required=False),
        "functions": items("functions"),
        "ui_statement": str(spec.get("ui_statement") or "无。").strip(),
        "api_groups": normalize_api_groups(spec.get("api_groups")),
        "error_handling": items("error_handling"),
        "figures": normalize_figures(spec),
    }
def normalize_modules(model: dict[str, Any]) -> list[dict[str, Any]]:
    raw = model.get("manual_modules")
    if not isinstance(raw, list) or not raw:
        raise SystemExit("operation 模式必须提供非空 manual_modules，由模型按真实页面撰写，脚本不会按分类模板兜底")
    modules: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"manual_modules 第 {index} 项必须是对象")
        title = str(item.get("title") or item.get("feature") or "").strip()
        if not title:
            raise SystemExit(f"manual_modules 第 {index} 项缺少 title")
        for field in ("purpose", "entry"):
            if not str(item.get(field) or "").strip():
                raise SystemExit(f"页面模块「{title}」缺少 {field}")
        usage = str(item.get("usage") or item.get("usage_scenario") or "").strip()
        if not usage:
            raise SystemExit(f"页面模块「{title}」缺少 usage 或 usage_scenario")
        paragraphs = item.get("paragraphs")
        if not isinstance(paragraphs, list) or len([p for p in paragraphs if str(p).strip()]) < MODULE_PARAGRAPH_COUNT:
            raise SystemExit(f"页面模块「{title}」缺少 paragraphs：每页至少 {MODULE_PARAGRAPH_COUNT} 段模型亲写的自然段，脚本不做句式生成")
        clean_paragraphs = [str(p).strip() for p in paragraphs if str(p).strip()]
        for pi, para in enumerate(clean_paragraphs, start=1):
            if effective_len(para) < MODULE_PARAGRAPH_MIN:
                raise SystemExit(f"页面模块「{title}」第 {pi} 段过短（{effective_len(para)} 字），每段至少 {MODULE_PARAGRAPH_MIN} 字")
        modules.append({
            "title": title,
            "evidence": [str(e).strip() for e in item.get("evidence") or [] if str(e).strip()],
            "purpose": str(item.get("purpose")).strip(),
            "usage": usage,
            "entry": str(item.get("entry")).strip(),
            "visible_elements": [str(e).strip() for e in item.get("visible_elements") or [] if str(e).strip()],
            "operation_steps": [str(s).strip() for s in item.get("operation_steps") or [] if str(s).strip()],
            "validation_rules": [str(r).strip() for r in item.get("validation_rules") or [] if str(r).strip()],
            "feedback": [str(f).strip() for f in item.get("feedback") or [] if str(f).strip()],
            "paragraphs": clean_paragraphs,
            "screenshot": str(item.get("screenshot") or "").strip(),
        })
    return modules
def normalize_model(model: dict[str, Any], software_name: str) -> dict[str, Any]:
    industry = require_text(model, "industry")
    purpose = require_text(model, "application_purpose")
    main_functions = require_text(model, "main_functions")
    tech = require_text(model, "technical_characteristics")
    for field, limit in LENGTH_RULES.items():
        if effective_len(str(model.get(field) or "")) > limit:
            raise SystemExit(f"模型稿字段 {field} 超过 {limit} 字上限")
    main_len = effective_len(main_functions)
    if not MAIN_MIN <= main_len <= MAIN_MAX:
        raise SystemExit(f"main_functions 需要 {MAIN_MIN}~{MAIN_MAX} 个非空白字符，当前 {main_len}")
    features = require_list(model, "business_features")
    details = model.get("business_feature_details")
    if not isinstance(details, dict):
        raise SystemExit("business_feature_details 必须是对象")
    for feature in features:
        if not str(details.get(feature) or "").strip():
            raise SystemExit(f"business_feature_details 缺少功能说明：{feature}")
    kind = normalize_kind(model)
    context: dict[str, Any] = {
        "software_name": software_name,
        "manual_kind": kind,
        "product_positioning": require_text(model, "product_positioning"),
        "industry": industry,
        "target_users": require_list(model, "target_users"),
        "core_value": require_text(model, "core_value"),
        "business_features": features,
        "business_feature_details": {f: str(details.get(f)).strip() for f in features},
        "operation_flow": require_list(model, "operation_flow"),
        "application_purpose": purpose,
        "main_functions": main_functions,
        "technical_characteristics": tech,
        "software_category": str(model.get("software_category") or "应用软件").strip(),
        "manual_sections": model.get("manual_sections") or [],
        "system_requirements": model.get("system_requirements") or [],
        "faq": model.get("faq") or [],
        "glossary": model.get("glossary") or [],
        "evidence_sources": [str(e).strip() for e in model.get("evidence_sources") or [] if str(e).strip()],
        "external_research_notes": str(model.get("external_research_notes") or "").strip(),
    }
    if kind == "design":
        if model.get("manual_modules"):
            raise SystemExit("manual_kind 为 design 时不要填写 manual_modules")
        context["design_spec"] = normalize_design_spec(model)
        for field in ("system_requirements", "faq", "glossary"):
            if context[field]:
                raise SystemExit(f"design 模式不使用 {field}，相关内容请并入 design_spec")
    else:
        context["manual_modules"] = normalize_modules(model)
        for field, label in (("system_requirements", "系统要求"), ("faq", "常见问题"), ("glossary", "术语表")):
            if not context[field]:
                raise SystemExit(f"operation 模式必须提供 {label}（{field}）")
    context.update({"user_confirmed": False, "confirmation_required": True, "gate": "business", "next_action": "请确认业务理解（含文档类型、行业、目标用户、核心功能与申请口径），确认后运行 confirm_gate.py --stage business。"})
    return context
def write_evidence_md(path: Path, evidence: dict[str, Any]) -> None:
    lines = ["# 业务理解证据", "", f"- 软件名称：{evidence['software_name']}", f"- 项目目录：{evidence['project_root']}", "", "本文件只登记项目证据，不决定行业、功能或文档结构。行业判断、功能取舍、章节组织必须由模型阅读证据与源码后自行作出。", "", "## 代码与页面证据", ""]
    for key, value in evidence["code_evidence"].items():
        if value:
            lines.append(f"- {key}：{value}")
    lines.extend(["", "## 文档证据", ""])
    for doc in evidence["documents"]:
        lines.extend([f"### {doc['path']}", "", f"- 大小：{doc['size']} 字节", f"- 格式：{doc['format']}", f"- 读取状态：{doc['note']}", f"- 标题线索：{'；'.join(doc['headings']) if doc['headings'] else '无'}", "", doc["opening"] or "（已登记路径，等待模型阅读）", ""])
    if evidence.get("web_notes"):
        lines.extend(["## 外部调研摘要", "", evidence["web_notes"], ""])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
def write_template(path: Path, evidence: dict[str, Any]) -> None:
    template = {
        "software_name": evidence["software_name"],
        "manual_kind": "operation 或 design：有用户可见页面/图形界面填 operation；无界面软件（固件、驱动、库、服务、命令行）填 design",
        "product_positioning": "产品定位一句话",
        "industry": "行业，不超过50字",
        "target_users": ["目标用户群体"],
        "core_value": "核心价值",
        "business_features": ["业务功能名称"],
        "business_feature_details": {"业务功能名称": "该功能的业务作用与用户可见结果"},
        "operation_flow": ["典型操作流程步骤"],
        "application_purpose": "开发目的，不超过50字，不能只写软件名称",
        "main_functions": "软件的主要功能，500~1300个非空白字符",
        "technical_characteristics": "技术特点描述，不超过100字",
        "software_category": "应用软件",
        "manual_sections": [{"title": "说明章节补充段落标题", "paragraphs": ["模型亲写的说明段落"]}],
        "manual_modules": [{"title": "真实页面或流程名称", "evidence": ["页面/路由/组件/文档证据路径"], "purpose": "页面用途", "usage": "用户在什么业务场景使用该页面", "entry": "从哪里进入", "visible_elements": ["用户可见元素"], "operation_steps": ["用户动作"], "validation_rules": ["输入限制或异常提示，没有则留空"], "feedback": ["操作结果反馈"], "paragraphs": ["模型亲写的自然段落一，至少80字", "模型亲写的自然段落二，至少80字"], "screenshot": "截图说明"}],
        "system_requirements": [{"item": "浏览器", "minimum": "最低配置", "recommended": "推荐配置"}],
        "faq": [{"question": "真实使用场景问题", "answer": "面向普通用户的处理方法"}],
        "glossary": [{"term": "业务术语", "definition": "普通中文解释"}],
        "design_spec": {"_说明": "仅 design 模式填写，此时不要填写 manual_modules/system_requirements/faq/glossary", "intro_note": "可选引言补充", "requirements": ["真实需求条目"], "conditions": "运行环境、开发环境、工具链与语言等条件限制", "architecture": "总体结构与部署形态描述", "modules": [{"name": "真实模块名", "description": "模块功能描述"}], "module_note": "可选分层或依赖说明", "overview": "设计和描述总述", "key_designs": [{"title": "关键设计点", "description": "设计原理与流程", "figure": "流程图"}], "functions": [{"title": "真实功能", "description": "设计说明与数据处理过程", "figure": "序列图或处理流"}], "ui_statement": "无。", "api_groups": [{"title": "接口分组", "summary": "传输方式与协议概述", "interfaces": [{"signature": "int demo(uint a)", "description": "接口行为说明", "params": [{"name": "a", "type": "uint", "detail": "参数含义"}], "returns": "返回0为成功，其余为错误码"}]}], "error_handling": [{"title": "出错处理机制", "description": "机制说明", "figure": ""}], "figures": {"_说明": "可选，DOT 图源按插槽命名：architecture、key_1..key_N、function_1..function_N；graphviz 不可用时自动输出中文文本框线图"}},
        "evidence_sources": ["支撑判断的证据路径"],
        "external_research_notes": "可选：区分项目证据与行业参考的外部调研结论",
    }
    C.save_json(path, template)
def write_context_md(path: Path, context: dict[str, Any]) -> None:
    lines = ["# 业务理解", "", f"- 软件名称：{context['software_name']}", f"- 文档类型：{'技术方案文档（无用户界面）' if context['manual_kind'] == 'design' else '操作手册（有用户界面）'}", f"- 产品定位：{context['product_positioning']}", f"- 面向领域 / 行业：{context['industry']}", f"- 核心价值：{context['core_value']}", "", "## 目标用户", ""]
    lines.extend(f"- {item}" for item in context["target_users"])
    lines.extend(["", "## 主要业务功能", ""])
    lines.extend(f"- {item}：{context['business_feature_details'][item]}" for item in context["business_features"])
    lines.extend(["", "## 典型操作流程", ""])
    lines.extend(f"{i}. {item}" for i, item in enumerate(context["operation_flow"], start=1))
    if context["manual_kind"] == "design":
        spec = context["design_spec"]
        lines.extend(["", "## 技术方案要点", "", f"- 模块：{'、'.join(m['name'] for m in spec['modules'][:12])}", f"- 功能：{'、'.join(f['title'] for f in spec['functions'][:12])}"])
        lines.extend(f"- 接口组：{g['title']}（{len(g['interfaces'])} 个接口）" for g in spec["api_groups"])
    else:
        lines.extend(["", "## 操作手册模块", ""])
        lines.extend(f"{i}. {m['title']}：{m['usage']}" for i, m in enumerate(context["manual_modules"], start=1))
    lines.extend(["", "## 申请表建议口径", "", f"- 开发目的：{context['application_purpose']}", f"- 主要功能：{context['main_functions']}", f"- 技术特点：{context['technical_characteristics']}", f"- 软件分类：{context['software_category']}", "", "## 证据来源", ""])
    lines.extend(f"- `{item}`" for item in context["evidence_sources"])
    if context["external_research_notes"]:
        lines.extend(["", "## 外部调研（行业参考，非项目证据）", "", context["external_research_notes"]])
    lines.extend(["", "## 待确认", ""])
    lines.extend(f"- {item}" for item in (["请确认文档类型（操作手册/技术方案文档）是否正确。", "请确认行业、目标用户、主要功能与申请口径是否符合实际申报口径。"] + (["请确认模块、功能、接口与项目源码一致。"] if context["manual_kind"] == "design" else ["请确认操作手册模块按真实页面展开。"])))
    lines.extend(["", "```text", "STOP_FOR_USER", f"NEXT_ACTION: {context['next_action']}", "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
def build_evidence(root: Path, analysis: dict[str, Any], software_name: str, web_notes: str) -> dict[str, Any]:
    source = analysis.get("source") or {}
    return {"software_name": software_name, "project_root": str(root.resolve()), "instruction": "本文件只收集证据；行业判断与结构决策由模型作出。", "documents": collect_documents(root), "code_evidence": {"frameworks": analysis.get("frameworks") or [], "language": analysis.get("language"), "routes": analysis.get("routes") or [], "entry_files": source.get("categorized_files", {}).get("entry") or [], "page_files": source.get("categorized_files", {}).get("page") or [], "api_files": source.get("categorized_files", {}).get("api") or [], "feature_name_candidates": analysis.get("feature_name_candidates") or []}, "web_notes": web_notes}
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--out-dir", default=f"{C.ROOT_NAME}/{C.DRAFT_NAME}")
    parser.add_argument("--web-notes", default="")
    parser.add_argument("--model-context", default="")
    args = parser.parse_args()
    root = Path(args.project)
    analysis = C.load_json(Path(args.analysis))
    web_notes = C.read_text(Path(args.web_notes)) if args.web_notes else ""
    out_dir = C.ensure_dir(Path(args.out_dir))
    evidence = build_evidence(root, analysis, args.software_name, web_notes)
    C.save_json(out_dir / "业务理解证据.json", evidence)
    write_evidence_md(out_dir / "业务理解证据.md", evidence)
    if not args.model_context:
        write_template(out_dir / "业务理解模型稿模板.json", evidence)
        print(f"OK 业务证据：{out_dir / '业务理解证据.md'}")
        print(f"OK 模型稿模板：{out_dir / '业务理解模型稿模板.json'}")
        print("NEXT_ACTION: 模型阅读证据与必要源码后填写模型稿 JSON，再用 --model-context 生成业务理解。")
        return
    model = C.load_json(Path(args.model_context))
    if not isinstance(model, dict):
        raise SystemExit("模型稿必须是 JSON 对象")
    context = normalize_model(model, args.software_name)
    C.save_json(out_dir / "业务理解.json", context)
    write_context_md(out_dir / "业务理解.md", context)
    print(f"OK 业务理解：{out_dir / '业务理解.md'}")
    print(f"文档类型：{context['manual_kind']}")
    C.stop_for_user(context["next_action"])
if __name__ == "__main__":
    main()
