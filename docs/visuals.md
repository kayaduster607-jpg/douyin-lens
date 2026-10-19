# 视觉材料来源

## 生成封面

- 文件：`assets/cover.png`。
- 方式：内置 `imagegen` 工具生成，再进行一次定向校对。
- 用途：README 项目品牌封面，属于概念视觉，不是运行截图或功能证明。
- 原始生成文件保留，仓库使用选定版本的副本。

### 主生成提示词

```text
Use case: ads-marketing. Asset type: wide GitHub README project cover,
approximately 2.7:1 horizontal composition, premium editorial developer-tool
brand artwork. Create a finished polished banner for DouyinLens, a local Python
Douyin video parser/downloader for noncommercial learning.

Exact text: large title 'DouyinLens'; subtitle '看懂链接背后的视频流';
small kicker 'DOUYIN VIDEO DOWNLOADER'; footer
'Python · Playwright · Local-first'.

Visual concept: a luminous optical glass lens / transparent prism intercepting
a video frame and revealing five thin flowing tracks. Deep ink charcoal
background, restrained ivory typography, vermilion red and a small icy cyan
highlight. Cinematic glass refractions, subtle fine grain, generous negative
space, title on the left, sculptural lens on the right. Original play-shaped
optical motif; no official Douyin/TikTok logo, people, screenshots, interface
mockups, fake stars, performance claims or badges.
```

### 定向校对提示词

```text
Preserve the complete composition, optical glass play prism, lighting,
background, Chinese subtitle, footer, and all other design details.
Correct the large title to exactly 'DouyinLens' (D o u y i n L e n s), with
Douyin ivory and Lens vermilion. Remove all numeric resolution labels on the
far right, leaving flowing video strips and tiny end dots. Do not add text
or change anything else.
```

## 真实运行截图

- `assets/runtime-home.jpg`：启动当前项目后，截图浏览器中的实际首页。
- `assets/runtime-result-ai.jpg`：实际解析 [AI 产品宣传片案例](https://v.douyin.com/M8wgmAEea1k/) 后，截取结果卡片；已替换初次发布时的旧案例图，并使用新文件名避免旧图缓存。
- 使用浏览器原生截图能力，仅选择截图范围，没有改写 DOM、合成作品信息或覆盖清晰度。
- 第三方作品、人物及其作品画面归对应权利人所有，不属于本项目许可授权内容。

截图不应被理解为平台官方背书、每个作品可用或永久访问保证。
