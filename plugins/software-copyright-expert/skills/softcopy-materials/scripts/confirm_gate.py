import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Any
import common as C
def valid_date(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False
REQUIRED_FIELDS = ("软件全称", "版本号", "软件分类", "开发完成日期", "开发方式", "软件说明", "发表状态", "著作权人", "权利范围", "权利取得方式", "开发的硬件环境", "运行的硬件环境", "开发该软件的操作系统", "软件开发环境 / 开发工具", "该软件的运行平台 / 操作系统", "软件运行支撑环境 / 支持软件", "编程语言", "源程序量", "开发目的", "面向领域 / 行业", "软件的主要功能", "软件的技术特点", "页数")
ENUMS = {"软件分类": {"应用软件", "嵌入式软件", "中间件", "系统软件", "其他"}, "开发方式": {"单独开发", "合作开发", "委托开发", "下达任务开发"}, "软件说明": {"原创", "修改（含翻译软件、合成软件）"}, "发表状态": {"已发表", "未发表"}, "权利范围": {"全部权利", "部分权利"}, "权利取得方式": {"原始取得", "继受取得"}}
LIMITS = {"开发的硬件环境": 50, "运行的硬件环境": 50, "开发该软件的操作系统": 50, "软件开发环境 / 开发工具": 50, "该软件的运行平台 / 操作系统": 50, "软件运行支撑环境 / 支持软件": 50, "开发目的": 50, "面向领域 / 行业": 50, "软件的技术特点": 100, "编程语言": 120}
def field_value(md_path: Path, field: str) -> str:
    if not md_path.exists():
        return ""
    prefix = f"➤{field}："
    for line in md_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return ""
def effective_len(value: str) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))
def application_issues(md_path: Path) -> list[str]:
    issues: list[str] = []
    if not md_path.exists():
        return [f"缺少 {md_path}"]
    for field in REQUIRED_FIELDS:
        value = field_value(md_path, field)
        if not value or "待确认" in value:
            issues.append(f"➤{field}：待确认或为空")
            continue
        limit = LIMITS.get(field)
        if limit and effective_len(value) > limit:
            issues.append(f"➤{field}：{effective_len(value)} 字超过 {limit} 字上限")
        allowed = ENUMS.get(field)
        if allowed and value not in allowed:
            issues.append(f"➤{field}：值“{value}”不在允许范围（{'/'.join(sorted(allowed))}）")
    for field in ("开发完成日期", "首次发表日期"):
        value = field_value(md_path, field)
        if value and "待确认" not in value and not valid_date(value):
            issues.append(f"➤{field}：必须为有效的 YYYY-MM-DD 日期")
    if field_value(md_path, "发表状态") == "已发表" and not field_value(md_path, "首次发表日期"):
        issues.append("➤首次发表日期：已发表时必填")
    for field in ("源程序量", "页数"):
        value = field_value(md_path, field)
        if value and "待确认" not in value and (not value.isdigit() or int(value) <= 0):
            issues.append(f"➤{field}：必须为大于 0 的纯数字")
    main = field_value(md_path, "软件的主要功能")
    if main and "待确认" not in main:
        length = effective_len(main)
        if not 500 <= length <= 1300:
            issues.append(f"➤软件的主要功能：{length} 字，需在 500~1300 字之间")
    return issues
def current_issue(path: Path, label: str) -> str | None:
    if not path.is_file():
        return f"{label}尚未确认"
    data = C.load_json(path)
    if not data.get("user_confirmed"):
        return f"{label}尚未确认"
    if not C.digest_current(data):
        return f"{label}在确认后被修改，需重新确认"
    return None
def confirm_simple(workdir: Path, filename: str, key: str, note: str) -> Path:
    path = workdir / filename
    data = C.load_json(path) if path.exists() else {}
    C.mark_confirmed(data, key, note)
    C.save_json(path, data)
    return path
def confirm_business(workdir: Path, note: str) -> Path:
    path = workdir / C.DRAFT_NAME / "业务理解.json"
    if not path.is_file():
        raise SystemExit(f"缺少 {path}")
    data = C.load_json(path)
    C.mark_confirmed(data, "user_confirmed", note)
    C.save_json(path, data)
    return path
def confirm_code_selection(workdir: Path, note: str) -> Path:
    path = workdir / C.DRAFT_NAME / "代码文件选择.json"
    if not path.is_file():
        raise SystemExit(f"缺少 {path}")
    data = C.load_json(path)
    files = [item for item in data.get("files") or [] if isinstance(item, dict) and item.get("selected")]
    if not files:
        C.stop_for_user("代码文件选择尚未由模型填写；请先选择文件并填写 model_reason，再交用户确认。")
    missing = [str(item.get("path")) for item in files if not str(item.get("model_reason") or "").strip()]
    if data.get("model_selection_required") and missing:
        C.stop_for_user("以下已选文件缺少 model_reason：\n" + "\n".join(f"- {p}" for p in missing[:20]))
    C.mark_confirmed(data, "user_confirmed", note)
    C.save_json(path, data)
    return path
