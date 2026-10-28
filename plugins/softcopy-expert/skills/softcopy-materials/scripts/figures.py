import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
import common as C
import dotgraph
HOST_FIGURE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
HOST_FIGURE_NOTE = "宿主技能产图优先于 DOT 渲染；插入正文前请用视觉能力复核无乱码、无遮挡"
def host_figures(workdir: Path) -> tuple[dict[str, Path], list[str]]:
    source_dir = workdir / "图纸原始"
    found: dict[str, Path] = {}
    warnings: list[str] = []
    if not source_dir.is_dir():
        return found, warnings
    for path in sorted(source_dir.iterdir(), key=lambda p: p.name.casefold()):
        if not path.is_file() or path.suffix.lower() not in HOST_FIGURE_EXTS:
            continue
        stem = re.sub(r"^\d+[-_]", "", path.stem)
        if not C.DOT_SLOT_RE.fullmatch(stem):
            warnings.append(f"图纸原始/{path.name}：文件名不含有效图纸插槽名（architecture/key_N/function_N），不会采用")
            continue
        if path.stat().st_size == 0:
            warnings.append(f"图纸原始/{path.name}：文件为空，不会采用")
            continue
        if stem in found:
            warnings.append(f"图纸原始/{path.name}：插槽 {stem} 已有图片，按文件名顺序取先者")
            continue
        found[stem] = path
    return found, warnings
def figure_order(keys: list[str]) -> list[str]:
    def order(key: str) -> tuple[int, int]:
        if key == "architecture":
            return (0, 0)
        match = re.fullmatch(r"(key|function)_(\d+)", key)
        return (1, int(match.group(2))) if match and match.group(1) == "key" else (2, int(match.group(2)) if match else 9)
    return sorted(keys, key=order)
def preferred_backends(workdir: Path) -> list[str]:
    env_path = workdir / "环境探测.json"
    if env_path.is_file():
        try:
            preferred = (C.load_json(env_path).get("capabilities") or {}).get("diagram_backend")
            if preferred in C.DIAGRAM_BACKENDS:
                return [preferred] + [name for name in C.DIAGRAM_BACKENDS if name != preferred]
        except Exception:
            pass
    return list(C.detect_diagram_backends().get("backends") or [])
