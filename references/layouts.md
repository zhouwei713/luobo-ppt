# 版式库

所有版式画在 13.333 × 7.5 英寸的画布上，原稿是其他 16:9 尺寸时整体等比缩放。

每页都有公共部分（由 build_deck.py 自动加）。

- 背景图：内容页 `bg_content`，封面 `bg_cover`，结尾 `bg_closing`
- 系列页眉：`meta.series` 居中加两片叶子，只在内容页出现，`style.decor.header=false` 关闭
- 底部：有 `takeaway` 时是一条带图标的半透明胶囊，右侧放页脚和页码；没有时左下页脚、右下页码
- 标题：左上，最大 36pt，下方一短一点两段小横条（`style.decor.title_mark=false` 关闭）

内容区在 y 2.15 到 6.05 英寸之间，左右边距 0.8 英寸。

## 版式一览

| 版式 | 适用 | 用到的字段 | 插画位 |
|---|---|---|---|
| `cover_hero` | 封面 | kicker, title, subtitle(带笔刷高亮), body, items(整行议程卡片), takeaway | 右侧大图 |
| `statement_number` | 一个核心数字加一句话 | number(背后垫笔刷), lines, body | 右侧大图 |
| `rows_side` | 名词解释、三到四个并列概念 | side, items{title,text,emphasis} | 左下侧图 |
| `stats_row` | 两到四个数据 | items{value,label}, takeaway | 右上角小图 |
| `media_text` | 示意图加解释 | diagram 或 image, point, body, callout | 右上角小图 |
| `side_cards` | 步骤、做法、一重一轻两张卡 | side, items{title?,text,emphasis} | 左下侧图 |
| `quote_cards` | 例句、提示词、原话 | lead, items{text} | 右上角小图 |
| `statement_hero` | 一句主张加说明 | headline(带笔刷), body, pill | 右侧大图 |
| `cards_quote` | 风险、坑、反例加一句总结 | items{title,text}, quote_lines | 右侧上方图 |
| `list_icons` | 兜底，任何列表，条目长也装得下 | items{title?,text} | 右上角小图 |
| `grid_cards` | 三到六个短要点，两列或三列大卡片 | items{title?,text,emphasis} | 右上角小图 |
| `closing` | 结尾页，默认深色 | kicker, headline, body, cta | 顶部居中图 |
| `steps_flow` | 有先后的两到五步，横排编号 | items{title,text} | 右上角小图 |
| `compare_split` | 两方对比，右边是推荐的一方 | left, right, vs_label | 无 |
| `cycle` | 循环往复的环节 | center, items{title,text} | 无 |
| `pyramid` | 层级，最上面最窄 | items{title,text} | 无 |
| `section` | 章节分隔，没插画时右侧铺超大淡色章节号 | number, kicker, title, subtitle | 右侧大图 |
| `toc` | 目录，左侧大字、右侧章节竖排，三到六章 | title, kicker, items{title,text} | 无 |
| `cover_type` | 大字封面，标题就是画面，没有插画 | kicker, title(可带 **强调词**), subtitle, body, items | 无 |
| `question` | 整页一个大问句，用来转场或抛悬念 | kicker, question, body | 无 |
| `cover_center` | 居中封面，配合底部风景（背景装饰 scene） | kicker, title, subtitle(黄色笔刷), body, takeaway | 背景里的风景 |
| `rank_grid` | TOP 榜单，最多 10 条，两行排开，下面可加"核心发现" | items{num,title,text}, findings{title,items} | 无 |
| `explain` | 讲解页，标签、正文、居中公式条、带色点的判断规则、小注，一到四栏，左边可放示意图；没有结论条时内容在页面里垂直居中 | image, blocks 或 columns[{blocks}], boxed, takeaway | 无 |
| `shot_notes` | 一张大截图配编号说明，横屏截图占六成宽，竖屏手机截图按高度缩窄；条目写了 `at` 就在截图上对应位置打编号点 | image, items{title?,text,at?:[x,y]}, caption, frame | 无 |
| `shot_stack` | 两到四张截图排成一行，按各自宽高比分配宽度；默认当作步骤，自动编号、中间加箭头，`flow: false` 变成并列对照 | items{image,title?,text?,num?}, flow, frame | 无 |
| `big_quote` | 整页一段引文，巨大引号做装饰 | quote, by, note | 无 |
| `toc_row` | 目录，章节横排一行，三到五章 | title, kicker, items{title,text} | 无 |
| `timeline` | 按时间排的三到六个里程碑 | items{date,title,text,emphasis} | 无 |
| `funnel` | 逐层转化或筛选，三到五层 | items{label,value,text} | 无 |
| `hub` | 一个中心连着三到六个部分 | center{title}, items{title,text} | 无 |
| `matrix` | 两个维度切出四个象限 | x_axis, y_axis, quadrants | 无 |
| `table` | 原生表格，可高亮一列 | columns, rows, highlight_col, note | 无 |
| `chart` | 原生图表配一到三条结论 | chart, insights, source | 无 |
| `framework` | SWOT、PEST、波特五力、商业画布 | framework{kind,blocks,labels} | 无 |
| `free` | 特殊页面，手工摆放 | deck 或 plan 里的 elements | 自定 |

## 选版式的经验

