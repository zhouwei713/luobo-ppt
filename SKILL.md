---
name: luobo-ppt
description: 做 PPT 和美化 PPT 的一站式 skill，输出可编辑的原生 .pptx。从零生成时，给一个题目、一篇文章或口播稿、一份大纲，产出结论式标题、带口播备注、风格统一的 PPT；按参考图美化时，给一份朴素的 .pptx 和一张参考图，文字一字不改地换上统一的配色、母版、版式、图标和插画。当用户说"做个PPT""把这篇文章做成PPT""生成口播PPT""美化PPT""照这张图的风格改PPT""套个风格""make slides""beautify my deck"，或丢来 pptx、文章、大纲时，务必使用此skill。生图模型可配置；没配置时先问用户，可以现场接入模型、搜可商用的公开图库实拍图、用自己的素材，或用程序化插画。口播和讲课的稿子自带逐条出现的动画。
---

# 萝卜 PPT（luobo-ppt）

两条路线共用一套设计引擎。生成是"写出内容再设计"，美化是"抽出原稿内容再设计"，从版式规划开始完全一样。

三份中间文件串起全流程，脚本负责确定性的活，Claude 负责理解内容和审美判断。

| 文件 | 内容 | 美化时 | 生成时 |
|---|---|---|---|
| `deck.json` | 每页的页型、标题、要点、数据、备注 | 从原稿抽取，文字一字不改 | 按 `references/generate.md` 写出来 |
| `style.json` | 色板、字体、圆角、装饰、插画风格 | 从参考图抽取 | 参考图抽取，或从预设库挑 |
| `plan.json` | 每页版式、图标、插画和提示词 | `plan_deck.py` 起草，Claude 审改 | 同左 |

下文 `$S` 指本 skill 的 scripts 目录，`$W` 指本次的工作目录（如 `./ppt_work`）。Windows 上把 `python3` 换成 `python`。

## 开工前

1. **判断路线**
   - 用户给了 .pptx，要换个好看的样子 → 路线 A 美化
   - 给的是题目、文章、口播稿、大纲或其他素材，要做成 PPT → 路线 B 生成
   - 给了 .pptx 但要重写内容、调整结构 → 路线 B，把 pptx 当素材读
   - 另外给了企业 VI 手册、品牌规范，或者说"按公司 VI 做""用我们的品牌色"→ 两条路线都先做"品牌套件"，风格从手册来，不再读参考图、不出风格样张
2. **环境自检**，之前通过的话一秒内结束，否则自动补装依赖。退出码非 0 就把建议告诉用户并停下；只缺推荐组件（如 LibreOffice）可以继续，pipeline 会改用 `render_lite.py` 按排版数据直接画近似预览，排版、配色、溢出照样能看，交付时说明预览是近似图。想跳过 LibreOffice 提速也可以加 `--lite`。
   ```bash
   python3 $S/setup_check.py --quick --install
   ```
3. **生图状态** `python3 $S/make_assets.py $W --status`，用一句话告诉用户接了哪家模型。没有模型时先别默认走程序化插画，等版式规划出来、确实需要配图时按下面的"配图来源"问用户。配置方法见 `references/imagegen_config.md`。
4. **一次提问**问清路线需要的选择，其余用默认值。用户说"直接做""不用问"或者不在场时，全部用默认值，交付时列出做过的选择。
5. **快速模式**：用户说"快速模式""别问了""赶时间"时，跳过风格卡、大纲、设计规格的确认，五维自评只修一轮"要修"，"顺手改"写进交付说明不动手。快速模式只省掉等用户确认的环节，逐字核对、图表和小字核对、全部 QA 检查照常跑，ERROR 没清零就不交付。12 页左右的稿子，正常 15 到 25 分钟，快速模式 10 分钟上下；时间大头在转写文字和看图，脚本本身只要一两分钟。
   - 美化：力度 light / standard / full（默认 full），是否允许精修文字（默认不允许）
   - 生成：用途、受众、时长、有无参考图、要不要口播备注，默认值见 `references/generate.md`

## 路线 A 美化

