import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
import common as C
def resolve_officecli() -> Path | None:
    for name in ("officecli", "officecli.exe"):
        hit = shutil.which(name)
        if hit:
            path = Path(hit)
            if path.is_file():
                return path.resolve()
    return None
def pending_windows_install() -> Path | None:
    base = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not base:
        return None
    path = Path(base) / "OfficeCLI" / "officecli.exe"
    return path.resolve() if path.is_file() else None
POSIX_INSTALL_DIRS = ("/usr/local/bin", "/opt/homebrew/bin")
def pending_posix_install() -> Path | None:
    candidates = [Path(base) for base in POSIX_INSTALL_DIRS]
    candidates.extend([Path.home() / ".local" / "bin", Path.home() / "bin"])
    for base in candidates:
        for name in ("officecli", "officecli.exe"):
            candidate = base / name
            if candidate.is_file():
                return candidate.resolve()
    return None
def pending_install() -> Path | None:
    return pending_windows_install() or pending_posix_install()
def officecli_version(executable: Path) -> tuple[str, str]:
    try:
        done = subprocess.run([str(executable), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False, env={**os.environ, "OFFICECLI_SKIP_UPDATE": "1"})
    except (OSError, subprocess.SubprocessError) as exc:
        return "", str(exc)
    raw = "\n".join(part for part in (done.stdout, done.stderr) if part).strip()
    if done.returncode != 0:
        return "", raw or f"exit {done.returncode}"
    match = re.search(r"\d+\.\d+\.\d+", raw)
    return (match.group(0) if match else raw), ""
def npm_global_prefix() -> Path | None:
    npm = shutil.which("npm") or shutil.which("npm.cmd") or shutil.which("npm.exe")
    if not npm:
        return None
    try:
        done = subprocess.run([npm, "prefix", "-g"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False, shell=os.name == "nt" and npm.lower().endswith(".cmd"))
        lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
        if done.returncode == 0 and lines:
            return Path(lines[-1]).expanduser()
    except (OSError, subprocess.SubprocessError):
        return None
    return None
def playwright_cli_state() -> dict[str, Any]:
    candidates: list[Path] = []
    hit = shutil.which("playwright-cli") or shutil.which("playwright-cli.cmd")
    if hit:
        candidates.append(Path(hit))
    prefix = npm_global_prefix()
    if prefix:
        if os.name == "nt":
            candidates.extend([prefix / "playwright-cli.cmd", prefix / "playwright-cli.exe"])
        else:
            candidates.extend([prefix / "bin" / "playwright-cli", prefix / "playwright-cli"])
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            done = subprocess.run([str(candidate), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False, shell=os.name == "nt" and candidate.suffix.lower() == ".cmd")
            raw = "\n".join(part for part in (done.stdout, done.stderr) if part).strip()
            match = re.search(r"\d+\.\d+\.\d+", raw)
            version = match.group(0) if match else raw
            if done.returncode == 0 and version:
                return {"available": True, "executable": str(candidate.resolve()), "version": version}
        except (OSError, subprocess.SubprocessError):
            continue
    return {"available": False, "executable": "", "version": ""}
def host_tools_report(raw: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for name in [item.strip() for item in raw.split(",") if item.strip()]:
        lowered = name.lower()
        hint = "由 agent 判断是否可用于提升材料质量"
        for key, usage in C.HOST_TOOL_HINTS.items():
            if key in lowered:
                hint = usage
                break
        entries.append({"name": name, "suggested_use": hint})
    return entries
def probe(host_tools: str) -> dict[str, Any]:
    executable = resolve_officecli()
    pending = pending_install() if executable is None else None
    version = ""
    error = ""
    if executable:
        version, error = officecli_version(executable)
    ready = bool(executable) and not error and C.officecli_version_ok(version)
    if ready:
        state = "ready"
        action = f"OfficeCLI {version} 已就绪（要求 {C.officecli_version_requirement()}），可进入项目分析。"
    elif pending:
        state = "restart_required"
        action = f"OfficeCLI 已安装在 {pending}，但当前进程 PATH 尚未包含该目录；请重启 coding agent 或新开终端后重新运行环境探测，不要把程序复制进项目目录。"
    elif not executable:
        state = "not_installed"
        install = C.OFFICECLI_INSTALL_WIN if os.name == "nt" else C.OFFICECLI_INSTALL_POSIX
        action = f"请用户确认后执行官方全局安装命令：{install}；安装完成后重启 coding agent 并重新探测。发布页：{C.OFFICECLI_RELEASE}"
    else:
        state = "version_mismatch"
        action = f"当前 OfficeCLI 为 {version or '未知'}，要求 {C.officecli_version_requirement()}；请切换版本，或由用户明确承担风险并在正式生成时传入 --allow-untested-officecli。"
    diagrams = C.detect_diagram_backends()
    chrome = C.find_chrome()
    playwright = playwright_cli_state()
    caps = {
        "markdown_drafts": True,
        "application_txt": True,
        "officecli": bool(executable) and not error,
        "officecli_tested": ready,
        "docx_create": ready,
        "docx_validate": ready,
        "docx_preview": ready,
        "native_page_count": platform.system() == "Windows",
        "diagram_png": diagrams["available"],
        "diagram_backend": diagrams["backend"],
        "diagram_backends": diagrams["backends"],
        "diagram_detail": diagrams["detail"],
        "diagram_text_fallback": True,
        "headless_browser": chrome or "",
        "playwright_cli": playwright,
        "cjk_font": C.cjk_font(),
    }
    return {
        "output_directory": f"当前目录/{C.ROOT_NAME}",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "officecli": {"path": str(executable) if executable else "", "version": version or "not found", "required": C.officecli_version_requirement(), "state": state, "error": error},
        "capabilities": caps,
        "host_tools": host_tools_report(host_tools),
        "requires_user_input": not ready,
        "gate": "environment",
        "next_action": action,
    }
def write_report(out_dir: Path, data: dict[str, Any]) -> None:
    caps = data["capabilities"]
    office = data["officecli"]
    lines = [
        "# 软著环境探测",
        "",
        f"- 输出目录：{data['output_directory']}",
        f"- Python：{data['python']}",
        f"- 平台：{data['platform']}",
        f"- OfficeCLI：{office['version']}（要求 {office['required']}，状态 {office['state']}）",
        f"- OfficeCLI 路径：{office['path'] or '未找到'}",
        f"- 中文字体（图纸渲染）：{caps['cjk_font']}",
        "",
        "## 能力状态",
        "",
        f"- Markdown 草稿与 TXT：可用",
        f"- OfficeCLI DOCX 生成/校验/预览：{'可用' if caps['docx_create'] else '不可用'}",
        f"- Word 原生页数：{'可能可用' if caps['native_page_count'] else '需在 Word/WPS 人工复核'}",
        f"- 图纸 PNG 渲染：{'可用（' + caps['diagram_backend'] + '）' if caps['diagram_png'] else '不可用'}（{caps['diagram_detail']}）",
        f"- 图纸中文文本框线图：始终可用（无 graphviz 时的兜底，Word 中直接可见）",
        f"- 宿主架构图技能产图（如 archify）：图片放入 图纸原始/（文件名 01-插槽名.png，插槽名 architecture/key_N/function_N），figures.py 优先采用并登记图纸清单",
        f"- 无头浏览器（HTML 转图）：{caps['headless_browser'] or '未找到'}",
        f"- Playwright CLI：{caps['playwright_cli']['version'] or '未找到'}",
        "",
        "## 宿主 agent 技能与工具",
        "",
    ]
    if data["host_tools"]:
        lines.extend(f"- {item['name']}：{item['suggested_use']}" for item in data["host_tools"])
    else:
        lines.append("- 未登记。请 agent 在启动时枚举自身可用的技能与工具并通过 --host-tools 传入。")
    lines.extend(["", "## 用户选择", "", data["next_action"], ""])
    if data["requires_user_input"]:
        lines.extend(["OfficeCLI 缺失、待重启或版本不匹配时必须停止，不得静默安装、不得伪造成 DOCX。", "", "```text", "STOP_FOR_USER", f"NEXT_ACTION: {data['next_action']}", "```", ""])
    (out_dir / "环境探测.md").write_text("\n".join(lines), encoding="utf-8")
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=C.ROOT_NAME)
    parser.add_argument("--host-tools", default="", help="逗号分隔的宿主 agent 技能/工具名称")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        raise SystemExit("需要 Python 3.10 及以上版本")
    out_dir = C.ensure_dir(Path(args.out_dir))
    data = probe(args.host_tools)
    C.save_json(out_dir / "环境探测.json", data)
    write_report(out_dir, data)
    print(f"OK 环境探测：{out_dir}")
    print(f"OfficeCLI: {data['officecli']['state']} ({data['officecli']['version']})")
    print(f"图纸渲染: {data['capabilities']['diagram_backend']}")
    if data["requires_user_input"]:
        C.stop_for_user(data["next_action"])
if __name__ == "__main__":
    main()
