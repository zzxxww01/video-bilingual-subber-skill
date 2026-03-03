# Video Bilingual Subber

Generate Chinese-English hard subtitles for local videos with Gemini:
- Chinese text on the first line (larger)
- English text on the second line
- Optional short-video publish copy (`title`, `description`, `hashtags`)

## Requirements

- Python 3.10+
- `requests`
- `ffmpeg` available in `PATH` (or set `FFMPEG_BIN`)

## Quick Start

1. Create local env file:
```bash
cp .env.example .env.local
```
2. Edit `.env.local` and set:
```env
GEMINI_API_KEY=your_real_key
```
3. Run checks:
```bash
python scripts/check_env.py --strict
python scripts/check_repo_safety.py
```
4. Run pipeline:
```bash
python scripts/run_pipeline.py "your_video.mp4"
```
5. After review, approve burn:
```bash
python scripts/run_pipeline.py "your_video.mp4" --approve-burn --resume
```

## Security Rules

- Never commit `.env`, `.env.local`, private keys, or raw tokens.
- Do not pass secrets on command line when possible (shell history can leak them).
- Before pushing to GitHub, always run:
```bash
python scripts/check_repo_safety.py --strict
```
- GitHub Actions includes an automated secret scan workflow at `.github/workflows/secret-scan.yml`.

## Output Paths

- `subs/*.en.raw.srt`
- `subs/*.zh_en.srt`
- `subs/*.zh_en.ass`
- `output/*.subtitle-review.txt`
- `output/*.copy.json`
- `final_videos/*.zh-en-hard.mp4`