1. **解析原稿** `python3 $S/extract_deck.py 原稿.pptx $W`，然后看 `source_png/sheet.png`。脚本会修复 LibreOffice 打不开的 zip，也能读出藏在 descr 属性里的口播备注。
2. **读参考图** `python3 $S/extract_style.py 参考图.png $W`，再亲自看图，按 `references/style_extraction.md` 写 `$W/style.json`，然后 `python3 $S/style_card.py $W` 出风格卡。用户在场就发风格卡确认。
3. **整理 deck.json**，按 `references/deck_schema.md` 从 `deck.draft.json` 转写。文字逐字复制，局部加粗写成 `**片段**`；图片里的文字重建成 `diagram` 等原生结构；`notes` 原样带上；写好 `meta.anchor` 视觉锚点。原稿页面上的小标签（"01 · 概览"这类章节胶带）写进该页的 `kicker`，条目自带的编号（01、02）写进条目的 `num`，这样换任何列表符号都不会丢字。原稿里用公式编辑器打的公式，解析时会自动转成普通文字公式（如 V′(x) = (a−2x)(a−6x)），照常逐字转写；公式多的讲解页用 `explain` 页型。SVG 图会顺手转一份 PNG（raw.json 里的 png 字段），版式里用 PNG。logo、"AI 生成"标识这类小图写进 `stamps` 原样保留。原稿里的图表在 `deck.draft.json` 每页的 `charts` 里已经整理成现成的图表写法，用 `chart` 页型照抄进去，`number_format`、`title`、`x_title`、`y_title` 一个都不能丢，丢了图上的单位和坐标轴说明就跟着没了。一页有两三个图表时整组抄进 `charts`，散点图带着每组的 `x` 原样抄。原稿表格在 `tables` 里，抄进 `table` 页型。页面底部带 * ※ 的注释、来源，role 是 footnote，写进该页的 `footnote` 和 `source`，两个可以同时写。原稿里的软件截图（`media/` 下的图片）用 `screenshot` 或 `screenshots` 页型，截图会放进统一的窗口外框，讲解点可以用 `at` 打在截图上。
4. 接着走下面的"版式、出图与检查"。

## 路线 B 生成

开始前先读 `references/generate.md`，里面有故事线、结论式标题、密度、口播备注和页型选择的全部规则。

1. **分析素材** `python3 $S/analyze_source.py $W --file 文章.md`（只有题目用 `--topic "…"`，可加 `--minutes 3`）。只有题目或需要补充事实时，先搜索查证，查不到的不写。
2. **写 deck.json**：先定故事线，再按"内容形状决定页型"逐页写，标题写结论，屏幕放关键词，完整的话放 `notes`。分了章节的稿子在封面后放一页 `toc` 目录（不写 items 会自动列章节），卡片页连得多了插一页 `question` 大问句或 `big_quote` 大引文。工具教程类的素材有截图时，一张图配几个操作点用 `screenshot`，几张图走流程用 `screenshots`。除了常规的卡片、步骤、对比，还有时间线、漏斗、中心辐射、2x2 矩阵、原生表格、原生图表和 SWOT/PEST/五力/商业画布，拿不准装不装得下就 `python3 $S/layout_info.py <版式名>` 查容量和示例。
3. **检查大纲** `python3 $S/outline_check.py $W`，修到没有 ERROR，把 outline.md 里的"只读标题"发给用户确认。
4. **定动画**：口播稿、讲课按 `scenario` 默认就是逐条点击出现，汇报默认只有翻页效果，一般不用写。用户提了要求或场景特殊再写 `meta.animation`（`none`、`transition`、`auto`、`click`），说明见 `references/deck_schema.md` 的"动画"一节。
5. **定风格**：有参考图走路线 A 第 2 步；没有就 `python3 $S/style_previews.py $W --auto` 出三张样张（用户自己的封面和内容页），发 `previews/sheet.png` 让用户挑，再 `--apply <id>`。预设在 `references/styles/`，共十四套，每套的硬规则排版时要遵守。要在会议室投影的，在 `meta` 里写 `"projection": true`，字号下限会抬高。
6. 接着走下面的"版式、出图与检查"。

## 品牌套件（有企业 VI 手册时）

VI 手册规定的是精确色值、字体、logo 的用法和安全空间。拿手册页当参考图取色会取错，色板只占页面的一小块，所以有手册时风格只从手册来，规则见 `references/brand.md`。

