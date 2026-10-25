import argparse
from pathlib import Path
from typing import Any
import common as C
def selected_estimate(item: dict[str, Any]) -> int:
    try:
        total = int(item.get("material_line_count") or item.get("line_count") or 0)
    except (TypeError, ValueError):
        total = 0
    return total
def load_selection(selection_path: Path) -> list[dict[str, Any]]:
    if not selection_path.exists():
        C.stop_for_user("代码抽取必须先由 code_selection.py 生成 草稿/代码文件选择.json 并完成确认。")
    data = C.load_json(selection_path)
    if isinstance(data, dict) and data.get("selection_required") and not data.get("user_confirmed"):
        C.stop_for_user("代码文件选择尚未确认。请确认或修改 草稿/代码文件选择.json 后记录 code-selection 门禁。")
    items = data.get("files") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SystemExit(f"选择文件格式无效：{selection_path}")
    selected = [item for item in items if isinstance(item, dict) and item.get("selected") and str(item.get("path") or "").strip()]
    if not selected:
        C.stop_for_user("选择文件中没有 selected 为 true 的源码文件；请先由模型选择并经用户确认。")
    return selected
def availability(selection_path: Path) -> tuple[int, int, int]:
    data = C.load_json(selection_path)
    items = [item for item in data.get("files", []) if isinstance(item, dict)]
    total = sum(selected_estimate(item) for item in items)
    unselected = sum(1 for item in items if not item.get("selected") and selected_estimate(item) > 0)
    pages = (total + C.CODE_LINES_PER_PAGE - 1) // C.CODE_LINES_PER_PAGE if total else 0
    return total, pages, unselected
def collect(root: Path, selection_path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    lines: list[str] = []
    manifest: list[dict[str, Any]] = []
    for item in load_selection(selection_path):
        rel = str(item["path"])
        path = (root / rel).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            raise SystemExit(f"选中的文件位于项目目录之外：{path}")
        if not C.is_source(path):
            print(f"警告：已跳过候选生成后不再适合抽取的文件：{rel}")
            continue
        text = C.read_text(path)
        style = C.comment_style(path)
        physical = text.splitlines()
        kept = C.strip_comments(text, style)
        material = C.material_lines(text, style)
        if not kept:
            continue
        start = len(lines) + 1
        lines.extend(material)
        manifest.append({"path": rel, "physical_line_count": len(physical), "blank_line_count": len(physical) - len([l for l in physical if l.strip()]), "comment_line_count": len([l for l in physical if l.strip()]) - len(kept), "kept_line_count": len(kept), "material_line_count": len(material), "material_line_start": start, "material_line_end": len(lines)})
    return lines, manifest
def write_code_md(path: Path, title: str, software_name: str, version: str, pages: list[tuple[int, list[str]]]) -> None:
    chunks = [f"# {title}", "", f"软件名称：{software_name}", f"版本号：{version}", ""]
    for number, rows in pages:
        chunks.extend([f"## 第 {number} 页", "", "```text"])
        chunks.extend(rows)
        chunks.extend(["```", ""])
    path.write_text("\n".join(chunks), encoding="utf-8")
def write_manifest_md(path: Path, manifest: dict[str, Any]) -> None:
    lines = ["# 代码提取清单", "", f"- 软件名称：{manifest['software_name']}", f"- 版本号：{manifest['version']}", f"- 项目目录：{manifest['project_root']}", f"- 已选源码文件数：{manifest['file_count']}", f"- 材料物理行数：{manifest['material_line_count']}", f"- 每页估算行数：{manifest['lines_per_page']}", f"- 单行最大显示列：{manifest['max_columns']}", f"- 已选源码估算页数：{manifest['estimated_pages']}", f"- 提交材料页数：{manifest['submitted_pages']}", f"- 输出模式：{manifest['mode']}", f"- 候选源码可生成页数：{manifest['candidate_pages']}", f"- 补充状态：{manifest['supplement_status']}", "", "## 文件来源", "", "| 文件 | 物理行数 | 去注释后行数 | 材料物理行数 | 材料行范围 |", "| --- | ---: | ---: | ---: | --- |"]
    for item in manifest["files"]:
        lines.append(f"| `{item['path']}` | {item['physical_line_count']} | {item['kept_line_count']} | {item['material_line_count']} | {item['material_line_start']}-{item['material_line_end']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
def extract(root: Path, out_dir: Path, software_name: str, version: str, selection_path: Path) -> dict[str, Any]:
    lines, files = collect(root, selection_path)
    if not lines:
        raise SystemExit("选中文件未产生任何材料行，请检查文件内容或重新选择。")
    pages = [lines[i: i + C.CODE_LINES_PER_PAGE] for i in range(0, len(lines), C.CODE_LINES_PER_PAGE)]
    total_pages = len(pages)
    _total_lines, candidate_pages, unselected = availability(selection_path)
    if total_pages < C.PAGE_TARGET and candidate_pages >= C.PAGE_TARGET and unselected > 0:
        C.stop_for_user(f"当前已选代码约 {total_pages} 页，候选源码可补足到 {C.PAGE_TARGET} 页；请在 代码文件选择.json 中继续补充文件并重新确认 code-selection 门禁。")
    for stale in C.STALE_CODE_DRAFTS | C.CODE_DRAFTS:
        (out_dir / stale).unlink(missing_ok=True)
    outputs: list[str] = []
    code_path = out_dir / "代码.md"
    if total_pages >= C.PAGE_TARGET:
        front = list(enumerate(pages[:30], start=1))
        back = [(31 + i, rows) for i, rows in enumerate(pages[-30:])]
        write_code_md(code_path, "代码材料（前30页+后30页）", software_name, version, front + back)
        mode = "front30_back30"
        submitted = 60
    else:
        write_code_md(code_path, "代码材料（全部）", software_name, version, list(enumerate(pages, start=1)))
        mode = "all_pages"
        submitted = total_pages
    outputs.append(code_path.name)
    manifest = {
        "software_name": software_name,
        "version": version,
        "project_root": str(root.resolve()),
        "file_count": len(files),
        "material_line_count": len(lines),
        "lines_per_page": C.CODE_LINES_PER_PAGE,
        "max_columns": C.CODE_COLUMNS,
        "estimated_pages": total_pages,
        "submitted_pages": submitted,
        "candidate_pages": candidate_pages,
        "supplement_status": "候选源码可达到前30页/后30页要求" if candidate_pages >= C.PAGE_TARGET else "候选源码不足60页，按全部代码材料生成",
        "mode": mode,
        "selection_file": str(selection_path),
        "outputs": outputs,
        "files": files,
        "safe_software_name": C.safe_name(software_name),
    }
    C.save_json(out_dir / "代码提取清单.json", manifest)
    write_manifest_md(out_dir / "代码提取清单.md", manifest)
    return manifest
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--version", default="V1.0")
    parser.add_argument("--out-dir", default=f"{C.ROOT_NAME}/{C.DRAFT_NAME}")
    args = parser.parse_args()
    root = Path(args.project)
    if not root.exists():
        raise SystemExit(f"项目目录不存在：{root}")
    selection = Path(args.selection)
    if not selection.exists():
        raise SystemExit(f"选择文件不存在：{selection}")
    manifest = extract(root, Path(args.out_dir), args.software_name, args.version, selection)
    print(f"OK 代码材料：{args.out_dir}")
    print(f"模式：{manifest['mode']}")
    print(f"已选估算页数：{manifest['estimated_pages']}")
    print(f"提交材料页数：{manifest['submitted_pages']}")
if __name__ == "__main__":
    main()
