# Local Ollama Context Preprocessing

Annota can use a local Ollama installation to reduce the amount of PDF text
sent to the main model. Ollama is optional; all new tools fall back to local
PyMuPDF search when it is unavailable.

## Configuration

Set these environment variables before starting the MCP server:

```text
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_LLM_MODEL=qwen2.5:7b
OLLAMA_LLM_FALLBACK_MODEL=deepseek-r1:1.5b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_TIMEOUT=90
```

Use `ollama_status` to check connectivity and the configured model names.
Embedding models are optional. The LLM model is used only to select and
compress evidence, and generated quotes are validated against the source text.
`qwen2.5:7b` is the primary model by default. If it fails (including an Ollama
out-of-memory error), the same request is retried with `deepseek-r1:1.5b`.

## Recommended workflow

1. Call `get_pdf_manifest` to inspect page counts and short previews.
2. Call `prepare_pdf_context` with the user's target (for example, `key findings`).
3. For each returned quote, call `highlight_text_phrase` to obtain verified PDF coordinates.
4. Pass all verified rectangles to `batch_annotate`.

`prepare_pdf_context` limits the candidate text sent to Ollama with `max_input_chars`.
If Ollama fails, it returns deterministically ranked source chunks and sets
`fallback` to `true`; no annotation data is lost.

For visual inspection, formulas, or scanned pages, use a page-specific PDF or
image workflow. Do not Base64-encode an entire PDF into a tool response.
