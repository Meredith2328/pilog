#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pilog 一键发布：构建站点并推送到 GitHub 仓库。

用法:
    python publish.py                          # 构建 + 提交 + 推送
    python publish.py -m "发布说明"            # 自定义提交信息
    python publish.py --skip-build             # 跳过重新构建

凭据: config.json 的 publish 段指定仓库与分支；令牌从
`publish.token_file`（默认 .publish-token，已 gitignore）读取，
也可以用环境变量 PILOG_TOKEN 提供。推荐使用 fine-grained PAT，
仅需 Contents: Read and write（Metadata: Read 为强制项）。

本工具只做 add/commit/push，绝不执行任何删除性 git 操作。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def git(args: list, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", "-c", "http.sslBackend=openssl", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=check,
    )


def run_publish(message: str | None = None, build: bool = True) -> dict:
    cfg = load_config()
    pub = cfg.get("publish", {})
    repo = str(pub.get("repo", "")).strip()
    branch = str(pub.get("branch", "main")).strip() or "main"
    token_file = ROOT / str(pub.get("token_file", ".publish-token"))
    token = (
        token_file.read_text(encoding="utf-8").strip()
        if token_file.is_file()
        else (os.environ.get("PILOG_TOKEN") or os.environ.get("GH_TOKEN") or "")
    )

    if "/" not in repo:
        return {"ok": False, "error": f"publish.repo 无效: {repo!r}（应为 owner/repo）"}
    if not token:
        return {
            "ok": False,
            "error": (
                "未找到令牌：请把 fine-grained PAT 写入 "
                f"{token_file}（或用环境变量 PILOG_TOKEN），或在工作台「发布」面板填写"
            ),
        }
    owner, name = repo.split("/", 1)
    # token as username (empty password) works for classic / fine-grained /
    # OAuth tokens alike; never stored in git config
    push_url = f"https://{token}@github.com/{owner}/{name}.git"
    lines: list[str] = []

    if build:
        from build import build_site

        build_site(ROOT / "config.json")
        lines.append("[1/3] 站点构建完成")
    else:
        lines.append("[1/3] 跳过构建")

    status = git(["status", "--porcelain"]).stdout
    local_head = git(["rev-parse", "HEAD"]).stdout.strip()
    try:
        remote_head = git(["ls-remote", push_url, f"refs/heads/{branch}"]).stdout.split("\t")[0].strip()
    except Exception:
        remote_head = ""

    if not status.strip() and remote_head == local_head:
        return {
            "ok": True,
            "output": "\n".join(lines) + "\n[2/3] 没有需要提交或推送的变更",
            "pushed": False,
        }

    if status.strip():
        git(["add", "-A"])
        msg = message or f"site update ({datetime.now():%Y-%m-%d %H:%M})"
        git(["commit", "-m", msg])
        lines.append(f"[2/3] 已提交：{msg}")
    else:
        lines.append("[2/3] 工作区无变更，推送已有本地提交")

    result = git(
        ["push", push_url, f"HEAD:{branch}"],
        check=False,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "error": "推送失败（请检查令牌权限是否包含 Contents: Read and write）",
            "output": "\n".join(lines) + "\n" + result.stdout + result.stderr,
        }
    lines.append(f"[3/3] 已推送到 {owner}/{name} 的 {branch} 分支")
    return {"ok": True, "output": "\n".join(lines), "pushed": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="pilog publish to GitHub")
    parser.add_argument("-m", "--message", default=None, help="提交信息")
    parser.add_argument("--skip-build", action="store_true", help="跳过重新构建")
    args = parser.parse_args()
    result = run_publish(args.message, build=not args.skip_build)
    if result.get("output"):
        print(result["output"])
    if not result.get("ok"):
        print("发布失败:", result.get("error", ""), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
