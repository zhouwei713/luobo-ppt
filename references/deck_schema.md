# deck.json 字段说明

deck.json 描述"这份 PPT 在讲什么"，和样式无关。版式函数只认这里的字段。

## 顶层

```json
{
  "meta": {
    "title": "Muse",
    "series": "小白入门 · 3 分钟看懂",
    "footer": "Muse 小白入门",
    "total": 11,
    "topic": "Muse, an AI agent app that does tasks for you",
    "anchor": {
      "description": "a glossy mint-teal rounded-square app icon with a bold white letter M, gently held by a sleek white robotic hand",
      "glyph": "M"
    }
  },
  "slides": [ ... ]
}
```

| 字段 | 说明 |
|---|---|
| `series` | 内容页顶部居中的系列页眉，两侧配叶片装饰。原稿封面上的小标签常适合放这里。不需要就留空 |
| `footer` | 原稿的页脚文字。有 takeaway 胶囊条时放在胶囊条右侧，否则放左下角 |
| `topic` | 英文一句话主题，插画提示词会引用 |
| `anchor` | 视觉锚点，见 `image_prompts.md`。`glyph` 是程序化插画里瓷砖上的字母 |
| `scenario` / `audience` / `density` | 生成模式用：场景（oral、talk、reading、report）、受众、密度（low / high） |
| `storyline` | 生成模式用，一句话故事线 |
| `notes` | 生成模式用，true 表示每页都要口播备注 |
| `auto_page` | true 时内容页自动加"03 / 11"式页码，不用逐页写 `page` |
| `projection` | true 时按投影场景排版，自动字号不低于 14pt、正文从 18pt 起，容量上限按 65% 计；装不下的页会被 QA 报出来，拆页处理 |
| `date` / `issue` | 杂志式页眉右上角的日期或期号，大字封面顶部也会用 |
| `auto_number` | 默认 true，没写 `number` 的章节页按顺序编成 01、02…；false 关掉 |
| `animation` | 动画，见下方"动画"。不写时按 `scenario` 定：oral、talk 用 `click`，其余用 `transition` |
| `animation_effect` | 条目出现的效果：`rise` 淡入加轻微上浮（默认）、`fade` 只淡入、`wipe` 从左擦除 |

## 每页通用字段

| 字段 | 说明 |
|---|---|
| `n` | 页码序号，从 1 开始，与原稿一致 |
| `type` | 页型，决定默认版式，见下表 |
| `layout` | 可选，直接指定版式，优先级低于 plan.json |
| `title` | 页面标题 |
| `takeaway` | 这一页的一句话结论，放进底部胶囊条（原稿里页面底部的强调条、提示框通常就是它） |
| `page` | 页码文字，照抄原稿，比如 `"02 / 11"`，封面结尾通常没有 |
| `notes` | 演讲备注。美化时照抄 `deck.draft.json`，生成时写口播原话 |
| `purpose` | 生成模式用，这一页在故事里负责什么，不上页面 |
| `source` | 数据出处，显示成页面底部的小字"来源：…" |
| `show_footer` | 默认内容页显示页脚，设 false 隐藏 |
| `animation` | 这一页单独的动画模式，覆盖 meta 里的设置，比如某页信息要一眼看全就写 `"transition"` |

文字里可以用 `**片段**` 标记局部加粗，渲染时加粗并用强调色。`\n` 表示换段。

## 动画

| 模式 | 效果 | 什么时候用 |
|---|---|---|
| `none` | 不切换不动 | 只拿来打印、发 PDF |
| `transition` | 只有翻页时的淡入淡出 | 汇报、发给别人自己翻，默认 |
| `auto` | 翻到这一页时，卡片、步骤、数据卡按顺序自己出来，间隔约 0.3 秒 | 路演、自动播放、录屏但不想一下下点 |
| `click` | 每点一次出一条 | 口播录视频、讲课、培训，讲一条出一条 |

哪些东西会动由版式决定：列表、卡片、步骤、数据卡、时间线、漏斗、循环、金字塔、对比两侧、矩阵四象限、SWOT/PEST/五力的格子、截图讲解点，按条目逐个出来。讲解页（explain）多栏时一栏一栏出来；只有一栏时按讲解步骤分组，每个小标签、每条判断规则、公式后面接着的文字各起一组，公式和小注跟着前一组。表格和图表是一整个对象，PowerPoint 里没法逐行出现，只有翻页效果。标题、背景、页眉页脚、插画始终在页面上。封面、章节页、大问句、金句、结尾页只有翻页效果。一页少于两条时也只有翻页效果。

动画在预览图里看不出来，要看效果运行 `python3 $S/anim_preview.py $W`，会出 `out/anim/storyboard.png`（每页逐次出现的分镜）和 `out/anim/preview.gif`。

## 每页都能用的小字段

