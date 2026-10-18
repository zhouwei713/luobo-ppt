# 品牌套件：按企业 VI 手册做 PPT

企业 VI 手册把颜色、字体、logo 和它的用法都定死了。萝卜 PPT 平时的风格是"像参考图"，有手册时要变成"守规矩"：颜色只用手册里的，logo 按手册放，手册说不许的不做。

## 流程

```bash
python3 $S/brand_kit.py pages 手册.pdf $W          # 拆页，列出文字层里的色值
# 看 $W/brand/pages/ 的每一页，填 brand.draft.json，另存为 $W/brand.json
python3 $S/brand_kit.py crop $W $W/brand/pages/p004.png 335 650 600 1022 logo_vertical --clear
python3 $S/brand_kit.py plate $W brand/logo_vertical.png logo_plate   # 深底用的白底版
python3 $S/brand_kit.py check $W                   # 字段、文件、对比度，色值回手册页面上找
python3 $S/brand_kit.py apply $W                   # 写 style.json 和 brand/brand_card.png
```

`crop` 的坐标可以是像素，也可以是 0 到 1 的比例。`--clear` 把贴着边的白色变透明，形象内部的白色不动。`--trim-bottom 0.15` 切掉底部（比如形象脚下的投影托盘）。

## brand.json

```json
{"name": "周萝卜",
 "colors": [
  {"name": "周萝卜蓝", "hex": "14306B", "role": "primary"},
  {"name": "亮蓝", "hex": "1FA3F5", "role": "secondary"},
  {"name": "活力橙", "hex": "F97316", "role": "accent"},
  {"name": "叶冠绿", "hex": "1FA84F", "role": "extra"},
  {"name": "浅灰", "hex": "F4F6FA", "role": "background"},
  {"name": "深灰文字", "hex": "1F2937", "role": "text"}],
 "allow": ["FFFFFF"],
 "tints": false,
 "fonts": {"heading_ea": "Source Han Sans SC Heavy", "body_ea": "Source Han Sans SC",
           "heading_latin": "Noto Sans SC", "body_latin": "Noto Sans SC"},
 "logos": [
  {"file": "brand/logo_horizontal.png", "kind": "horizontal", "on": "light"},
  {"file": "brand/logo_vertical.png", "kind": "vertical", "on": "light"},
  {"file": "brand/logo_plate.png", "kind": "vertical", "on": "dark"}],
 "logo": {"clear_space": 0.25, "height": 0.55, "min_height": 0.3, "content": "top-right",
          "cover": "vertical", "closing": "vertical"},
 "signature": {"title_bar": "accent", "outline": false, "radius": 0.12},
 "art": ["brand/ip_0.png", "brand/ip_1.png"],
 "forbid": {"gradients": true, "shadows": true},
 "rules": ["活力橙只做强调", "logo 不压任何元素"]}
```