def confirm_screenshot_method(workdir: Path, note: str, method: str) -> Path:
    if method not in C.SHOT_METHODS:
        C.stop_for_user("必须通过 --method 显式选择截图方式：" + "/".join(C.SHOT_METHODS) + "；不从备注中猜测。")
    path = workdir / "截图方式确认.json"
    data = C.load_json(path) if path.exists() else {}
    data["screenshot_method"] = method
    C.mark_confirmed(data, "screenshot_method_confirmed", note)
    C.save_json(path, data)
    return path
def confirm_application_fields(workdir: Path, note: str) -> Path:
    md_path = workdir / C.DRAFT_NAME / "申请表信息.md"
    issues = application_issues(md_path)
    if issues:
        C.stop_for_user("申请表字段仍有问题，处理后再确认：\n" + "\n".join(f"- {item[1:]}" for item in issues[:20]))
    path = workdir / C.DRAFT_NAME / "申请表字段确认.json"
    data = C.load_json(path) if path.exists() else {}
    data["application_md_sha256"] = C.sha256_file(md_path)
    C.mark_confirmed(data, "application_fields_confirmed", note)
    C.save_json(path, data)
    return path
def confirm_markdown(workdir: Path, note: str) -> Path:
    issues: list[str] = []
    draft_dir = workdir / C.DRAFT_NAME
    for path, label in ((draft_dir / "业务理解.json", "业务理解"), (draft_dir / "代码文件选择.json", "代码文件选择")):
        found = current_issue(path, label)
        if found:
            issues.append(found)
    kind = C.manual_kind_of(draft_dir)
    screenshot = workdir / "截图方式确认.json"
    if kind == "operation":
        if not screenshot.is_file() or not C.load_json(screenshot).get("screenshot_method_confirmed"):
            issues.append("截图方式尚未确认")
        elif C.load_json(screenshot).get("screenshot_method") not in C.SHOT_METHODS:
            issues.append("截图方式取值无效，请重新记录")
        elif not C.digest_current(C.load_json(screenshot)):
            issues.append("截图方式确认在记录后被修改，请重新记录")
    elif screenshot.exists():
        issues.append("技术方案文档模式不需要截图方式；请删除 截图方式确认.json 或改回操作手册模式")
    fields = draft_dir / "申请表字段确认.json"
    if not fields.is_file() or not C.load_json(fields).get("application_fields_confirmed"):
        issues.append("申请表字段尚未确认")
    else:
        app_md = draft_dir / "申请表信息.md"
        if not app_md.is_file() or C.load_json(fields).get("application_md_sha256") != C.sha256_file(app_md):
            issues.append("申请表信息在确认后被修改，请重新确认")
    field_issues = application_issues(draft_dir / "申请表信息.md")
    if field_issues:
        issues.append("申请表信息仍有字段未满足要求：")
        issues.extend(field_issues)
    issues.extend(C.draft_completeness_issues(workdir))
    if issues:
        C.stop_for_user("Markdown 确认前需先处理以下事项：\n" + "\n".join(f"- {item}" for item in issues))
    path = draft_dir / "最终确认.json"
    data = C.load_json(path) if path.exists() else {}
    data["draft_file_sha256"] = C.draft_snapshot(workdir)
    C.mark_confirmed(data, "markdown_confirmed", note)
    C.save_json(path, data)
    return path
def review_gate_issues(workdir: Path) -> list[str]:
    """审查门禁是否已确认且指纹仍有效；返回问题列表（空表示有效）。"""
    path = C.review_gate_of(workdir)
    if not path.is_file():
        return ["合规审查尚未确认"]
    data = C.load_json(path)
    if not data.get(C.REVIEW_GATE_KEY):
        return ["合规审查尚未确认"]
    expected = data.get("final_file_sha256") or {}
    current = C.final_snapshot(workdir)
    if expected != current:
        changed = sorted(set(expected) ^ set(current)) or [
            key for key in expected if expected.get(key) != current.get(key)
        ]
        return ["正式交付物或审查产物在确认后被修改（" + "、".join(changed[:8]) + "），需重新审查"]
    return []


