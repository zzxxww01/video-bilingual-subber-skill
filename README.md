# Video Bilingual Subber

为本地视频或 YouTube 视频自动生成中英双语硬字幕，基于 Gemini API：
- 中文在上方（较大字号）
- 英文在下方
- 可选生成短视频发布文案（标题、描述、标签）

## 环境要求

- Python 3.10+
- `ffmpeg`（需在 PATH 中，或通过 `FFMPEG_BIN` 指定路径）
- 依赖安装：
  ```bash
  pip install -r requirements.txt
  ```
  包含 `requests`、`imageio-ffmpeg`（系统无 ffmpeg 时备用）、`yt-dlp`（YouTube 模式需要）

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env.local
```

编辑 `.env.local`，填入真实值：

```env
GEMINI_API_KEY=你的_gemini_api_key

# 可选：覆盖默认 Gemini 模型
# GEMINI_MODEL=gemini-3-pro-preview

# 可选：YouTube 下载认证（二选一）
# YTDLP_COOKIE_FILE=C:\Users\你的用户名\Downloads\www.youtube.com_cookies.txt
# YTDLP_COOKIES_FROM_BROWSER=chrome:Profile 2

# 可选：ffmpeg 不在 PATH 时手动指定
# FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe
```

### 2. 检查环境

```bash
python scripts/check_env.py --strict
python scripts/check_repo_safety.py
```

### 3. 运行流水线

**本地视频：**

```bash
python scripts/run_pipeline.py "你的视频.mp4"
```

**YouTube 单个视频：**

```bash
python scripts/run_pipeline.py --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

**YouTube 批量处理：**

```bash
python scripts/run_pipeline.py \
  --url "https://www.youtube.com/watch?v=AAA" \
  --url "https://www.youtube.com/watch?v=BBB"
```

### 4. 审核并烧录字幕

首次运行会在生成字幕后暂停，输出审核文件 `output/*.subtitle-review.txt`。确认字幕无误后，执行：

```bash
python scripts/run_pipeline.py "你的视频.mp4" --approve-burn --resume
```

## 功能特性

### 输入源

| 模式 | 说明 |
|------|------|
| 本地视频 | 支持 `.mp4`、`.mov`、`.mkv`、`.m4v`、`.webm` |
| YouTube URL | 自动下载视频，优先使用 YouTube 英文字幕；不可用时回退到 Gemini 转录 |
| 批量 YouTube | 多个 `--url` 参数依次处理，单个失败不阻塞其他任务 |

### 流水线步骤

1. **英文转录** — Gemini API 转录音频，或复用 YouTube 英文字幕
2. **中英翻译** — Gemini API 将英文字幕翻译为中文，支持术语表
3. **ASS 样式生成** — 中文大字号在上，英文小字号在下
4. **审核暂停** — 生成审核文件，等待用户确认
5. **硬字幕烧录** — ffmpeg 将 ASS 字幕烧入视频
6. **文案生成**（可选）— 生成标题、描述、标签 JSON

### 缓存与增量运行

- 流水线元数据保存在 `output/*.pipeline-manifest.json`
- `--resume` 模式下自动跳过已完成且参数未变的步骤
- 修改 model、batch-size、glossary、字号等参数后，下游缓存自动失效并重新生成
- 大视频文件（>100MB）使用 size + mtime 指纹，小文件额外计算 SHA256

### YouTube 认证

YouTube 下载认证支持三种方式（优先级从高到低）：

1. 命令行参数：`--cookies <cookies.txt>` 或 `--cookies-from-browser chrome`
2. 环境变量：`YTDLP_COOKIE_FILE` 或 `YTDLP_COOKIES_FROM_BROWSER`
3. 在 `.env.local` 中配置以上变量

### 术语表

使用 glossary JSON 确保专有名词翻译一致：

```bash
python scripts/run_pipeline.py "video.mp4" --glossary "references/glossary.sample.json"
```

默认会自动加载 `references/glossary.sample.json`（如果存在），使用 `--no-glossary` 禁用。

## 常用参数

| 参数 | 说明 |
|------|------|
| `--model` | Gemini 模型名称（默认 `gemini-3-pro-preview`，可通过 `GEMINI_MODEL` 全局覆盖） |
| `--batch-size` | 翻译批次大小（默认 20） |
| `--zh-size` / `--en-size` | 中文/英文字号（默认 48/34） |
| `--glossary` | 术语表 JSON 路径 |
| `--no-glossary` | 禁用默认术语表 |
| `--copy` / `--no-copy` | 启用/禁用文案生成 |
| `--resume` | 跳过已完成步骤（默认行为） |
| `--force` | 强制重新运行所有步骤 |
| `--approve-burn` | 允许烧录硬字幕 |
| `--review-lines` | 审核文件中的字幕条目数（默认 12） |
| `--no-youtube-captions` | 禁用 YouTube 字幕下载，始终使用 Gemini 转录 |
| `--cookies` | YouTube 认证 cookies 文件路径 |
| `--cookies-from-browser` | 从浏览器加载 YouTube cookies（如 `chrome` 或 `chrome:Default`） |
| `--download-dir` | YouTube 视频下载目录（默认 `downloads`） |

## 输出路径

```
downloads/                          # YouTube 模式下载的源视频
downloads/_meta/*.source.json       # YouTube 下载元数据
subs/*.en.raw.srt                   # 英文转录 SRT
subs/*.zh_en.srt                    # 中英双语 SRT
subs/*.zh_en.ass                    # 带样式的 ASS 字幕
output/*.subtitle-review.txt        # 字幕审核文件
output/*.pipeline-manifest.json     # 流水线缓存元数据
output/*.copy.json                  # 短视频文案（标题/描述/标签）
output/logs/*.ffmpeg.log            # ffmpeg 烧录日志
final_videos/*.zh-en-hard.mp4       # 最终硬字幕视频
```

## 分步运行

如需手动控制每个步骤，可单独调用各脚本：

```bash
# 1. 下载 YouTube 视频（仅 YouTube 模式）
python scripts/download_youtube.py --url "<url>" --download-dir downloads --out-meta downloads/_meta/meta.json

# 2. 英文转录
python scripts/transcribe_gemini.py --in "video.mp4" --out "subs/en.raw.srt"

# 3. 中英翻译
python scripts/translate_bilingual.py --in "subs/en.raw.srt" --out "subs/zh_en.srt" --batch-size 20

# 4. 生成 ASS 字幕
python scripts/srt_to_ass.py --in "subs/zh_en.srt" --out "subs/zh_en.ass" --zh-size 48 --en-size 34

# 5. 烧录硬字幕
python scripts/burn_ass.py --video "video.mp4" --ass "subs/zh_en.ass" --out "final_videos/video.zh-en-hard.mp4"

# 6. 生成文案
python scripts/generate_copy.py --video "video.mp4" --srt "subs/zh_en.srt" --out "output/video.copy.json"
```

## 测试与验证

```bash
python -m unittest discover -s tests -q
python scripts/check_repo_safety.py --strict
```

## 安全规范

- 禁止提交 `.env`、`.env.local`、私钥或明文 token
- 避免在命令行中直接传递密钥（shell 历史可能泄露）
- 推送到 GitHub 前务必运行 `python scripts/check_repo_safety.py --strict`
- GitHub Actions 包含自动密钥扫描工作流（`.github/workflows/secret-scan.yml`）