- 相邻两页不要用同一个版式，同类内容（比如连续两页 side_cards）可以通过插画和图标拉开差异
- 内容多的页先考虑 `list_icons`，它的行高会自动压缩；要点少而短时用 `grid_cards`，画面更饱满（plan_deck 对 list 页型会自动这样选）
- 没有 side 也没有插画时，`rows_side` 的卡片会自动铺满整行；封面内容少时文字块会自动垂直居中
- 原稿本来就是"左侧引导 + 右侧卡片"的结构时，用 `rows_side` 或 `side_cards`，信息关系最不容易错
- 一页只有一句话的，用 `statement_hero` 或 `statement_number`，配大插画撑住画面
- `stats_row` 数字超过四个时改用 `list_icons` 或拆成 free
- 数字之间要比大小、看趋势、看占比时用 `chart`，只是罗列几个亮眼数字时用 `stats_row`
- 表格和图表都是原生对象，用户能在 PowerPoint 里直接改数据；图表的数据一改，右侧 insights 里的结论也得跟着重写
- 漏斗的 value 全是数字时，每层宽度按数值比例画；有一个不是数字就改成等差收窄
- 新加的几个版式都没有插画位，画面靠结构撑，插画预算留给封面和 statement 类页面
- 目录页和章节页的编号样式由风格的 `decor.number_style` 统一决定，两处永远一致；目录不写 items 时自动从章节页取，改了章节标题目录会跟着变
- 八页以上、分了章节的稿子，封面后面放一页目录，结尾回到封面的视觉，整套才完整
- 连续几页卡片之后，插一页 `question` 或 `big_quote` 让节奏松一下，五维自评里"节奏"一项会看这个
- 靠字撑画面的风格（钴蓝字体、墨水杂志、硬边网格）封面默认用 `cover_type`，由预设的 `prefer_layouts` 决定

## 风格对版式的影响

同一个版式，在不同风格下会自动换几处细节，不用改 deck.json。

| style.json 字段 | 取值 | 效果 |
|---|---|---|
| `shape.depth` | flat / ring / whisper / shadow | 卡片只有底色、描一条细边、极淡的晕影，或者经典投影 |
| `decor.bullet` | icon / dash / number | 列表每条前面是图标、强调色短横，还是 01、02 编号；大数字、按钮这类页面的图标直接去掉 |
| `decor.emphasis` | color / serif | 标题里的 **强调词** 换色，或者换色的同时换成宋体 |
| `decor.chrome` | standard / editorial | 顶部居中系列名加底部胶囊条，或者杂志式的顶部信息条、细线和右下角页码 |
| `decor.number_style` | plain / badge / ring / block / diamond | 目录和章节页的编号样子 |
| `type_scale` | 字号列表或 false | 全篇字号只用这组阶梯，排版时直接按阶梯试字号，默认约 1.2 倍一级 |

build_deck 会把每个算出来的字号向下吸附到最近的一级，所以同一类文字在不同页上大小一致，全篇通常只剩六到十种字号。

## 每个版式装得下多少

每个版式都标了容量，按"阅读单位"计，一个汉字或一个英文单词算 1。超出容量时，plan_deck 会自动换成同页型的下一个版式或兜底的 `list_icons`，并在 design_spec.md 的"容量提醒"里列出来，outline_check 也会提前报"装不下"。

```bash
python3 $S/layout_info.py              # 所有版式、对应页型、用途
python3 $S/layout_info.py funnel        # 单个版式的容量和 deck.json 示例
python3 $S/layout_info.py --check $W    # 逐页检查 deck.json 超没超容量
```

写 deck.json 时拿不准就先查一下，比出图后再拆页省事。容量数字在 `scripts/capacity.py`，调整版式尺寸后记得同步改这里。

## plan.json 里每页可调的键

```json
{"n": 3, "layout": "rows_side", "hero": "hero_03",
 "icons": ["smartphone", "cpu", "message-circle"],
 "takeaway_icon": "globe", "lead_icon": "message-circle",
 "info": {"header": false}}
```

`icons` 按 items 顺序对应；没有 items 的页面，第一个图标用于 callout、pill 或 cta。
`info.header=false` 可以单页关掉系列页眉。

## free 版式的元素格式

```json
{"n": 7, "layout": "free", "master": "content", "elements": [
  {"t": "text", "x": 0.8, "y": 0.95, "w": 8, "h": 0.8, "text": "标题", "size": 36, "color": "text",
   "bold": true, "font": "heading", "align": "l", "valign": "m", "ls": 1.2, "spc": 0},
  {"t": "rect", "x": 0.8, "y": 2.2, "w": 5, "h": 1.2, "fill": "surface", "alpha": 0.88,
   "radius": 0.18, "line": "line", "shadow": true},
  {"t": "ellipse", "x": 1, "y": 2.4, "w": 0.6, "h": 0.6, "fill": "tint"},
  {"t": "icon", "x": 1, "y": 2.4, "size": 0.6, "name": "lightbulb", "color": "primary", "bg": "tint", "circle": true},
  {"t": "image", "x": 7.5, "y": 1, "w": 5, "h": 5, "path": "/abs/path/assets/hero_07.png", "fit": "contain"},
  {"t": "line", "x1": 0.8, "y1": 3.6, "x2": 5.8, "y2": 3.6, "color": "line", "lw": 1.5, "dash": false, "arrow": false}
]}
```

线条只写两个端点 `x1 y1 x2 y2`，不用写 x、y、w、h。

elements 写在 deck.json 那一页或 plan.json 那一页都可以，plan 里有就用 plan 的。重新跑 plan_deck 时，这页的 deck 内容改了，plan 里手写的 elements 也会带过去。两边都没有时页面是空的，QA 报 ERROR。

颜色可写色板角色名（primary、primary_dark、accent、tint、surface、text、muted、line、on_primary、bg_top、bg_bottom，
以及自动推导的 strong 大标题色、highlight 彩色文字色），
`primary@0.3` 表示主色和白色按 30% 混合的浅色，也可以直接写十六进制。
`font` 取 heading、body、display 之一。free 版式的文字尺寸要自己用 `common.fit_size` 算，或者留足余量，QA 会检查溢出。
