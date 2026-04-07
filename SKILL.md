---
name: video-bilingual-subber
description: Generate Chinese-only or bilingual Chinese-English hard subtitles for videos. Use this skill when the user asks to "add subtitles", "add Chinese subtitles", "add bilingual subtitles", "add CN+EN subtitles", "burn Chinese captions", "burn Chinese and English captions", "process video with subtitles", "generate bilingual subs", mentions "中文字幕", "双语字幕", "中英字幕", or wants to create hard-subtitled videos. Also applies when user wants to generate short-video copy (title/description/hashtags) from video content.
license: MIT License - see LICENSE file
---

# Video Bilingual Subber

This skill generates production-ready subtitle videos using Gemini API for transcription and translation. It supports bilingual Chinese-English output and Chinese-only hard subtitles.

## When This Skill Applies

Use this skill when the user wants to:
- Add Chinese-only subtitles to videos
- Add bilingual Chinese-English subtitles to videos
- Process local video files (MP4, MOV, MKV, M4V, WEBM)
- Download and subtitle YouTube videos
- Process multiple videos one by one with review checkpoints
- Generate short-video publishing copy (title, description, hashtags)
- Create hard-subtitled videos with burned-in captions

## Core Workflow

### Interactive Mode (Recommended for Codex)

When executing this skill interactively, follow this gated workflow:

1. **Environment Check**
   ```bash
   python scripts/check_env.py --strict
   ```

2. **Download (YouTube only)**
   ```bash
   python scripts/download_youtube.py --url "<youtube_url>" --download-dir downloads --out-meta downloads/_meta/meta.json
   ```

3. **Transcribe English**
   ```bash
   python scripts/transcribe_gemini.py --in "<video>.mp4" --out "subs/en.raw.srt"
   ```

4. **Translate to Subtitle Output**
   ```bash
   # Bilingual output
   python scripts/translate_bilingual.py --in "subs/en.raw.srt" --out "subs/zh_en.srt" --batch-size 20 --layout bilingual

   # Chinese-only output
   python scripts/translate_bilingual.py --in "subs/en.raw.srt" --out "subs/zh.srt" --batch-size 20 --layout zh-only
   ```

5. **STOP FOR REVIEW** ⚠️
   - Read the generated subtitle file (`subs/zh_en.srt` or `subs/zh.srt`)
   - Even for Chinese-only output, show the user Chinese and English together during review so they can verify the translation against the source line
   - Send the user the complete subtitle list in the conversation for review, not just a sample
   - If the subtitle list is Chinese-only, still include the corresponding English lines alongside each entry during review
   - Ask: "Please review these subtitles. Do they look correct? Should I continue?"
   - Wait for explicit confirmation: "yes", "continue", "approve", "looks good"
   - If user requests changes, make edits and ask for confirmation again
   - If the request includes multiple videos, stop here for the current video and do not start the next video until the user explicitly approves this one

6. **Convert to ASS** (only after approval)
   ```bash
   # Bilingual output
   python scripts/srt_to_ass.py --in "subs/zh_en.srt" --out "subs/zh_en.ass" --zh-size 48 --en-size 34 --layout bilingual

   # Chinese-only output
   python scripts/srt_to_ass.py --in "subs/zh.srt" --out "subs/zh.ass" --zh-size 48 --en-size 34 --layout zh-only
   ```

7. **Burn Subtitles** (only after approval)
   ```bash
   # Bilingual output
   python scripts/burn_ass.py --video "<video>.mp4" --ass "subs/zh_en.ass" --out "final_videos/<video>.zh-en-hard.mp4"

   # Chinese-only output
   python scripts/burn_ass.py --video "<video>.mp4" --ass "subs/zh.ass" --out "final_videos/<video>.zh-hard.mp4"
   ```

8. **Generate Copy** (optional)
   ```bash
   # Bilingual output
   python scripts/generate_copy.py --video "<video>.mp4" --srt "subs/zh_en.srt" --out "output/<video>.copy.json"

   # Chinese-only output
   python scripts/generate_copy.py --video "<video>.mp4" --srt "subs/zh.srt" --out "output/<video>.zh.copy.json"
   ```

### One-Command Mode (Manual Shell Usage)

For direct terminal use without interactive review:

```bash
# Local video
python scripts/run_pipeline.py "video.mp4"

# Local video, Chinese-only
python scripts/run_pipeline.py "video.mp4" --zh-only

# YouTube single URL
python scripts/run_pipeline.py --url "https://www.youtube.com/watch?v=VIDEO_ID"

# YouTube batch
python scripts/run_pipeline.py --url "URL1" --url "URL2" --url "URL3"
```

For interactive multi-video requests in Codex, do not use one batch command for local videos or mixed sources. Process one video at a time, stop for review, wait for explicit approval, burn that video, and only then move to the next one.

The pipeline will stop after generating subtitles and create `output/*.subtitle-review.txt`. After manual review:

```bash
python scripts/run_pipeline.py "video.mp4" --approve-burn --resume
```

## Key Features

### Input Sources
- **Local videos**: MP4, MOV, MKV, M4V, WEBM formats
- **YouTube URLs**: Automatic download with yt-dlp
- **YouTube captions**: Prefers existing English captions when available
- **Batch processing**: Multiple URLs processed sequentially with failure tolerance

### Subtitle Generation
- **Transcription**: Gemini API audio-to-text (or YouTube caption reuse)
- **Translation**: English → Simplified Chinese with batch processing
- **Glossary support**: Consistent terminology via JSON glossary
- **Bilingual format**: Chinese (larger) above English (smaller)
- **Chinese-only mode**: Burn only Simplified Chinese subtitles with `--zh-only`
- **ASS styling**: Customizable font sizes and positioning

