"""Annota MCP Server — 主入口。

通过 FastMCP 注册以下工具：
  - get_pdf_layout_text:   提取 PDF 页面文本及坐标
  - get_pdf_text_bulk:     批量提取多页纯文本（无坐标，适合大 PDF）
  - create_pdf_annotation: 创建 PDF 高亮批注
  - batch_annotate:        一次性创建多条标注（减少调用次数）
  - add_child_note:        为条目创建子笔记
  - list_zotero_items:     列出文献条目
  - search_zotero_items:   按标题/作者/key 搜索条目
  - get_item_metadata:     获取条目元数据（作者、年份、期刊等）
  - list_annotations:      列出 PDF 上已有的标注
  - list_collections:      列出 Zotero 文件夹
  - zotero_status:         检查 Zotero 进程与数据库锁
  - delete_annotation:     删除单个标注
  - delete_annotations_batch: 批量删除标注
  - find_duplicate_pdfs:   查找同标题下内容相同的 PDF
  - merge_duplicate_pdfs:  合并重复 PDF 的标注与笔记

运行方式: python server.py  (stdio transport, 供 Claude Code 调用)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── 必须最先执行：将项目根目录加入 sys.path ────────────────────────
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import json
import logging
import math
import sqlite3

from mcp.server.fastmcp import FastMCP

from annota import duplicates, ollama_client, pdf_tools, zotero_db
from annota.config import (
    OLLAMA_EMBED_MODEL,
    OLLAMA_LLM_FALLBACK_MODEL,
    OLLAMA_LLM_MODEL,
    ZOTERO_DB_PATH,
    ZOTERO_STORAGE_DIR,
)
from annota.zotero_status import ensure_write_ready, get_status as get_zotero_status

# ── 日志配置（输出到 stderr，不干扰 stdio JSON-RPC）──────────────
logging.basicConfig(
    level=logging.INFO,
    format="[annota] %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ── MCP Server ──────────────────────────────────────────────────
mcp = FastMCP(
    name="annota",
    instructions=(
        "Annota: 读取本地 Zotero 库中的 PDF 文件，提取带坐标的文本，"
        "并精准回写高亮批注和笔记。所有坐标均为 PDF user space（原点左下角）。\n\n"
        "【大 PDF 两阶段工作流】处理超过 10 页的论文时，请遵循：\n"
        "  Phase 1 — 理解：先用 get_pdf_text_bulk 批量提取纯文本（无坐标），让 LLM 理解全文内容，"
        "确定哪些页面的哪些句子需要标注。\n"
        "  Phase 2 — 定位：只对目标页调用 get_pdf_layout_text 获取精确坐标，"
        "然后用 create_pdf_annotation 写入标注。\n"
        "  切勿对每一页都调用 get_pdf_layout_text，这会导致上下文溢出。\n\n"
        "【文字级精确标注】新增词级标注工具：\n"
        "  - search_text_instances: 搜索特定短语，返回每个匹配的精确坐标\n"
        "  - extract_word_level_text: 提取页面所有词的独立坐标（比行级更精细）\n"
        "  - highlight_text_phrase: 最智能的方式，自动处理跨行文本和排版差异\n"
        "  - create_annotation_direct: 直接用坐标创建标注，无需搜索文本\n"
        "  推荐：需要标注特定词语时，优先使用 highlight_text_phrase。\n"
        "  如果已知精确坐标，使用 create_annotation_direct 最快。"
        "  For large PDFs prefer get_pdf_manifest -> prepare_pdf_context -> highlight_text_phrase -> batch_annotate.\n"
        "  prepare_pdf_context uses local Ollama when configured and safely falls back to local retrieval.\n"
    ),
)


# ── Tool 1: get_pdf_layout_text ─────────────────────────────────

@mcp.tool()
def get_pdf_layout_text(item_id: str, page_number: int) -> str:
    """提取 PDF 指定页面的文本及物理坐标。

    返回 JSON，每个文本行包含 text 和 rect [x0, y0, x1, y1]（Zotero PDF 坐标系）。
    可以直接将 rect 传给 create_pdf_annotation 使用。

    Args:
        item_id: Zotero PDF 附件的 itemID（数字），或 PDF 文件的绝对路径
        page_number: 页码（从 0 开始）
    """
    pdf_path = _resolve_pdf_path(item_id)

    result = pdf_tools.extract_page_text(pdf_path, page_number)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Tool 2: create_pdf_annotation ───────────────────────────────

@mcp.tool()
def create_pdf_annotation(
    item_id: str,
    page_index: int,
    rects: list[list[float]],
    color: str = "#ffd400",
    comment: str = "",
    text: str = "",
    type: str = "highlight",
) -> str:
    """在 Zotero PDF 上创建高亮/下划线批注。

    坐标使用 get_pdf_layout_text 返回的 rect 值，无需手动转换。
    写入后需重启 Zotero 或按 Ctrl+Shift+R 刷新才能看到批注。

    注意：写操作需要关闭 Zotero 桌面应用，否则会因数据库锁而失败。

    Args:
        item_id: Zotero PDF 附件的 itemID（数字），或 PDF 文件的绝对路径
        page_index: 页码（从 0 开始）
        rects: 坐标数组，每项为 [x0, y0, x1, y1]（来自 get_pdf_layout_text）
        color: 十六进制颜色，如 "#ffd400"(黄), "#28CA42"(绿), "#2EA8E5"(蓝)
        comment: 附加在批注上的文字评论（可选）
        text: 被高亮的原始文本（可选，用于 Zotero 中显示）
        type: 批注类型: "highlight"(默认) 或 "underline"
    """
    try:
        attachment_id = _resolve_item_id(item_id)

        # 获取 page_height（用于 sortIndex 计算）
        pdf_path = _resolve_pdf_path(item_id)
        page_data = pdf_tools.extract_page_text(pdf_path, page_index)
        page_height = page_data["page_height"]

        result = zotero_db.create_annotation(
            parent_attachment_id=attachment_id,
            page_index=page_index,
            rects=rects,
            page_height=page_height,
            color=color,
            comment=comment,
            text=text,
            ann_type=type,
        )
        return json.dumps({
            **result,
            "message": "批注已写入 Zotero 数据库。请重启 Zotero 或按 Ctrl+Shift+R 刷新查看。",
        }, ensure_ascii=False)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return json.dumps({
                "error": "database_locked",
                "message": "Zotero 数据库被锁定，请先关闭 Zotero 桌面应用再重试。",
            }, ensure_ascii=False)
        raise


# ── Tool 3: add_child_note ──────────────────────────────────────

@mcp.tool()
def add_child_note(parent_item_id: str, note_content: str) -> str:
    """为 Zotero 文献条目创建子笔记。

    支持 HTML 和纯文本。写入后需重启 Zotero 或按 Ctrl+Shift+R 刷新。
    注意：写操作需要关闭 Zotero 桌面应用。

    Args:
        parent_item_id: 父文献条目的 itemID（数字字符串）
        note_content: 笔记内容（HTML 或纯文本，支持 Markdown 风格）
    """
    try:
        result = zotero_db.create_child_note(
            parent_item_id=int(parent_item_id),
            note_content=note_content,
        )
        return json.dumps({
            **result,
            "message": "笔记已写入 Zotero 数据库。请重启 Zotero 或按 Ctrl+Shift+R 刷新查看。",
        }, ensure_ascii=False)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return json.dumps({
                "error": "database_locked",
                "message": "Zotero 数据库被锁定，请先关闭 Zotero 桌面应用再重试。",
            }, ensure_ascii=False)
        raise


# ── Tool 4: list_zotero_items ──────────────────────────────────

@mcp.tool()
def list_zotero_items(limit: int = 50, collection: str | None = None) -> str:
    """列出 Zotero 库中的文献条目。

    返回每个条目的 itemID、key、标题、所属文件夹，以及 PDF 附件 ID（如有）。
    用于发现 item_id 以供其他工具使用。

    Args:
        limit: 最多返回条目数（默认 50）
        collection: 可选，按文件夹名称或路径片段过滤（不区分大小写）
    """
    items = zotero_db.list_items(limit=limit, collection=collection)
    return json.dumps(items, ensure_ascii=False, indent=2)


# ── Tool 5: search_zotero_items ────────────────────────────────

@mcp.tool()
def search_zotero_items(
    query: str,
    limit: int = 20,
    collection: str | None = None,
) -> str:
    """按标题、作者或 key 搜索 Zotero 条目，可按文件夹缩小范围。

    比 list_zotero_items 更高效，可直接定位目标论文。

    Args:
        query: 搜索关键词（标题/作者的部分文字，或 Zotero item key）
        limit: 最多返回条目数（默认 20）
        collection: 可选，按文件夹名称或路径片段过滤（不区分大小写）
    """
    items = zotero_db.search_items(query=query, limit=limit, collection=collection)
    return json.dumps(items, ensure_ascii=False, indent=2)


@mcp.tool()
def list_collections() -> str:
    """列出 Zotero 文件夹（collection）及其条目数量。

    返回 collectionID、名称、层级路径和直接包含的条目数，可用于
    search_zotero_items / list_zotero_items 的 collection 参数。
    """
    collections = zotero_db.list_collections()
    return json.dumps(collections, ensure_ascii=False, indent=2)


# ── Tool 6: get_pdf_text_bulk ─────────────────────────────────

@mcp.tool()
def get_pdf_text_bulk(
    item_id: str,
    pages: list[int] | None = None,
    skip_refs: bool = True,
    compact: bool = True,
    max_chars_per_page: int | None = None,
    max_total_chars: int | None = None,
) -> str:
    """批量提取多页 PDF 纯文本（无坐标），适合大 PDF 内容理解。

    与 get_pdf_layout_text 的区别：不返回坐标，context 占用减少 ~80%。
    推荐工作流：
      1. 先用此工具理解全文 → 确定目标页和目标句子
      2. 再用 get_pdf_layout_text 获取目标页的精确坐标
      3. 最后用 create_pdf_annotation 写入标注

    Args:
        item_id: Zotero PDF 附件的 itemID（数字），或 PDF 文件的绝对路径
        pages: 要提取的页码列表（0-indexed），不传则提取全文
        skip_refs: 是否自动跳过参考文献页（默认 True）
    """
    pdf_path = _resolve_pdf_path(item_id)
    result = pdf_tools.extract_bulk_text(
        pdf_path,
        pages=pages,
        skip_refs=skip_refs,
        max_chars_per_page=max_chars_per_page,
        max_total_chars=max_total_chars,
    )
    if compact:
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Tool 7: get_item_metadata ─────────────────────────────────

@mcp.tool()
def get_pdf_manifest(
    item_id: str,
    skip_refs: bool = True,
    preview_chars: int = 140,
) -> str:
    """Return page counts and short previews without returning full PDF text."""
    pdf_path = _resolve_pdf_path(item_id)
    result = pdf_tools.extract_pdf_manifest(
        pdf_path, skip_refs=skip_refs, preview_chars=preview_chars
    )
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


@mcp.tool()
def search_pdf_text(
    item_id: str,
    query: str,
    pages: list[int] | None = None,
    skip_refs: bool = True,
    context_chars: int = 160,
    max_matches: int = 50,
) -> str:
    """Search the PDF locally and return only page-labelled snippets."""
    pdf_path = _resolve_pdf_path(item_id)
    result = pdf_tools.search_pdf_text(
        pdf_path,
        query,
        pages=pages,
        skip_refs=skip_refs,
        context_chars=context_chars,
        max_matches=max_matches,
    )
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


@mcp.tool()
def ollama_status() -> str:
    """Report local Ollama availability and configured models."""
    result = ollama_client.status()
    result["llm_model"] = OLLAMA_LLM_MODEL or None
    result["llm_fallback_model"] = OLLAMA_LLM_FALLBACK_MODEL or None
    result["embed_model"] = OLLAMA_EMBED_MODEL or None
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


@mcp.tool()
def prepare_pdf_context(
    item_id: str,
    query: str,
    pages: list[int] | None = None,
    skip_refs: bool = True,
    top_k: int = 8,
    chunk_chars: int = 2800,
    max_input_chars: int = 12000,
    use_ollama: bool = True,
) -> str:
    """Retrieve relevant chunks and optionally compress them with Ollama.

    The response contains verbatim evidence and source pages, not generated
    coordinates. Call highlight_text_phrase to validate phrases before writing.
    """
    query = " ".join(query.split())
    if not query:
        raise ValueError("query must not be empty")
    if top_k < 1 or top_k > 50:
        raise ValueError("top_k must be between 1 and 50")
    if max_input_chars < 512:
        raise ValueError("max_input_chars must be at least 512")

    pdf_path = _resolve_pdf_path(item_id)
    extracted = pdf_tools.extract_text_chunks(
        pdf_path,
        pages=pages,
        skip_refs=skip_refs,
        max_chars_per_chunk=chunk_chars,
    )
    chunks = extracted["chunks"]
    backend = "lexical"
    ranked = pdf_tools.rank_text_chunks(chunks, query, limit=top_k)

    if use_ollama and OLLAMA_EMBED_MODEL and chunks:
        try:
            vectors = ollama_client.embed(
                OLLAMA_EMBED_MODEL,
                [query] + [chunk["text"] for chunk in chunks],
            )
            if len(vectors) == len(chunks) + 1:
                query_vector = vectors[0]
                ranked = [
                    dict(chunk, score=round(_cosine_similarity(query_vector, vector), 4))
                    for chunk, vector in zip(chunks, vectors[1:])
                ]
                ranked.sort(key=lambda item: (-item["score"], item["page"], item["chunk_id"]))
                ranked = ranked[:top_k]
                backend = "ollama_embeddings"
        except ollama_client.OllamaError as exc:
            logger.warning("Ollama embeddings unavailable; using lexical ranking: %s", exc)

    candidates = []
    used_chars = 0
    for chunk in ranked:
        value = chunk["text"]
        remaining = max_input_chars - used_chars
        if remaining <= 0:
            break
        value = value[:remaining]
        candidates.append({
            "chunk_id": chunk["chunk_id"],
            "page": chunk["page"],
            "text": value,
            "score": chunk.get("score", 0),
        })
        used_chars += len(value)

    evidence = [
        {
            "chunk_id": candidate["chunk_id"],
            "page": candidate["page"],
            "quote": candidate["text"],
            "reason": "retrieved by local text ranking",
        }
        for candidate in candidates
    ]
    model_used = None
    fallback_reason = None
    if use_ollama and OLLAMA_LLM_MODEL and candidates:
        candidate_text = "\n\n".join(
            f"[{candidate['chunk_id']} page={candidate['page']}]\n{candidate['text']}"
            for candidate in candidates
        )
        prompt = (
            "Select the passages relevant to the user request. Return JSON only with "
            "an evidence array. Each entry must contain chunk_id, page, quote and "
            "reason. quote must be copied verbatim from one candidate; never invent "
            "text, page numbers, coordinates, or conclusions. Keep at most 8 entries.\n\n"
            f"User request: {query}\n\nCandidates:\n{candidate_text}"
        )
        generated = None
        attempted_models = []
        for model_name in (OLLAMA_LLM_MODEL, OLLAMA_LLM_FALLBACK_MODEL):
            if not model_name or model_name in attempted_models:
                continue
            attempted_models.append(model_name)
            try:
                generated = ollama_client.generate_json(
                    model_name,
                    prompt,
                    system="You are a conservative research evidence selector.",
                )
                model_used = model_name
                if model_name != OLLAMA_LLM_MODEL:
                    fallback_reason = "primary_model_failed_or_insufficient_vram"
                break
            except ollama_client.OllamaError as exc:
                logger.warning("Ollama model %s failed: %s", model_name, exc)
                fallback_reason = str(exc)

        try:
            generated_items = generated.get("evidence", []) if isinstance(generated, dict) else []
            by_id = {candidate["chunk_id"]: candidate for candidate in candidates}
            validated = []
            for item in generated_items:
                if not isinstance(item, dict):
                    continue
                source = by_id.get(item.get("chunk_id"))
                quote = str(item.get("quote", "")).strip()
                if source and quote and quote.casefold() in source["text"].casefold():
                    validated.append({
                        "chunk_id": source["chunk_id"],
                        "page": source["page"],
                        "quote": quote,
                        "reason": str(item.get("reason", "")).strip()[:500],
                    })
            if validated:
                evidence = validated
            else:
                model_used = None
        except (AttributeError, TypeError) as exc:
            logger.warning("Ollama returned an unexpected response: %s", exc)
            model_used = None

    return json.dumps({
        "query": query,
        "backend": backend,
        "model": model_used,
        "fallback_reason": fallback_reason if model_used else None,
        "total_chunks": len(chunks),
        "candidate_chars": used_chars,
        "evidence": evidence,
        "fallback": model_used is None,
    }, ensure_ascii=False, separators=(",", ":"))


@mcp.tool()
def get_item_metadata(item_id: str) -> str:
    """获取 Zotero 条目的完整元数据。

    返回标题、作者列表、年份、期刊、DOI 等信息。
    支持传入文献条目 ID 或 PDF 附件 ID（自动查找父条目）。

    Args:
        item_id: Zotero 条目或 PDF 附件的 itemID（数字），或 PDF 文件路径
    """
    numeric_id = _resolve_item_id(item_id)
    result = zotero_db.get_item_metadata(numeric_id)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Tool 8: list_annotations ──────────────────────────────────

@mcp.tool()
def list_annotations(item_id: str) -> str:
    """列出 PDF 附件上已有的所有标注。

    用于检查已有标注，避免重复标注。返回每条标注的类型、颜色、文本和评论。

    Args:
        item_id: Zotero PDF 附件的 itemID（数字），或 PDF 文件的绝对路径
    """
    attachment_id = _resolve_item_id(item_id)
    result = zotero_db.list_annotations(attachment_id)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Tool 9: batch_annotate ────────────────────────────────────

@mcp.tool()
def batch_annotate(
    item_id: str,
    annotations: list[dict],
) -> str:
    """一次性创建多条 PDF 标注（减少调用次数）。

    每条标注需包含 page_index 和 rects，可选 color/text/comment/type。
    写操作需要关闭 Zotero 桌面应用。

    Args:
        item_id: Zotero PDF 附件的 itemID（数字），或 PDF 文件的绝对路径
        annotations: 标注列表，每项为:
            {"page_index": int, "rects": [[x0,y0,x1,y1],...],
             "color": str, "text": str, "comment": str, "type": str}
    """
    try:
        attachment_id = _resolve_item_id(item_id)
        pdf_path = _resolve_pdf_path(item_id)

        # 缓存每页的 page_height，避免重复解析
        page_heights: dict[int, float] = {}
        results = []

        for ann in annotations:
            page_idx = ann["page_index"]
            rects = ann["rects"]

            if page_idx not in page_heights:
                page_data = pdf_tools.extract_page_text(pdf_path, page_idx)
                page_heights[page_idx] = page_data["page_height"]

            result = zotero_db.create_annotation(
                parent_attachment_id=attachment_id,
                page_index=page_idx,
                rects=rects,
                page_height=page_heights[page_idx],
                color=ann.get("color", "#ffd400"),
                comment=ann.get("comment", ""),
                text=ann.get("text", ""),
                ann_type=ann.get("type", "highlight"),
            )
            results.append(result)

        return json.dumps({
            "created": len(results),
            "annotations": results,
            "message": f"已创建 {len(results)} 条标注。请重启 Zotero 或按 Ctrl+Shift+R 刷新查看。",
        }, ensure_ascii=False)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return json.dumps({
                "error": "database_locked",
                "message": "Zotero 数据库被锁定，请先关闭 Zotero 桌面应用再重试。",
            }, ensure_ascii=False)
        raise


# ── Tool 10: search_text_instances ─────────────────────────────

@mcp.tool()
def search_text_instances(
    item_id: str,
    page_number: int,
    search_text: str,
    case_sensitive: bool = False,
) -> str:
    """在 PDF 页面中精确搜索文本短语，返回每个匹配的坐标（用于创建标注）。

    这个工具只负责查找和返回坐标，不直接创建标注。
    配合 create_annotation_direct 使用完成标注。

    工作流：
    1. 用此工具搜索 → 获得 rects 坐标
    2. 用 create_annotation_direct → 创建标注

    Args:
        item_id: Zotero PDF 附件的 itemID（数字），或 PDF 文件的绝对路径
        page_number: 页码（从 0 开始）
        search_text: 要搜索的文本短语（如 "deep learning", "结论"）
        case_sensitive: 是否区分大小写（默认 False）

    Returns:
        {
            "matches": [
                {
                    "instance": 0,
                    "rect": [x0, y0, x1, y1],  # 单个矩形（同行文本）
                    "context": "...surrounding text..."
                }
            ]
        }
    """
    pdf_path = _resolve_pdf_path(item_id)
    result = pdf_tools.search_text_instances(
        pdf_path, page_number, search_text, case_sensitive
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Tool 11: highlight_text_phrase ─────────────────────────────

@mcp.tool()
def highlight_text_phrase(
    item_id: str,
    page_number: int,
    phrase: str,
    case_sensitive: bool = False,
) -> str:
    """智能查找文本短语并返回精确坐标（推荐使用）。

    相比 search_text_instances，这个工具能处理：
    - 跨行的文本（自动合并同行词为连续矩形）
    - 多余的空格和换行符
    - 词间的排版差异

    返回的 rects 格式与 Zotero 手动标注完全一致：
    - 同行文本 → 1个连续矩形
    - 跨行文本 → 每行1个矩形

    工作流：
    1. 用此工具搜索 → 获得 rects 坐标数组
    2. 用 create_annotation_direct → 创建标注

    使用场景：
    - "查找 'neural network' 的位置" → 返回所有匹配的坐标
    - "定位'深度学习'这个词" → 精确定位中文短语
    - 处理跨行的公式名称、专有名词等

    Args:
        item_id: Zotero PDF 附件的 itemID（数字），或 PDF 文件的绝对路径
        page_number: 页码（从 0 开始）
        phrase: 要查找的文本短语
        case_sensitive: 是否区分大小写（默认 False）

    Returns:
        {
            "matches": [
                {
                    "instance": 0,
                    "rects": [[x0,y0,x1,y1], ...],  # 可能多个矩形（跨行）
                    "matched_text": "actual text found"
                }
            ]
        }
    """
    pdf_path = _resolve_pdf_path(item_id)
    result = pdf_tools.highlight_text_phrase(
        pdf_path, page_number, phrase, case_sensitive
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Tool 12: extract_word_level_text ───────────────────────────

@mcp.tool()
def extract_word_level_text(item_id: str, page_number: int) -> str:
    """提取 PDF 页面的词级文本及坐标（用于自定义匹配逻辑）。

    返回页面上每个单词的独立坐标，适合需要自定义匹配逻辑的场景。
    比如：标注所有大写缩写词、特定模式的文本等。

    工作流：
    1. 用此工具获取所有词的坐标
    2. 自己筛选需要标注的词
    3. 用 create_annotation_direct 创建标注

    Args:
        item_id: Zotero PDF 附件的 itemID（数字），或 PDF 文件的绝对路径
        page_number: 页码（从 0 开始）

    Returns:
        {
            "words": [
                {
                    "text": "word",
                    "rect": [x0, y0, x1, y1],
                    "block_no": 0,
                    "line_no": 0,
                    "word_no": 0
                }
            ]
        }
    """
    pdf_path = _resolve_pdf_path(item_id)
    result = pdf_tools.extract_word_level_text(pdf_path, page_number)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Tool 13: create_annotation_direct ──────────────────────────

@mcp.tool()
def create_annotation_direct(
    item_id: str,
    page_index: int,
    rects: list[list[float]],
    text: str,
    color: str = "#ffd400",
    comment: str = "",
    type: str = "highlight",
) -> str:
    """直接创建标注 - 使用精确坐标，与 Zotero 手动标注完全一致。

    这是所有标注工具的最终写入接口。
    其他工具（search_text_instances, highlight_text_phrase）负责查找坐标，
    这个工具负责将坐标写入 Zotero 数据库。

    坐标格式说明：
    - 单行文本：rects = [[x0, y0, x1, y1]]（1个矩形）
    - 跨行文本：rects = [[...], [...], [...]]（每行1个矩形）
    - 使用 Zotero 坐标系（左下角原点，Y轴向上）

    示例 1 - 标注标题（跨两行，绿色高亮）：
    ```
    create_annotation_direct(
        item_id="path/to/paper.pdf",
        page_index=0,
        rects=[
            [74.0, 715.4, 538.0, 731.0],    # 第一行
            [226.5, 687.5, 385.5, 703.1]    # 第二行
        ],
        text="DDPOPlace: Reinforcement-Learned Diffusion...",
        color="#5fb236",
        type="highlight"
    )
    ```

    示例 2 - 标注作者（单行，红色下划线）：
    ```
    create_annotation_direct(
        item_id="path/to/paper.pdf",
        page_index=0,
        rects=[[109.2, 665.7, 502.8, 675.4]],
        text="Junqi Chen, Haotian Wang...",
        color="#ff6666",
        type="underline"
    )
    ```

    Args:
        item_id: Zotero PDF 附件的 itemID（数字），或 PDF 文件的绝对路径
        page_index: 页码（从 0 开始）
        rects: 矩形坐标数组 [[x0,y0,x1,y1], ...]
               - 同行连续文本：1个矩形覆盖整个文本范围
               - 跨行文本：每行1个矩形
        text: 被标注的文本内容
        color: 十六进制颜色
               - "#ffd400" 黄色（默认）
               - "#28CA42" 绿色
               - "#2EA8E5" 蓝色
               - "#ff6666" 红色
               - "#a28ae5" 紫色
        comment: 附加评论（可选）
        type: "highlight"（高亮，默认）或 "underline"（下划线）
    """
    try:
        attachment_id = _resolve_item_id(item_id)
        pdf_path = _resolve_pdf_path(item_id)

        # 自动获取 page_height
        page_data = pdf_tools.extract_page_text(pdf_path, page_index)
        page_height = page_data["page_height"]

        # 创建标注
        result = zotero_db.create_annotation(
            parent_attachment_id=attachment_id,
            page_index=page_index,
            rects=rects,
            page_height=page_height,
            color=color,
            comment=comment,
            text=text,
            ann_type=type,
        )

        return json.dumps({
            **result,
            "message": "标注已创建。请重启 Zotero 或按 Ctrl+Shift+R 刷新查看。",
            "annotation_type": type,
            "rects_count": len(rects),
        }, ensure_ascii=False)

    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return json.dumps({
                "error": "database_locked",
                "message": "Zotero 数据库被锁定，请先关闭 Zotero 桌面应用再重试。",
            }, ensure_ascii=False)
        raise


# ── 内部辅助 ────────────────────────────────────────────────────

# 匹配 Zotero storage 路径中的 key: .../storage/{8字符KEY}/...
_STORAGE_KEY_RE = re.compile(r"[/\\]storage[/\\]([A-Z0-9]{8})[/\\]", re.IGNORECASE)


def _resolve_pdf_path(item_id: str) -> Path:
    """将 item_id 解析为 PDF 文件路径。

    如果是纯数字，按 Zotero itemID 查找；
    如果包含路径分隔符，按文件路径处理。
    """
    if "/" in item_id or "\\" in item_id or ":" in item_id:
        p = Path(item_id)
        if not p.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {item_id}")
        return p

    attachment_id = int(item_id)
    pdf_path = zotero_db.get_pdf_path(attachment_id)
    if pdf_path is None:
        raise FileNotFoundError(
            f"在 Zotero 数据库中未找到 itemID={attachment_id} 对应的 PDF 文件"
        )
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件在磁盘上不存在: {pdf_path}")
    return pdf_path


# ── Tool 14: delete_annotation ───────────────────────────────

@mcp.tool()
def delete_annotation(annotation_id: int) -> str:
    """删除指定的 PDF 标注。

    从 Zotero 数据库中删除一个标注。删除后需要重启 Zotero 或按 Ctrl+Shift+R 刷新。
    注意：写操作需要关闭 Zotero 桌面应用。

    Args:
        annotation_id: 标注的 itemID（从 list_annotations 获取）

    Returns:
        JSON 格式的删除结果，包含是否成功和错误信息（如有）
    """
    try:
        result = zotero_db.delete_annotation(annotation_id)
        if result.get("deleted"):
            return json.dumps({
                **result,
                "message": f"标注 {annotation_id} 已删除。请重启 Zotero 或按 Ctrl+Shift+R 刷新查看。",
            }, ensure_ascii=False)
        else:
            return json.dumps(result, ensure_ascii=False)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return json.dumps({
                "error": "database_locked",
                "message": "Zotero 数据库被锁定，请先关闭 Zotero 桌面应用再重试。",
            }, ensure_ascii=False)
        raise


# ── Tool 15: delete_annotations_batch ──────────────────────

@mcp.tool()
def delete_annotations_batch(annotation_ids: list[int]) -> str:
    """批量删除多个 PDF 标注。

    一次性删除多个标注，比逐个调用 delete_annotation 更高效。
    写操作需要关闭 Zotero 桌面应用。

    Args:
        annotation_ids: 标注 itemID 列表（从 list_annotations 获取）

    Returns:
        JSON 格式的批量删除结果，包含成功数量和失败列表
    """
    try:
        result = zotero_db.delete_annotations_batch(annotation_ids)
        return json.dumps({
            **result,
            "message": f"已删除 {result['deleted_count']} 个标注。请重启 Zotero 或按 Ctrl+Shift+R 刷新查看。",
        }, ensure_ascii=False)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return json.dumps({
                "error": "database_locked",
                "message": "Zotero 数据库被锁定，请先关闭 Zotero 桌面应用再重试。",
            }, ensure_ascii=False)
        raise


# ── 内部辅助 ────────────────────────────────────────────────────

# 匹配 Zotero storage 路径中的 key: .../storage/{8字符KEY}/...
_STORAGE_KEY_RE = re.compile(r"[/\\]storage[/\\]([A-Z0-9]{8})[/\\]", re.IGNORECASE)


def _resolve_item_id(item_id: str) -> int:
    """将 item_id（数字或文件路径）统一解析为 Zotero 数字 itemID。

    支持三种输入：
    1. 纯数字字符串 "6667" → 直接返回 6667
    2. 文件路径 ".../storage/4SQST7E8/xxx.pdf" → 提取 key → 查数据库
    3. Zotero key "4SQST7E8" → 查数据库
    """
    # 纯数字：直接返回
    if item_id.isdigit():
        return int(item_id)

    # 文件路径：从中提取 storage key
    if "/" in item_id or "\\" in item_id or ":" in item_id:
        m = _STORAGE_KEY_RE.search(item_id)
        if m:
            key = m.group(1)
            aid = zotero_db.get_attachment_id_by_key(key)
            if aid is not None:
                return aid
        raise ValueError(
            f"无法从路径中解析 Zotero itemID: {item_id}\n"
            f"请确保路径包含 .../storage/{{KEY}}/... 格式"
        )

    # 可能是 Zotero key
    aid = zotero_db.get_attachment_id_by_key(item_id)
    if aid is not None:
        return aid

    raise ValueError(f"无法解析 item_id: {item_id}")


@mcp.tool()
def zotero_status() -> str:
    """检查 Zotero 进程、数据库路径和写锁状态。

    Call this before write operations or when a tool reports database_locked.
    Reports whether Zotero is running, its PIDs, whether the database is
    writable, and a hint for the user.
    """
    return json.dumps(get_zotero_status(refresh=True), ensure_ascii=False, indent=2)


@mcp.tool()
def find_duplicate_pdfs() -> str:
    """Find byte-identical PDFs stored under the same paper title.

    Read-only. Each group reports whether it is mergeable and which attachment
    would be kept. Copies detected as different languages are reported with
    reason=different_language and are never merged.
    """
    groups = duplicates.find_duplicate_pdfs()
    return json.dumps(
        {"group_count": len(groups), "groups": groups},
        ensure_ascii=False,
        separators=(",", ":"),
    )


@mcp.tool()
def merge_duplicate_pdfs(dry_run: bool = True, title: str | None = None) -> str:
    """Merge duplicate PDF annotations and notes into the kept copy.

    Always inspect with find_duplicate_pdfs or dry_run=true first. Applying a
    merge (dry_run=false) requires Zotero to be closed: unique annotations and
    notes are moved, tags/collections are merged, and duplicate items are moved
    to the Zotero trash. Different-language copies are skipped.
    """
    try:
        result = duplicates.merge_duplicate_pdfs(dry_run=dry_run, title=title)
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return json.dumps({
                "error": "database_locked",
                "message": "Zotero database is locked; close Zotero and retry.",
            }, ensure_ascii=False)
        raise


# ── 入口 ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Annota MCP Server 启动中...")
    logger.info("Zotero 数据库: %s", ZOTERO_DB_PATH)
    logger.info("Zotero 存储目录: %s", ZOTERO_STORAGE_DIR)
    mcp.run(transport="stdio")
