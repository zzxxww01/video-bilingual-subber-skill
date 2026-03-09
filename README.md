# Video Bilingual Subber

一个 Claude Code Skill，用于为视频自动生成中英双语硬字幕。

## 这是什么？

这是一个 **Claude Code Skill**（技能插件），可以让 Claude 自动为你的视频添加专业的中英双语字幕。当你在 Claude Code 中说"给这个视频加双语字幕"或"处理这个 YouTube 视频"时，Claude 会自动调用这个 skill 来完成任务。

### Skill vs 普通工具

- **Skill（技能）**：Claude 根据你的需求自动识别并调用，无需手动指定
- **触发方式**：自然语言描述任务即可，如"给 video.mp4 加中英字幕"
- **智能执行**：Claude 会自动选择合适的参数和流程
- **交互式审核**：在烧录字幕前会暂停让你确认翻译质量

## 功能特性

### 自动化流程
- **音频转录** — 使用 Gemini API 将视频音频转为英文字幕
- **智能翻译** — 英文自动翻译为简体中文，支持术语表
- **双语字幕** — 中文（大字号）在上，英文（小字号）在下
- **硬字幕烧录** — 使用 ffmpeg 将字幕永久嵌入视频
- **文案生成** — 可选生成短视频发布文案（标题、描述、标签）

### 输入源支持
- **本地视频** — MP4、MOV、MKV、M4V、WEBM 格式
- **YouTube 视频** — 自动下载，优先使用 YouTube 英文字幕
- **批量处理** — 支持多个 YouTube URL 批量处理

### 智能缓存
- **增量运行** — 自动跳过已完成的步骤
- **参数追踪** — 修改模型、批次大小、术语表等参数时自动重新生成
- **性能优化** — 大文件（>100MB）跳过 SHA256 计算

## 快速开始

### 1. 环境配置

```bash
# 复制配置模板
cp .env.example .env.local

# 编辑 .env.local，填入你的 API Key
GEMINI_API_KEY=你的_gemini_api_key
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

需要：
- Python 3.10+
- `ffmpeg`（需在 PATH 中，或通过 `FFMPEG_BIN` 指定）
- 依赖包：`requests`、`imageio-ffmpeg`、`yt-dlp`

### 3. 在 Claude Code 中使用

直接用自然语言告诉 Claude：

```
"给 video.mp4 添加中英双语字幕"
"处理这个 YouTube 视频：https://www.youtube.com/watch?v=xxx"
"批量处理这些 YouTube 视频并加双语字幕"
```

Claude 会自动：
1. 检查环境配置
2. 下载视频（如果是 YouTube）
3. 转录英文字幕
4. 翻译为中文
5. **暂停并展示字幕样本让你审核**
6. 等你确认后继续生成 ASS 样式
7. 烧录硬字幕到视频
8. 可选生成发布文案

### 4. 手动命令行使用

如果你想直接在终端运行（不通过 Claude）：

```bash
# 本地视频
python scripts/run_pipeline.py "video.mp4"

# YouTube 视频
python scripts/run_pipeline.py --url "https://www.youtube.com/watch?v=VIDEO_ID"