1. **拆页** `python3 $S/brand_kit.py pages 手册.pdf $W`，手册页面放在 `$W/brand/pages/`，一整张长图导出的手册会按页切开。文字层里的色值会列出来；手册是整页图片时没有文字层，要看图读。
2. **读手册写 brand.json**：把 `brand.draft.json` 填好另存为 `$W/brand.json`。色值一律抄手册上印的数字，不从图上取色；每个颜色标 role（primary、secondary、accent、extra、text、background、neutral）。字体、logo 安全空间和最小尺寸、标志性元素（标题竖条、粗描边加硬投影）、禁用项、IP 形象和辅助图形都照手册写。logo 和形象用 `brand_kit.py crop $W 页面.png x0 y0 x1 y1 名字 --clear` 从页面上截下来（白底变透明）；手册没有深底用的反白 logo 时，`brand_kit.py plate` 做一个白底版。手册对形象有限制的（比如"只用于运营活动"），写进 rules 并照办。
3. **核对** `python3 $S/brand_kit.py check $W`，每个色值会回到手册页面上找，一个像素都找不到的多半读错了，回去再看。
4. **生成风格** `python3 $S/brand_kit.py apply $W`，写出 `style.json` 和 `brand/brand_card.png`。把品牌卡发给用户确认颜色、字体和 logo，代替风格卡。
5. 回到原来的路线继续，跳过读参考图和挑风格。logo 每页自动放在手册要求的位置并留出安全空间，不要再写进 `stamps`；某页不要 logo 就在这页写 `"logo": false`。手册内页用文字页眉、不放 logo 图形的，`logo.content` 写 header。IP 形象只放封面、章节页、结尾页和需要情绪的页：在那一页写 `"art": "question"` 这类动作名（brand.json 里给每个形象标 mood），一份稿子内容页最多出现四次，整张放、不裁切。数据页、列表页不放形象。
6. QA 多出一组 brand 检查：手册以外的颜色、手册不许的渐变、logo 安全空间里有别的东西、logo 小于最小尺寸都是 ERROR。手册字体没装是 WARN，要告诉用户装上，或者发给别人前在 PowerPoint 里嵌入字体。

## 版式、出图与检查（两条路线共用）

1. **版式规划** `python3 $S/plan_deck.py $W --level full`（有生图模型时加 `--sheets`，一张大图切出几张小插画，风格更统一也更省）。
   重跑时内容没变的页会保留原来的规划（包括手改过的版式和插画提示词），要全部重排加 `--reset`。
   审 plan.json：版式贴不贴内容（`references/layouts.md`）、图标达不达意（`references/icons.md`）、插画提示词具不具体（`references/image_prompts.md`）。内容超出版式容量时脚本会自动换版式，并写进 design_spec.md 的"容量提醒"，出图前先处理掉。
   把生成的 design_spec.md 发给用户确认后再出图，出图最花钱。快速模式跳过确认。
   没有生图模型时再跑一次 `make_assets.py $W --status`，输出里有 `ASK` 就按"配图来源"问用户，和设计规格放在同一次确认里问。
2. **出图、组装、自检**一条命令：
   ```bash
   python3 $S/pipeline.py $W
   ```
   依次运行 make_assets（插画、背景、装饰，AI 提示词先落盘到 `prompts/`）、build_deck、render、qa_check、compare_sheet、review。
   然后打开 `out/fine_print.md` 单独对一遍：每个图表的类别、系列名、数字显示出来的样子（带不带单位）、图表标题和坐标轴标题，以及每条注释、来源、单位说明和带 * ※ 的小字，左边原稿右边成品。正文逐字都对的稿子，意思常常就变在这些地方，交付前一定看。
   有逐条动画（auto 或 click）时再跑 `python3 $S/anim_preview.py $W`，看 `out/anim/storyboard.png` 确认出现顺序对不对，交付时可以附上 `out/anim/preview.gif`。

   | 检查 | 级别 | 处理 |
   |---|---|---|
   | 美化时原稿文字缺失或被改；生成时 deck.json 的文字没上页面 | ERROR | 对照原文或 deck.json 修正 |
   | 文字溢出、文本框重叠、文字越过底线（压到胶囊条或页脚） | ERROR | 换版式、拆页，或用 `free` 版式手工摆 |
   | 强调色一页超过 3 处或面积超过 8% | WARN | 只留一处强调 |
   | 文字压插画、对比度不足、出界、正文过小 | WARN | 看图判断，多数要修 |
   | 图表少了，或者类别、系列名、数据、显示出来的数字（单位）、图表标题、坐标轴标题和原稿对不上 | ERROR | 按 deck.draft.json 的 charts 照抄 |
   | 注释、来源、单位说明这类小字被改了，比如 * ※ 符号丢了 | ERROR | 原样恢复，符号也要留 |
   | 动画指向不存在的形状 | ERROR | 重跑 build_deck.py |
   | 一页要点超过 6 次才出完 | WARN | 拆页，或这一页改 `auto` |
   | 新增的页眉、页码、步骤编号 | INFO | 正常 |

