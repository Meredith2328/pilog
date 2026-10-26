from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def git(args: list[str], cwd: Path = ROOT, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env,
        capture_output=True, text=True, encoding="utf-8", check=True,
    )


def publish_directory(site: Path, repository: str, branch: str, message: str, token: str = "") -> bool:
    site = site.resolve()
    if not (site / "index.html").is_file():
        raise FileNotFoundError(f"构建产物缺少 index.html：{site}")
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if token:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
        authorization = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env["GIT_CONFIG_COUNT"] = str(count + 1)
        env[f"GIT_CONFIG_KEY_{count}"] = "http.https://github.com/.extraheader"
        env[f"GIT_CONFIG_VALUE_{count}"] = f"AUTHORIZATION: basic {authorization}"

    scratch = ROOT / ".deploy_test"
    scratch.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="publish-", dir=scratch) as temporary:
        checkout = Path(temporary) / "repository"
        git(["clone", "--depth", "1", "--single-branch", "--branch", branch, repository, str(checkout)], env=env)
        git(["config", "core.autocrlf", "false"], cwd=checkout)
        destination = checkout / "docs"
        if destination.is_symlink():
            raise ValueError("部署仓库的 docs 不能是符号链接")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(site, destination)
        git(["add", "--force", "--all", "--", "docs"], cwd=checkout)
        if not git(["diff", "--cached", "--name-only"], cwd=checkout).stdout.strip():
            return False
        for setting in ("user.name", "user.email"):
            value = git(["config", "--get", setting]).stdout.strip()
            git(["config", setting, value], cwd=checkout)
        git(["commit", "-m", message], cwd=checkout)
        git(["push", "origin", f"HEAD:{branch}"], cwd=checkout, env=env)
    return True


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
        return {"ok": False, "error": "publish.repo 应为 owner/repo"}
    if not token:
        return {"ok": False, "error": f"请在 {token_file} 或 PILOG_TOKEN 环境变量中配置令牌"}
    if build:
        from build import build_site

        build_site(ROOT / "config.json")
    site = ROOT / cfg.get("site", {}).get("out_dir", "docs")
    pushed = publish_directory(
        site, f"https://github.com/{repo}.git", branch,
        message or f"site update ({datetime.now():%Y-%m-%d %H:%M})", token,
    )
    output = f"已发布到 {repo} 的 {branch} 分支" if pushed else "生成内容没有变化"
    return {"ok": True, "output": output, "pushed": pushed}


def main() -> None:
    parser = argparse.ArgumentParser(description="构建博客并同步至部署仓库")
    parser.add_argument("-m", "--message", default=None, help="部署提交信息")
    parser.add_argument("--skip-build", action="store_true", help="使用已有构建产物")
    args = parser.parse_args()
    result = run_publish(args.message, build=not args.skip_build)
    if result.get("output"):
        print(result["output"])
    if not result.get("ok"):
        print("发布失败:", result.get("error", ""), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
