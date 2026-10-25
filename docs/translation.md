# Paper Translation

Annota can translate a paper and save the result as a Zotero child note. It
prefers a local model and only falls back to a paid API when necessary.

## Provider order

Default mode: `ANNOTA_TRANSLATION_PROVIDER=auto`.

1. **Local Ollama**
   - Uses the running Ollama server at `OLLAMA_BASE_URL`.
   - If the server is not running and `OLLAMA_AUTO_START=1` (default), Annota
     locates the `ollama` executable and starts `ollama serve` in the
     background, then waits for it to become available.
   - The model is chosen from `OLLAMA_LLM_MODEL`, then `qwen2.5:7b`, then any
     installed model.
2. **DeepSeek API**
   - Used when no local model is available.
   - Reads `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL` (default
     `https://api.deepseek.com`), and `DEEPSEEK_MODEL` (default
     `deepseek-chat`) from the environment or `~/.annota/config.json`.
3. **Interactive prompt (CLI only)**
   - If neither provider is available, `translate_paper.py` asks for the
     DeepSeek API key, base URL, and model, and optionally saves them to
     `~/.annota/config.json`.
   - MCP calls never prompt. They return `translation_unavailable` and tell the
     user to configure a provider or run the CLI once.

Provider modes:

- `auto` (default): local first, then DeepSeek.
- `local` / `ollama`: only local Ollama.
- `deepseek` / `api`: only DeepSeek.

If a local request fails on a chunk, the next configured provider (DeepSeek) is
tried for that chunk.

## MCP tools

```text
translation_status()
translate_paper(item_id, pages=None, target_language="zh-CN",
                save_note=True, max_chars_per_chunk=3000)
```

- `translation_status` is read-only and does not start Ollama or prompt.
- `translate_paper` extracts text (skipping references), splits it into chunks,
  translates each chunk, and saves an HTML child note with page headings.
- `save_note=false` returns the translation instead of writing a note.
- Saving a note requires Zotero to be closed. The tool checks the database lock
  before spending model/API time.

Example:

```text
translation_status()
translate_paper(item_id="12345", pages=[0, 1, 2])
translate_paper(item_id="12345", save_note=false)
```

## CLI

```bash
# Translate and save a note (Zotero must be closed)
python translate_paper.py --item 12345

# Only the first three pages, into English
python translate_paper.py --item 12345 --pages 0,1,2 --target en

# Translate a plain PDF and print the result
python translate_paper.py --pdf paper.pdf --no-note

# Preview which provider would be used
python -c "from annota.translation import provider_status; print(provider_status())"
```

On the first run without a local model and without a DeepSeek key, the CLI asks
for the API settings. Saving writes to `~/.annota/config.json` with restrictive
permissions; environment variables always take precedence.

## Notes and limits

- Scanned PDFs without a text layer are rejected with an OCR hint. OCR is not
  part of this feature.
- Long papers are translated chunk by chunk; `max_chars_per_chunk` controls
  request size and memory use.
- Local models keep all text on the machine. DeepSeek sends paper text to the
  configured API endpoint; review your data policy before using it.
- Technical terms, citations, formulas, and paragraph structure are requested
  in the prompt, but translation quality depends on the selected model.
