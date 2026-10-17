# 生图接口配置

不配置也能用，插画会走程序化生成。想要附件示例那种 AI 插画效果，就配一个生图模型。

## 配置文件放哪

按下面顺序查找，找到第一个就用。

1. 命令行 `--config 路径`
2. 环境变量 `LUOBO_PPT_CONFIG` 指向的文件
3. 当前目录的 `luobo-ppt.config.json`，其次是工作目录里的同名文件
4. `~/.config/luobo-ppt/config.json`
5. skill 目录下的 `config.json`

旧名字 ppt-studio、ppt-beautify 对应的配置文件名和环境变量仍然有效，升级后不用改。都没有时，还可以只用环境变量：`LUOBO_PPT_PROVIDER=openai` 加对应的 key 变量。

检查当前生效的配置：`python3 scripts/make_assets.py 工作目录 --status`

## 字段

| 字段 | 说明 |
|---|---|
| `provider` | `openai`、`gemini`、`ark`、`hiapi`、`openai_compatible`、`command`、`none` |
| `api_key_env` | 存放 key 的环境变量名（推荐，key 不落盘） |
| `api_key` | 直接写 key（不推荐，别把文件分享出去） |
| `model` | 模型名，不填用默认 |
| `base_url` | 接口地址，不填用官方默认 |
| `quality` | 仅 openai gpt-image，`low` / `medium` / `high` |
| `resolution` | 仅 hiapi，`1K` / `2K` / `4K`，默认 `1K` |
| `size` | 强制尺寸，一般不用填 |
| `use_for` | `{"hero": true, "background": false}`，默认只用 AI 画插画，背景走程序化（更干净、不抢字） |
| `max_parallel` | 并发数，默认 3 |
| `timeout` / `retries` | 单次超时秒数和重试次数，默认 180 和 1 |
| `extra` | 原样并入请求体的额外参数 |

## 各家示例

OpenAI（支持原生透明底）

```json
{"provider": "openai", "api_key_env": "OPENAI_API_KEY", "model": "gpt-image-1", "quality": "medium"}
```

Google Gemini

```json
{"provider": "gemini", "api_key_env": "GEMINI_API_KEY", "model": "gemini-2.5-flash-image"}
```

火山方舟（即梦 / Seedream）

```json
{"provider": "ark", "api_key_env": "ARK_API_KEY", "model": "doubao-seedream-4-0-250828"}
```

HiAPI（异步任务接口，先提交任务再轮询结果，一张图大约一到两分钟，脚本默认三张并行）

```json
{"provider": "hiapi", "api_key_env": "HIAPI_API_KEY", "model": "gpt-image-2.5-flare/text-to-image", "resolution": "1K"}
```

`resolution` 可选 `1K`、`2K`、`4K`。透明底只有 `1K` 支持，插画默认需要透明底，所以保持 `1K`；2K、4K 出的是白底图，脚本会自动去白底。也可以只用环境变量：`LUOBO_PPT_PROVIDER=hiapi` 加 `HIAPI_API_KEY`。

其他兼容 OpenAI 图片接口的服务（中转站、自建服务等）

```json
{"provider": "openai_compatible", "api_key_env": "IMAGE_API_KEY",
 "base_url": "https://your-endpoint/v1", "model": "your-model"}
```

本地命令（比如自己的 ComfyUI 脚本）。命令必须把 PNG 写到 `{out}`，可用占位符 `{prompt_file}`、`{prompt}`、`{out}`、`{w}`、`{h}`。

```json
{"provider": "command", "command": "python my_gen.py --prompt-file {prompt_file} --out {out} --size {w}x{h}"}
```

模型名和默认地址会随服务商更新，调用报错时先去服务商文档核对模型名。

## 失败时会怎样

- 单张图失败会自动改用程序化插画，`assets/manifest.json` 里记录 `procedural (after AI error)` 和错误信息
- 在 Claude 的云端环境里，生图请求要经过网络白名单，被拦截时同样会降级，交付时如实告诉用户
- 如果运行环境自带原生生图工具（比如某些 Agent 平台），也可以直接用它按 `--dry-run` 打印出的提示词出图，存成 `assets/hero_NN.png` 并在 manifest 里登记，再继续组装

## 图库 key（没有生图模型、想用实拍图时）

Openverse 和 Wikimedia Commons 不用 key。下面三家注册后有免费 key，配了会优先用，图片质量通常更好：

| 图库 | 环境变量 | 申请地址 |
|---|---|---|
| Pexels | `PEXELS_API_KEY` | https://www.pexels.com/api/ |
| Unsplash | `UNSPLASH_ACCESS_KEY` | https://unsplash.com/developers |
| Pixabay | `PIXABAY_API_KEY` | https://pixabay.com/api/docs/ |

也可以写进上面的配置文件：`"photo": {"pexels_key_env": "MY_PEXELS_KEY"}`，或直接 `"pexels_key": "..."`（不推荐）。
检查能用哪些：`python3 scripts/photo_assets.py sources`