| 字段 | 说明 |
|---|---|
| `kicker` | 标题上方的小标签，如"01 · DEVDAY 概览"。原稿每页的章节胶带、小标签放这里，封面、内容页、章节页、结尾页都会显示 |
| `stamps` | 原稿里要原样保留的小图，如 logo、"AI 生成"标识：[{image, x, y, w, h}]（英寸，13.333×7.5 画布） |
| `items[].num` | 条目自带的编号，如 "01"。写了它，这一条前面显示编号而不是图标，任何风格都不会丢 |
| `source` | 数据来源。已经以"来源""数据来源""Source"开头的不会再加前缀 |

## 几个页型的可选字段

- `stats` 每项可加 `note`（数字下面的一行小注）；整页可加 `body`（卡片下面一段说明）或 `detail` {title, body}（带小标题的说明框）
- `definitions`（rows_side 版式）的 `side` 可加 `number`，侧栏变成"标签 + 大数字 + 说明"；整页可加 `list_title` 放在右侧列表上方
- `compare` 的条目可以写成 {num, text} 保留编号；某一栏写 `"bullet": "dash"` 用短横代替图标；`vs_label` 写成空字符串就去掉中间的 VS，适合两栏并列的总结页
- `footnote` 页底一行说明，原样显示，不加"来源"前缀

## 页型与专属字段

| type | 默认版式 | 专属字段 |
|---|---|---|
| `cover` | cover_hero 或 cover_type | `kicker` 小标签，`subtitle`，`body` 一句说明，`items` 议程或要点（每项 `text`） |
| `big_number` | statement_number | `number` 大数字，`lines` 两三行大字，`body` 补充说明 |
| `definitions` | rows_side | `side` {title, body} 左侧引导，`items` 每项 {title, text, emphasis} |
| `stats` | stats_row | `items` 每项 {value, label}，`takeaway` |
| `diagram_text` | media_text | `diagram` {title, icon, boxes:[{text, emphasis}], caption}，`point` 右侧要点，`body`，`callout` 提示框 |
| `steps` | side_cards | `side`，`items` 每项 {title?, text, emphasis} |
| `quotes` | quote_cards | `lead` 引导句，`items` 每项 {text} |
| `statement` | statement_hero | `headline`，`body`，`pill` 小胶囊 |
| `warnings` | cards_quote | `items` 每项 {title, text}，`quote_lines` 右侧两行金句 |
| `side_cards` | side_cards | 同 steps |
| `list` | list_icons 或 grid_cards | `items` 每项 {title?, text} |
| `grid` | grid_cards | `items` 每项 {title?, text, emphasis} |
| `process` | steps_flow | `items` 2 到 5 步，每项 {title, text}，自动加 01、02 编号 |
| `compare` | compare_split | `left` / `right` 各 {title, items:[文字…], icon?}，右边是推荐的一方；`vs_label` 可改中间的字 |
| `cycle` | cycle | `center` 圆环中间的短词，`items` 3 到 6 项 {title, text} |
| `layers` | pyramid | `items` 从上到下 3 到 5 层 {title, text}，最上面最窄 |
| `section` | section | `number` 章节号如 "01"（不写就自动编号），`title`，`subtitle` |
| `ranking` | rank_grid | `items` 3 到 10 条 {num, title, text}，`findings` {title, items:[文字…]} 榜单下面的结论框 |
| `explain` | explain | 理科、教学类讲解页。`blocks` 一栏，或 `columns` 两到四栏（每栏 {blocks}）；block 是 {label} 小标签、{text} 正文、{formula} 公式（浅色条里居中，一页的公式同一字号）、{rule, tone} 判断规则（tone 取 up 绿 / down 红）、{note} 小注；`image` 左侧示意图；`boxed` 是否给每栏加卡片（多栏默认加） |
| `screenshot` | shot_notes | `image` 截图路径（相对工作目录），`items` 0 到 5 条 {title?, text, at?: [横向比例, 纵向比例]}，`at` 是 0 到 1 的位置，会在截图上打对应编号；`caption` 截图下方小字；`frame` 外框样式 |
| `screenshots` | shot_stack | `items` 1 到 4 条 {image, title?, text?, num?}，`flow` 默认 true（步骤，带编号和箭头），false 为并列对照；`frame` 外框样式 |
| `question` | question | `question` 大问句（可带 **强调词**），`kicker` 小引子，`body` 一句提示 |
| `big_quote` | big_quote | `quote` 引文，`by` 出处，`note` 补充说明（时间、场合） |
| `toc` | toc 或 toc_row | `title` 默认"目录"，`kicker` 默认"CONTENTS"，`items` 每项 {title, text?}；不写 items 时自动列出全部章节页的标题和副标题 |
| `closing` | closing | `headline`，`body`，`cta` 按钮文字 |
| `timeline` | timeline | `items` 3 到 6 个 {date, title, text, emphasis}，按时间先后写 |
| `funnel` | funnel | `items` 3 到 5 层 {label, value, text}，从宽到窄；value 都是数字时宽度按比例 |
| `hub` | hub | `center` {title} 中心，`items` 3 到 6 个 {title, text}，左右两列连线 |
| `matrix` | matrix | `x_axis` / `y_axis` 各 {label, low, high}，`quadrants` 按左上、右上、左下、右下四项 {title, items:[文字…], emphasis} |
| `table` | table | `columns` 表头，`rows` 二维数组，`highlight_col` 高亮第几列（从 0 数），`note` 表下注释；单元格里可以用 `**加粗**` |
| `chart` | chart | `chart` 见下，`insights` 右侧一到三条结论，`source` 数据来源 |
| `framework` | framework | `framework` {kind, blocks, labels?}，见下 |

