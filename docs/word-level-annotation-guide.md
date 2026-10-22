# 文字级标注功能指南

## 概述

Annota 现在支持**词级（word-level）精确标注**，可以精确高亮 PDF 中的特定词语或短语，而不仅仅是整行文本。

### 新增工具对比

| 工具 | 粒度 | 使用场景 |
|------|------|----------|
| `get_pdf_layout_text` | **行级** | 提取整行文本，适合理解页面结构 |
| `extract_word_level_text` | **词级** | 提取每个词的独立坐标，适合精细操作 |
| `search_text_instances` | **词级** | 搜索特定短语，返回精确位置 |
| `highlight_text_phrase` | **词级（智能）** | 🌟 推荐：自动处理跨行、空格等问题 |

---

## 三种文字级标注方法

### 方法 1: `search_text_instances` - 精确搜索

**适合场景**: 你知道要标注的确切文本

```python
# 搜索 "deep learning" 这个短语
result = search_text_instances(
    item_id="path/to/paper.pdf",
    page_number=0,
    search_text="deep learning",
    case_sensitive=False
)

# 返回格式:
{
    "page_number": 0,
    "page_height": 792.0,
    "search_text": "deep learning",
    "matches": [
        {
            "instance": 0,
            "rect": [100.5, 650.2, 180.3, 665.8],
            "context": "...recent advances in deep learning have..."
        },
        {
            "instance": 1,
            "rect": [50.2, 400.5, 130.1, 415.3],
            "context": "...using deep learning models..."
        }
    ]
}
```

**优点**: 
- 快速、精确
- 返回上下文信息
- 支持大小写敏感/不敏感

**缺点**: 
- 只能找到完全匹配的文本
- 如果短语跨行会找不到

---

### 方法 2: `extract_word_level_text` - 获取所有词

**适合场景**: 需要完全控制标注逻辑，自己选择要标注的词

```python
# 提取页面所有词的坐标
result = extract_word_level_text(
    item_id="path/to/paper.pdf",
    page_number=0
)

# 返回格式:
{
    "page_number": 0,
    "page_height": 792.0,
    "words": [
        {
            "text": "Abstract",
            "rect": [72.0, 720.5, 120.3, 735.2],
            "block_no": 0,
            "line_no": 0,
            "word_no": 0
        },
        {
            "text": "This",
            "rect": [72.0, 700.1, 95.6, 712.8],
            "block_no": 0,
            "line_no": 1,
            "word_no": 0
        },
        // ... 页面上所有的词
    ]
}
```

**优点**: 
- 最大的灵活性
- 可以自己实现复杂的匹配逻辑
- 获得页面的完整结构信息

**缺点**: 
- 数据量大（一页可能有几百个词）
- 需要自己编写匹配逻辑

---

### 方法 3: `highlight_text_phrase` - 智能匹配 🌟推荐

**适合场景**: 标注任何文本短语，自动处理各种排版问题

```python
# 智能查找并高亮短语
result = highlight_text_phrase(
    item_id="path/to/paper.pdf",
    page_number=0,
    phrase="neural network",
    case_sensitive=False
)

# 返回格式:
{
    "page_number": 0,
    "page_height": 792.0,
    "phrase": "neural network",
    "matches": [
        {
            "instance": 0,
            "rects": [
                [100.5, 650.2, 140.3, 665.8],  # "neural"
                [142.0, 650.2, 185.6, 665.8]   # "network"
            ],
            "matched_text": "neural network"
        }
    ]
}
```

**优点**: ✅
- 自动处理跨行文本（如果 "neural" 和 "network" 在不同行）
- 自动规范化空格和换行符
- 返回的 `rects` 可以直接用于 `create_pdf_annotation`
- 最符合人类直觉的使用方式

**推荐使用**: 这是最智能的方法，适合大多数场景

---

## 完整工作流示例

### 示例 1: 标注摘要中的关键词

```python
# Step 1: 查找 "conclusion" 这个词的所有出现位置
result = highlight_text_phrase(
    item_id="path/to/paper.pdf",
    page_number=0,
    phrase="conclusion"
)

# Step 2: 为每个匹配创建标注
for match in result['matches']:
    create_pdf_annotation(
        item_id="path/to/paper.pdf",
        page_index=0,
        rects=match['rects'],
        color="#28CA42",  # 绿色
        text=match['matched_text'],
        comment="重要结论",
        type="highlight"
    )
```

### 示例 2: 批量标注多个关键词

```python
# 要标注的关键词列表
keywords = ["machine learning", "neural network", "deep learning"]

annotations = []

for keyword in keywords:
    result = highlight_text_phrase(
        item_id="path/to/paper.pdf",
        page_number=0,
        phrase=keyword
    )
    
    # 收集所有匹配
    for match in result['matches']:
        annotations.append({
            "page_index": 0,
            "rects": match['rects'],
            "color": "#ffd400",  # 黄色
            "text": match['matched_text'],
            "comment": f"关键词: {keyword}",
            "type": "highlight"
        })

# 一次性写入所有标注
batch_annotate(
    item_id="path/to/paper.pdf",
    annotations=annotations
)
```

### 示例 3: 标注中文短语

