"""Academic paper translation with a local Ollama model and DeepSeek fallback.

Provider order (default ``ANNOTA_TRANSLATION_PROVIDER=auto``):

1. Local Ollama.  If the server is not running but the ``ollama`` executable is
   available, it is started in the background and the first installed model is
   used.
2. DeepSeek API, when ``DEEPSEEK_API_KEY`` is configured (environment or
   ``~/.annota/config.json``).
3. Interactive CLI prompt for DeepSeek settings.  This never happens for MCP
   calls: they fail with a clear ``translation_unavailable`` error instead.
"""

from __future__ import annotations

import getpass
import html
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import fitz  # PyMuPDF

from . import ollama_client, pdf_tools, zotero_db
from .config import (
    ANNOTA_USER_CONFIG_PATH,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT,
    OLLAMA_AUTO_START,
    OLLAMA_LLM_FALLBACK_MODEL,
    OLLAMA_LLM_MODEL,
    TRANSLATION_CHUNK_CHARS,
    TRANSLATION_GLOSSARY_FILE,
    TRANSLATION_PROVIDER,
    TRANSLATION_TARGET_LANGUAGE,
)

logger = logging.getLogger(__name__)

_TARGET_NAMES = {
    "zh": "Simplified Chinese",
    "zh-cn": "Simplified Chinese",
    "zh-hans": "Simplified Chinese",
    "zh-tw": "Traditional Chinese",
    "zh-hant": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
}


class TranslationError(RuntimeError):
    """Raised when translation fails after provider selection."""


class TranslationUnavailableError(TranslationError):
    """Raised when neither a local model nor a configured API is available."""


@dataclass
class OllamaProvider:
    model: str
    kind: str = "ollama"

    def translate(
        self,
        text: str,
        target_language: str,
        page_number: int,
        system_prompt: str | None = None,
    ) -> str:
        return ollama_client.generate(
            self.model,
            _user_prompt(text, page_number),
            system=system_prompt or _system_prompt(target_language),
            temperature=0.2,
        )

    def summary(self) -> dict:
        return {"provider": self.kind, "model": self.model}


