---
title: 用 pilog 搭建像素风博客
date: 2026-07-30
tags: [pilog, meta]
pin: true
preview: 一套轻量的静态博客框架：读取 `blogs/` 目录下的 Markdown，生成卡片 / 清单 / 图谱三种视图，主题复刻 Chrome 断网页的像素美学。
preview_image: assets/cover-pixel.png
---

# 用 pilog 搭建像素风博客

**pilog** 是一个轻量的静态博客生成器：你只管在 Obsidian 里写 Markdown，构建脚本会把整个 `blogs/` 目录变成带三种视图的静态站点。

## 三种视图

页面顶端可以切换三种视图，它们描述的是同一棵内容树：

1. **卡片视图** — 每条博客以卡片形式预览，右侧是缩放后的预览图；
2. **清单视图** — 以类似 Windows 文件树的层级结构展示全部博客；
3. **图谱视图** — 以关系图谱展示目录层级与文章之间的引用关系。

![像素封面](assets/cover-pixel.png)

也支持 Obsidian 的全局引用与宽度控制：

![[cover-pixel.png|240]]

## 代码高亮

构建时使用 Pygments 服务端高亮，支持几乎所有常见语言：

```python
def hello(name: str) -> str:
    """A tiny pixel greeting."""
    return f"Hello, {name}!"
```

```javascript
const views = ['card', 'tree', 'graph'];
document.querySelector('.view-switch').dataset.active = views[0];
```

```bash
conda activate moni
python build.py
python serve.py --watch
```

## Obsidian 语法

图片既支持 Markdown 原生语法，也支持 Obsidian 的 `![[图片名]]` 形式，构建时会自动解析并复制到站点。文章之间的链接同样支持 `[[另一篇文章]]` 写法。

更多语法细节见 [Markdown 速查表](markdown-cheatsheet.md)。