### Caching & Incremental Runs
- **Manifest tracking**: `output/*.pipeline-manifest.json` records all artifact metadata
- **Smart invalidation**: Changing model, batch-size, glossary, or font sizes invalidates downstream cache
- **Resume mode**: `--resume` skips completed steps (default behavior)
- **Force mode**: `--force` reruns all steps regardless of cache

### Performance Optimizations
- **Large file fingerprinting**: Files >100MB skip SHA256, use size+mtime only
- **Batch translation**: Configurable batch size (default 20 entries)
- **Parallel processing**: Independent YouTube downloads can run concurrently

## Environment Setup

### Required
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### Optional
```env
# Override default model globally
GEMINI_MODEL=gemini-3-pro-preview

# YouTube authentication (choose one)
YTDLP_COOKIE_FILE=C:\path\to\cookies.txt
YTDLP_COOKIES_FROM_BROWSER=chrome:Profile 2

# Custom ffmpeg path
FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe
```

Place these in `.env.local` (recommended) or export as environment variables.

## Common Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--model` | Gemini model name | `gemini-3-pro-preview` |
| `--batch-size` | Translation batch size | 20 |
| `--zh-size` | Chinese font size | 48 |
| `--en-size` | English font size | 34 |
| `--glossary` | Terminology JSON path | `references/glossary.sample.json` |
| `--no-glossary` | Disable glossary | - |
| `--copy` / `--no-copy` | Enable/disable copy generation | Enabled |
| `--resume` | Skip completed steps | Default |
| `--force` | Rerun all steps | - |
| `--approve-burn` | Allow subtitle burning | Required for burn |
| `--review-lines` | Review sample size | 12 |
| `--zh-only` | Output Chinese-only subtitles | Disabled |
| `--no-youtube-captions` | Force Gemini transcription | - |
| `--cookies` | YouTube cookies file | - |
| `--cookies-from-browser` | Browser cookie source | - |
| `--download-dir` | YouTube download directory | `downloads` |

## Output Structure

```
downloads/                          # YouTube source videos
downloads/_meta/*.source.json       # YouTube metadata
subs/*.en.raw.srt                   # English transcription
subs/*.zh_en.srt                    # Bilingual SRT
subs/*.zh_en.ass                    # Styled bilingual ASS subtitles
subs/*.zh.srt                       # Chinese-only SRT
subs/*.zh.ass                       # Styled Chinese-only ASS subtitles
output/*.subtitle-review.txt        # Review sample
output/*.zh.subtitle-review.txt     # Chinese-only review sample
output/*.pipeline-manifest.json     # Cache metadata
output/*.zh.pipeline-manifest.json  # Chinese-only cache metadata
output/*.copy.json                  # Publishing copy
output/logs/*.ffmpeg.log            # Burn logs
final_videos/*.zh-en-hard.mp4       # Final bilingual output
final_videos/*.zh-hard.mp4          # Final Chinese-only output
```

## Glossary Format

Create `references/glossary.sample.json` for consistent terminology:

```json
{
  "AI": "人工智能",
  "machine learning": "机器学习",
  "neural network": "神经网络"
}
```

The pipeline automatically loads this file if it exists. Use `--glossary <path>` for custom glossaries or `--no-glossary` to disable.

## YouTube Authentication

For age-restricted or private videos, provide authentication:

**Method 1: Cookies file**
```bash
python scripts/run_pipeline.py --url "<url>" --cookies "cookies.txt"
```

**Method 2: Browser cookies**
```bash
python scripts/run_pipeline.py --url "<url>" --cookies-from-browser "chrome:Profile 2"
```

**Method 3: Environment variable**
```env
YTDLP_COOKIE_FILE=C:\path\to\cookies.txt
# or
YTDLP_COOKIES_FROM_BROWSER=chrome:Default
```

## Error Handling

- **Batch mode**: Individual URL failures don't block other URLs
- **Retry logic**: Gemini API calls retry 3 times with exponential backoff
- **Cleanup**: Uploaded Gemini files are deleted even on failure (unless `--keep-upload`)
- **Validation**: Environment checks run before expensive operations

## Testing

```bash
# Run all tests
python -m unittest discover -s tests -q

# Check for secrets before commit
python scripts/check_repo_safety.py --strict
```

## Important Notes

- **Review gate**: Always stop after subtitle generation for user review in interactive mode
- **Full review content**: During interactive review, paste the full subtitle set into the conversation. Do not send only the first few entries unless the user explicitly asks for a sample.
- **Multi-video interactive rule**: For multiple local videos or mixed inputs, process exactly one video at a time and wait for approval before starting the next
- **Burn approval**: The `--approve-burn` flag is required to burn subtitles into video
- **First run behavior**: Even with `--approve-burn`, first run stops for review
- **Manifest tracking**: Changing parameters invalidates downstream cache automatically
- **YouTube captions**: Preferred when available; use `--no-youtube-captions` to force Gemini
- **Dotenv search**: Searches up to git repository root, not entire drive
- **UTF-8 handling**: Automatically configured for Windows console compatibility

## Security

- Never commit `.env`, `.env.local`, or files containing secrets
- Avoid passing API keys via command line (shell history risk)
- Run `python scripts/check_repo_safety.py --strict` before git push
- GitHub Actions includes automated secret scanning

## Dependencies

```
requests>=2.31.0
imageio-ffmpeg>=0.5.1  # Fallback when system ffmpeg unavailable
yt-dlp>=2025.1.15      # YouTube download support
```

Install with:
```bash
pip install -r requirements.txt
```
