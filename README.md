# Video Bilingual Subber

A Claude Code skill for generating production-ready bilingual Chinese-English subtitle videos using Gemini API.

## Overview

This skill automatically:
- Transcribes video audio to English subtitles (or reuses YouTube captions)
- Translates English to Simplified Chinese
- Generates bilingual SRT/ASS files (Chinese above English)
- Burns hard subtitles into video with customizable styling
- Optionally generates short-video publishing copy

## Quick Start

### 1. Setup Environment

```bash
# Copy example config
cp .env.example .env.local

# Edit .env.local
GEMINI_API_KEY=your_api_key_here
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Requires:
- Python 3.10+
- `ffmpeg` in PATH (or set `FFMPEG_BIN`)
- `requests`, `imageio-ffmpeg`, `yt-dlp`

### 3. Run Pipeline

**Local video:**
```bash
python scripts/run_pipeline.py "video.mp4"
```

**YouTube video:**
```bash
python scripts/run_pipeline.py --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

**Batch YouTube:**
```bash
python scripts/run_pipeline.py --url "URL1" --url "URL2" --url "URL3"
```

### 4. Review and Burn

After subtitle generation, review `output/*.subtitle-review.txt`, then:

```bash
python scripts/run_pipeline.py "video.mp4" --approve-burn --resume
```

## Features

### Input Sources
- **Local videos**: MP4, MOV, MKV, M4V, WEBM
- **YouTube URLs**: Auto-download with yt-dlp
- **YouTube captions**: Prefers existing English captions
- **Batch processing**: Multiple URLs with failure tolerance

### Subtitle Pipeline
1. **Transcription**: Gemini audio-to-text or YouTube caption reuse
2. **Translation**: English → Chinese with batch processing (default 20 entries)
3. **Glossary**: Optional terminology consistency via JSON
4. **Styling**: ASS format with larger Chinese (48pt) above smaller English (34pt)
5. **Burning**: ffmpeg hard-subtitle integration

### Caching & Incremental Runs
- **Manifest tracking**: Records all artifact metadata in `output/*.pipeline-manifest.json`
- **Smart invalidation**: Changing model/batch-size/glossary/fonts invalidates downstream cache
- **Resume mode**: `--resume` skips completed steps (default)
- **Force mode**: `--force` reruns everything

### Performance
- Files >100MB skip SHA256 (use size+mtime fingerprint)
- Configurable batch translation size
- Dotenv search stops at git repo root

## Common Usage

### Basic Options
```bash
# Custom model
python scripts/run_pipeline.py "video.mp4" --model gemini-2.0-flash-exp

# Custom batch size
python scripts/run_pipeline.py "video.mp4" --batch-size 30

# Custom font sizes
python scripts/run_pipeline.py "video.mp4" --zh-size 52 --en-size 38

# Use custom glossary
python scripts/run_pipeline.py "video.mp4" --glossary "my-glossary.json"

# Disable copy generation
python scripts/run_pipeline.py "video.mp4" --no-copy

# Force full rerun
python scripts/run_pipeline.py "video.mp4" --force
```

### YouTube Options
```bash
# Disable YouTube captions (force Gemini transcription)
python scripts/run_pipeline.py --url "URL" --no-youtube-captions

# Use cookies for authentication
python scripts/run_pipeline.py --url "URL" --cookies "cookies.txt"

# Load cookies from browser
python scripts/run_pipeline.py --url "URL" --cookies-from-browser "chrome:Profile 2"

# Custom download directory
python scripts/run_pipeline.py --url "URL" --download-dir "my-downloads"
```

## Environment Variables

Create `.env.local` with:

```env
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Override default model globally
GEMINI_MODEL=gemini-3-pro-preview

# Optional: YouTube authentication (choose one)
YTDLP_COOKIE_FILE=C:\path\to\cookies.txt
YTDLP_COOKIES_FROM_BROWSER=chrome:Profile 2

# Optional: Custom ffmpeg path
FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe
```

## Output Structure

```
downloads/                          # YouTube source videos
downloads/_meta/*.source.json       # YouTube download metadata
subs/*.en.raw.srt                   # English transcription
subs/*.zh_en.srt                    # Bilingual SRT (Chinese + English)
subs/*.zh_en.ass                    # Styled ASS subtitles
output/*.subtitle-review.txt        # Review sample for manual check
output/*.pipeline-manifest.json     # Cache invalidation metadata
output/*.copy.json                  # Publishing copy (title/description/hashtags)
output/logs/*.ffmpeg.log            # ffmpeg burn logs
final_videos/*.zh-en-hard.mp4       # Final hard-subtitled video
```

## Step-by-Step Workflow

For manual control, run individual scripts:

```bash
# 1. Check environment
python scripts/check_env.py --strict

# 2. Download YouTube video (if needed)
python scripts/download_youtube.py --url "<url>" --download-dir downloads --out-meta downloads/_meta/meta.json

# 3. Transcribe English
python scripts/transcribe_gemini.py --in "video.mp4" --out "subs/en.raw.srt"

# 4. Translate to bilingual
python scripts/translate_bilingual.py --in "subs/en.raw.srt" --out "subs/zh_en.srt" --batch-size 20

# 5. Generate ASS
python scripts/srt_to_ass.py --in "subs/zh_en.srt" --out "subs/zh_en.ass" --zh-size 48 --en-size 34

# 6. Burn subtitles
python scripts/burn_ass.py --video "video.mp4" --ass "subs/zh_en.ass" --out "final_videos/video.zh-en-hard.mp4"

# 7. Generate copy (optional)
python scripts/generate_copy.py --video "video.mp4" --srt "subs/zh_en.srt" --out "output/video.copy.json"
```

## Glossary Format

Create `references/glossary.sample.json` for consistent terminology:

```json
{
  "AI": "人工智能",
  "machine learning": "机器学习",
  "neural network": "神经网络",
  "deep learning": "深度学习"
}
```

The pipeline automatically loads this file if present. Use `--glossary <path>` for custom glossaries or `--no-glossary` to disable.

## Testing

```bash
# Run all tests
python -m unittest discover -s tests -q

# Check for secrets before commit
python scripts/check_repo_safety.py --strict
```

## Security

- Never commit `.env`, `.env.local`, or files with secrets
- Avoid passing API keys via command line (shell history risk)
- Run `python scripts/check_repo_safety.py --strict` before pushing
- GitHub Actions includes automated secret scanning (`.github/workflows/secret-scan.yml`)

## Troubleshooting

### Missing ffmpeg
```bash
# Install imageio-ffmpeg as fallback
pip install imageio-ffmpeg

# Or set custom path
export FFMPEG_BIN=/path/to/ffmpeg
```

### YouTube download fails
```bash
# Use cookies for authentication
python scripts/run_pipeline.py --url "URL" --cookies "cookies.txt"

# Or load from browser
python scripts/run_pipeline.py --url "URL" --cookies-from-browser "chrome"
```

### Gemini API errors
- Check `GEMINI_API_KEY` is set correctly
- Verify API quota and billing
- Check network connectivity
- Review `output/logs/*.ffmpeg.log` for burn errors

### Cache not invalidating
- Use `--force` to bypass cache
- Delete `output/*.pipeline-manifest.json` to reset
- Check file timestamps with `ls -l subs/`

## License

See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run `python scripts/check_repo_safety.py --strict`
5. Submit pull request

## Support

For issues or questions:
- Check existing GitHub issues
- Review SKILL.md for detailed documentation
- Run tests to verify setup: `python -m unittest discover -s tests -q`