3. **五维自评**：看 `out/sheet.png` 和逐页 PNG，对照 `out/review.md` 里脚本数出的证据，按 `references/critique.md` 给统一、层级、细节、传达、节奏各打 0 到 10 分，写出保留、要修、顺手改三张清单。"要修"的交付前改掉，改完只重跑受影响的步骤，最多三轮。

## 配图来源

需要配图但没有生图模型时，先问用户选哪种，不要自己默认。一次问清，四个选项：

1. **现在接入生图模型**：按 `references/imagegen_config.md` 帮用户配好（OpenAI、Gemini、即梦/Seedream、HiAPI 或兼容接口）。用户在聊天里给 key 时只放进环境变量，不写进任何文件，提醒他用完作废，`make_assets.py $W --status` 确认生效后照常出图。
2. **搜公开图库的实拍图**：适合讲具体东西的稿子，比如门店、产品、城市、食物、活动现场。抽象概念（效率、增长、底层逻辑）搜出来大多是俗套图，这类页继续用插画。
3. **用自己的素材**：用户给图片文件或文件夹，按页对应放进去。
4. **用程序化插画**：不联网、不花钱，风格统一。

用户不在场、说了"直接做"或快速模式时选 4，交付时说明可以换成实拍图或接入模型。几种可以混用，比如封面用自己的照片，其余页用插画。

实拍图和用户素材都用 `photo_assets.py`：

```bash
python3 $S/photo_assets.py sources                         # 现在能用哪些图库
python3 $S/photo_assets.py search $W hero_01 "coffee shop interior"   # 关键词用英文、写具体名词
python3 $S/photo_assets.py pick   $W hero_01 3             # 看 photos/hero_01/sheet.png 挑一张
python3 $S/photo_assets.py local  $W hero_01 用户的图.jpg   # 用户自己的图
python3 $S/photo_assets.py drop   $W hero_01               # 退回插画
```

- 搜图前先看 plan.json 里哪些图位值得放照片：封面、章节页、结尾页和图文页的大图位最合适；内容页右上角的小装饰位放照片偏挤，脚本会提醒，这类页继续用插画
- 候选图先看 `sheet.png` 再挑，挑和这一页内容真正相关、画面干净、没有水印和大段文字的，特别留意杯子、招牌、包装上别家的品牌名；都不合适就换关键词或退回插画，宁缺毋滥
- 照片会按图位裁切、圆角、加柔和投影；想让照片和配色更统一加 `--tint 0.12`；主体被裁掉就用 `--focus X Y` 调保留位置
- 只收可商用、可修改的图：CC0、公有领域、CC BY、CC BY-SA，以及 Pexels、Unsplash、Pixabay 自家协议（这三家要用户在环境变量里配免费 key，见 `references/imagegen_config.md`）
- CC BY 和 CC BY-SA 必须署名：脚本会打出 `CREDIT` 行。生成模式把它加到该页 `notes` 末尾；美化模式不改备注，把 `out/image_credits.md` 交给用户自己决定放哪
- 输出 `NO_NETWORK` 说明命令行连不上图库（网络受限）。这时如果有浏览器工具，可以在浏览器里请求 Openverse 接口（`https://api.openverse.org/v1/images/?q=关键词&license_type=commercial,modification`），挑好图拿到图片文件，把作者、原始页面、协议、原图宽高写进一个 json，用 `local $W hero_01 图片 --credit meta.json` 放进去，署名照样记录；没有浏览器就告诉用户，改用他的素材或程序化插画
- 原图太小（裁到图位后不到图位宽度的一半）脚本会提醒会发虚，换一张大图
- 选好的照片和用户素材之后重跑 `make_assets.py`（包括 `--force`）都会保留，除非在 `--only` 里点名

