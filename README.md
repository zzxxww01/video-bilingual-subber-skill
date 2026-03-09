# 视频双语字幕生成器 (video-bilingual-subber)

> 一款 **Claude Code Skill**，使用 Gemini API 自动为视频生成专业的中英双语硬字幕。中文大字号在上，英文小字号在下，支持本地视频和 YouTube URL 输入。

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Gemini](https://img.shields.io/badge/Gemini_API-Powered-orange.svg)](https://ai.google.dev/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 目录

[作为 Skill 安装（推荐）](#作为-skill-安装推荐) • [直接使用](#直接使用) • [功能特性](#功能特性) • [配置说明](#配置说明) • [快速开始](#快速开始) • [分步执行](#分步执行) • [常��问题](#常见问题)

---

## 作为 Skill 安装（推荐）

这是本工具的主要使用方式。安装后，在 Claude Code 中用自然语言即可驱动完整的字幕生成流程，无需手动输入命令。

### 第一步：克隆到 Skills 目录

```bash
# macOS / Linux
cd ~/.claude/skills
git clone https://github.com/zzxxww01/video-bilingual-subber-skill.git video-bilingual-subber

# Windows（PowerShell）
cd "$env:USERPROFILE\.claude\skills"
git clone https://github.com/zzxxww01/video-bilingual-subber-skill.git video-bilingual-subber
```

### 第二步：安装 Python 依赖

```bash
cd video-bilingual-subber
pip install -r requirements.txt
```

> 需要 Python 3.10+ 和 `ffmpeg`（需在 PATH 中，或通过 `FFMPEG_BIN` 环境变量指定）

### 第三步：配置 API Key

```bash
cp .env.example .env.local
```

用文本编辑器打开 `.env.local`，填入必填项：

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

> 可选配置：`GEMINI_MODEL`（覆盖默认模型）、`YTDLP_COOKIE_FILE`（YouTube 认证）等

### 第四步：重启 Claude Code

重启后即可在对话中直接使用：

```
给 video.mp4 添加中英双语字幕
```

```
处理这个 YouTube 视频并加双语字幕：
https://www.youtube.com/watch?v=VIDEO_ID
```

```
批量处理这些 YouTube 视频：
https://www.youtube.com/watch?v=AAA
https://www.youtube.com/watch?v=BBB
```

> Claude Code 会自动识别意图、下载视频（YouTube 模式）、转录音频、翻译字幕、**暂停让你审核翻译质量**、然后烧录硬字幕到视频。

---

## 直接使用

不使用 Skill 机制时，也可以直接在命令行调用。

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境

```bash
cp .env.example .env.local
# 编辑 .env.local，至少填入 GEMINI_API_KEY
```

### 运行

```bash
# 本地视频
python scripts/run_pipeline.py "video.mp4"

# YouTube 视频
python scripts/run_pipeline.py --url "https://www.youtube.com/watch?v=VIDEO_ID"

# 批量 YouTube
python scripts/run_pipeline.py --url "URL1" --url "URL2" --url "URL3"
```

首次运行会在生成字幕后暂停，输出审核文件 `output/*.subtitle-review.txt`。确认无误后：

```bash
python scripts/run_pipeline.py "video.mp4" --approve-burn --resume
```

---

## 功能特性

- **双输入源** — 本地视频（MP4/MOV/MKV/M4V/WEBM）+ YouTube URL 自动下载
- **智能字幕源** — YouTube 视频优先使用平台英文字幕，不可用时自动回退到 Gemini 转录
- **批量处理** — 支持多个 YouTube URL 顺序处理，单个失败不阻塞其他任务
- **Gemini AI 驱动** — 音频转录 + 英译中，支持自定义术语表确保专业术语一致性
- **双语样式** — 中文 48pt 在上，英文 34pt 在下，ASS 格式可自定义字号和字体
- **智能缓存** — Manifest 追踪所有产物元数据，参数变化时自动失效下游缓存
- **性能优化** — 大文件（>100MB）跳过 SHA256 计算，使用 size+mtime 指纹
- **可选文案生成** — 自动生成短视频发布文案（标题、描述、标签）

---

## 配置说明

所有配置通过项目根目录的 `.env.local` 文件管理（推荐）或直接设置环境变量。

### 必填

| 配置项 | 说明 |
|--------|------|
| `GEMINI_API_KEY` | Google Gemini API Key |

### 常用可选项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `GEMINI_MODEL` | 全局覆盖默认模型 | `gemini-3-pro-preview` |
| `YTDLP_COOKIE_FILE` | YouTube 认证 cookies 文件路径 | — |
| `YTDLP_COOKIES_FROM_BROWSER` | 从浏览器加载 cookies（如 `chrome:Profile 2`） | — |
| `FFMPEG_BIN` | 自定义 ffmpeg 路径 | 自动检测 |

完整配置项参见 [.env.example](.env.example)。

### 术语表

创建 `references/glossary.sample.json` 确保专业术语翻译一致：

```json
{
  "AI": "人工智能",
  "machine learning": "机器学习",
  "neural network": "神经网络"
}
```

流水线会自动加载此文件（如果存在）。使用 `--glossary <路径>` 指定自定义术语表，或 `--no-glossary` 禁用。

---

## 快速开始

### 作为 Skill 使用

安装完成后，直接在 Claude Code 对话框输入自然语言即可：

| 意图 | 示例指令 |
|------|----------|
| 本地视频加字幕 | `给 video.mp4 添加中英双语字幕` |
| YouTube 视频 | `处理这个 YouTube 视频：https://...` |
| 批量 YouTube | `批量处理这些视频并加双语字幕：<URL列表>` |
| 自定义参数 | `用 gemini-2.0-flash-exp 模型处理 video.mp4` |
| 生成文案 | `给 video.mp4 加字幕并生成发布文案` |

Claude 会自动执行完整流程，并在烧录前暂停让你审核字幕质量。

### CLI 示例

<details>
<summary>本地视频基础用法</summary>

```bash
python scripts/run_pipeline.py "video.mp4"
# 审核后继续
python scripts/run_pipeline.py "video.mp4" --approve-burn --resume
```
</details>

<details>
<summary>YouTube 单个视频</summary>

```bash
python scripts/run_pipeline.py --url "https://www.youtube.com/watch?v=VIDEO_ID"
# 审核后继续
python scripts/run_pipeline.py --url "https://www.youtube.com/watch?v=VIDEO_ID" --approve-burn --resume
```
</details>

<details>
<summary>YouTube 批量处理</summary>

```bash
python scripts/run_pipeline.py \
  --url "https://www.youtube.com/watch?v=AAA" \
  --url "https://www.youtube.com/watch?v=BBB" \
  --url "https://www.youtube.com/watch?v=CCC"
```
</details>

<details>
<summary>自定义参数</summary>

```bash
# 自定义模型和批次大小
python scripts/run_pipeline.py "video.mp4" \
  --model gemini-2.0-flash-exp \
  --batch-size 30

# 自定义字号
python scripts/run_pipeline.py "video.mp4" \
  --zh-size 52 \
  --en-size 38

# 使用自定义术语表
python scripts/run_pipeline.py "video.mp4" \
  --glossary "my-glossary.json"

# 禁用文案生成
python scripts/run_pipeline.py "video.mp4" --no-copy

# 强制重新运行所有步骤
python scripts/run_pipeline.py "video.mp4" --force
```
</details>

<details>
<summary>YouTube 认证</summary>

```bash
# 使用 cookies 文件
python scripts/run_pipeline.py --url "URL" \
  --cookies "cookies.txt"

# 从浏览器加载 cookies
python scripts/run_pipeline.py --url "URL" \
  --cookies-from-browser "chrome:Profile 2"

# 禁用 YouTube 字幕，强制 Gemini 转录
python scripts/run_pipeline.py --url "URL" \
  --no-youtube-captions
```
</details>

---

## 分步执行

如需手动控制每个步骤，可单独调用各脚本：

```bash
# 1. 检查环境
python scripts/check_env.py --strict

# 2. 下载 YouTube 视频（如需要）
python scripts/download_youtube.py \
  --url "<url>" \
  --download-dir downloads \
  --out-meta downloads/_meta/meta.json

# 3. 转录英文
python scripts/transcribe_gemini.py \
  --in "video.mp4" \
  --out "subs/en.raw.srt"

# 4. 翻译为双语
python scripts/translate_bilingual.py \
  --in "subs/en.raw.srt" \
  --out "subs/zh_en.srt" \
  --batch-size 20

# 5. 生成 ASS 字幕
python scripts/srt_to_ass.py \
  --in "subs/zh_en.srt" \
  --out "subs/zh_en.ass" \
  --zh-size 48 \
  --en-size 34

# 6. 烧录字幕
python scripts/burn_ass.py \
  --video "video.mp4" \
  --ass "subs/zh_en.ass" \
  --out "final_videos/video.zh-en-hard.mp4"

# 7. 生成文案（可选）
python scripts/generate_copy.py \
  --video "video.mp4" \
  --srt "subs/zh_en.srt" \
  --out "output/video.copy.json"
```

---

## 工作流程

```
输入 → 环境检查 → 下载视频（YouTube 模式）
     → 英文转录（Gemini / YouTube 字幕）
     → 中英翻译（Gemini + 术语表）
     → 生成 ASS 样式
     → 审核暂停（生成 review 文件）
     → 烧录硬字幕（ffmpeg）
     → 文案生成（可选）
```

---

## 输出结构

```
downloads/                          # YouTube 下载的源视频
downloads/_meta/*.source.json       # YouTube 下载元数据
subs/*.en.raw.srt                   # 英文转录字幕
subs/*.zh_en.srt                    # 中英双语 SRT
subs/*.zh_en.ass                    # 带样式的 ASS 字幕
output/*.subtitle-review.txt        # 字幕审核文件
output/*.pipeline-manifest.json     # 缓存元数据
output/*.copy.json                  # 发布文案（标题/描述/标签）
output/logs/*.ffmpeg.log            # ffmpeg 烧录日志
final_videos/*.zh-en-hard.mp4       # 最终硬字幕视频
```

---

## 项目结构

| 文件/目录 | 说明 |
|-----------|------|
| `SKILL.md` | Claude Code Skill 执行指南（Skill 核心） |
| `scripts/run_pipeline.py` | 主流水线（一键模式） |
| `scripts/download_youtube.py` | YouTube 视频下载 |
| `scripts/transcribe_gemini.py` | Gemini 音频转录 |
| `scripts/translate_bilingual.py` | 英译中 + 双语 SRT 生成 |
| `scripts/srt_to_ass.py` | SRT 转 ASS 样式 |
| `scripts/burn_ass.py` | ffmpeg 硬字幕烧录 |
| `scripts/generate_copy.py` | 短视频文案生成 |
| `scripts/common.py` | 共享工具函数 |
| `scripts/check_env.py` | 环境依赖检查 |
| `tests/` | 单元测试 |
| `.env.example` | 环境变量模板 |

---

## 常见问题

**Q: 首次运行需要做什么？**
A: 只需配置 `GEMINI_API_KEY`。其他依赖（ffmpeg、yt-dlp）会在运行时自动检查并提示安装。

**Q: YouTube 视频下载失败怎么办？**
A: 对于年龄限制或私有视频，需要提供认证。在 `.env.local` 中设置 `YTDLP_COOKIE_FILE` 或 `YTDLP_COOKIES_FROM_BROWSER`，或使用命令行参数 `--cookies` / `--cookies-from-browser`。

**Q: 如何获取 YouTube cookies？**
A: 使用浏览器扩展（如 Get cookies.txt LOCALLY）导出 Netscape 格式的 cookies.txt 文件，或直接使用 `--cookies-from-browser chrome` 从浏览器加载。

**Q: Gemini API 超时或无法访问？**
A: 检查网络连接和 API Key 配额。国内用户可能需要配置代理。

**Q: 字幕翻译质量不满意？**
A: 可以在审核阶段手动编辑 `subs/*.zh_en.srt` 文件，然后用 `--resume` 继续流水线。也可以通过 `--glossary` 提供术语表提升专业术语准确性。

**Q: 如何跳过审核直接烧录？**
A: 不推荐，但如果确实需要，可以在首次运行时同时传入 `--approve-burn`。注意首次运行仍会暂停，需要第二次运行 `--approve-burn --resume` 才会烧录。

**Q: 缓存没有生效？**
A: 检查 `output/*.pipeline-manifest.json` 是否存在。如果修改了模型、批次大小、术语表等参数，缓存会自动失效。使用 `--force` 可以强制重新运行所有步骤。

**Q: 可以同时处理多个本地视频吗？**
A: 当前版本不支持。可以多次运行命令，或编写脚本循环调用。批量处理仅支持 YouTube URL。

**Q: ffmpeg 找不到怎么办？**
A: 确保 ffmpeg 在 PATH 中，或在 `.env.local` 中设置 `FFMPEG_BIN` 指向 ffmpeg 可执行文件路径。也可以安装 `imageio-ffmpeg` 作为备用：`pip install imageio-ffmpeg`。

---

## 测试

```bash
# 运行所有测试
python -m unittest discover -s tests -q

# 提交前检查敏感信息
python scripts/check_repo_safety.py --strict
```

---

## 安全规范

- 禁止提交 `.env`、`.env.local` 或包含密钥的文件
- 避免在命令行传递 API 密钥（shell 历史可能泄露）
- 推送前务必运行 `python scripts/check_repo_safety.py --strict`
- GitHub Actions 包含自动密钥扫描（`.github/workflows/secret-scan.yml`）

---

## 贡献指南

1. Fork 本仓库
2. 创建功能分支
3. 添加测试并确保通过
4. 运行 `python scripts/check_repo_safety.py --strict`
5. 提交 Pull Request

---

## License

[MIT License](LICENSE)
