import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import common as C
import manual_draft
from build_final import confirmation_issues, field_value, parse_code_pages
from confirm_gate import application_issues
BLOCK = "阻断"
ADVISORY = "提示"
VERDICT_PASS = "通过"
VERDICT_ADVISORY = "整改后通过"
VERDICT_FAIL = "不通过"
def report_warnings(report_md: Path) -> list[str]:
    if not report_md.is_file():
        return []
    captured: list[str] = []
    in_section = False
    for line in report_md.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_section = line.strip() == "## 警告"
            continue
        if in_section and line.startswith("- "):
            item = line[2:].strip()
            if item and item != "无":
                captured.append(item)
    return captured
def code_traceability(workdir: Path, manifest: dict[str, Any], code_md: Path) -> tuple[str, str]:
    """代码真实性：提交材料逐行回溯到项目源码。

    依据《计算机软件著作权登记办法》与登记实务，程序鉴别材料必须是登记软件
    自身的真实源代码。全量比对而非抽样：集合查找为 O(1)，任何一行编造代码
    都会被抓出，不给抽样漏检留下空间。
    """
    root = Path(str(manifest.get("project_root") or ""))
    files = manifest.get("files") or []
    if not root.is_dir() or not files:
        return "", "项目源码不可访问，跳过逐字回溯"
    source_lines: set[str] = set()
    for item in files:
        path = (root / str(item.get("path") or "")).resolve()
        if not path.is_file():
            continue
        text = C.read_text(path)
        style = C.comment_style(path)
        source_lines.update(line.strip() for line in C.material_lines(text, style))
    if not source_lines:
        return "", "源码材料行为空，跳过逐字回溯"
    pages = parse_code_pages(code_md)
    material = [row.strip() for _number, rows in pages for row in rows if row.strip()]
    if not material:
        return "", "代码材料为空，跳过逐字回溯"
    unmatched = [row for row in material if row not in source_lines]
    if unmatched:
        sample = "；".join(row[:60] for row in unmatched[:3])
        return (f"提交材料 {len(material)} 行中有 {len(unmatched)} 行在项目源码中找不到，例：{sample}",
                "程序鉴别材料必须为登记软件自身的真实源代码")
    return "", ""


def name_consistency(workdir: Path, name: str, version: str, prose_docx: Path) -> list[str]:
    """名称版本一致性：申请表、交付文件名、文档标题与代码清单必须统一。"""
    issues: list[str] = []
    draft_dir = workdir / C.DRAFT_NAME
    if name:
        for path in sorted((workdir / C.FINAL_NAME).glob("*.docx")):
            if name not in path.stem:
                issues.append(f"交付文件“{path.name}”的文件名未包含软件全称“{name}”")
    manifest = C.load_json(draft_dir / "代码提取清单.json") if (draft_dir / "代码提取清单.json").is_file() else {}
    if manifest:
        if name and manifest.get("software_name") != name:
            issues.append(f"代码清单软件名“{manifest.get('software_name')}”与申请表“{name}”不一致")
        if version and manifest.get("version") != version:
            issues.append(f"代码清单版本号“{manifest.get('version')}”与申请表“{version}”不一致")
    kind = C.manual_kind_of(draft_dir)
    doc_md = draft_dir / C.PROSE_FILES[kind][0]
    if doc_md.is_file():
        lines = C.read_text(doc_md).splitlines()
        head = lines[0].strip() if lines else ""
        if name and name not in head:
            issues.append(f"说明文档标题“{head}”未包含软件全称“{name}”")
    return issues


def check_development_purpose(app_txt: Path, app_draft: Path, name: str) -> str:
    """开发目的不得只写软件名称。"""
    target = app_txt if app_txt.is_file() else app_draft
    purpose = field_value(target, "开发目的")
    if not purpose:
        return ""
    if len(re.sub(r"\s+", "", purpose)) <= len(re.sub(r"\s+", "", name or "")):
        return f"开发目的“{purpose}”未体现开发意图，不能只写软件名称"
    return ""


