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
                save_note=True, max_chars_per_chunk=3000, glossary=None)
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

# Enforce a terminology glossary
python translate_paper.py --pdf paper.pdf --no-note --glossary terms.csv

# Preview which provider would be used
python -c "from annota.translation import provider_status; print(provider_status())"
```

On the first run without a local model and without a DeepSeek key, the CLI asks
for the API settings. Saving writes to `~/.annota/config.json` with restrictive
permissions; environment variables always take precedence.

## Chunking and terminology

- Chunks are packed from **sentences and paragraphs**, not raw characters.
  Long sentences are split at word boundaries, so a word is never cut in half
  at a chunk edge.
- The system prompt keeps author names, personal names, and organization names
  in their original Latin script instead of inventing Chinese names.
- A glossary CSV can enforce terminology across the whole paper:

  ```csv
  source,target,tgt_lng
  engagement,参与度,zh-CN
  treatment,处理,zh-CN
  topic-shift transfer,主题迁移,zh-CN
  Jian Li,Jian Li,zh-CN
  ```

  Pass it with `translate_paper(..., glossary={...})`, the CLI
  `--glossary terms.csv`, or `translation.glossary_file` in the config file.
  An entry whose source and target are identical protects a name from
  transliteration.

## Formula-heavy papers: BabelDOC

The native note translator still extracts formulas as scattered glyphs, so
formula pages remain unsuitable for Markdown notes. For those pages use the
optional BabelDOC companion, which keeps formulas and layout in a translated
PDF:

```bash
# Install once
uv tool install --python 3.12 BabelDOC

# If BabelDOC reports: cannot import name 'BitStream'
uv pip install --python <babeldoc-python> "bitstring==4.1.4"

# Translate pages 1-5 (1-based, BabelDOC syntax)
python babeldoc_translate.py --pdf paper.pdf --pages 1-5

# Force DeepSeek, custom terminology, dual-language PDF
python babeldoc_translate.py --pdf paper.pdf --pages 3-4 \
    --provider deepseek --glossary terms.csv --dual
```

`babeldoc_translate.py` reads the same `~/.annota/config.json` for Ollama and
DeepSeek settings. It invokes the external BabelDOC CLI, so BabelDOC's
AGPL-3.0 license applies to that tool; it is not embedded in Annota.

Trial result on `Li (2026)` pages 1–5 with DeepSeek:

- 5 pages, about 120 seconds, ~46k tokens including automatic term extraction.
- Equations (1)–(5) are preserved visually in the translated PDF; page 3–4
  prose is readable Chinese.
- Author names stayed in Latin script (`Jian Li`), not transliterated.
- An automatic glossary CSV was produced; a custom glossary kept
  `engagement → 参与度` and `topic-shift transfer → 主题迁移`.
- Text extracted from the output PDF still splits formula glyphs across lines,
  so use the PDF for reading and Annota notes for prose.


## Notes and limits

- Scanned PDFs without a text layer are rejected with an OCR hint. OCR is not
  part of this feature.
- Long papers are translated chunk by chunk; `max_chars_per_chunk` controls
  request size and memory use.
- Local models keep all text on the machine. DeepSeek sends paper text to the
  configured API endpoint; review your data policy before using it.
- Technical terms, citations, formulas, and paragraph structure are requested
  in the prompt, but translation quality depends on the selected model.