def _run(command: list[str], *, stdin: bytes | None = None, stdout_path: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    if stdout_path is not None:
        with stdout_path.open("wb") as handle:
            return subprocess.run(command, input=stdin, stdout=handle, stderr=subprocess.PIPE, timeout=120, check=False)
    return subprocess.run(command, input=stdin, capture_output=True, timeout=120, check=False)
def _trim_png(output: Path) -> None:
    for tool in ("magick", "convert"):
        binary = shutil.which(tool)
        if not binary:
            continue
        trimmed = output.with_name(f".{output.stem}-trim{output.suffix}")
        try:
            done = subprocess.run([binary, str(output), "-trim", "-bordercolor", "white", "-border", "12", str(trimmed)], capture_output=True, timeout=120, check=False)
            if done.returncode == 0 and trimmed.is_file() and trimmed.stat().st_size > 0:
                trimmed.replace(output)
                return
        except (OSError, subprocess.SubprocessError):
            continue
def render_png(dot: str, output: Path, backend: str) -> tuple[str | None, list[str]]:
    dot_binary = shutil.which("dot")
    if not dot_binary:
        return "未安装 graphviz", []
    source = C.normalize_dot(dot)
    warnings: list[str] = []
    try:
        if backend == "dot-png":
            done = _run([dot_binary, "-Tpng", f"-Gdpi={C.DIAGRAM_DPI}"], stdin=source.encode("utf-8"), stdout_path=output)
            if done.returncode != 0:
                detail = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
                return f"dot 渲染失败：{detail[0] if detail else done.returncode}", []
            warnings = _dot_notes(done.stderr)
        elif backend.startswith("dot-svg-"):
            svg = output.with_suffix(".svg")
            done = _run([dot_binary, "-Tsvg"], stdin=source.encode("utf-8"), stdout_path=svg)
            if done.returncode != 0:
                detail = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
                return f"dot SVG 失败：{detail[0] if detail else done.returncode}", []
            warnings = _dot_notes(done.stderr)
            converter = backend[len("dot-svg-"):]
            if converter == "cairosvg":
                command = [sys.executable, "-m", "cairosvg", str(svg), "-o", str(output), "--dpi", str(C.DIAGRAM_DPI)]
            elif converter == "inkscape":
                command = ["inkscape", str(svg), "-o", str(output), "-d", str(C.DIAGRAM_DPI)]
            elif converter == "librsvg":
                command = ["rsvg-convert", "-o", str(output), "--dpi-x", str(C.DIAGRAM_DPI), "--dpi-y", str(C.DIAGRAM_DPI), str(svg)]
            else:
                tool = shutil.which("magick") or shutil.which("convert")
                command = [tool, "-density", str(C.DIAGRAM_DPI), str(svg), str(output)]
            converted = _run(command)
            svg.unlink(missing_ok=True)
            if converted.returncode != 0:
                detail = converted.stderr.decode("utf-8", errors="replace").strip().splitlines()
                return f"SVG 转换失败（{converter}）：{detail[0] if detail else converted.returncode}", warnings
        else:
            return f"未知渲染后端：{backend}", []
        if not output.is_file() or output.stat().st_size == 0:
            return "渲染输出为空", warnings
        _trim_png(output)
        return None, warnings
    except (OSError, subprocess.SubprocessError) as exc:
        return f"渲染异常：{exc}", []
def _dot_notes(stderr: bytes) -> list[str]:
    text = stderr.decode("utf-8", errors="replace")
    notes: list[str] = []
    if "do not currently handle edge labels" in text:
        notes.append("graphviz 提示正交边不支持边标签，已自动改用折线；若仍错位请精简边标签")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Warning:") and "edge labels" not in line:
            notes.append(f"graphviz 提示：{line[len('Warning:'):].strip()}")
    return list(dict.fromkeys(notes))[:4]
def render_all(workdir: Path, business: dict[str, Any]) -> dict[str, Any]:
    draft_dir = workdir / C.DRAFT_NAME
    figure_dir = C.ensure_dir(draft_dir / "图纸")
    spec = (business.get("design_spec") or {})
    figures_spec = {key: str(value) for key, value in (spec.get("figures") or {}).items() if str(key).strip()}
    host, host_warnings = host_figures(workdir)
    backends = preferred_backends(workdir) if figures_spec else []
    font = C.cjk_font()
    manifest: dict[str, Any] = {"figures": [], "cjk_font": font or "", "host_figure_warnings": host_warnings, "unmatched_host_figures": sorted(key for key in host if key not in figures_spec)}
    for index, key in enumerate(figure_order(list(figures_spec)), start=1):
        dot = figures_spec[key]
        host_path = host.get(key)
        if host_path is not None:
            ext = host_path.suffix.lower()
            target = figure_dir / f"{index:02d}-{key}{ext}"
            shutil.copy2(host_path, target)
            notes = [HOST_FIGURE_NOTE]
            if dot.strip():
                notes.append("该插槽已声明 DOT 源，本次被宿主技能图片取代；删除 图纸原始/ 对应文件可恢复 DOT 渲染")
            if ext != ".png":
                notes.append("非 PNG 图片未做尺寸比例校验，请用视觉能力复核版式")
            entry: dict[str, Any] = {"key": key, "title": key, "status": "ok", "format": ext[1:], "path": f"图纸/{target.name}", "backend": "host-image", "source": f"图纸原始/{host_path.name}", "lint": [], "notes": notes}
            if ext == ".png":
                entry["layout"] = C.png_layout_issues(target)
            manifest["figures"].append(entry)
            continue
        blocking, advisory = C.lint_dot(dot)
        entry = {"key": key, "title": key, "lint": advisory}
        if blocking:
            entry.update({"status": "text", "format": "text", "path": f"图纸/{index:02d}-{key}.txt", "backend": "text", "notes": blocking + ["标签过长不适用 PNG 渲染，已输出中文文本框线图，建议拆行后重跑"]})
        elif font is None:
            entry.update({"status": "text", "format": "text", "path": f"图纸/{index:02d}-{key}.txt", "backend": "text", "notes": ["系统未检测到中文字体，PNG 渲染中文会变成方框乱码，已改用中文文本框线图；安装中文字体（如 Noto Sans CJK）后重跑本脚本可获得 PNG"]})
        else:
            error: str | None = "无可用 PNG 渲染后端" if not backends else None
            used = ""
            render_warnings: list[str] = []
            png_path = figure_dir / f"{index:02d}-{key}.png"
            for backend in backends:
                error, render_warnings = render_png(dot, png_path, backend)
                if error is None:
                    used = backend
                    break
            if error is None:
                layout = C.png_layout_issues(png_path, allow_wide=bool(re.search(r"\brankdir\s*=\s*LR\b", dot)))
                entry.update({"status": "ok", "format": "png", "path": f"图纸/{png_path.name}", "backend": used, "lint": advisory + render_warnings, "layout": layout})
            else:
                entry.update({"status": "text", "format": "text", "path": f"图纸/{index:02d}-{key}.txt", "backend": "text", "notes": [f"PNG 渲染不可用（{error}），已改用中文文本框线图"]})
        if entry["format"] == "text":
            try:
                content = dotgraph.text_diagram_from_dot(dot)
                (figure_dir / f"{index:02d}-{key}.txt").write_text(content, encoding="utf-8")
            except Exception as exc:
                entry.update({"status": "error", "format": "none", "path": "", "error": f"文本框线图生成失败：{exc}"})
        manifest["figures"].append(entry)
    C.save_json(draft_dir / "图纸清单.json", manifest)
    return manifest
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default=C.ROOT_NAME)
    args = parser.parse_args()
    workdir = Path(args.workdir)
    business_path = workdir / C.DRAFT_NAME / "业务理解.json"
    if not business_path.is_file():
        raise SystemExit(f"缺少 {business_path}")
    business = C.load_json(business_path)
    if business.get("manual_kind") != "design":
        print("SKIP：业务理解不是技术方案文档模式，无需渲染图纸")
        return
    figures_spec = (business.get("design_spec") or {}).get("figures") or {}
    if not figures_spec:
        host, host_warnings = host_figures(workdir)
        for name in sorted(host):
            host_warnings.append(f"图纸原始/ 中插槽 {name} 的图片未对应业务理解声明的图纸，不会采用；请先在 design_spec.figures 声明该插槽或删除文件")
        for note in host_warnings:
            print(f"提示：{note}")
        print("OK：未声明图纸，技术方案文档保留【图预留】占位")
        return
    manifest = render_all(workdir, business)
    for note in manifest.get("host_figure_warnings") or []:
        print(f"提示：{note}")
    for key in manifest.get("unmatched_host_figures") or []:
        print(f"提示：图纸原始/ 中插槽 {key} 的图片未对应业务理解声明的图纸，不会采用；请先在 design_spec.figures 声明该插槽或删除文件")
    for entry in manifest["figures"]:
        if entry.get("status") in ("ok", "text"):
            print(f"OK 图纸 {entry['key']} -> {entry['path']}（{entry.get('backend')}）")
            for note in entry.get("notes") or []:
                print(f"提示：{note}")
        else:
            print(f"ERROR 图纸 {entry['key']}：{entry.get('error')}")
    errors = [entry for entry in manifest["figures"] if entry.get("status") == "error"]
    if errors:
        C.stop_for_user("存在既无法渲染 PNG 也无法生成文本框线图的图纸；请修正 DOT 图源后重跑。")
if __name__ == "__main__":
    main()
