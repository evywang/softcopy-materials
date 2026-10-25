import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
import common as C
from probe_env import officecli_version, pending_install, resolve_officecli
INSTALL_TIMEOUT = 600
def current_state() -> dict[str, Any]:
    executable = resolve_officecli()
    pending = pending_install() if executable is None else None
    version = ""
    error = ""
    if executable:
        version, error = officecli_version(executable)
    if executable and not error and C.officecli_version_ok(version):
        state = "ready"
        action = f"OfficeCLI {version} 已就绪（要求 {C.officecli_version_requirement()}），可进入环境探测与项目分析。"
    elif pending:
        state = "restart_required"
        action = f"OfficeCLI 已安装在 {pending}，但当前进程 PATH 尚未包含该目录；请重启 coding agent 或新开终端后重新运行本脚本确认。"
    elif not executable:
        install = C.OFFICECLI_INSTALL_WIN if os.name == "nt" else C.OFFICECLI_INSTALL_POSIX
        state = "not_installed"
        action = f"未检测到 OfficeCLI；请征得用户同意后运行本脚本并加 --install 执行官方全局安装（{install}）。"
    else:
        state = "version_mismatch"
        action = f"当前版本 {version or '未知'} 不满足版本要求（{C.officecli_version_requirement()}）；可征得用户同意后用 --install 升级到最新版，或手动切换版本后重跑自检，发布页 {C.OFFICECLI_RELEASE}。"
    return {"state": state, "version": version or "not found", "required": C.officecli_version_requirement(), "path": str(executable) if executable else "", "next_action": action}
def install_command() -> list[str]:
    if os.name == "nt":
        shell = shutil.which("powershell") or "powershell"
        return [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", C.OFFICECLI_INSTALL_WIN]
    shell = shutil.which("bash") or "sh"
    return [shell, "-c", C.OFFICECLI_INSTALL_POSIX]
def run_install() -> tuple[bool, str]:
    try:
        done = subprocess.run(install_command(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=INSTALL_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"安装命令执行异常：{exc}"
    tail = [line for line in "\n".join(part for part in (done.stdout, done.stderr) if part).strip().splitlines() if line.strip()]
    detail = tail[-1] if tail else f"exit {done.returncode}"
    return done.returncode == 0, detail
def build_report(want_install: bool) -> dict[str, Any]:
    report: dict[str, Any] = {"before": current_state()}
    if want_install:
        if report["before"]["state"] in ("not_installed", "version_mismatch"):
            ok, detail = run_install()
            report["install"] = {"ok": ok, "detail": detail}
            after = current_state()
            if after["state"] != "ready":
                after["next_action"] = after["next_action"] + " 若安装命令刚执行成功，请重启 coding agent 后重新自检。"
            report["after"] = after
        else:
            report["install"] = {"ok": True, "detail": f"当前状态为 {report['before']['state']}，无需执行安装"}
            report["after"] = report["before"]
    else:
        report["after"] = report["before"]
    return report
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true", help="仅在用户明确同意后传入，执行官方全局安装；不传时只做只读自检")
    parser.add_argument("--out", default="", help="可选结果 JSON 输出路径")
    args = parser.parse_args()
    report = build_report(args.install)
    if args.out:
        C.save_json(Path(args.out), report)
    final = report["after"]
    print(f"OfficeCLI 状态：{final['state']}（{final['version']}，要求 {final['required']}）")
    if args.install and not report["install"]["ok"]:
        print(f"安装输出末行：{report['install']['detail']}")
    print(final["next_action"])
    if final["state"] != "ready":
        C.stop_for_user(final["next_action"])
    print("READY")
if __name__ == "__main__":
    main()