def review(workdir: Path) -> dict[str, Any]:
    draft_dir = workdir / C.DRAFT_NAME
    final_dir = workdir / C.FINAL_NAME
    kind = C.manual_kind_of(draft_dir)
    doc_md, _review_json, _review_md, suffix = C.PROSE_FILES[kind]
    findings: list[dict[str, str]] = []
    def flag(level: str, area: str, issue: str, basis: str) -> None:
        findings.append({"id": f"R{len(findings) + 1:02d}", "level": level, "area": area, "issue": issue, "basis": basis})
    app_txt = final_dir / "申请表信息.txt"
    app_draft = draft_dir / "申请表信息.md"
    name = field_value(app_txt, "软件全称") if app_txt.is_file() else field_value(app_draft, "软件全称")
    version = field_value(app_txt, "版本号") if app_txt.is_file() else field_value(app_draft, "版本号")
    safe = C.safe_name(name or "软件")
    code_docx = final_dir / f"{safe}-代码.docx"
    # PROSE_FILES 的后缀已含 .docx（与 build_final 生成的文件名口径一致）
    prose_docx = final_dir / f"{safe}{suffix}"
    report_md = final_dir / "生成报告.md"
    evidence: dict[str, Any] = {"final_files": {}, "kind": kind, "software_name": name or "", "version": version or ""}
    for path in (app_txt, code_docx, prose_docx, report_md):
        exists = path.is_file() and path.stat().st_size > 0
        evidence["final_files"][path.name] = {"exists": exists, "bytes": path.stat().st_size if path.is_file() else 0}
        if not exists:
            flag(BLOCK, "正式文件", f"缺少或为空：申请资料/{path.name}", "正式生成三轮验证第 1 轮（文件存在且非空）")
    if app_txt.is_file():
        for issue in application_issues(app_txt):
            flag(BLOCK, "申请表", issue[1:] if issue.startswith("➤") else issue, "官网申请表填写口径（枚举/日期/长度/500~1300字）")
    manifest_path = draft_dir / "代码提取清单.json"
    manifest = C.load_json(manifest_path) if manifest_path.is_file() else {}
    mode = manifest.get("mode") or ""
    pages_field = ""
    for source in (app_txt, app_draft):
        if source.is_file():
            pages_field = field_value(source, "页数")
            if pages_field:
                break
    code_md = draft_dir / "代码.md"
    if code_md.is_file():
        pages = parse_code_pages(code_md)
        evidence["code_pages"] = len(pages)
        blanks = sum(1 for _number, rows in pages for row in rows if not row.strip())
        if blanks:
            flag(BLOCK, "代码材料", f"代码正文残留 {blanks} 个空行", "鉴别材料抽取规则（去注释与空行）")
        material_last = pages[-1][0] if pages else None
        for number, rows in pages:
            if len(rows) < 50:
                level = ADVISORY if number == material_last else BLOCK
                flag(level, "代码材料", f"第 {number} 页仅 {len(rows)} 行（每页不少于 50 行）", "《计算机软件著作权登记办法》第十条")
        if mode == "front30_back30" and len(pages) != 60:
            flag(BLOCK, "代码材料", f"前30+后30 模式实际 {len(pages)} 页，应为 60 页", "《计算机软件著作权登记办法》第十条")
        if pages_field:
            if not pages_field.isdigit() or int(pages_field) <= 0:
                flag(BLOCK, "申请表", f"页数字段“{pages_field}”不是正整数", "官网申请表填写口径")
            elif int(pages_field) != len(pages):
                flag(BLOCK, "申请表", f"页数字段 {pages_field} 与代码材料 {len(pages)} 页不一致", "官网申请表填写口径")
    else:
        flag(BLOCK, "代码材料", "缺少 草稿/代码.md，无法复核鉴别材料", "草稿完整性要求")
    doc_text: str | None = None
    business: dict[str, Any] = {}
    if (draft_dir / "业务理解.json").is_file():
        try:
            loaded = C.load_json(draft_dir / "业务理解.json")
            if isinstance(loaded, dict):
                business = loaded
        except Exception:
            business = {}
    doc_path = draft_dir / doc_md
    if doc_path.is_file():
        doc_text = doc_path.read_text(encoding="utf-8")
        try:
            if kind == "design":
                if not isinstance(business.get("design_spec"), dict):
                    business["design_spec"] = {}
                blocking, advisory = manual_draft.check_design(doc_text, business)
                basis = "references/design.md 技术方案文档骨架"
            else:
                blocking, advisory = manual_draft.check_operation(doc_text, business)
                basis = "references/manual.md 操作手册骨架"
            for item in blocking:
                flag(BLOCK, "文档结构", item, basis)
            for item in advisory:
                flag(ADVISORY, "文档结构", item, basis)
        except Exception as exc:
            flag(BLOCK, "文档结构", f"无法复核 {doc_md}：{exc}", "references/manual.md / references/design.md")
    else:
        flag(BLOCK, "文档结构", f"缺少 草稿/{doc_md}，无法复核文档骨架", "references/manual.md / references/design.md")
    shot_confirm = workdir / "截图方式确认.json"
    method = ""
    if shot_confirm.is_file():
        method = str((C.load_json(shot_confirm) or {}).get("screenshot_method") or "")
    evidence["screenshot_method"] = method
    if kind == "operation":
        if method == "skip":
            evidence["screenshot_note"] = "用户选择跳过截图；操作手册保留可见截图预留文字"
        elif method in C.SHOT_METHODS:
            listing = workdir / "截图" / "截图清单.json"
            if not listing.is_file():
                flag(BLOCK, "截图", "缺少 截图/截图清单.json", "references/shots.md 截图规则")
            else:
                data = C.load_json(listing) or {}
                if data.get("status") != "ok":
                    flag(BLOCK, "截图", f"截图清单状态为 {data.get('status') or '空'}，应为 ok", "references/shots.md 截图规则")
                if str(data.get("method") or "") != method:
                    flag(BLOCK, "截图", f"截图清单方式 {data.get('method') or '空'} 与确认方式 {method} 不一致", "门禁 screenshot-method")
                shots = [e for e in data.get("screenshots") or [] if isinstance(e, dict)]
                valid = 0
                for entry in shots:
                    image = Path(str(entry.get("path") or ""))
                    if not image.is_absolute():
                        image = listing.parent / image
                    if image.is_file() and image.stat().st_size > 0:
                        valid += 1
                    else:
                        flag(BLOCK, "截图", f"截图文件缺失或为空：{entry.get('path')}", "references/shots.md（每张必须落盘且非空）")
                placeholders = doc_text.count("【截图预留：") if doc_text is not None else 0
                if valid != placeholders:
                    flag(ADVISORY, "截图", f"截图清单 {valid} 张与手册预留位置 {placeholders} 处不匹配", "references/shots.md（按清单插入，不猜测顺序）")
        else:
            flag(BLOCK, "截图", "截图方式未确认或取值无效", "门禁 screenshot-method（四选一，必须显式确认）")
    figure_listing = draft_dir / "图纸清单.json"
    if kind == "design" and figure_listing.is_file():
        entries = C.load_json(figure_listing).get("figures") or []
        evidence["figures"] = [{"key": e.get("key"), "format": e.get("format"), "backend": e.get("backend")} for e in entries if isinstance(e, dict)]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("status") == "error":
                flag(BLOCK, "图纸", f"图纸 {entry.get('key')} 渲染失败", "references/figures.md")
            elif entry.get("format") == "text":
                flag(ADVISORY, "图纸", f"图纸 {entry.get('key')} 为中文文本框线图（当前环境无 graphviz）；可安装 graphviz 或用宿主架构图技能产图升级为 PNG", "references/figures.md")
    for issue in confirmation_issues(workdir):
        flag(BLOCK, "门禁链", issue, "七道内容指纹门禁（正式资料必须与用户确认过的草稿一致）")
    # 上一轮审查门禁是否已失效：正式交付物在确认后被改动时必须重新审查
    gate_path = C.review_gate_of(workdir)
    if gate_path.is_file():
        gate = C.load_json(gate_path)
        if gate.get(C.REVIEW_GATE_KEY):
            expected = gate.get("final_file_sha256") or {}
            current = C.final_snapshot(workdir)
            if expected != current:
                changed = sorted(set(expected) ^ set(current)) or [
                    key for key in expected if expected.get(key) != current.get(key)
                ]
                flag(BLOCK, "审查门禁",
                     "上一轮审查已确认，但正式交付物在确认后被修改（"
                     + "、".join(changed[:6]) + "），必须重新审查后再确认",
                     "第八道门禁内容指纹（审查确认后正式材料不得改动）")
            else:
                evidence["review_gate"] = "confirmed"
    # 名称版本一致性：申请表、交付文件名、文档标题与代码清单统一
    for issue in name_consistency(workdir, name or "", version or "", prose_docx):
        flag(BLOCK, "名称一致性", issue, "登记口径（软件全称与版本号以申请表信息为准，全文统一）")
    # 开发目的口径
    purpose_issue = check_development_purpose(app_txt, app_draft, name or "")
    if purpose_issue:
        flag(BLOCK, "申请表", purpose_issue, "官网申请表填写口径（开发目的不能只写软件名称）")
    # 代码真实性：逐行回溯到项目源码
    if code_md.is_file() and manifest:
        traceability, basis = code_traceability(workdir, manifest, code_md)
        if traceability:
            flag(BLOCK, "代码真实性", traceability, basis)
    for warning in report_warnings(report_md):
        flag(ADVISORY, "生成报告", warning, "build_final 生成报告警告")
    blocking = [f for f in findings if f["level"] == BLOCK]
    advisory = [f for f in findings if f["level"] == ADVISORY]
    verdict = VERDICT_FAIL if blocking else (VERDICT_ADVISORY if advisory else VERDICT_PASS)
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "workdir": str(workdir), "verdict": verdict, "counts": {"blocking": len(blocking), "advisory": len(advisory)}, "findings": findings, "evidence": evidence}
def write_markdown(out_dir: Path, data: dict[str, Any]) -> Path:
    evidence = data["evidence"]
    kind_label = "操作手册（operation）" if evidence["kind"] == "operation" else "技术方案文档（design）"
    lines = ["# 软著合规审查底稿", "", f"- 审查时间：{data['generated_at']}", f"- 软件名称：{evidence['software_name'] or '未知'}　版本：{evidence['version'] or '未知'}", f"- 文档类型：{kind_label}", f"- 审查结论：**{data['verdict']}**（阻断 {data['counts']['blocking']} 项，提示 {data['counts']['advisory']} 项）", "", "分级口径：阻断=不符合登记口径、提交前必须整改；提示=不影响受理、建议处理。", "", "## 问题清单", ""]
    if data["findings"]:
        lines.extend(["| 编号 | 级别 | 方面 | 问题 | 依据 |", "| --- | --- | --- | --- | --- |"])
        for item in data["findings"]:
            lines.append(f"| {item['id']} | {item['level']} | {item['area']} | {item['issue']} | {item['basis']} |")
    else:
        lines.append("未发现问题。")
    file_bits = []
    for name, info in evidence["final_files"].items():
        state = "存在" if info["exists"] else "缺失"
        file_bits.append(f"{name}（{state}）")
    lines.extend(["", "## 证据摘要", "", "- 正式文件：" + "、".join(file_bits)])
    if "code_pages" in evidence:
        lines.append(f"- 代码鉴别材料：{evidence['code_pages']} 页（模式见代码提取清单）")
    if evidence.get("screenshot_method"):
        note = evidence.get("screenshot_note") or f"方式 {evidence['screenshot_method']}"
        lines.append(f"- 截图：{note}")
    if evidence.get("figures"):
        lines.append("- 图纸：" + "、".join(f"{f['key']}（{f['backend']}）" for f in evidence["figures"]))
    lines.extend(["", "## 模型撰写指引", "", "以软著审查专员身份撰写 `软著/审查/审查报告.md`：①审查结论（通过/整改后通过/不通过，与底稿一致）；②逐项合规情况（对应底稿编号）；③问题与整改建议（阻断项指明回到哪个阶段重跑）；④提交前检查清单（docx 另存 PDF、按官网当前要求填报、自行核对材料真实性）。脚本阻断项不得降级或省略；整改必须回到对应阶段重新生成并重新确认，不得直接改正式文件。", ""])
    path = out_dir / "合规审查底稿.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default=C.ROOT_NAME)
    args = parser.parse_args()
    workdir = Path(args.workdir)
    data = review(workdir)
    out_dir = C.ensure_dir(workdir / "审查")
    C.save_json(out_dir / "合规审查底稿.json", data)
    write_markdown(out_dir, data)
    print(f"OK 合规审查底稿：{out_dir / '合规审查底稿.md'}")
    print(f"结论：{data['verdict']}（阻断 {data['counts']['blocking']} 项，提示 {data['counts']['advisory']} 项）")
    for item in data["findings"]:
        print(f"{item['level']}｜{item['id']}｜{item['area']}｜{item['issue']}")
    C.stop_for_user("模型以软著审查专员身份阅读底稿与正式文件（有宿主 docx/视觉技能时抽查 DOCX 页眉、标题、截图与图纸乱码），撰写 软著/审查/审查报告.md 并呈交用户；存在阻断项时由用户决定回到对应阶段整改重跑还是停止提交。")
if __name__ == "__main__":
    main()
