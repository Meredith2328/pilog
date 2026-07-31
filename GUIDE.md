# pilog 使用指南

这是一份写给「人」或「Agent」的最小完整指南。照着做，不需要读任何代码或配置文件，就能完成博客的添加、更新、删除、图片、发布与评论。

## 一分钟上手

```bash
python -m pip install -r requirements.txt
python pilog.py build       # 构建站点
python pilog.py serve --watch   # 本地预览，http://127.0.0.1:8000/
```

预览页面顶部可以切换三种视图：**卡片**（带预览图与标签）、**清单**（文件树）、**图谱**（关系图，可折叠、可单击目录展开）。右上角搜索框支持标题/全文/标签检索（按 `/` 聚焦）。

所有内容都来自 `blogs/` 目录：每篇文章是一个 Markdown 文件，目录结构就是文章层级。你可以在 Obsidian 里直接打开 `blogs/` 来写。

## 写文章

在 `blogs/` 任意子目录新建 `.md` 文件即可，例如 `blogs/posts/tech/我的文章.md`：

```markdown
---
title: 我的文章
date: 2026-08-01
tags: [tech, 随笔]
preview: 一句话介绍，会显示在卡片上（支持 Markdown）。
preview_image: assets/封面.png
pin: false        # true 时卡片视图置顶
highlight: false  # true 时三种视图都加黄色描边
---

# 我的文章

正文从这里开始。
```

字段几乎都可以省略：不写 `title` 取第一个标题，不写 `date` 取文件修改时间，不写 `preview` 自动截取正文，不写 `tags` 用目录路径当标签，`preview_image` 缺省时用正文第一张图。加 `draft: true` 的文章不会出现在站点里。

删除文章 = 删除对应的 `.md` 文件（或 `python pilog.py delete posts/tech/我的文章 --yes`），再构建即可。

## 图片

三种写法都支持：

```markdown
![相对路径](assets/封面.png)
![[Obsidian 全局引用.png]]
![[指定宽度.png|300]]
```

图片可以放 `blogs/assets/`（全局）或文章同目录。批量导入、裁剪、缩放、旋转、加文字、画笔，都在工作台完成：`python pilog.py serve` 后打开 `http://127.0.0.1:8000/manager` 的「文件管理」页——把图片（甚至整个文件夹）拖进去即可，拖入 Markdown 时会自动解析并保留目录结构，缺失的图片引用和文章引用会列出来由你决定保留还是移除。

## 站点设置与导航

打开工作台的「配置」页即可修改标题、副标题、部署路径、社交账号、评论、分页数量等，全部即时写入本地并可撤销。导航栏来自 `blogs/nav.md`，在预览页悬停导航项即可增删改（也可以在 Obsidian 里直接编辑它）。

## 发布到 GitHub

```bash
python pilog.py publish -m "发布说明"
```

它自动完成「构建 → 提交 → 推送」，推送后仓库自带的 GitHub Actions 会部署到 Pages。也可以在工作台「配置 → 发布到 GitHub」填仓库、分支和令牌后点按钮——两条路走的是同一套代码。

令牌：在 GitHub 网页端创建一个 fine-grained PAT（仓库只选博客仓库，权限仅 **Contents: Read and write**，Metadata 会自动带上），粘贴到工作台即可（只存本地，不会进仓库）。

## 评论（giscus）

评论由 GitHub Discussions 驱动，不需要令牌，只需要两步仓库级设置（一次性）：

1. 仓库 Settings 里开启 **Discussions**；
2. 安装 **giscus GitHub App** 到该仓库（https://giscus.app → Install）。

然后在工作台「配置 → 评论」填入 `repo`、`repo_id`、`category`、`category_id`（giscus.app 会给出），保存并重新构建。文章页底部就会出现评论区。

## 批量迁移旧笔记

```bash
python pilog.py import 笔记目录1 笔记目录2 --dir posts/migrated
python pilog.py list                 # 看看导入了什么
python pilog.py publish -m "迁移旧笔记"
```

`import` 支持多个文件或目录（含多层嵌套），自动保留目录结构，图片一并导入，并分析每篇里引用的图片与文章：已存在的标记为 ok，缺失的会提示，可用 `--strip-missing-images` / `--strip-missing-links` 自动清理。批量删除用 `delete` 加 `--yes`。CLI 与工作台走完全相同的数据处理代码，行为一致。

## 常见问题

- **本地能打开、线上路径不对？** 部署到子目录（如 `/pilog`）时，`config.json` 里的 `base_path` 和 `site_url` 必须与线上地址一致（在「配置」页修改即可）。站内所有链接都是构建时按页面计算的相对路径，只要这两个值对，返回首页、资源引用都不会迷路。
- **改了文章没生效？** 需要重新构建：`python pilog.py build`（或开着 `serve --watch` 自动构建，`publish` 也会先构建）。
- **404 页面**：样式与站点一致，5 秒后自动回首页。
- **删了文章但线上还有？** 构建会自动清理已删除文章的页面，重新 `publish` 即可。
