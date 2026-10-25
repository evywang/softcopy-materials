import argparse
from pathlib import Path
from typing import Any
import common as C
def evidence_label(weight: int, path: Path) -> str:
    table = {0: "入口文件", 10: "路由文件", 20: "页面文件", 30: "数据交互文件", 40: "状态管理文件", 45: "数据模型文件", 50: "组件文件", 60: "通用能力文件", 70: "服务端文件", 80: "前端源码", 85: "其他源码", 90: "样式文件"}
    return table.get(weight, "其他源码")
def build_candidates(root: Path) -> list[dict[str, Any]]:
    files = sorted(C.iter_sources(root), key=lambda p: (C.category_weight(p, root), str(p).lower()))
    candidates: list[dict[str, Any]] = []
    for path in files:
        try:
            text = C.read_text(path)
        except Exception:
            continue
        style = C.comment_style(path)
        material = len(C.material_lines(text, style))
        physical = len(text.splitlines())
        weight = C.category_weight(path, root)
        candidates.append({"path": C.rel_posix(path, root), "selected": False, "line_count": physical, "material_line_count": material, "priority": weight, "evidence": evidence_label(weight, path), "model_reason": ""})
    return candidates
def estimate_pages(lines: int) -> int:
    return (lines + C.CODE_LINES_PER_PAGE - 1) // C.CODE_LINES_PER_PAGE if lines > 0 else 0
def write_listing(path: Path, data: dict[str, Any]) -> None:
    chosen = [item for item in data["files"] if item.get("selected")]
    lines = [
        "# 代码文件候选清单",
        "",
        "本清单只登记候选源码证据，不默认选择任何文件。",
        "模型需先阅读业务理解、入口、页面与必要源码，再在 代码文件选择.json 中填写 selected 与 model_reason，最后交用户确认。",
        f"候选源码合计约 {data['estimated_candidate_pages']} 页；当前模型已选约 {data['estimated_selected_pages']} 页（目标不少于 {C.PAGE_TARGET} 页）。",
        "",
        f"| 文件 | 物理行数 | 材料行数 | 证据类型 | 模型选择理由 |",
        f"| --- | ---: | ---: | --- | --- |",
    ]
    for item in data["files"]:
        reason = item.get("model_reason") or ""
        mark = "✓" if item.get("selected") else ""
        lines.append(f"| {mark} `{item['path']}` | {item['line_count']} | {item['material_line_count']} | {item['evidence']} | {reason} |")
    lines.extend(["", "```text", "STOP_FOR_USER", "NEXT_ACTION: 模型先填写 草稿/代码文件选择.json 的 selected/model_reason，再由用户确认并记录 code-selection 门禁。", "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--analysis", default="")
    parser.add_argument("--out-dir", default=f"{C.ROOT_NAME}/{C.DRAFT_NAME}")
    args = parser.parse_args()
    root = Path(args.project)
    if not root.exists():
        raise SystemExit(f"项目目录不存在：{root}")
    if args.analysis and not Path(args.analysis).exists():
        raise SystemExit(f"分析文件不存在：{args.analysis}")
    out_dir = C.ensure_dir(Path(args.out_dir))
    candidates = build_candidates(root)
    selected_lines = sum(item["material_line_count"] for item in candidates if item.get("selected"))
    candidate_lines = sum(item["material_line_count"] for item in candidates)
    data = {
        "project_root": str(root.resolve()),
        "selection_required": True,
        "model_selection_required": True,
        "user_confirmed": False,
        "lines_per_page": C.CODE_LINES_PER_PAGE,
        "target_pages": C.PAGE_TARGET,
        "estimated_selected_lines": selected_lines,
        "estimated_selected_pages": estimate_pages(selected_lines),
        "estimated_candidate_lines": candidate_lines,
        "estimated_candidate_pages": estimate_pages(candidate_lines),
        "supplement_rule": f"模型优先选择能体现软件功能与运行逻辑的完整文件；合计不足 {C.PAGE_TARGET} 页时先从候选补充；候选仍不足时才生成全部代码材料。",
        "gate": "code-selection",
        "next_action": "模型填写 selected/model_reason 后交用户确认，再运行 confirm_gate.py --stage code-selection。",
        "files": candidates,
    }
    C.save_json(out_dir / "代码文件选择.json", data)
    write_listing(out_dir / "代码文件候选清单.md", data)
    print(f"OK 代码候选：{out_dir}")
    print(f"候选文件：{len(candidates)}")
    print(f"候选估算页数：{data['estimated_candidate_pages']}")
    C.stop_for_user(data["next_action"])
if __name__ == "__main__":
    main()
