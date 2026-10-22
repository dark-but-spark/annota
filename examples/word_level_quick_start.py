#!/usr/bin/env python3
"""
Word-Level Annotation Quick Start Examples

这个文件展示如何使用 Annota 的文字级标注功能。
复制粘贴这些代码片段到 Claude Code 中使用。
"""

# ============================================================
# Example 1: 基础用法 - 标注单个短语
# ============================================================

def example_1_basic():
    """最简单的用法：查找并标注一个短语"""

    # Step 1: 查找短语
    result = highlight_text_phrase(
        item_id="path/to/paper.pdf",
        page_number=0,
        phrase="deep learning"
    )

    # Step 2: 为每个匹配创建标注
    for match in result['matches']:
        create_pdf_annotation(
            item_id="path/to/paper.pdf",
            page_index=0,
            rects=match['rects'],
            color="#ffd400",  # 黄色
            text=match['matched_text'],
            type="highlight"
        )

    print(f"✅ 标注了 {len(result['matches'])} 个 'deep learning'")


# ============================================================
# Example 2: 批量标注多个关键词
# ============================================================

def example_2_batch_keywords():
    """一次性标注多个关键词"""

    keywords = [
        "neural network",
        "machine learning",
        "artificial intelligence"
    ]

    all_annotations = []

    # 为每个关键词查找所有匹配
    for keyword in keywords:
        result = highlight_text_phrase(
            item_id="path/to/paper.pdf",
            page_number=0,
            phrase=keyword
        )

        # 收集标注
        for match in result['matches']:
            all_annotations.append({
                "page_index": 0,
                "rects": match['rects'],
                "color": "#ffd400",
                "text": match['matched_text'],
                "comment": f"关键词: {keyword}",
                "type": "highlight"
            })

    # 一次性写入所有标注
    batch_annotate(
        item_id="path/to/paper.pdf",
        annotations=all_annotations
    )

    print(f"✅ 批量标注了 {len(all_annotations)} 个关键词")


# ============================================================
# Example 3: 不同颜色标注不同类型
# ============================================================

def example_3_colored_categories():
    """用不同颜色标注不同类型的内容"""

    # 定义标注类别
    categories = {
        "methods": {
            "keywords": ["CNN", "LSTM", "transformer"],
            "color": "#2EA8E5",  # 蓝色
        },
        "results": {
            "keywords": ["accuracy", "precision", "F1 score"],
            "color": "#28CA42",  # 绿色
        },
        "problems": {
            "keywords": ["limitation", "challenge", "issue"],
            "color": "#ff6666",  # 红色
        }
    }

    all_annotations = []

    for category_name, config in categories.items():
        for keyword in config["keywords"]:
            result = highlight_text_phrase(
                item_id="path/to/paper.pdf",
                page_number=0,
                phrase=keyword
            )

            for match in result['matches']:
                all_annotations.append({
                    "page_index": 0,
                    "rects": match['rects'],
                    "color": config["color"],
                    "text": match['matched_text'],
                    "comment": f"类别: {category_name}",
                    "type": "highlight"
                })

    batch_annotate("path/to/paper.pdf", all_annotations)
    print(f"✅ 创建了 {len(all_annotations)} 个分类标注")


# ============================================================
# Example 4: 标注研究问题 (RQ1, RQ2, ...)
# ============================================================

def example_4_research_questions():
    """标注论文中的所有研究问题"""

    # 研究问题通常在摘要或引言部分
    rq_patterns = ["RQ1", "RQ2", "RQ3", "RQ4"]

    annotations = []

    # 在前3页搜索
    for page in range(3):
        for rq in rq_patterns:
            result = highlight_text_phrase(
                item_id="path/to/paper.pdf",
                page_number=page,
                phrase=rq
            )

            for match in result['matches']:
                annotations.append({
                    "page_index": page,
                    "rects": match['rects'],
                    "color": "#a28ae5",  # 紫色
                    "text": match['matched_text'],
                    "comment": f"研究问题: {rq}",
                    "type": "highlight"
                })

    if annotations:
        batch_annotate("path/to/paper.pdf", annotations)
        print(f"✅ 标注了 {len(annotations)} 个研究问题")
    else:
        print("⚠️ 未找到研究问题标记")


# ============================================================
# Example 5: 中文短语标注
# ============================================================

def example_5_chinese():
    """标注中文短语"""

    chinese_terms = [
        "深度学习",
        "神经网络",
        "机器学习",
        "人工智能"
    ]

    annotations = []

    for term in chinese_terms:
        result = highlight_text_phrase(
            item_id="path/to/paper.pdf",
            page_number=0,
            phrase=term
        )

        for match in result['matches']:
            annotations.append({
                "page_index": 0,
                "rects": match['rects'],
                "color": "#ffd400",
                "text": match['matched_text'],
                "type": "highlight"
            })

    batch_annotate("path/to/paper.pdf", annotations)
    print(f"✅ 标注了 {len(annotations)} 个中文术语")


# ============================================================
# Example 6: 搜索并验证（先看后标注）
# ============================================================

