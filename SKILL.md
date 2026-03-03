---
name: video-bilingual-subber
description: Generate bilingual Chinese-English hard subtitles for local videos with Gemini, where Chinese is larger and displayed above English, and optionally generate short-video copy. Trigger when users ask to add CN+EN subtitles to xxx.mp4, burn bilingual captions into video, export a subtitle-burned final MP4, or generate title/description/hashtags from the same video.
---

# Video Bilingual Subber

Run this workflow for local short videos and Gemini API.

## Required Environment

- Set `GEMINI_API_KEY` in environment or in `.env.local` (recommended from `.env.example`).
- Ensure Python 3.10+ is available.
- Install dependencies:
  - `requests`
  - `imageio-ffmpeg` (only needed when system `ffmpeg` is unavailable)
- Before uploading this skill to GitHub, run:
  - `python .codex/skills/video-bilingual-subber/scripts/check_repo_safety.py --strict`

## Workflow

1. Check environment:
   - `python .codex/skills/video-bilingual-subber/scripts/check_env.py`
2. Transcribe English subtitles from local video:
   - `python .codex/skills/video-bilingual-subber/scripts/transcribe_gemini.py --in "<video>.mp4" --out "subs/en.raw.srt" --model "gemini-3-pro-preview"`
3. Translate to Chinese and build bilingual SRT (Chinese first line, English second line):
   - `python .codex/skills/video-bilingual-subber/scripts/translate_bilingual.py --in "subs/en.raw.srt" --out "subs/zh_en.srt" --model "gemini-3-pro-preview" --batch-size 20`
4. Convert bilingual SRT to ASS with larger Chinese subtitles:
   - `python .codex/skills/video-bilingual-subber/scripts/srt_to_ass.py --in "subs/zh_en.srt" --out "subs/zh_en.ass" --zh-size 48 --en-size 34`
5. Burn ASS subtitles into MP4:
   - `python .codex/skills/video-bilingual-subber/scripts/burn_ass.py --video "<video>.mp4" --ass "subs/zh_en.ass" --out "final_videos/<video>.zh-en-hard.mp4"`
6. Generate simple copy package:
   - `python .codex/skills/video-bilingual-subber/scripts/generate_copy.py --video "<video>.mp4" --srt "subs/zh_en.srt" --model "gemini-3-pro-preview" --out "output/<video>.copy.json"`

### Default One-Command Run

- `python .codex/skills/video-bilingual-subber/scripts/run_pipeline.py "<video>.mp4"`

This default command does all of the following:
- Use model `gemini-3-pro-preview`.
- Generate bilingual subtitles (Chinese first line, English second line).
- Generate ASS style with larger Chinese text.
- Generate subtitle review text file for manual confirmation.
- Stop before burning (burn is blocked by default).
- Resume from existing outputs if previous run already produced partial files.

### Required Confirm-Before-Burn Step

After reviewing subtitles, burn with explicit approval:

- `python .codex/skills/video-bilingual-subber/scripts/run_pipeline.py "<video>.mp4" --approve-burn --resume`

This forced two-step workflow guarantees subtitle review before hard-sub burn.

Optional:
- Disable copy generation: `--no-copy`
- Force full rerun: `--force`
- Disable glossary: `--no-glossary`

## Output Contract

- `subs/en.raw.srt`: English transcription SRT.
- `subs/zh_en.srt`: bilingual SRT.
- `subs/zh_en.ass`: styled ASS subtitles (Chinese larger).
- `output/*.subtitle-review.txt`: review sample for subtitle confirmation.
- `final_videos/*.zh-en-hard.mp4`: hard-subtitled video only.
- `output/logs/*.ffmpeg.log`: burn logs.
- `output/*.copy.json`: copy package with `title`, `description`, `hashtags`.

## Notes

- Keep Chinese on the first line and English on the second line in each subtitle block.
- Use glossary JSON when terminology consistency matters:
  - `--glossary ".codex/skills/video-bilingual-subber/references/glossary.sample.json"`
- Script prompts live in `references/prompts.md`.
- When the input filename contains spaces, `burn_ass.py` uses a temporary safe path for subtitle burning.
