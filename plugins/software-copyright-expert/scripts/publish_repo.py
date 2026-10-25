#!/usr/bin/env python3
"""把专家 + 市场清单组装成 Git 仓库内容并推送到 GitHub。

仓库布局（既是可安装的市场，也是源码仓库）：
    .codebuddy-plugin/marketplace.json   市场清单（必须在根，CLI 只在这里找）
    plugins/<插件名>/                     专家本体
    README.md / LICENSE / docs/           仓库说明与文档

与 build_marketplace.py 的分工：
    build_marketplace.py  → 产出 zip 分发包
    publish_repo.py       → 产出 git 仓库（可被 /plugin marketplace add owner/repo 添加）

用法：
    python scripts/publish_repo.py \
        --marketplace-dir <市场源目录> \
        --expert-dir <专家目录> \
        --repo-dir <仓库工作目录> \
        [--repo <owner/name>] [--push]
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".idea", ".vscode"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
SKIP_SUFFIX = (".pyc", ".pyo", ".map", ".log")


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(
        *SKIP_DIRS, *SKIP_FILES, *[f"*{s}" for s in SKIP_SUFFIX]))


def run(args: list[str], cwd: Path) -> str:
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise SystemExit(f"命令失败：{' '.join(args)}\n{done.stdout}\n{done.stderr}")
    return done.stdout.strip()


def assemble(repo_dir: Path, marketplace_dir: Path, expert_dirs: list[Path],
             docs_dir: Path | None) -> None:
    """组装仓库内容（不动 .git）。"""
    if repo_dir.exists():
        for child in repo_dir.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    repo_dir.mkdir(parents=True, exist_ok=True)

    # 市场清单（富元数据权威副本）
    manifest_src = marketplace_dir / ".codebuddy-plugin" / "marketplace.json"
    if not manifest_src.is_file():
        raise SystemExit(f"缺少市场清单：{manifest_src}")
    manifest_dest = repo_dir / ".codebuddy-plugin"
    manifest_dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_src, manifest_dest / "marketplace.json")
    # 仓库首页 + 市场说明
    if (marketplace_dir / "README.md").is_file():
        shutil.copy2(marketplace_dir / "README.md", repo_dir / "README.md")
    if (marketplace_dir / "MARKETPLACE.md").is_file():
        shutil.copy2(marketplace_dir / "MARKETPLACE.md", repo_dir / "MARKETPLACE.md")

    # 专家本体
    plugins_dir = repo_dir / "plugins"
    plugins_dir.mkdir(exist_ok=True)
    for expert_dir in expert_dirs:
        if not expert_dir.is_dir():
            raise SystemExit(f"专家目录不存在：{expert_dir}")
        plugin_json = None
        for meta in (".codebuddy-plugin", ".workbuddy-plugin"):
            candidate = expert_dir / meta / "plugin.json"
            if candidate.is_file():
                plugin_json = candidate
                break
        if plugin_json is None:
            raise SystemExit(f"专家目录缺少 plugin.json：{expert_dir}")
        import json
        name = json.loads(plugin_json.read_text(encoding="utf-8")).get("name") or expert_dir.name
        copy_tree(expert_dir, plugins_dir / name)

    # 文档与许可
    if docs_dir and docs_dir.is_dir():
        docs_dest = repo_dir / "docs"
        docs_dest.mkdir(exist_ok=True)
        for item in docs_dir.glob("*.md"):
            shutil.copy2(item, docs_dest / item.name)
    license_src = expert_dirs[0] / "LICENSE"
    if license_src.is_file():
        shutil.copy2(license_src, repo_dir / "LICENSE")
    elif (expert_dirs[0] / "skills").is_dir():
        for skill_license in (expert_dirs[0] / "skills").glob("*/LICENSE"):
            shutil.copy2(skill_license, repo_dir / "LICENSE")
            break
    # NOTICE：来源声明与第三方组件（MIT 要求保留原项目著作权声明）
    notice_src = marketplace_dir / "NOTICE"
    if notice_src.is_file():
        shutil.copy2(notice_src, repo_dir / "NOTICE")
    # .gitattributes：统一 LF，避免 Windows 检出的 CRLF 影响脚本
    attributes_src = marketplace_dir / ".gitattributes"
    if attributes_src.is_file():
        shutil.copy2(attributes_src, repo_dir / ".gitattributes")


def git_publish(repo_dir: Path, repo: str, push: bool) -> None:
    if not (repo_dir / ".git").exists():
        run(["git", "init", "-b", "main"], repo_dir)
    run(["git", "add", "-A"], repo_dir)
    status = run(["git", "status", "--porcelain"], repo_dir)
    if status:
        run(["git", "commit", "-m", "feat: 发布软著材料专家与市场清单\n\n"
                                    "- 新增 .codebuddy-plugin/marketplace.json，可直接作为插件市场添加\n"
                                    "- 新增 plugins/software-copyright-expert 专家包\n"
                                    "- 新增 docs 与 LICENSE"], repo_dir)
    else:
        print("（无变更，跳过提交）")
    if push:
        run(["git", "remote", "remove", "origin"], repo_dir) if _has_origin(repo_dir) else None
        run(["git", "remote", "add", "origin", f"https://github.com/{repo}.git"], repo_dir)
        run(["git", "push", "-u", "origin", "main"], repo_dir)


def _has_origin(repo_dir: Path) -> bool:
    done = subprocess.run(["git", "remote"], cwd=repo_dir, capture_output=True, text=True)
    return "origin" in done.stdout.split()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marketplace-dir", required=True)
    parser.add_argument("--expert-dir", action="append", default=[], required=True)
    parser.add_argument("--repo-dir", required=True, help="仓库工作目录")
    parser.add_argument("--docs-dir", default="", help="额外文档目录（*.md 复制到 docs/）")
    parser.add_argument("--repo", default="", help="owner/name，用于设置 origin")
    parser.add_argument("--push", action="store_true", help="推送到 GitHub")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).expanduser().resolve()
    marketplace_dir = Path(args.marketplace_dir).expanduser().resolve()
    expert_dirs = [Path(item).expanduser().resolve() for item in args.expert_dir]
    docs_dir = Path(args.docs_dir).expanduser().resolve() if args.docs_dir else None

    assemble(repo_dir, marketplace_dir, expert_dirs, docs_dir)
    print(f"OK 仓库内容已组装：{repo_dir}")
    if args.repo and args.push:
        git_publish(repo_dir, args.repo, True)
        print(f"OK 已推送：https://github.com/{args.repo}")
    elif args.repo:
        print(f"下一步：cd {repo_dir} && git remote add origin https://github.com/{args.repo}.git && git push -u origin main")


if __name__ == "__main__":
    main()