`chart` 的写法

- `type` 取 column、bar、line、pie、doughnut、stacked
- `categories` 类别，`series` 每条 {name, values}，values 和 categories 一样长
- `highlight` 要突出的类别序号（单系列柱、条图和饼图生效）
- `unit` 数字后面带的单位，所有图表类型都生效，写 "%" 时 35 显示成 35%，写 "万" 时显示成 35万；`number_format` 优先于 unit，如 `"0"` `"0.0"` `"#,##0"` `"0%"`（注意 `"0%"` 会把 0.35 显示成 35%，数据是 35 时要用 `'0"%"'` 或者直接写 unit）
- `title` 图表标题，`y_title` 数值轴说明（常见的是"单位：万元"），`x_title` 类别轴说明；数值轴是隐藏的，这两条会作为小字放在图表上方和下方
- 美化时原稿的图表已经在 deck.draft.json 的 `charts` 里，照抄即可；QA 会把类别、系列、数值、显示出来的数字、标题和轴说明逐项和原稿对
- 多条折线只在末端标数，免得数字挤在一起
- 数字必须来自素材或查证过的来源，`source` 必填；数据改了，`insights` 和标题里的结论要一起重写

`framework` 的 blocks 键

| kind | blocks 的键 | 每块条数 |
|---|---|---|
| swot | s, w, o, t | 1 到 4 |
| pest | p, e, s, t | 1 到 4 |
| five_forces | center, entrant, substitute, supplier, buyer | 1 到 3 |
| canvas | kp, ka, kr, vp, cr, ch, cs, cost, revenue | 1 到 3 |

每块是一个字符串数组。想换块名（比如把"优势"写成"我们的长处"）就在 `labels` 里按同样的键覆盖。

`emphasis: "primary"` 表示这张卡是重点（实心主色卡片或浅色底强调）。原稿里用主色填充的那张卡一般就是重点。

## 从原稿映射的经验

- `deck.draft.json` 里每个文本单元带有 `role` 猜测（title、number、footer、page、decor、text）、字号、是否加粗、所在色块 `container.fill`。同一个色块里的文字属于同一张卡片。
- 原稿的 `「` 这类单独引号是装饰，美化后用引号图标代替，不必写进 deck.json（QA 会忽略单个标点）。
- 原稿图片里的文字（`pictures[].svg_texts`）要落进 `diagram`，QA 会对这类文字做缺失提醒。
- 一页内容装不进任何版式时，优先换版式（比如 list_icons 最能装），实在不行用 `free` 版式手工排，不要删字。
- 原稿没有的文字不要编。版式需要标签时只能用原稿已有的文字。
- 想突出"可回收物：纸类、塑料、金属"里的前半句，不要拆成 title 和 text（冒号会丢），写成 `"**可回收物**：纸类、塑料、金属"`。加粗标记不算改字，QA 会忽略它。
- 原稿每个段落是一个校验单元，所以把一段项目符号列表拆成多张卡片没有问题，但不要把一个段落拆开或合并两个段落。

## 完整示例（节选）

```json
{"n": 4, "type": "stats", "title": "它火得数据很硬",
 "items": [{"value": "73万", "label": "上线 5 天下载量"},
           {"value": "250万", "label": "13 天全网累计下载"},
           {"value": "64万", "label": "美国移动端日活"}],
 "takeaway": "日活是 ChatGPT 同期近 3 倍，说明真有人天天用",
 "page": "04 / 11", "notes": "那它到底有多火？……"}

{"n": 5, "type": "diagram_text", "title": "为什么关屏还能干活",
 "diagram": {"title": "Secure VM 独立云端电脑", "icon": "cloud",
             "boxes": [{"text": "你的登录信息 · 浏览器 · 账号"}, {"text": "Sentinel 监工", "emphasis": "primary"}],
             "caption": "任何对外操作都要它点头"},
 "point": "每人一台独立云端电脑，关屏任务照跑",
 "body": "你的账号数据跟别人完全隔离，旁边还有监工盯着它。",
 "callout": "门槛低到**注册个账号就能用**，之前那类 Agent 还得自己本地部署。",
 "page": "05 / 11"}
```
