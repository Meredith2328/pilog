# AGENTS.md

本仓库是 pilog 静态博客：Markdown 内容在 `blogs/`，构建输出在 `docs/`。源码仓库忽略 `docs/`；生成文件由自动部署或手动发布同步至部署仓库。

- 项目介绍：README.md
- API / 配置项文档：posts/toy/pilog-blog（内容保持克制；新增 API 或配置项时直接追加到已有表格行之后）
- 构建：`python pilog.py build`；本地预览：`python pilog.py serve --watch`
- 测试：改动构建或渲染后至少运行 `python tests/test_dom.py` 与 `python tests/test_features.py`
- 提交：`git add -A && git commit`；令牌只放本地 `.publish-token*`，绝不可提交
- 文章发布：提交 Markdown 和资源并推送 `pilog` 分支即可；GitHub Actions 自动构建并把 `docs/` 推到部署仓库 `meredith2328.github.io` 的 `pilog` 分支。日常写作无需本地构建、提交生成文件或运行回归测试；修改生成器和渲染代码时按上面的测试要求验证。
- 用户说「推上去 / 推到远端」= `git push origin pilog`，然后用 `gh run list --workflow deploy.yml` 确认部署成功；`python pilog.py publish` 仅作本地手动兜底
