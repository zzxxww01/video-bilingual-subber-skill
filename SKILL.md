---
name: video-bilingual-subber
description: Generate bilingual Chinese-English hard subtitles for local videos or YouTube URLs with Gemini, where Chinese is larger and displayed above English, and optionally generate short-video copy. Trigger when users ask to add CN+EN subtitles to xxx.mp4, burn bilingual captions into video, process a YouTube URL into a subtitle-burned final MP4, or generate title/description/hashtags from the same video.
---

# Video Bilingual Subber

Run this workflow for local short videos or YouTube URLs with Gemini API.

## Codex Execution Rule

When Codex is executing this skill for a user, do **not** run the whole pipeline straight through before user review.

Required interaction gate:
- Run only until the bilingual SRT is ready.
- Then stop and review the subtitles with the user directly in the chat.
- Codex should read the generated bilingual SRT itself and present a concise review sample in the conversation.
- Codex should ask the user whether the subtitles look correct and whether to continue.
- Wait for an explicit confirmation such as `continue` / `confirm` / `approve`.
- Only after that confirmation may Codex continue to ASS generation, hard-sub burn, and copy generation.
- Do not treat "I wrote the file" or "here is the path" as sufficient review.

This means Codex should prefer the step-by-step workflow below over the one-command pipeline during an interactive session.

## Required Environment

- Set `GEMINI_API_KEY` in environment or in `.env.local` (recommended from `.env.example`).
- Optional: set `GEMINI_MODEL` in environment or `.env.local` to override the default model across scripts.
- Optional: set `YTDLP_COOKIE_FILE` or `YTDLP_COOKIES_FROM_BROWSER` in `.env` / `.env.local` for authenticated YouTube downloads.
- Ensure Python 3.10+ is available.
- Install dependencies:
  - `requests`
  - `imageio-ffmpeg` (only needed when system `ffmpeg` is unavailable)
  - `yt-dlp` (only needed for YouTube URL input)
- Before uploading this skill to GitHub, run:
  - `python .codex/skills/video-bilingual-subber/scripts/check_repo_safety.py --strict`

## Workflow

1. Check environment:
   - `python .codex/skills/video-bilingual-subber/scripts/check_env.py`
2. If the input is a YouTube URL, download the video first:
   - `python .codex/skills/video-bilingual-subber/scripts/download_youtube.py --url "<youtube_url>" --download-dir "downloads" --out-meta "downloads/_meta/<id>.source.json" --captions-mode prefer`
   - If English YouTube captions exist, prefer them; otherwise the pipeline falls back to Gemini transcription.
3. Transcribe English subtitles from local video or downloaded YouTube video:
   - `python .codex/skills/video-bilingual-subber/scripts/transcribe_gemini.py --in "<video>.mp4" --out "subs/en.raw.srt" --model "gemini-3-pro-preview"`
4. Translate to Chinese and build bilingual SRT (Chinese first line, English second line):
   - `python .codex/skills/video-bilingual-subber/scripts/translate_bilingual.py --in "subs/en.raw.srt" --out "subs/zh_en.srt" --model "gemini-3-pro-preview" --batch-size 20`
5. **Stop here for human review when Codex is driving the workflow.**
   - Codex must open/read `subs/zh_en.srt` itself.
   - Show the user a concise sample directly in chat.
   - Ask for explicit confirmation before proceeding.
   - If the user requests subtitle fixes, make those fixes first and ask for confirmation again.
6. Convert bilingual SRT to ASS with larger Chinese subtitles:
   - `python .codex/skills/video-bilingual-subber/scripts/srt_to_ass.py --in "subs/zh_en.srt" --out "subs/zh_en.ass" --zh-size 48 --en-size 34`
7. Burn ASS subtitles into MP4:
   - `python .codex/skills/video-bilingual-subber/scripts/burn_ass.py --video "<video>.mp4" --ass "subs/zh_en.ass" --out "final_videos/<video>.zh-en-hard.mp4"`
8. Generate simple copy package:
   - `python .codex/skills/video-bilingual-subber/scripts/generate_copy.py --video "<video>.mp4" --srt "subs/zh_en.srt" --model "gemini-3-pro-preview" --out "output/<video>.copy.json"`

### Manual One-Command Run

- `python .codex/skills/video-bilingual-subber/scripts/run_pipeline.py "<video>.mp4"`
- `python .codex/skills/video-bilingual-subber/scripts/run_pipeline.py --url "<youtube_url>"`
- `python .codex/skills/video-bilingual-subber/scripts/run_pipeline.py --url "<u1>" --url "<u2>"`

Use this only for manual shell usage when an interactive Codex checkpoint is not needed.

This command does all of the following:
- Use model `gemini-3-pro-preview`.
- Accept either a local video path or one/more `--url` YouTube inputs.
- Download YouTube inputs into `downloads/` before subtitle generation.
- Prefer YouTube English captions when available unless `--no-youtube-captions` is used.
- Generate bilingual subtitles (Chinese first line, English second line).
- Generate ASS style with larger Chinese text.
- Generate subtitle review text file for manual confirmation.
- Track output metadata in `output/*.pipeline-manifest.json` so later runs can detect stale cached artifacts after parameter changes.
- Stop before burning; the first run always holds for review even if `--approve-burn` was passed.
- Resume from existing outputs if previous run already produced partial files.

### Required Confirm-Before-Burn Step

After reviewing subtitles, burn with explicit approval:

- `python .codex/skills/video-bilingual-subber/scripts/run_pipeline.py "<video>.mp4" --approve-burn --resume`
- `python .codex/skills/video-bilingual-subber/scripts/run_pipeline.py --url "<youtube_url>" --approve-burn --resume`

This forced two-step workflow is acceptable for direct terminal use, but when Codex is executing the skill it should still pause after Step 3, inspect the generated subtitles itself, and ask the user directly before continuing.

Optional:
- Disable copy generation: `--no-copy`
- Force full rerun: `--force`
- Disable glossary: `--no-glossary`
- Use a Netscape cookies file for YouTube auth: `--cookies "C:\path\to\cookies.txt"`
- Disable YouTube caption download and always use Gemini transcription: `--no-youtube-captions`

## Output Contract

- `downloads/*`: downloaded source videos and normalized English caption SRTs for YouTube mode.
- `downloads/_meta/*.source.json`: YouTube download metadata used to resume without redownloading.
- `subs/en.raw.srt`: English transcription SRT.
- `subs/zh_en.srt`: bilingual SRT.
- `subs/zh_en.ass`: styled ASS subtitles (Chinese larger).
- `output/*.subtitle-review.txt`: review sample for subtitle confirmation.
- `output/*.pipeline-manifest.json`: pipeline metadata used for cache invalidation.
- `final_videos/*.zh-en-hard.mp4`: hard-subtitled video only.
- `output/logs/*.ffmpeg.log`: burn logs.
- `output/*.copy.json`: copy package with `title`, `description`, `hashtags`.

## Notes

- Keep Chinese on the first line and English on the second line in each subtitle block.
- Local video input remains fully supported; YouTube URL input is additive.
- Use glossary JSON when terminology consistency matters:
  - `--glossary ".codex/skills/video-bilingual-subber/references/glossary.sample.json"`
- Script prompts live in `references/prompts.md`.
- When the input filename contains spaces, `burn_ass.py` uses a temporary safe path for subtitle burning.
