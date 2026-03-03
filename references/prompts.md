# Prompt Templates

## Transcription Prompt

Use this shape for transcription output:

- Return strict JSON object with key `segments`.
- Each segment item includes:
  - `start_ms` integer
  - `end_ms` integer
  - `text` string in English

Rules:

- Transcribe spoken content only.
- Keep punctuation natural.
- Do not add explanations.
- Keep chronological order.

## Translation Prompt

Use batch translation with strict JSON:

- Return strict JSON object with key `items`.
- Each item includes:
  - `id` integer from input
  - `zh_text` Simplified Chinese translation

Rules:

- Preserve meaning and tone.
- Keep names and terms consistent.
- Do not include numbering or extra commentary.

## Copywriting Prompt

Return strict JSON:

- `title` string
- `description` string
- `hashtags` array of strings

Rules:

- Write for Chinese short-video publishing.
- Keep concise and practical.
- Use 8-15 hashtags and include `#`.
