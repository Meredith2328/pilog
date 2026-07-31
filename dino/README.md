# Chrome 断网小恐龙（T-Rex Runner）网页版

一个高度还原 Chrome 断网页面小恐龙游戏的单文件网页版。双击 `index.html` 即可游玩，无需联网、无需依赖。

## 玩法

- `空格` / `↑`：跳跃
- `↓`：下蹲；在空中按下可急速下坠
- `Enter` / `空格` / 点击画面：游戏结束后重新开始
- 触屏：轻点跳跃；游戏结束后点击画面重开
- 游戏结束时双击左上角 `HI` 高分可以清零高分
- 右上角有音效开关（跳跃 / 撞击 / 每 100 分的提示音）

高分保存在浏览器本地存储中。

## 还原内容

- 使用 Chrome 官方精灵图（`100-offline-sprite.png` / `200-offline-sprite.png`，1x/2x 按屏幕自动选择），像素级一致
- 官方音效（`button-press.mp3` / `hit.mp3` / `score-reached.mp3`）
- 与 Chromium 源码一致的游戏逻辑与常量：
  - 小恐龙站立眨眼、奔跑、跳跃、下蹲、撞击姿态与物理（重力 0.6、起跳速度 -10、速度掉落系数 3）
  - 开场 intro 动画（画面从 44px 展开到 600px）、首次跳跃触发开场
  - 小/大仙人掌（可成组）、翼龙（三种高度、扇翅动画、速度 ±0.8、速度 ≥ 8.5 才出现）
  - 与源码一致的精细碰撞盒（含下蹲碰撞盒）
  - 地面滚动、双段地平线纹理、云层视差
  - 夜晚模式：每 700 分进入，持续 12 秒，月亮月相变化 + 星星，画面反色
  - 计分：每 100 分闪烁并播放提示音；`HI` 高分显示
  - 速度从 6 起步，每帧加速 0.001，上限 13
  - 游戏结束面板（GAME OVER 文字 + 动画重开按钮）、失焦自动暂停

## 技术说明

- 纯 HTML + Canvas + 原生 JS，单文件自包含
- 精灵图与音效以 base64 内嵌；高分与音效偏好存于 `localStorage`
- 可选调试：URL 加 `?debug=1` 可显示碰撞检测框

## 重新构建

素材位于 `reference/`，修改 `game.template.html` 后运行：

```powershell
python build.py
```

## 自动化验证

`test_game.py` 用无头 Chromium 跑 26 项检查（开场画面与官方精灵图逐像素对比、
跳跃/下蹲/急坠物理、intro 动画、夜晚模式、翼龙、碰撞与重开、高分存档、
失焦暂停等）；`make_preview.py` 可重新生成 `preview/` 下的效果截图。
运行前先安装浏览器：`python -m playwright install chromium`。

## 素材许可

精灵图与音效来自 Chromium 项目（BSD-3-Clause），
出处：`components/neterror/resources/`（images、sounds、dino_game）。
游戏逻辑还原自 Chromium 开源实现，参考了
[wayou/t-rex-runner](https://github.com/wayou/t-rex-runner)（MIT）的 Canvas 移植版。