| 字段 | 说明 |
|---|---|
| `colors[].hex` | 抄手册上印的数字。手册同时给了 HEX 和 RGB 的，两个对一下 |
| `colors[].role` | primary 主色；secondary 辅助色；accent 强调色；extra 其他点缀色；text 正文色；background 浅底色（卡片底）；neutral 其他中性色。图表系列按 primary、secondary、accent、extra 的顺序取色 |
| `allow` | 手册没列但允许出现的颜色，最常见的是白 FFFFFF。手册把白列进色板了就不用写 |
| `tints` | 手册允许用主色的浅色调时写 true。默认 false，所有颜色都吸附到色板上 |
| `page` | 页面底色，默认白（白在色板或 allow 里时），否则用 background |
| `fonts` | 中文标题、中文正文、英文标题、英文正文。写字体的正式名称，Windows 上装好以后在 PowerPoint 字体列表里看到的那个名字 |
| `logos[]` | 每个 logo 文件。`kind` 写 horizontal（横版）或 vertical（竖版、组合版）；`on` 写 light（放浅底）、dark（放深底，反白版）或 any |
| `logo.clear_space` | 安全空间，按 logo 高度的倍数。手册写"四周留字高 X"或"直径 1/4"时换算成这个比例 |
| `logo.height` | 内容页 logo 的高度（英寸），封面和结尾页会放大 |
| `logo.min_height` | 手册的最小尺寸换成英寸，屏幕 32px 约 0.33 英寸 |
| `logo.content` | 内容页放哪：top-right、top-left、bottom-right、bottom-left、none，或者 header。很多手册内页不放 logo 图形，顶上是一行小字页眉（品牌名在左、栏目名在右、下面一条细线），这种就写 header，图形 logo 只放封面和封底 |
| `logo.header_text` | header 模式左边那行字，比如"周萝卜 ZHOULUOBO"，不写就用 name。右边自动放章节名，没有章节就放这一页的 kicker |
| `logo.cover` / `logo.closing` | 封面、结尾页用哪种 logo：vertical、horizontal |
| `signature.title_bar` | 标题左侧的竖条，写颜色（accent、primary 或色值），手册没有就不写 |
| `signature.title_mark` | 平时标题下方的两段短横，手册没有就保持 false |
| `signature.outline` | true 时卡片是粗描边加硬投影（贴纸感），`outline_w` 描边粗细（磅），`hard_shadow` 投影偏移（英寸） |
| `signature.radius` | 卡片圆角（英寸） |
| `art` | IP 形象、表情贴纸、辅助图形。可以只写文件名，也可以写 {file, mood}，mood 是这个动作的意思，比如 wave、love、question、like |
| `art_max` | 内容页最多出现几次形象，默认 4。封面、章节页、结尾页不算 |
| `forbid.gradients` | 不许渐变（默认 true）：背景和结尾页都是纯色 |
| `forbid.shadows` | 不许阴影（默认 true）：卡片是平的。outline 风格的硬投影不受影响 |
| `rules` | 手册里其他的规矩，原话写进来，排版时遵守 |

## 自动做的事

- **颜色**：风格需要的十几个颜色位（主色、强调色、正文、浅灰小字、标签色……）全部从色板里选。用作文字的只选在页面上读得清的颜色。版式里用到的"主色的浅色"会吸附到最近的品牌色，浅底上的大片卡片用手册的浅灰。手改 style.json 填了色板以外的颜色，会吸附到最近的品牌色，并在 build 时提示。
- **浅色主色**：主色是橙、黄这类在白底上读不清的颜色时，它照样当主色用在色块、竖条、图表和步骤圆点上，文字、小标签和大数字按 primary、secondary、accent 的顺序退到第一个读得清的品牌色，结尾页这类深色底用最深的品牌色
- **图表**：系列按手册顺序用品牌色，不用浅色调；突出某一根柱子时用强调色；读不清的颜色（白底上的亮黄）排到最后，线尾数字读不清时换成正文色；描边风格下网格线用浅灰或不画。
- **形象**：只出现在封面、章节页、结尾页，以及 deck.json 里写了 `"art": true` 或 `"art": "question"` 的页（按 mood 挑对应的动作），整张放不裁切，不压内容。数据页、列表页默认不放，写 `"art": false` 也能关掉。每页都放一个形象等于没放，观众第三页就不看了
- **logo**：每页按 `logo.content` 放，安全空间里有插画就把插画往下挪，有文字就换一个角。底色深就换反白版，没有反白版就用 `plate` 做的白底版。
- **背景**：纯色，不画装饰斑点和渐变。

## 品牌检查（qa_check.py）

| 检查 | 级别 |
|---|---|
| brand-color 用了色板（加 allow）以外的颜色，列出颜色和页码 | ERROR |
| brand-gradient 手册不许渐变，页面有渐变（背景图上下颜色不同也算） | ERROR |
| brand-logo logo 安全空间里有别的东西，或 logo 小于最小尺寸 | ERROR |
| brand-logo 某页没有 logo（不要的写 `"logo": false`） | WARN |
| brand-font 这台电脑没装手册字体 | WARN |

## 手册本身的问题

- **整页图片导出的 PDF** 没有文字层，色值、字体名都要看图读，读完一定跑 `check`，它会去页面上找每个色值。
- **logo 只有手册里的小图**：截出来常常只有两三百像素，投影放大会糊。交付时提醒用户要一份原始 logo 文件（PNG 透明底或 SVG），换进 `brand/` 再跑一遍。
- **字体没装**：PowerPoint 会换成别的字体，品牌部一眼能看出来。装上字体再看预览，发给别人前用"文件 → 选项 → 保存 → 将字体嵌入文件"。
