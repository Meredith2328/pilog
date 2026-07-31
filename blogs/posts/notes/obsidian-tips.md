---
title: 在 Obsidian 中高效写作
date: 2026-07-20
tags: [obsidian, workflow]
---

# 在 Obsidian 中高效写作

把 `blogs/` 目录直接作为 Obsidian 仓库打开，就能获得双向链接、图谱视图等本地能力。

## 几个推荐设置

- 新建文件默认位置：当前文件夹；
- 附件默认保存位置：`assets`；
- Wiki 链接格式：最短路径。

这样拖进来的图片会自动落到 `blogs/assets/`，写作时用 `![[图片名.png]]` 引用，构建时 pilog 会原样解析。

博客框架本身的细节，可以看 [[pixel-blog]]。

## 预览字段

在 front matter 里可以手动指定 `preview`，卡片视图会优先展示它（支持 Markdown 语法）；不指定时则自动截取正文。

```yaml
---
title: 我的文章
date: 2026-07-01
tags: [随笔]
preview: 一句话介绍这篇文章。
---
```
