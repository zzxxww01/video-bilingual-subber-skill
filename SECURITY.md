# Security Notes

## Secret Handling

- Store `GEMINI_API_KEY` in environment variables or `.env.local` only.
- `.env` and `.env.local` are ignored by `.gitignore`.
- API keys are redacted in runtime error logs where possible.

## Pre-Publish Checklist

1. `python scripts/check_repo_safety.py --strict`
2. Confirm there is no `.env`, `.pem`, `.key`, `.p12`, `.pfx` file in staged changes.
3. Confirm generated artifacts (`subs/`, `output/`, `final_videos/`) are not staged.

## If Secret Leakage Happens

1. Revoke/rotate the leaked key immediately.
2. Remove the secret from repository history.
3. Force-push cleaned history only after key rotation.