@dataclass
class DeepSeekProvider:
    api_key: str
    model: str
    base_url: str
    kind: str = "deepseek"

    def translate(
        self,
        text: str,
        target_language: str,
        page_number: int,
        system_prompt: str | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or _system_prompt(target_language),
                },
                {"role": "user", "content": _user_prompt(text, page_number)},
            ],
            "temperature": 0.2,
            "stream": False,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.base_url}/chat/completions"
        last_error: Exception | None = None

        for attempt in range(3):
            request = Request(
                url,
                data=data,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            try:
                with urlopen(request, timeout=DEEPSEEK_TIMEOUT) as response:
                    parsed = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:500]
                last_error = TranslationError(
                    f"DeepSeek API error {exc.code}: {body}"
                )
                if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error from exc
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last_error = TranslationError(f"DeepSeek request failed: {exc}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error from exc
        else:
            raise last_error or TranslationError("DeepSeek request failed")

        try:
            content = parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationError(
                f"Unexpected DeepSeek response: {str(parsed)[:300]}"
            ) from exc
        text = str(content).strip()
        if not text:
            raise TranslationError("DeepSeek returned an empty translation")
        return text

    def summary(self) -> dict:
        return {"provider": self.kind, "model": self.model}


def _system_prompt(
    target_language: str,
    glossary: dict[str, str] | None = None,
) -> str:
    target = _TARGET_NAMES.get(target_language.casefold(), target_language)
    prompt = (
        "You are a professional academic translator. Translate the supplied "
        f"paper excerpt into {target}. Preserve technical terminology, "
        "citations, numbers, equations, and paragraph structure. Keep author "
        "names, personal names, and organization names in their original "
        "Latin script; never transliterate them or invent Chinese names. "
        "Translate personal names to their conventional form only when an "
        "official Chinese name is well known; otherwise keep the original. "
        "Do not summarize, explain, or add commentary. Output only the "
        "translation. Keep placeholder tokens such as ⟦EQ_p3_1⟧ exactly "
        "unchanged; never translate, reorder, or remove them."
    )
    if glossary:
        pairs = "; ".join(
            f"{source} => {target_term}"
            for source, target_term in list(glossary.items())[:80]
        )
        prompt += (
            " Use the following terminology consistently and do not choose "
            f"alternative translations: {pairs}."
        )
    return prompt


def load_glossary(path: str | Path) -> dict[str, str]:
    """Load a CSV glossary with ``source,target[,tgt_lng]`` columns."""
    import csv

    glossary: dict[str, str] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return glossary
        fields = {name.strip().lower(): name for name in reader.fieldnames}
        source_key = fields.get("source")
        target_key = fields.get("target")
        if not source_key or not target_key:
            raise ValueError("Glossary CSV must contain source and target columns")
        for row in reader:
            source = (row.get(source_key) or "").strip()
            target = (row.get(target_key) or "").strip()
            if source and target:
                glossary[source] = target
    return glossary


def _user_prompt(text: str, page_number: int) -> str:
    return f"Excerpt from page {page_number + 1}:\n\n{text}"


def _load_user_config() -> dict:
    path = Path(ANNOTA_USER_CONFIG_PATH)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _save_user_config(values: dict) -> None:
    path = Path(ANNOTA_USER_CONFIG_PATH)
    data = _load_user_config()
    for key, value in values.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _deepseek_settings() -> dict:
    config = _load_user_config()
    section = config.get("deepseek")
    if not isinstance(section, dict):
        section = {}

    api_key = (
        os.environ.get("DEEPSEEK_API_KEY")
        or section.get("api_key")
        or config.get("deepseek_api_key", "")
    )
    base_url = (
        os.environ.get("DEEPSEEK_BASE_URL")
        or section.get("base_url")
        or config.get("deepseek_base_url")
        or DEEPSEEK_BASE_URL
    ).rstrip("/")
    model = (
        os.environ.get("DEEPSEEK_MODEL")
        or section.get("model")
        or config.get("deepseek_model")
        or DEEPSEEK_MODEL
    )
    return {"api_key": api_key, "base_url": base_url, "model": model}


def _find_ollama_executable() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path("/usr/local/bin/ollama"),
        Path("/usr/bin/ollama"),
        Path("/Applications/Ollama.app/Contents/Resources/ollama"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _start_ollama_server() -> bool:
    executable = _find_ollama_executable()
    if not executable:
        return False
    kwargs: dict = {}
    if platform.system() == "Windows":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(
            [executable, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
    except OSError as exc:
        logger.warning("Could not start Ollama: %s", exc)
        return False

    for _ in range(20):
        time.sleep(0.5)
        if ollama_client.status().get("available"):
            return True
    return False


def _choose_local_model(models: list[str]) -> str | None:
    if not models:
        return None
    preferred = [
        OLLAMA_LLM_MODEL,
        "qwen2.5:7b",
        "qwen2.5:14b",
        "llama3.1:8b",
        OLLAMA_LLM_FALLBACK_MODEL,
    ]
    for wanted in preferred:
        if not wanted:
            continue
        if wanted in models:
            return wanted
        for installed in models:
            if installed.startswith(f"{wanted}:"):
                return installed
    return models[0]


def _local_provider() -> OllamaProvider | None:
    if TRANSLATION_PROVIDER in {"deepseek", "api"}:
        return None

    status = ollama_client.status()
    if not status.get("available") and OLLAMA_AUTO_START:
        logger.info("Ollama is not running; attempting to start it")
        if _start_ollama_server():
            status = ollama_client.status()
    if not status.get("available"):
        return None

    model = _choose_local_model(status.get("models", []))
    if not model:
        logger.info("Ollama is running but no model is installed")
        return None
    return OllamaProvider(model)


def _deepseek_provider() -> DeepSeekProvider | None:
    if TRANSLATION_PROVIDER in {"local", "ollama"}:
        return None
    settings = _deepseek_settings()
    if not settings["api_key"]:
        return None
    return DeepSeekProvider(
        api_key=settings["api_key"],
        model=settings["model"],
        base_url=settings["base_url"],
    )


def _prompt_deepseek_provider() -> DeepSeekProvider | None:
    if not sys.stdin or not sys.stdin.isatty():
        return None

    print(
        "\nNo local Ollama model is available and no DeepSeek API key is configured.",
        file=sys.stderr,
    )
    try:
        api_key = getpass.getpass("DeepSeek API key (leave empty to cancel): ").strip()
        if not api_key:
            return None
        base_url = input(
            f"DeepSeek base URL [{DEEPSEEK_BASE_URL}]: "
        ).strip() or DEEPSEEK_BASE_URL
        model = input(f"DeepSeek model [{DEEPSEEK_MODEL}]: ").strip() or DEEPSEEK_MODEL
        save = input("Save these settings to ~/.annota/config.json? [Y/n]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None

    if save.casefold() not in {"n", "no"}:
        _save_user_config(
            {
                "deepseek": {
                    "api_key": api_key,
                    "base_url": base_url.rstrip("/"),
                    "model": model,
                }
            }
        )
        print("Saved DeepSeek settings to ~/.annota/config.json", file=sys.stderr)

    return DeepSeekProvider(api_key=api_key, model=model, base_url=base_url.rstrip("/"))


def available_providers(allow_prompt: bool = True) -> list:
    """Resolve translation providers in preference order."""
    providers: list = []
    local = _local_provider()
    if local:
        providers.append(local)
    deepseek = _deepseek_provider()
    if deepseek:
        providers.append(deepseek)

    if (
        not providers
        and allow_prompt
        and TRANSLATION_PROVIDER not in {"local", "ollama"}
    ):
        deepseek = _prompt_deepseek_provider()
        if deepseek:
            providers.append(deepseek)

    if not providers:
        raise TranslationUnavailableError(
            "No translation provider is available. Start Ollama with an "
            "installed model, or configure DEEPSEEK_API_KEY "
            "(environment or ~/.annota/config.json). MCP calls cannot prompt "
            "for credentials; run translate_paper.py interactively once to "
            "save them."
        )
    return providers


def provider_status() -> dict:
    """Report provider availability without starting Ollama or prompting."""
    local = ollama_client.status()
    settings = _deepseek_settings()
    return {
        "provider_mode": TRANSLATION_PROVIDER,
        "ollama_auto_start": OLLAMA_AUTO_START,
        "local": {
            "available": bool(local.get("available")),
            "base_url": local.get("base_url"),
            "models": local.get("models", []),
            "error": local.get("error"),
            "selected_model": _choose_local_model(local.get("models", [])),
        },
        "deepseek": {
            "configured": bool(settings["api_key"]),
            "base_url": settings["base_url"],
            "model": settings["model"],
        },
        "target_language": TRANSLATION_TARGET_LANGUAGE,
    }


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def _split_long_unit(text: str, max_chars: int) -> list[str]:
    """Split a too-long sentence at word boundaries, never mid-word."""
    parts: list[str] = []
    current = ""
    for word in text.split():
        if len(word) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.extend(
                word[start:start + max_chars]
                for start in range(0, len(word), max_chars)
            )
            continue
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = word
    if current:
        parts.append(current)
    return parts or [text[:max_chars]]


_MATH_FONTS = (
    "EuclidMath",
    "Symbol",
    "CMMI",
    "CMSY",
    "MSAM",
    "MSBM",
    "MTMI",
    "MTSY",
    "STIXMath",
    "CambriaMath",
    "AsanaMath",
    "XITSMath",
    "LatinModernMath",
)
_MATH_CHARS = set("+−=<>≤≥±×÷∑∫√∞≈≠∂∇∆∈∉⊂⊃∪∩→←↔·∙∗")
_FORMULA_MARKER_RE = re.compile(r"⟦EQ_p(\d+)_(\d+)⟧")


def _is_formula_block(block: dict) -> bool:
    fonts = [span["font"] for line in block["lines"] for span in line["spans"]]
    text = "".join(
        span["text"] for line in block["lines"] for span in line["spans"]
    ).strip()
    if len(text) < 2:
        return False
    math_font = any(
        any(name in font for name in _MATH_FONTS) for font in fonts
    )
    math_chars = sum(
        1
        for char in text
        if char in _MATH_CHARS or unicodedata.category(char) == "Sm"
    )
    ratio = math_chars / len(text)
    return bool((math_font and (ratio >= 0.04 or len(text) <= 120)) or ratio >= 0.2)


def _is_equation_number(block: dict) -> bool:
    text = "".join(
        span["text"] for line in block["lines"] for span in line["spans"]
    ).strip()
    return bool(re.fullmatch(r"\(\d+\)", text))


def _merge_formula_regions(blocks: list[dict]) -> list["fitz.Rect"]:
    regions = []
    for block in blocks:
        box = fitz.Rect(block["bbox"])
        box = fitz.Rect(box.x0 - 10, box.y0 - 6, box.x1 + 10, box.y1 + 20)
        merged = False
        for region in regions:
            horizontally_close = not (box.x1 < region.x0 or box.x0 > region.x1)
            vertically_close = (
                box.y0 <= region.y1 + 12 and region.y0 <= box.y1 + 12
            )
            if region.intersects(box) or (horizontally_close and vertically_close):
                region |= box
                merged = True
                break
        if not merged:
            regions.append(box)

    changed = True
    while changed:
        changed = False
        for index in range(len(regions)):
            for other in range(index + 1, len(regions)):
                if regions[index].intersects(regions[other]):
                    regions[index] |= regions.pop(other)
                    changed = True
                    break
            if changed:
                break
    return regions


def _extract_pages_with_formulas(
    pdf_path: str | Path,
    pages: list[int] | None = None,
    skip_refs: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Extract page text and replace formula blocks with stable markers."""
    doc = fitz.open(str(pdf_path))
    try:
        total_pages = len(doc)
        refs_start = pdf_tools._detect_refs_page(doc) if skip_refs else total_pages
        if pages is None:
            target_pages = list(range(min(refs_start, total_pages)))
        else:
            target_pages = sorted(
                {
                    page
                    for page in pages
                    if 0 <= page < total_pages and page < refs_start
                }
            )

        page_texts = []
        formulas = []
        for page_number in target_pages:
            page = doc[page_number]
            blocks = [
                block
                for block in page.get_text("dict")["blocks"]
                if block.get("type") == 0
            ]
            formula_blocks = [block for block in blocks if _is_formula_block(block)]
            if not formula_blocks:
                page_texts.append({
                    "page": page_number,
                    "text": page.get_text("text").strip(),
                })
                continue

            regions = _merge_formula_regions(formula_blocks)
            markers: dict[int, str] = {}
            pieces = []
            emitted: set[int] = set()
            page_formula_count = 0

            for block in blocks:
                text = "".join(
                    span["text"]
                    for line in block["lines"]
                    for span in line["spans"]
                ).strip()
                block_box = fitz.Rect(block["bbox"])
                region_index = next(
                    (
                        index
                        for index, region in enumerate(regions)
                        if region.intersects(block_box)
                    ),
                    None,
                )
                short_fragment = region_index is not None and len(text) <= 40
                if (
                    _is_formula_block(block)
                    or _is_equation_number(block)
                    or short_fragment
                ):
                    if region_index is None:
                        region_index = len(regions)
                        regions.append(block_box)
                    if region_index not in markers:
                        page_formula_count += 1
                        marker = (
                            f"⟦EQ_p{page_number + 1}_{page_formula_count}⟧"
                        )
                        markers[region_index] = marker
                        region = regions[region_index]
                        formulas.append({
                            "page": page_number,
                            "marker": marker,
                            "bbox": [
                                round(region.x0, 1),
                                round(region.y0, 1),
                                round(region.x1, 1),
                                round(region.y1, 1),
                            ],
                        })
                    if region_index not in emitted:
                        pieces.append(markers[region_index])
                        emitted.add(region_index)
                    continue
                if text:
                    pieces.append(text)

            page_texts.append({
                "page": page_number,
                "text": "\n\n".join(pieces).strip(),
            })
        return page_texts, formulas
    finally:
        doc.close()


def _split_text(text: str, max_chars: int) -> list[str]:
    """Pack sentences into chunks without cutting words or sentences."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    units: list[tuple[str, bool]] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences = [
            sentence.strip()
            for sentence in _SENTENCE_SPLIT.split(paragraph)
            if sentence.strip()
        ]
        if not sentences:
            sentences = [paragraph]
        for index, sentence in enumerate(sentences):
            if len(sentence) > max_chars:
                pieces = _split_long_unit(sentence, max_chars)
                for piece_index, piece in enumerate(pieces):
                    units.append((piece, index == 0 and piece_index == 0))
            else:
                units.append((sentence, index == 0))

    parts: list[str] = []
    current = ""
    for unit, starts_paragraph in units:
        if not current:
            candidate = unit
        elif starts_paragraph:
            candidate = f"{current}\n\n{unit}"
        else:
            candidate = f"{current} {unit}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = unit
    if current:
        parts.append(current)
    return parts


def _chunk_pages(pages: list[dict], max_chars: int) -> list[dict]:
    chunks = []
    for page in pages:
        text = (page.get("text") or "").strip()
        if not text:
            continue
        for part in _split_text(text, max_chars):
            if part.strip():
                chunks.append({"page": page["page"], "text": part})
    return chunks


def translate_pdf(
    pdf_path: str | Path,
    *,
    pages: list[int] | None = None,
    target_language: str = TRANSLATION_TARGET_LANGUAGE,
    max_chars_per_chunk: int = TRANSLATION_CHUNK_CHARS,
    glossary: dict[str, str] | None = None,
    glossary_file: str | Path | None = None,
    formula_placeholders: bool = True,
    allow_prompt: bool = True,
    progress=None,
) -> dict:
    """Extract and translate a PDF, returning translated chunks by page."""
    if max_chars_per_chunk < 500:
        raise ValueError("max_chars_per_chunk must be at least 500")

    merged_glossary: dict[str, str] = {}
    if glossary_file is None and TRANSLATION_GLOSSARY_FILE:
        glossary_file = TRANSLATION_GLOSSARY_FILE
    if glossary_file:
        merged_glossary.update(load_glossary(glossary_file))
    if glossary:
        merged_glossary.update(glossary)
    system_prompt = _system_prompt(target_language, merged_glossary or None)

    providers = available_providers(allow_prompt=allow_prompt)
    formulas: list[dict] = []
    if formula_placeholders:
        page_texts, formulas = _extract_pages_with_formulas(
            pdf_path, pages=pages, skip_refs=True
        )
    else:
        extracted = pdf_tools.extract_bulk_text(
            pdf_path,
            pages=pages,
            skip_refs=True,
        )
        page_texts = extracted.get("pages", [])
    if not any((page.get("text") or "").strip() for page in page_texts):
        raise TranslationError(
            "No extractable text was found in this PDF. It may be a scanned "
            "image; OCR is required before translation."
        )

    chunks = _chunk_pages(page_texts, max_chars_per_chunk)
    if not chunks:
        raise TranslationError("No text chunks were produced from this PDF")

    translated = []
    used_provider = None
    for index, chunk in enumerate(chunks):
        if progress:
            progress(index + 1, len(chunks), chunk)
        errors = []
        output = None
        for provider in providers:
            try:
                output = provider.translate(
                    chunk["text"],
                    target_language,
                    chunk["page"],
                    system_prompt=system_prompt,
                )
                used_provider = provider
                break
            except Exception as exc:
                logger.warning(
                    "Translation failed with %s/%s: %s",
                    provider.kind,
                    provider.model,
                    exc,
                )
                errors.append(f"{provider.kind}/{provider.model}: {exc}")
        if output is None:
            raise TranslationError(
                "All translation providers failed: " + "; ".join(errors)
            )
        translated.append({"page": chunk["page"], "translation": output})

    return {
        **used_provider.summary(),
        "target_language": target_language,
        "page_count": len(page_texts),
        "chunk_count": len(chunks),
        "glossary_terms": len(merged_glossary),
        "formula_count": len(formulas),
        "formulas": formulas,
        "pages": translated,
    }


def _html_paragraphs(text: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    if not blocks:
        blocks = [text.strip()]
    return "\n".join(
        f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>"
        for block in blocks
        if block
    )


def render_translation_note(title: str, result: dict) -> str:
    """Render a translation result as an HTML child note."""
    grouped: dict[int, list[str]] = {}
    for item in result["pages"]:
        grouped.setdefault(item["page"], []).append(item["translation"])

    parts = [
        f"<h1>翻译：{html.escape(title or '未命名论文')}</h1>",
        (
            f"<p><strong>目标语言：</strong>{html.escape(result['target_language'])}"
            f"<br><strong>翻译服务：</strong>{html.escape(result['provider'])}"
            f" / {html.escape(result['model'])}</p>"
        ),
    ]
    if result.get("formula_count"):
        parts.append(
            "<p><strong>提示：</strong>本页含公式。公式未由文本翻译器翻译，"
            "已标记为 <code>[公式 p页码-序号]</code>；"
            "建议用 <code>babeldoc_translate.py</code> 生成保留公式的 PDF 对照。</p>"
        )
    for page_number in sorted(grouped):
        parts.append(f"<h2>第 {page_number + 1} 页</h2>")
        for chunk in grouped[page_number]:
            chunk = _FORMULA_MARKER_RE.sub(
                lambda match: f"[公式 p{match.group(1)}-{match.group(2)}]",
                chunk,
            )
            parts.append(_html_paragraphs(chunk))
    return "\n".join(parts)


def save_translation_note(parent_item_id: int, title: str, result: dict) -> dict:
    """Create a child note containing the translated paper."""
    note_html = render_translation_note(title, result)
    return zotero_db.create_child_note(parent_item_id, note_html)
