# Changelog

All notable changes to Annota will be documented in this file.

## [Unreleased]

### Added - Paper Translation

- `translate_paper` MCP tool: translate a paper and save it as a Zotero child
  note with page headings
- `translation_status` MCP tool: report local Ollama and DeepSeek availability
  without starting a server or prompting
- Provider order: local Ollama first (auto-starts `ollama serve` when possible),
  then DeepSeek API
- DeepSeek settings from `DEEPSEEK_API_KEY` / `~/.annota/config.json`; the CLI
  prompts for API settings when neither provider is available
- MCP calls never prompt: without a local model or API key they return
  `translation_unavailable`
- `translate_paper.py` CLI with page selection, target language, and note output
- Documentation in `docs/translation.md`

### Added - Zotero Process and Lock Preflight

- Detect running Zotero processes and probe SQLite write availability
- Fail writes early with a clear close-Zotero message instead of a generic lock
  timeout
- `zotero_status` MCP tool with PIDs, database state, and a user hint

### Added - Collection-Aware Search

- `list_collections` MCP tool with nested folder paths and item counts
- `search_zotero_items` / `list_zotero_items` accept a `collection` filter
- Search results and item metadata include collection paths

### Added - Duplicate PDF Detection and Merging

- `find_duplicate_pdfs` MCP tool: read-only scan for byte-identical PDFs stored
  under the same normalized title
- `merge_duplicate_pdfs` MCP tool: merge annotations, notes, tags, and
  collections into the kept copy; duplicates move to the Zotero trash
- Language guard: different metadata/detected languages are reported as
  `different_language` and are never merged (translation is a separate feature)
- `merge_duplicate_pdfs.py` CLI with dry-run and `--apply` modes
- Documentation in `docs/duplicate-pdf-merge.md`

### Added - Word-Level Annotation Support 🎉

#### New MCP Tools (3)

1. **`search_text_instances`** - Precise text search with word-level coordinates
   - Search for exact phrases in PDF pages
   - Returns bounding box for each match
   - Includes surrounding context
   - Supports case-sensitive/insensitive matching

2. **`extract_word_level_text`** - Word-by-word coordinate extraction
   - Extracts every word on a page with individual coordinates
   - More granular than line-level `get_pdf_layout_text`
   - Includes block/line/word numbering for structure analysis
   - Useful for custom matching logic

3. **`highlight_text_phrase`** - Smart phrase matching (recommended) ⭐
   - Intelligent phrase search with cross-line support
   - Automatically handles text wrapping and hyphenation
   - Normalizes whitespace and formatting differences
   - Returns multiple rectangles for phrases spanning multiple lines
   - Best choice for most annotation scenarios

#### New Functions in `pdf_tools.py`

- `search_text_instances()` - PyMuPDF-based exact text search
- `extract_word_level_text()` - Word-level coordinate extraction
- `highlight_text_phrase()` - Smart phrase matching with sliding window
- `_extract_context()` - Helper for extracting text context around matches

#### Documentation

- Added `docs/word-level-annotation-guide.md` - Comprehensive guide with examples
- Added `test_word_level_annotation.py` - Testing and demo script
- Updated README.md with new tool descriptions and Example 8

#### Technical Improvements

- **Precision**: Can now annotate individual words/phrases instead of entire lines
- **Smart matching**: Handles cross-line text, extra spaces, and formatting variations
- **Flexible**: Three different approaches for different use cases
- **Compatible**: Works with existing `create_pdf_annotation` and `batch_annotate`

#### Use Cases Enabled

- Highlight specific terminology (e.g., "machine learning", "p < 0.05")
- Annotate research questions (e.g., "RQ1", "RQ2")
- Mark key phrases in abstracts and conclusions
- Precisely locate formula names and variables
- Support both English and Chinese phrase annotation

---

## [0.2.0] - Previous Release

### Added
- `/annota-read` skill for reading papers
- `/annota-annotate` skill with semantic color coding
- Cross-platform support (Windows, macOS, Linux)

### Features
- 9 MCP tools for Zotero integration
- Two-phase workflow for large PDFs
- Auto-skip references detection
- Batch annotation support

### Changed
- Renamed from `zotero-mcp` to `annota` (trademark compliance)
- Added English translations for documentation

---

## [0.1.0] - Initial Release

### Added
- Basic PDF text extraction
- Zotero database integration
- SQLite direct write support
- Child note creation
