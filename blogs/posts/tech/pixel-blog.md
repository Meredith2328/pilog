---
title: 用 pilog 搭建像素风博客
date: 2026-07-30
tags: [pilog, meta]
highlight: true
preview: 一套个人自制的轻量静态博客框架：读取 `blogs/` 目录下的 Markdown，生成卡片 / 清单 / 图谱三种视图，主题复刻 Chrome 断网页的像素美学。
preview_image: assets/cover-pixel.png
---

# 用 pilog 搭建像素风博客

**pilog** 是个人自制的轻量静态博客生成器：你只管在 Obsidian 里写 Markdown，构建脚本会把整个 `blogs/` 目录变成带三种视图的静态站点。它没有数据库、没有后端，只有一个个 Markdown 文件和一个负责构建的脚本。

## 三种视图

页面顶端可以切换三种视图，它们描述的是同一棵内容树：

1. **卡片视图** — 每条博客以卡片形式预览，右侧是缩放后的预览图；
2. **清单视图** — 以类似 Windows 文件树的层级结构展示全部博客；
3. **图谱视图** — 以关系图谱展示目录层级与文章之间的引用关系。

![像素封面](assets/cover-pixel.png)

也支持 Obsidian 的全局引用与宽度控制：

![[cover-pixel.png|240]]

## 用 Obsidian 写作

把 `blogs/` 目录直接作为 Obsidian 仓库打开，就能获得双向链接、图谱视图等本地能力。几个推荐设置：

- 新建文件默认位置：当前文件夹；
- 附件默认保存位置：`assets`；
- Wiki 链接格式：最短路径。

这样拖进来的图片会自动落到 `blogs/assets/`，写作时用 `![[图片名.png]]` 引用，构建时 pilog 会原样解析；文章之间的链接同样支持 `[[另一篇文章]]` 写法。

### 预览字段

在 front matter 里可以手动指定 `preview`，卡片视图会优先展示它（支持 Markdown 语法）；不指定时则自动截取正文。

```yaml
---
title: 我的文章
date: 2026-07-01
tags: [随笔]
preview: 一句话介绍这篇文章。
---
```

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
python -m pip install -r requirements.txt
python build.py
python serve.py --watch
```

## 更多语法

删除线：~~这一段会被划掉~~；LaTeX 行内公式 $E = mc^2$，整行公式即使写在行内也会独立成块：$$x^2 + y^2 = z^2$$ 公式后面还可以继续写文字。图片可以混用 Markdown 相对路径、`![[图片名.png]]` 以及带宽度写法。博客自身的全部功能，也都来自这套简单的 Markdown 约定。