# 批量处理
python scripts/run_pipeline.py --url "URL1" --url "URL2" --url "URL3"
```

首次运行会在生成字幕后暂停，生成审核文件 `output/*.subtitle-review.txt`。确认无误后：

```bash
python scripts/run_pipeline.py "video.mp4" --approve-burn --resume
```

## Skill 触发条件

当你在 Claude Code 中提到以下内容时，这个 skill 会自动激活：

- "添加双语字幕"、"加中英字幕"
- "burn Chinese and English captions"
- "处理 YouTube 视频"、"生成双语字幕"
- "双语字幕"、"中英字幕"
- 想要创建带中英硬字幕的视频
- 从视频内容生成短视频文案

## 环境变量配置

在 `.env.local` 中配置：

```env
# 必需
GEMINI_API_KEY=你的_gemini_api_key

# 可选：全局覆盖默认模型
GEMINI_MODEL=gemini-3-pro-preview

# 可选：YouTube 认证（二选一）
YTDLP_COOKIE_FILE=C:\路径\到\cookies.txt
YTDLP_COOKIES_FROM_BROWSER=chrome:Profile 2

# 可选：自定义 ffmpeg 路径
FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe
```

## 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--model` | Gemini 模型名称 | `gemini-3-pro-preview` |
| `--batch-size` | 翻译批次大小 | 20 |
| `--zh-size` | 中文字号 | 48 |
| `--en-size` | 英文字号 | 34 |
| `--glossary` | 术语表 JSON 路径 | `references/glossary.sample.json` |
| `--no-glossary` | 禁用术语表 | - |
| `--copy` / `--no-copy` | 启用/禁用文案生成 | 启用 |
| `--resume` | 跳过已完成步骤 | 默认 |
| `--force` | 强制重新运行 | - |
| `--approve-burn` | 允许烧录字幕 | 烧录时必需 |
| `--no-youtube-captions` | 强制使用 Gemini 转录 | - |
| `--cookies` | YouTube cookies 文件 | - |
| `--cookies-from-browser` | 从浏览器加载 cookies | - |

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

## 术语表格式

创建 `references/glossary.sample.json` 确保专业术语翻译一致：

```json
{
  "AI": "人工智能",
  "machine learning": "机器学习",
  "neural network": "神经网络",
  "deep learning": "深度学习"
}
```

流水线会自动加载此文件（如果存在）。使用 `--glossary <路径>` 指定自定义术语表，或 `--no-glossary` 禁用。

## 分步执行

如需手动控制每个步骤：

```bash
# 1. 检查环境
python scripts/check_env.py --strict

# 2. 下载 YouTube 视频（如需要）
python scripts/download_youtube.py --url "<url>" --download-dir downloads --out-meta downloads/_meta/meta.json

# 3. 转录英文
python scripts/transcribe_gemini.py --in "video.mp4" --out "subs/en.raw.srt"

# 4. 翻译为双语
python scripts/translate_bilingual.py --in "subs/en.raw.srt" --out "subs/zh_en.srt" --batch-size 20

# 5. 生成 ASS 字幕
python scripts/srt_to_ass.py --in "subs/zh_en.srt" --out "subs/zh_en.ass" --zh-size 48 --en-size 34

# 6. 烧录字幕
python scripts/burn_ass.py --video "video.mp4" --ass "subs/zh_en.ass" --out "final_videos/video.zh-en-hard.mp4"

# 7. 生成文案（可选）
python scripts/generate_copy.py --video "video.mp4" --srt "subs/zh_en.srt" --out "output/video.copy.json"
```

## YouTube 认证

对于年龄限制或私有视频，提供认证信息：

**方法 1：Cookies 文件**
```bash
python scripts/run_pipeline.py --url "<url>" --cookies "cookies.txt"
```

**方法 2：浏览器 Cookies**
```bash
python scripts/run_pipeline.py --url "<url>" --cookies-from-browser "chrome:Profile 2"
```

**方法 3：环境变量**
```env
YTDLP_COOKIE_FILE=C:\路径\到\cookies.txt
# 或
YTDLP_COOKIES_FROM_BROWSER=chrome:Default
```

## 测试

```bash
# 运行所有测试
python -m unittest discover -s tests -q

# 提交前检查敏感信息
python scripts/check_repo_safety.py --strict
```

## 常见问题

### ffmpeg 未找到
```bash
# 安装 imageio-ffmpeg 作为备用
pip install imageio-ffmpeg

# 或设置自定义路径
export FFMPEG_BIN=/path/to/ffmpeg
```

### YouTube 下载失败
```bash
# 使用 cookies 认证
python scripts/run_pipeline.py --url "URL" --cookies "cookies.txt"

# 或从浏览器加载
python scripts/run_pipeline.py --url "URL" --cookies-from-browser "chrome"
```

### Gemini API 错误
- 检查 `GEMINI_API_KEY` 是否正确设置
- 验证 API 配额和计费状态
- 检查网络连接
- 查看 `output/logs/*.ffmpeg.log` 了解烧录错误

### 缓存未失效
- 使用 `--force` 绕过缓存
- 删除 `output/*.pipeline-manifest.json` 重置
- 用 `ls -l subs/` 检查文件时间戳

## 安全规范

- 禁止提交 `.env`、`.env.local` 或包含密钥的文件
- 避免在命令行传递 API 密钥（shell 历史可能泄露）
- 推送前务必运行 `python scripts/check_repo_safety.py --strict`
- GitHub Actions 包含自动密钥扫描（`.github/workflows/secret-scan.yml`）

## 开源协议

本项目采用 MIT 协议开源。详见 [LICENSE](LICENSE) 文件。

## 贡献指南

1. Fork 本仓库
2. 创建功能分支
3. 添加测试并确保通过
4. 运行 `python scripts/check_repo_safety.py --strict`
5. 提交 Pull Request

## 技术支持

遇到问题或有疑问：
- 查看现有 GitHub Issues
- 阅读 [SKILL.md](SKILL.md) 了解详细文档
- 运行测试验证配置：`python -m unittest discover -s tests -q`

## 相关链接

- [Claude Code 文档](https://docs.anthropic.com/claude/docs)
- [Gemini API 文档](https://ai.google.dev/docs)
- [yt-dlp 文档](https://github.com/yt-dlp/yt-dlp)
