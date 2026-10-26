import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build import build_site
from publish import publish_directory


def git(*args, cwd):
    return subprocess.check_output(["git", *args], cwd=cwd)


def main():
    scratch = ROOT / ".deploy_test"
    scratch.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="publish-test-", dir=scratch) as temporary:
        directory = Path(temporary)
        output = directory / "site"
        build_site(ROOT / "config.json", out_dir=str(output))
        remote = directory / "remote.git"
        seed = directory / "seed"
        git("init", "--bare", str(remote), cwd=directory)
        git("init", "-b", "pilog", str(seed), cwd=directory)
        git("config", "core.autocrlf", "false", cwd=seed)
        git("config", "user.name", "Publish test", cwd=seed)
        git("config", "user.email", "publish-test@example.invalid", cwd=seed)
        (seed / "README.md").write_bytes((ROOT / "README.md").read_bytes())
        (seed / "docs").mkdir()
        (seed / "docs" / "obsolete.html").write_bytes((output / "index.html").read_bytes())
        git("add", ".", cwd=seed)
        git("commit", "-m", "Initialize deployment repository", cwd=seed)
        git("remote", "add", "origin", str(remote), cwd=seed)
        git("push", "origin", "pilog", cwd=seed)
        source_status = git("status", "--porcelain", cwd=ROOT)

        assert publish_directory(output, str(remote), "pilog", "Publish site")
        assert git("show", "pilog:docs/index.html", cwd=remote) == (output / "index.html").read_bytes()
        assert git("show", "pilog:README.md", cwd=remote) == (ROOT / "README.md").read_bytes()
        tracked = git("ls-tree", "-r", "--name-only", "pilog", cwd=remote).decode().splitlines()
        assert "docs/obsolete.html" not in tracked
        assert "docs/.nojekyll" in tracked
        assert "docs/write/index.html" in tracked
        assert "config.json" not in tracked
        first_commit = git("rev-parse", "pilog", cwd=remote)
        assert not publish_directory(output, str(remote), "pilog", "Publish unchanged site")
        assert git("rev-parse", "pilog", cwd=remote) == first_commit
        assert git("status", "--porcelain", cwd=ROOT) == source_status
        print("[PASS] 实际构建产物发布成功、删除过期页面、保留部署仓库文件、重复发布不创建提交，源码目录保持不变")


if __name__ == "__main__":
    main()