```python
# 中文短语也完全支持
result = highlight_text_phrase(
    item_id="path/to/paper.pdf",
    page_number=2,
    phrase="深度学习"
)

for match in result['matches']:
    create_pdf_annotation(
        item_id="path/to/paper.pdf",
        page_index=2,
        rects=match['rects'],
        color="#2EA8E5",  # 蓝色
        text=match['matched_text'],
        type="highlight"
    )
```

---

## 与 Claude Code 配合使用

### 自然语言示例

```
# 用户：标注第2页所有 "hypothesis" 这个词为黄色
AI 调用:
1. highlight_text_phrase(item_id, page=2, phrase="hypothesis")
2. batch_annotate(item_id, [...所有匹配的标注...])

# 用户：高亮摘要中的 "contribution"
AI 调用:
1. get_pdf_text_bulk(item_id) → 确定摘要在第0页
2. highlight_text_phrase(item_id, page=0, phrase="contribution")
3. create_pdf_annotation(...) → 为每个匹配创建标注

# 用户：用绿色标注所有研究问题（RQ1, RQ2, RQ3）
AI 调用:
1. 对每个研究问题调用 highlight_text_phrase
2. 收集所有匹配
3. batch_annotate 一次性写入，color="#28CA42"
```

---

## 技术细节

### 坐标系统

所有工具返回的坐标都是 **Zotero PDF user space**（左下角原点，Y轴向上）：

```
(0, page_height) ─────────────── (page_width, page_height)
       │                                  │
       │         PDF 内容区域              │
       │                                  │
     (0, 0) ──────────────────── (page_width, 0)
```

### 跨行文本处理

`highlight_text_phrase` 能够处理跨行的短语：

```
PDF 中的实际排版:
    "We propose a novel ap-
     proach for deep learning"

查找 "approach for deep" 时:
✅ highlight_text_phrase 能找到（跨行匹配）
❌ search_text_instances 找不到（只能匹配单行内容）
```

### 性能对比

| 工具 | 单页处理时间 | 内存占用 | 适用页数 |
|------|------------|---------|---------|
| `search_text_instances` | ~50ms | 低 | 任意 |
| `extract_word_level_text` | ~100ms | 中 | <50 |
| `highlight_text_phrase` | ~150ms | 中 | 任意 |

---

## 最佳实践

### ✅ 推荐做法

1. **大多数场景使用 `highlight_text_phrase`**
   - 自动处理各种边缘情况
   - 使用最简单

2. **批量操作使用 `batch_annotate`**
   ```python
   # 收集所有标注
   annotations = []
   for keyword in keywords:
       result = highlight_text_phrase(...)
       annotations.extend(...)
   
   # 一次性写入
   batch_annotate(item_id, annotations)
   ```

3. **需要完全控制时使用 `extract_word_level_text`**
   - 例如：标注特定模式（所有大写词、所有数字等）

### ❌ 避免的做法

1. **不要对每个匹配单独调用 `create_pdf_annotation`**
   ```python
   # ❌ 慢且低效
   for match in matches:
       create_pdf_annotation(...)
   
   # ✅ 使用批量操作
   batch_annotate(item_id, [...所有标注...])
   ```

2. **不要在不需要时使用 `extract_word_level_text`**
   - 数据量大，处理慢
   - 大多数情况下 `highlight_text_phrase` 就够了

---

## 常见问题

### Q1: 找不到我要的文本？

**A**: 检查以下几点：
- 确认页码正确（0-indexed）
- 检查大小写（默认不区分，可以设置 `case_sensitive=True`）
- PDF 可能是扫描版（图片），无法提取文本
- 尝试搜索更短的片段

### Q2: 跨行文本没有被找到？

**A**: 使用 `highlight_text_phrase` 而不是 `search_text_instances`

### Q3: 如何标注公式或特殊符号？

**A**: 直接将公式文本作为 phrase 传入即可，例如：
```python
highlight_text_phrase(item_id, page, phrase="α = 0.05")
```

### Q4: 可以标注部分重叠的文本吗？

**A**: 可以，Zotero 支持重叠的标注：
```python
# 这两个标注可以重叠
highlight_text_phrase(..., phrase="deep learning")  # 黄色
highlight_text_phrase(..., phrase="learning models")  # 绿色
```

---

## 与旧功能的对比

### 旧方法（行级）

```python
# 只能标注整行
result = get_pdf_layout_text(item_id, page=0)
# 手动找到包含目标文本的行
target_line = [b for b in result['blocks'] if 'neural network' in b['text']][0]
# 标注整行（包括不需要的文字）
create_pdf_annotation(item_id, 0, [target_line['rect']], ...)
```

**问题**: 会高亮整行，包括目标词前后的所有文字

### 新方法（词级）

```python
# 精确标注特定短语
result = highlight_text_phrase(item_id, page=0, phrase="neural network")
create_pdf_annotation(item_id, 0, result['matches'][0]['rects'], ...)
```

**优势**: 只高亮 "neural network" 这两个词，不影响其他文字

---

## 总结

新的文字级标注功能让 Annota 能够：

✅ 精确标注特定词语和短语  
✅ 自动处理跨行文本  
✅ 支持中英文混合标注  
✅ 大幅提升标注精度  

**推荐使用顺序**:
1. 🌟 首选 `highlight_text_phrase`（覆盖 90% 场景）
2. 特殊需求使用 `search_text_instances`
3. 完全自定义使用 `extract_word_level_text`