## 交付

- `out/beautified.pptx`，文件名用 `原名_美化版.pptx` 或 `主题.pptx`
- 美化附 `out/compare.png` 前后对比图，生成附 `out/sheet.png` 全览图
- 一句话报五维自评的分数和最弱的一项
- 用了实拍图时附 `out/image_credits.md`，需要署名的图提醒用户
- 一两句话说明风格、插画来源（哪家模型、程序化插画、图库实拍或用户素材）、字体，美化时说明有无精修文字，生成时说明哪些内容需要用户再核实
- 用户连接了本地文件夹时，写回素材所在的位置

## 硬规则

通用
1. 所有文字都是可编辑文本框，卡片、胶囊条、分隔线用原生形状，只有背景、插画、图标、笔刷是图片。
2. 参考图只用来抽风格，不裁切、不贴进 PPT。
3. AI 插画里不出现文字（产品首字母这种图形化字母除外），提示词始终带负面约束。
4. 程序化插画是兜底方案，交付时如实说明，不说成 AI 生成。
5. 逐字核对和 QA 检查在任何模式下都不跳过，快速模式、用户不在场也一样。
6. 做稿子的过程中不改 skill 自己的文件。遇到 skill 的问题，绕过去完成交付，再把问题写进交付说明，由用户决定要不要改 skill。

美化
7. 默认不改任何文字；用户允许精修时，改动逐条列给用户过目。
8. 页序和页数与原稿一致，备注保留。

生成
9. 数据和事实只用素材里的或查证过的，标上 `source`；查不到就不写，绝不编数字。图表数据改了，标题和 insights 的结论跟着重写。
10. 大纲（只读标题）经用户确认后再做设计；风格和设计规格同理，快速模式除外。

## 局部修改

- **单页重做**：改 plan.json 里那一页的 `layout`、`icons`，或改 `prompts/hero_NN.md`，再 `make_assets.py $W --only hero_NN --force` 和 `pipeline.py $W`
- **换风格**：换 style.json（参考图或 `style_previews.py --apply`），插画 `--force` 重出，deck.json 和 plan.json 可以沿用
- **特殊页面**：该页 layout 设为 `free`，在 plan 里直接写 `elements`（格式见 `references/layouts.md`）
- **只要轻度美化**：`plan_deck.py $W --level light`，不出插画

## 常见问题

- `soffice` 转换失败：渲染只影响预览，不影响交付文件；先确认 `extract_deck.py` 产出的 `source.pptx` 能打开
- 美化后原稿的动画没了：重建时不保留原稿动画，默认只加翻页效果。用户要动画就在 deck.json 的 `meta` 里写 `"animation": "click"` 或 `"auto"` 重跑
- 预览字体和用户电脑不同：预览用思源黑体代替微软雅黑，版式留了余量，见 `references/fonts.md`
- 生图失败：自动换程序化插画，`assets/manifest.json` 记录错误，交付时说明哪几页是兜底图

## 文件索引

| 路径 | 用途 |
|---|---|
| `references/generate.md` | 生成路线的完整规则（生成前必读） |
| `references/deck_schema.md` | deck.json 字段和全部页型 |
| `references/critique.md` | 五维自评的评分规则和常见改法 |
| `references/layouts.md` | 版式库、适用场景、容量、free 版式元素格式 |
| `scripts/layout_info.py` | 查版式容量和 deck.json 示例，`--check $W` 逐页查超容量 |
| `references/style_extraction.md` | 从参考图读出 style.json |
| `references/brand.md` | 企业 VI 手册做成品牌套件：brand.json 字段、logo 规则、品牌检查 |
| `references/styles/` | 十四套风格预设（index.json + 每套 json，含硬规则和 imagery 标签），样张在 `assets/style_gallery.jpg`（第 N 行对应 index.json 里的 gallery_row） |
| `references/image_prompts.md` | 视觉锚点和插画提示词 |
| `references/imagegen_config.md` | 生图接口配置 |
| `references/fonts.md` | 字体选择和兼容性 |
| `references/icons.md` | 内置图标清单 |
| `INSTALL.md` / `install.sh` / `install.ps1` / `install.bat` | 安装说明和一键安装 |
| `config.example.json` | 生图配置模板 |
