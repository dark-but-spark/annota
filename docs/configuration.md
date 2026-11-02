# Configuration

Annota reads settings in this order (highest priority first):

1. Environment variables
2. `~/.annota/config.json` (`ANNOTA_CONFIG_PATH` overrides the path)
3. Built-in defaults

On Windows the user config is:

```text
C:\Users\<you>\.annota\config.json
```

The MCP server and CLI read this file at startup. Restart the MCP server after
editing it.

A complete template is available at [`config.example.json`](../config.example.json).
The file is JSON, so it cannot contain comments; `null` means "derive from
another setting".

## Example

```json
{
  "zotero": {
    "data_dir": "C:/Users/yourname/Zotero",
    "db_path": null,
    "storage_dir": null,
    "library_id": 1
  },
  "database": {
    "timeout": 30,
    "retry_count": 3,
    "retry_base_delay": 1
  },
  "ollama": {
    "base_url": "http://127.0.0.1:11434",
    "llm_model": "qwen2.5:7b",
    "fallback_model": "deepseek-r1:1.5b",
    "embed_model": "",
    "timeout": 90,
    "auto_start": true
  },
  "deepseek": {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "timeout": 120
  },
  "translation": {
    "provider": "auto",
    "target_language": "zh-CN",
    "chunk_chars": 3000,
    "glossary_file": ""
  }
}
```

## Fields

### `zotero`

| Field | Default | Environment | Notes |
|-------|---------|-------------|-------|
| `data_dir` | `~/Zotero` | `ZOTERO_DATA_DIR` | Folder containing `zotero.sqlite` and `storage/` |
| `db_path` | `<data_dir>/zotero.sqlite` | `ZOTERO_DB_PATH` | Usually leave `null` |
| `storage_dir` | `<data_dir>/storage` | `ZOTERO_STORAGE_DIR` | Usually leave `null` |
| `library_id` | `1` | `ZOTERO_LIBRARY_ID` | Local user library is normally `1` |

### `database`

| Field | Default | Environment | Notes |
|-------|---------|-------------|-------|
| `timeout` | `30` | `ANNOTA_DB_TIMEOUT` | Seconds |
| `retry_count` | `3` | `ANNOTA_DB_RETRY_COUNT` | Lock retries |
| `retry_base_delay` | `1` | `ANNOTA_DB_RETRY_DELAY` | Exponential backoff base (seconds) |

### `ollama`

| Field | Default | Environment | Notes |
|-------|---------|-------------|-------|
| `base_url` | `http://127.0.0.1:11434` | `OLLAMA_BASE_URL` | Local Ollama server |
| `llm_model` | `qwen2.5:7b` | `OLLAMA_LLM_MODEL` | Preferred model |
| `fallback_model` | `deepseek-r1:1.5b` | `OLLAMA_LLM_FALLBACK_MODEL` | Secondary model |
| `embed_model` | `""` | `OLLAMA_EMBED_MODEL` | Empty disables embeddings |
| `timeout` | `90` | `OLLAMA_TIMEOUT` | Seconds |
| `auto_start` | `true` | `OLLAMA_AUTO_START` | Start `ollama serve` if not running |

### `deepseek`

| Field | Default | Environment | Notes |
|-------|---------|-------------|-------|
| `api_key` | `""` | `DEEPSEEK_API_KEY` | Keep this file private |
| `base_url` | `https://api.deepseek.com` | `DEEPSEEK_BASE_URL` | OpenAI-compatible base URL |
| `model` | `deepseek-chat` | `DEEPSEEK_MODEL` | API model name |
| `timeout` | `120` | `DEEPSEEK_TIMEOUT` | Seconds |

If you run `translate_paper.py` without a local model and without an API key, it
asks for these DeepSeek values and can save them to this file automatically.

### `translation`

| Field | Default | Environment | Notes |
|-------|---------|-------------|-------|
| `provider` | `auto` | `ANNOTA_TRANSLATION_PROVIDER` | `auto`, `local`/`ollama`, or `deepseek` |
| `target_language` | `zh-CN` | `ANNOTA_TRANSLATION_TARGET` | Translation target |
| `chunk_chars` | `3000` | `ANNOTA_TRANSLATION_CHUNK_CHARS` | Maximum characters per model request |
| `glossary_file` | `""` | `ANNOTA_GLOSSARY_FILE` | Optional CSV glossary (`source,target[,tgt_lng]`) |

`auto` tries local Ollama first, then DeepSeek. `local` disables the API
fallback. `deepseek` skips the local model.

## Legacy flat keys

The previous flat DeepSeek keys are still accepted:

```json
{
  "deepseek_api_key": "sk-...",
  "deepseek_base_url": "https://api.deepseek.com",
  "deepseek_model": "deepseek-chat"
}
```

Nested `deepseek` keys take precedence over the flat form.

## Security

- Do not commit `~/.annota/config.json`; it may contain an API key.
- The CLI writes the file with restrictive permissions where supported.
- Environment variables override the file, which is useful for temporary keys
  or CI.