def machine_review_state(workdir: Path) -> tuple[str, list[str]]:
    """重新跑一次机器核查，返回（结论, 阻断项列表）。

    确认门禁时必须以当前状态为准，不能只信报告里的结论——
    否则「脚本已报阻断、报告却写通过」的降级就能蒙混过关。
    「审查门禁」类阻断项在重新确认时排除：那正是本次确认要解除的状态。
    """
    import review_final

    data = review_final.review(workdir)
    blocking = [
        f"{item['id']} {item['area']}：{item['issue']}"
        for item in data["findings"]
        if item["level"] == review_final.BLOCK and item["area"] != "审查门禁"
    ]
    advisory = [
        item for item in data["findings"]
        if item["level"] == review_final.ADVISORY
    ]
    verdict = review_final.VERDICT_FAIL if blocking else (
        review_final.VERDICT_ADVISORY if advisory else review_final.VERDICT_PASS
    )
    return verdict, blocking


# 结论的宽松程度：越靠后越宽松。模型结论不得比机器结论更宽松。
_VERDICT_LENIENCY = {C.REVIEW_VERDICT_FAIL: 0, C.REVIEW_VERDICT_ADVISORY: 1, C.REVIEW_VERDICT_PASS: 2}


def confirm_review(workdir: Path, note: str) -> Path:
    """第八道门禁：合规审查确认。

    与前七道门禁的关键差别：
    - 前七道确认的是「过程产物」（草稿、字段、截图方式）；
    - 本道确认的是「最终交付物的可提交性」，因此指纹覆盖 申请资料/ 与 审查报告.md，
      正式材料在审查后被改动即失效，必须重新审查。
    """
    issues: list[str] = []
    # 1. 上游门禁链必须仍然有效（正式资料须与用户确认过的草稿同源）
    import build_final

    issues.extend(build_final.confirmation_issues(workdir))
    # 2. 审查报告必须存在且结论明确
    issues.extend(C.review_verdict_issues(workdir))
    report = C.review_report_of(workdir)
    verdict = C.review_verdict_of(C.read_text(report)) if report.is_file() else ""
    # 3. 以当前机器核查为准：存在阻断项时不允许确认
    machine_verdict, blocking = machine_review_state(workdir)
    if blocking:
        issues.append(f"当前机器核查仍有 {len(blocking)} 项阻断问题，整改前不得确认审查门禁：")
        issues.extend(f"  {item}" for item in blocking[:10])
    # 4. 结论不得为「不通过」——有阻断项时由用户决定整改还是停止提交
    if verdict == C.REVIEW_VERDICT_FAIL:
        issues.append(f"审查结论为「{C.REVIEW_VERDICT_FAIL}」：存在阻断项，整改前不得确认审查门禁")
    elif not verdict:
        issues.append("审查结论未明确写出，无法确认审查门禁")
    # 5. 模型结论不得比机器结论更宽松（脚本阻断项不得降级）
    elif machine_verdict in _VERDICT_LENIENCY and verdict in _VERDICT_LENIENCY:
        if _VERDICT_LENIENCY[verdict] > _VERDICT_LENIENCY[machine_verdict]:
            issues.append(
                f"审查报告结论「{verdict}」比机器核查结论「{machine_verdict}」更宽松；"
                "脚本发现的问题不得降级或省略"
            )
    if issues:
        C.stop_for_user("审查门禁确认前需先处理以下事项：\n" + "\n".join(f"- {item}" for item in issues))
    path = C.review_gate_of(workdir)
    data = C.load_json(path) if path.exists() else {}
    data["review_verdict"] = verdict
    data["machine_verdict"] = machine_verdict
    data["final_file_sha256"] = C.final_snapshot(workdir)
    C.mark_confirmed(data, C.REVIEW_GATE_KEY, note)
    C.save_json(path, data)
    return path


def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default=C.ROOT_NAME)
    parser.add_argument("--stage", required=True, choices=["environment", "project", "business", "code-selection", "screenshot-method", "application-fields", "markdown", "review"])
    parser.add_argument("--note", default="用户已确认")
    parser.add_argument("--method", choices=list(C.SHOT_METHODS))
    args = parser.parse_args()
    workdir = Path(args.workdir)
    if args.stage == "environment":
        path = confirm_simple(workdir, "环境确认.json", "environment_confirmed", args.note)
    elif args.stage == "project":
        path = confirm_simple(workdir, "项目确认.json", "project_confirmed", args.note)
    elif args.stage == "business":
        path = confirm_business(workdir, args.note)
    elif args.stage == "code-selection":
        path = confirm_code_selection(workdir, args.note)
    elif args.stage == "screenshot-method":
        if not args.method:
            C.stop_for_user("screenshot-method 门禁必须显式传 --method（" + "/".join(C.SHOT_METHODS) + "）。")
        path = confirm_screenshot_method(workdir, args.note, args.method)
    elif args.stage == "application-fields":
        path = confirm_application_fields(workdir, args.note)
    elif args.stage == "review":
        path = confirm_review(workdir, args.note)
    else:
        path = confirm_markdown(workdir, args.note)
    print(f"OK 门禁已记录：{args.stage}")
    print(path)
if __name__ == "__main__":
    main()
