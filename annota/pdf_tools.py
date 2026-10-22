"""PDF 文本提取与坐标转换。

使用 PyMuPDF (fitz) 解析 PDF 页面，提取文本块及其物理坐标，
并将坐标从 PyMuPDF 空间（左上角原点）转换为 Zotero PDF user space（左下角原点）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


# ── 坐标转换 ────────────────────────────────────────────────────

def pymupdf_rect_to_zotero(rect: tuple[float, ...], page_height: float) -> list[float]:
    """PyMuPDF rect (左上角原点, y↓) → Zotero rect (左下角原点, y↑)。

    PyMuPDF:  (x0, y0_top, x1, y1_top)  y0 < y1, y 从上往下
    Zotero:   [x0, y0_bot, x1, y1_bot]  y0 < y1, y 从下往上
    转换: zotero_y0 = H - pymupdf_y1,  zotero_y1 = H - pymupdf_y0
    """
    x0, y0, x1, y1 = rect[:4]
    return [
        round(x0, 3),
        round(page_height - y1, 3),
        round(x1, 3),
        round(page_height - y0, 3),
    ]


def zotero_rect_to_pymupdf(rect: list[float], page_height: float) -> tuple[float, ...]:
    """Zotero rect → PyMuPDF rect（逆变换）。"""
    x0, y0, x1, y1 = rect
    return (x0, page_height - y1, x1, page_height - y0)


# ── 文本提取 ────────────────────────────────────────────────────

def extract_page_text(
    pdf_path: str | Path,
    page_number: int,
) -> dict:
    """提取指定 PDF 页面的文本块及其 Zotero 空间坐标。

    Returns:
        {
            "page_number": int,
            "page_width": float,
            "page_height": float,
            "blocks": [
                {"text": str, "rect": [x0, y0, x1, y1]},
                ...
            ]
        }
    """
    doc = fitz.open(str(pdf_path))
    try:
        if page_number < 0 or page_number >= len(doc):
            raise ValueError(
                f"page_number {page_number} 超出范围，"
                f"该 PDF 共 {len(doc)} 页 (0-indexed)"
            )

        page = doc[page_number]
        page_height = page.rect.height
        page_width = page.rect.width

        # 使用 dict 模式获取结构化文本（blocks → lines → spans）
        text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        blocks = []
        for block in text_dict["blocks"]:
            if block["type"] != 0:  # 只处理文本块，跳过图片块
                continue

            for line in block["lines"]:
                # 合并同一行所有 span 的文本
                line_text = ""
                for span in line["spans"]:
                    line_text += span["text"]

                line_text = line_text.strip()
                if not line_text:
                    continue

                # 用行的整体 bbox 作为坐标
                line_rect = line["bbox"]  # (x0, y0, x1, y1) PyMuPDF 坐标
                zotero_rect = pymupdf_rect_to_zotero(line_rect, page_height)

                blocks.append({
                    "text": line_text,
                    "rect": zotero_rect,
                })

        logger.info(
            "提取页面 %d: %d 个文本行, 页面尺寸 %.1f x %.1f",
            page_number, len(blocks), page_width, page_height,
        )

        return {
            "page_number": page_number,
            "page_width": round(page_width, 3),
            "page_height": round(page_height, 3),
            "blocks": blocks,
        }
    finally:
        doc.close()


def extract_bulk_text(
    pdf_path: str | Path,
    pages: list[int] | None = None,
    skip_refs: bool = True,
    max_chars_per_page: int | None = None,
    max_total_chars: int | None = None,
) -> dict:
    """批量提取多页 PDF 纯文本（无坐标），适合内容理解阶段。

    与 extract_page_text 的区别：不返回坐标，体积缩小 ~80%。
    用于两阶段工作流的第一阶段：先理解内容，再对目标页获取精确坐标。

    Args:
        pdf_path: PDF 文件路径
        pages: 要提取的页码列表（0-indexed），None = 全文
        skip_refs: 是否自动跳过参考文献页（默认 True）

    Returns:
        {
            "total_pages": int,
            "extracted_pages": int,
            "refs_start_page": int | None,
            "pages": [
                {"page": int, "text": str, "char_count": int},
                ...
            ]
        }
    """
    doc = fitz.open(str(pdf_path))
    try:
        total_pages = len(doc)

        # 检测参考文献起始页
        refs_start = _detect_refs_page(doc) if skip_refs else total_pages

        # 确定要提取的页码
        if pages is not None:
            target_pages = [p for p in pages if 0 <= p < total_pages]
        else:
            target_pages = list(range(min(refs_start, total_pages)))

        result_pages = []
        returned_chars = 0
        truncated = False
        if max_chars_per_page is not None and max_chars_per_page < 1:
            raise ValueError("max_chars_per_page must be positive")
        if max_total_chars is not None and max_total_chars < 1:
            raise ValueError("max_total_chars must be positive")
        for pn in target_pages:
            page = doc[pn]
            text = page.get_text("text").strip()
            if text:
                if max_chars_per_page is not None and len(text) > max_chars_per_page:
                    text = text[:max_chars_per_page].rstrip()
                    truncated = True
                if max_total_chars is not None:
                    remaining = max_total_chars - returned_chars
                    if remaining <= 0:
                        truncated = True
                        break
                    if len(text) > remaining:
                        text = text[:remaining].rstrip()
                        truncated = True
                result_pages.append({
                    "page": pn,
                    "text": text,
                    "char_count": len(text),
                })
                returned_chars += len(text)

        logger.info(
            "批量提取: %d/%d 页, 跳过参考文献=%s (refs_start=%s)",
            len(result_pages), total_pages, skip_refs,
            refs_start if skip_refs else "N/A",
        )

        return {
            "total_pages": total_pages,
            "extracted_pages": len(result_pages),
            "refs_start_page": refs_start if skip_refs and refs_start < total_pages else None,
            "pages": result_pages,
            "returned_chars": returned_chars,
            "truncated": truncated,
        }
    finally:
        doc.close()


def _detect_refs_page(doc) -> int:
    """启发式检测参考文献起始页。

    从最后 10 页往前扫描，寻找 References / Bibliography / 参考文献 标题。
    返回参考文献起始页码（0-indexed），未找到则返回总页数。
    """
    total = len(doc)
    scan_start = max(0, total - 10)

    for i in range(total - 1, scan_start - 1, -1):
        text = doc[i].get_text("text")
        lines = text.split("\n")
        for line in lines[:15]:  # 只检查页面前 15 行
            stripped = line.strip().lower()
            if stripped in (
                "references",
                "bibliography",
                "参考文献",
                "reference",
            ):
                return i

    return total  # 未检测到


def extract_pdf_manifest(
    pdf_path: str | Path,
    *,
    skip_refs: bool = True,
    preview_chars: int = 140,
) -> dict:
    """Return a compact page index without returning full page text."""
    if preview_chars < 0:
        raise ValueError("preview_chars must be non-negative")
    doc = fitz.open(str(pdf_path))
    try:
        total_pages = len(doc)
        refs_start = _detect_refs_page(doc) if skip_refs else total_pages
        pages = []
        for page_number in range(total_pages):
            text = doc[page_number].get_text("text").strip()
            first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
            pages.append({
                "page": page_number,
                "char_count": len(text),
                "preview": first_line[:preview_chars],
                "included": page_number < refs_start,
            })
        return {
            "total_pages": total_pages,
            "refs_start_page": refs_start if skip_refs and refs_start < total_pages else None,
            "pages": pages,
        }
    finally:
        doc.close()


def extract_text_chunks(
    pdf_path: str | Path,
    *,
    pages: list[int] | None = None,
    skip_refs: bool = True,
    max_chars_per_chunk: int = 2800,
) -> dict:
    """Extract bounded text chunks while retaining their source page."""
    if max_chars_per_chunk < 256:
        raise ValueError("max_chars_per_chunk must be at least 256")
    doc = fitz.open(str(pdf_path))
    try:
        total_pages = len(doc)
        refs_start = _detect_refs_page(doc) if skip_refs else total_pages
        if pages is None:
            target_pages = list(range(min(refs_start, total_pages)))
        else:
            target_pages = sorted({p for p in pages if 0 <= p < total_pages and p < refs_start})

        chunks = []
        total_chars = 0
        for page_number in target_pages:
            text = doc[page_number].get_text("text").strip()
            if not text:
                continue
            start = 0
            while start < len(text):
                end = min(start + max_chars_per_chunk, len(text))
                if end < len(text):
                    split_at = text.rfind(" ", start, end)
                    if split_at > start + max_chars_per_chunk // 2:
                        end = split_at
                value = text[start:end].strip()
                if value:
                    chunks.append({
                        "chunk_id": f"p{page_number}-c{len(chunks)}",
                        "page": page_number,
                        "text": value,
                        "char_count": len(value),
                    })
                    total_chars += len(value)
                start = max(end, start + 1)

        return {
            "total_pages": total_pages,
            "refs_start_page": refs_start if skip_refs and refs_start < total_pages else None,
            "chunks": chunks,
            "total_chars": total_chars,
        }
    finally:
        doc.close()


def search_pdf_text(
    pdf_path: str | Path,
    query: str,
    *,
    pages: list[int] | None = None,
    skip_refs: bool = True,
    context_chars: int = 160,
    max_matches: int = 50,
) -> dict:
    """Search page text locally and return only short, page-labelled snippets."""
    query = " ".join(query.split())
    if not query:
        raise ValueError("query must not be empty")
    if context_chars < 0 or max_matches < 1:
        raise ValueError("context_chars must be non-negative and max_matches must be positive")

    data = extract_text_chunks(
        pdf_path,
        pages=pages,
        skip_refs=skip_refs,
        max_chars_per_chunk=max(256, context_chars * 4 + len(query)),
    )
    query_folded = query.casefold()
    terms = [term for term in query_folded.split() if term]
    matches = []
    for chunk in data["chunks"]:
        text = chunk["text"]
        folded = text.casefold()
        exact_at = folded.find(query_folded)
        term_hits = sum(folded.count(term) for term in terms)
        if exact_at < 0 and term_hits == 0:
            continue
        center = exact_at if exact_at >= 0 else folded.find(terms[0])
        start = max(0, center - context_chars)
        end = min(len(text), center + max(len(query), 1) + context_chars)
        snippet = " ".join(text[start:end].split())
        matches.append({
            "page": chunk["page"],
            "chunk_id": chunk["chunk_id"],
            "score": round((5 if exact_at >= 0 else 0) + term_hits / max(len(terms), 1), 3),
            "matched_text": text[exact_at:exact_at + len(query)] if exact_at >= 0 else "",
            "snippet": snippet,
        })

    matches.sort(key=lambda item: (-item["score"], item["page"], item["chunk_id"]))
    return {
        "query": query,
        "searched_pages": sorted({chunk["page"] for chunk in data["chunks"]}),
        "matches": matches[:max_matches],
        "total_matches": len(matches),
        "refs_start_page": data["refs_start_page"],
    }


def rank_text_chunks(chunks: list[dict], query: str, limit: int = 8) -> list[dict]:
    """Rank chunks deterministically; useful as an Ollama-free fallback."""
    query_folded = " ".join(query.split()).casefold()
    terms = [term for term in query_folded.split() if term]
    ranked = []
    for chunk in chunks:
        folded = chunk["text"].casefold()
        hits = sum(folded.count(term) for term in terms)
        phrase_bonus = 5 if query_folded and query_folded in folded else 0
        if hits:
            ranked.append((phrase_bonus + hits / max(len(terms), 1), chunk))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["page"], pair[1]["chunk_id"]))
    return [dict(chunk, score=round(score, 3)) for score, chunk in ranked[:limit]]


def get_total_pages(pdf_path: str | Path) -> int:
    """返回 PDF 总页数。"""
    doc = fitz.open(str(pdf_path))
    try:
        return len(doc)
    finally:
        doc.close()


def search_text_instances(
    pdf_path: str | Path,
    page_number: int,
    search_text: str,
    case_sensitive: bool = False,
) -> dict:
    """在指定页面精确搜索文本短语，返回每个匹配实例的词级坐标。

    使用 PyMuPDF 的 search_for 功能进行精确文本匹配，
    返回的坐标可直接用于创建精确的高亮标注。

    Args:
        pdf_path: PDF 文件路径
        page_number: 页码（0-indexed）
        search_text: 要搜索的文本短语
        case_sensitive: 是否区分大小写（默认 False）

    Returns:
        {
            "page_number": int,
            "page_width": float,
            "page_height": float,
            "search_text": str,
            "matches": [
                {
                    "instance": int,  # 第几个匹配（从0开始）
                    "rect": [x0, y0, x1, y1],  # Zotero 空间坐标
                    "context": str,  # 周围的上下文文本
                },
                ...
            ]
        }
    """
    doc = fitz.open(str(pdf_path))
    try:
        if page_number < 0 or page_number >= len(doc):
            raise ValueError(
                f"page_number {page_number} 超出范围，"
                f"该 PDF 共 {len(doc)} 页 (0-indexed)"
            )

        page = doc[page_number]
        page_height = page.rect.height
        page_width = page.rect.width

        # 使用 search_for 进行文本搜索
        # flags: 0=默认（不区分大小写），16=区分大小写
        flags = 16 if case_sensitive else 0
        quads = page.search_for(search_text, flags=flags)

        matches = []
        for idx, quad in enumerate(quads):
            # quad 是一个包含4个点的四边形，转换为矩形
            rect = quad.rect  # 获取包围矩形
            zotero_rect = pymupdf_rect_to_zotero(rect, page_height)

            # 获取上下文：提取匹配位置周围的文本
            context = _extract_context(page, rect)

            matches.append({
                "instance": idx,
                "rect": zotero_rect,
                "context": context,
            })

        logger.info(
            "搜索文本 '%s' 在页面 %d: 找到 %d 个匹配",
            search_text, page_number, len(matches),
        )

        return {
            "page_number": page_number,
            "page_width": round(page_width, 3),
            "page_height": round(page_height, 3),
            "search_text": search_text,
            "matches": matches,
        }
    finally:
        doc.close()


def _extract_context(page, target_rect, context_chars: int = 50) -> str:
    """提取目标矩形周围的上下文文本。

    Args:
        page: PyMuPDF Page 对象
        target_rect: 目标文本的矩形区域
        context_chars: 前后各提取多少字符

    Returns:
        包含目标文本及其上下文的字符串
    """
    # 扩展矩形以包含周围区域
    expanded = fitz.Rect(
        target_rect.x0 - 200,  # 向左扩展
        target_rect.y0 - 50,   # 向上扩展
        target_rect.x1 + 200,  # 向右扩展
        target_rect.y1 + 50,   # 向下扩展
    )

    # 裁剪到页面边界
    expanded = expanded & page.rect

    # 提取扩展区域的文本
    context_text = page.get_textbox(expanded).strip()

    # 限制长度
    if len(context_text) > context_chars * 3:
        context_text = context_text[:context_chars * 3] + "..."

    return context_text


def _merge_rects_by_line(word_rects: list[dict], page_height: float) -> list[list[float]]:
    """将同一行的词矩形合并为连续的矩形，实现"划词"效果。

    Args:
        word_rects: 词矩形列表，每项包含 {"rect": [x0,y0,x1,y1], "pymupdf_rect": (...)}
        page_height: 页面高度

    Returns:
        合并后的矩形列表。同行的词会合并为一个大矩形，不同行的保持独立。
    """
    if not word_rects:
        return []

    # 按行分组：使用 pymupdf_rect 的 y 坐标判断是否同行
    # 允许 2 个点的垂直误差（处理轻微的行内偏移）
    LINE_TOLERANCE = 2.0

    lines = []  # [[word_rect, ...], ...]
    current_line = [word_rects[0]]

    for i in range(1, len(word_rects)):
        prev_rect = word_rects[i-1]["pymupdf_rect"]
        curr_rect = word_rects[i]["pymupdf_rect"]

        # 判断是否在同一行（y0 和 y1 都接近）
        y0_diff = abs(curr_rect[1] - prev_rect[1])
        y1_diff = abs(curr_rect[3] - prev_rect[3])

        if y0_diff <= LINE_TOLERANCE and y1_diff <= LINE_TOLERANCE:
            # 同一行
            current_line.append(word_rects[i])
        else:
            # 新行
            lines.append(current_line)
            current_line = [word_rects[i]]

    # 添加最后一行
    lines.append(current_line)

    # 合并每行的矩形
    merged_rects = []
    for line in lines:
        if len(line) == 1:
            # 单个词，直接使用
            merged_rects.append(line[0]["rect"])
        else:
            # 多个词，合并为一个大矩形
            # 使用 Zotero 坐标系统
            zotero_rects = [wr["rect"] for wr in line]

            x0 = min(r[0] for r in zotero_rects)  # 最左边
            y0 = min(r[1] for r in zotero_rects)  # 最下边（Zotero 坐标系 y 向上）
            x1 = max(r[2] for r in zotero_rects)  # 最右边
            y1 = max(r[3] for r in zotero_rects)  # 最上边

            merged_rects.append([
                round(x0, 3),
                round(y0, 3),
                round(x1, 3),
                round(y1, 3),
            ])

    return merged_rects


def extract_word_level_text(
    pdf_path: str | Path,
    page_number: int,
) -> dict:
    """提取页面的词级文本及坐标（比 extract_page_text 更精细）。

    使用 PyMuPDF 的 words 提取，每个词都有独立的坐标。
    适合需要精确到单词级别标注的场景。

    Returns:
        {
            "page_number": int,
            "page_width": float,
            "page_height": float,
            "words": [
                {
                    "text": str,
                    "rect": [x0, y0, x1, y1],  # Zotero 坐标
                    "block_no": int,
                    "line_no": int,
                    "word_no": int,
                },
                ...
            ]
        }
    """
    doc = fitz.open(str(pdf_path))
    try:
        if page_number < 0 or page_number >= len(doc):
            raise ValueError(
                f"page_number {page_number} 超出范围，"
                f"该 PDF 共 {len(doc)} 页 (0-indexed)"
            )

        page = doc[page_number]
        page_height = page.rect.height
        page_width = page.rect.width

        # 提取词级文本
        # 返回格式: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
        words_data = page.get_text("words")

        words = []
        for word_tuple in words_data:
            x0, y0, x1, y1, text, block_no, line_no, word_no = word_tuple

            # 转换为 Zotero 坐标
            zotero_rect = pymupdf_rect_to_zotero((x0, y0, x1, y1), page_height)

            words.append({
                "text": text,
                "rect": zotero_rect,
                "block_no": block_no,
                "line_no": line_no,
                "word_no": word_no,
            })

        logger.info(
            "提取页面 %d 词级文本: %d 个词",
            page_number, len(words),
        )

        return {
            "page_number": page_number,
            "page_width": round(page_width, 3),
            "page_height": round(page_height, 3),
            "words": words,
        }
    finally:
        doc.close()


def highlight_text_phrase(
    pdf_path: str | Path,
    page_number: int,
    phrase: str,
    case_sensitive: bool = False,
    match_whole_word: bool = False,
    merge_rects: bool = True,
) -> dict:
    """智能查找并返回文本短语的精确坐标，支持跨行匹配。

    相比 search_text_instances，这个函数能处理：
    - 跨行的文本短语（PDF 中可能因排版被拆成多行）
    - 多余的空格和换行符
    - 连字符断词（如 "re-\nsearch" 匹配 "research"）

    Args:
        pdf_path: PDF 文件路径
        page_number: 页码（0-indexed）
        phrase: 要查找的文本短语
        case_sensitive: 是否区分大小写
        match_whole_word: 是否只匹配完整单词
        merge_rects: 是否合并同行的矩形为连续高亮（默认 True）
                     True=连续划词效果，False=每个词独立框出

    Returns:
        {
            "page_number": int,
            "page_height": float,
            "phrase": str,
            "matches": [
                {
                    "instance": int,
                    "rects": [[x0,y0,x1,y1], ...],  # merge_rects=True时同行词会合并
                    "matched_text": str,  # 实际匹配到的原始文本
                },
                ...
            ]
        }
    """
    doc = fitz.open(str(pdf_path))
    try:
        if page_number < 0 or page_number >= len(doc):
            raise ValueError(
                f"page_number {page_number} 超出范围，"
                f"该 PDF 共 {len(doc)} 页 (0-indexed)"
            )

        page = doc[page_number]
        page_height = page.rect.height

        # 标准化搜索短语
        search_phrase = phrase if case_sensitive else phrase.lower()
        search_phrase = " ".join(search_phrase.split())  # 规范化空格

        # 提取词级数据
        words_data = page.get_text("words")
        if not words_data:
            return {
                "page_number": page_number,
                "page_height": round(page_height, 3),
                "phrase": phrase,
                "matches": [],
            }

        # 构建词序列和位置映射
        words = []
        for w in words_data:
            text = w[4] if not case_sensitive else w[4]
            if not case_sensitive:
                text = text.lower()
            words.append({
                "text": text,
                "original": w[4],
                "rect": (w[0], w[1], w[2], w[3]),
            })

        # 滑动窗口匹配
        matches = []
        phrase_words = search_phrase.split()
        window_size = len(phrase_words)

        i = 0
        match_idx = 0
        while i <= len(words) - window_size:
            # 提取窗口内的词
            window_words = words[i:i + window_size]
            window_text = " ".join([w["text"] for w in window_words])

            # 检查是否匹配
            if window_text == search_phrase:
                # 收集词的矩形
                word_rects = []
                matched_text_parts = []

                for w in window_words:
                    pymupdf_rect = w["rect"]
                    zotero_rect = pymupdf_rect_to_zotero(pymupdf_rect, page_height)
                    word_rects.append({
                        "rect": zotero_rect,
                        "pymupdf_rect": pymupdf_rect,
                        "text": w["original"]
                    })
                    matched_text_parts.append(w["original"])

                # 根据 merge_rects 决定是否合并
                if merge_rects:
                    rects = _merge_rects_by_line(word_rects, page_height)
                else:
                    rects = [wr["rect"] for wr in word_rects]

                matches.append({
                    "instance": match_idx,
                    "rects": rects,
                    "matched_text": " ".join(matched_text_parts),
                })
                match_idx += 1
                i += window_size  # 跳过已匹配的词
            else:
                i += 1

        logger.info(
            "智能搜索短语 '%s' 在页面 %d: 找到 %d 个匹配",
            phrase, page_number, len(matches),
        )

        return {
            "page_number": page_number,
            "page_height": round(page_height, 3),
            "phrase": phrase,
            "matches": matches,
        }
    finally:
        doc.close()