def example_6_search_before_annotate():
    """先搜索，确认后再标注"""

    phrase = "statistical significance"

    # Step 1: 搜索
    result = highlight_text_phrase(
        item_id="path/to/paper.pdf",
        page_number=0,
        phrase=phrase
    )

    if not result['matches']:
        print(f"❌ 未找到 '{phrase}'")
        return

    # Step 2: 显示所有匹配
    print(f"找到 {len(result['matches'])} 个匹配:")
    for i, match in enumerate(result['matches']):
        print(f"  {i+1}. '{match['matched_text']}'")

    # Step 3: 用户确认后标注（这里自动标注）
    annotations = [
        {
            "page_index": 0,
            "rects": match['rects'],
            "color": "#28CA42",
            "text": match['matched_text'],
            "type": "highlight"
        }
        for match in result['matches']
    ]

    batch_annotate("path/to/paper.pdf", annotations)
    print(f"✅ 已标注")


# ============================================================
# Example 7: 高级 - 使用词级提取自定义匹配
# ============================================================

def example_7_custom_matching():
    """使用词级提取实现自定义匹配逻辑"""

    # 提取所有词
    result = extract_word_level_text(
        item_id="path/to/paper.pdf",
        page_number=0
    )

    annotations = []

    # 自定义逻辑：标注所有大写的缩写词（如 CNN, LSTM, NLP）
    for word in result['words']:
        text = word['text']
        # 判断是否是2-5个字母的全大写词
        if text.isupper() and 2 <= len(text) <= 5 and text.isalpha():
            annotations.append({
                "page_index": 0,
                "rects": [word['rect']],
                "color": "#2EA8E5",
                "text": text,
                "comment": "缩写词",
                "type": "highlight"
            })

    if annotations:
        batch_annotate("path/to/paper.pdf", annotations)
        print(f"✅ 标注了 {len(annotations)} 个缩写词")


# ============================================================
# Example 8: 标注公式和数学符号
# ============================================================

def example_8_formulas():
    """标注论文中的公式引用"""

    # 公式通常表示为 (1), (2), Eq. 1 等
    formula_refs = ["Eq. 1", "Eq. 2", "Equation 3"]

    annotations = []

    for ref in formula_refs:
        result = highlight_text_phrase(
            item_id="path/to/paper.pdf",
            page_number=0,
            phrase=ref
        )

        for match in result['matches']:
            annotations.append({
                "page_index": 0,
                "rects": match['rects'],
                "color": "#2EA8E5",
                "text": match['matched_text'],
                "comment": "公式引用",
                "type": "underline"  # 用下划线而不是高亮
            })

    if annotations:
        batch_annotate("path/to/paper.pdf", annotations)
        print(f"✅ 标注了 {len(annotations)} 个公式引用")


# ============================================================
# Example 9: 完整工作流 - 从搜索到标注
# ============================================================

def example_9_complete_workflow():
    """完整的工作流示例"""

    pdf_path = "path/to/paper.pdf"

    # Phase 1: 理解论文内容
    print("📖 Phase 1: 读取论文...")
    content = get_pdf_text_bulk(pdf_path, skip_refs=True)
    print(f"  ✓ 提取了 {content['extracted_pages']} 页")

    # Phase 2: 确定要标注的关键词
    print("\n🎯 Phase 2: 确定关键词...")
    keywords = {
        "contributions": ["novel", "propose", "contribution"],
        "methods": ["algorithm", "approach", "method"],
        "results": ["demonstrate", "achieve", "outperform"]
    }

    # Phase 3: 查找并标注
    print("\n✏️ Phase 3: 创建标注...")
    all_annotations = []
    stats = {}

    for category, terms in keywords.items():
        count = 0
        for term in terms:
            # 在前5页搜索
            for page in range(min(5, content['total_pages'])):
                result = highlight_text_phrase(pdf_path, page, term)

                for match in result['matches']:
                    all_annotations.append({
                        "page_index": page,
                        "rects": match['rects'],
                        "color": {
                            "contributions": "#a28ae5",
                            "methods": "#2EA8E5",
                            "results": "#28CA42"
                        }[category],
                        "text": match['matched_text'],
                        "comment": f"类别: {category}",
                        "type": "highlight"
                    })
                    count += 1

        stats[category] = count

    # Phase 4: 批量写入
    if all_annotations:
        batch_annotate(pdf_path, all_annotations)
        print(f"\n✅ 完成！共创建 {len(all_annotations)} 个标注")
        for category, count in stats.items():
            print(f"  - {category}: {count} 个")
    else:
        print("\n⚠️ 未找到任何匹配")


# ============================================================
# 使用说明
# ============================================================

if __name__ == "__main__":
    print("="*60)
    print("Word-Level Annotation Examples")
    print("="*60)
    print()
    print("这些示例展示了如何使用 Annota 的文字级标注功能。")
    print()
    print("在 Claude Code 中使用时，直接说：")
    print('  "参考 word_level_quick_start.py 的 example_2，')
    print('   帮我标注这篇论文的关键词"')
    print()
    print("或者直接复制代码并修改 PDF 路径和关键词。")
    print()
    print("="*60)
    print()
    print("可用示例:")
    print("  1. example_1_basic() - 基础单短语标注")
    print("  2. example_2_batch_keywords() - 批量关键词")
    print("  3. example_3_colored_categories() - 分类彩色标注")
    print("  4. example_4_research_questions() - 研究问题标注")
    print("  5. example_5_chinese() - 中文短语")
    print("  6. example_6_search_before_annotate() - 先搜索再标注")
    print("  7. example_7_custom_matching() - 自定义匹配逻辑")
    print("  8. example_8_formulas() - 公式引用标注")
    print("  9. example_9_complete_workflow() - 完整工作流")
    print()
    print("="*60)
