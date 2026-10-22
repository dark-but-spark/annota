# Annota 配置指南

**日期**: 2026-09-10  
**项目位置**: D:\annota  
**目标**: 配置annota用于AI辅助论文阅读和标注

---

## 📋 当前状态

```
✅ 项目已clone到: D:\annota
✅ 虚拟环境已创建: D:\annota\.venv
🔲 依赖包需要安装
🔲 Claude Code MCP配置
🔲 Zotero集成
```

---

## 🚀 完整配置步骤

### 步骤1: 安装Python依赖 (2分钟)

在**PowerShell**或**命令提示符**中执行：

```powershell
# 进入项目目录
cd D:\annota

# 激活虚拟环境
.\.venv\Scripts\activate

# 安装依赖
pip install pymupdf mcp

# 验证安装
python -c "import pymupdf; print('PyMuPDF version:', pymupdf.__version__)"
python -c "import mcp; print('MCP installed successfully')"
```

**预期输出**:
```
PyMuPDF version: 1.24.x
MCP installed successfully
```

---

### 步骤2: 找到Zotero数据目录 (1分钟)

#### 方法1: 通过Zotero界面查找

1. 打开Zotero
2. 点击 **编辑 (Edit)** → **首选项 (Preferences)**
3. 点击 **高级 (Advanced)** 标签
4. 查看 **数据存储位置 (Data Directory Location)**

**默认位置**:
```
C:\Users\你的用户名\Zotero
```

#### 方法2: 手动查找

在文件资源管理器中导航到：
```
C:\Users\cjy\Zotero
```

如果存在，应该看到：
```
C:\Users\cjy\Zotero\
  ├── storage\        ← PDF文件存储在这里
  ├── zotero.sqlite   ← Zotero数据库
  └── ...
```

---

### 步骤3: 配置Claude Code MCP服务器 (3分钟)

#### 找到配置文件位置

Windows上Claude Code的配置文件在：
```
C:\Users\cjy\.claude\config.json
```

如果不存在，创建它。

#### 添加MCP服务器配置

编辑或创建 `C:\Users\cjy\.claude\config.json`，添加以下内容：

```json
{
  "mcpServers": {
    "annota": {
      "command": "D:/annota/.venv/Scripts/python.exe",
      "args": ["D:/annota/annota/server.py"],
      "env": {
        "ZOTERO_DATA_DIR": "C:/Users/cjy/Zotero"
      }
    }
  }
}
```

**重要**: 
- 路径使用正斜杠 `/` 或双反斜杠 `\\`
- 确认你的Zotero数据目录路径正确

#### 如果已有其他MCP服务器

如果文件已存在并有其他配置，合并添加：

```json
{
  "mcpServers": {
    "existing-server": {
      ...
    },
    "annota": {
      "command": "D:/annota/.venv/Scripts/python.exe",
      "args": ["D:/annota/annota/server.py"],
      "env": {
        "ZOTERO_DATA_DIR": "C:/Users/cjy/Zotero"
      }
    }
  }
}
```

---

### 步骤4: 安装Claude Skills (可选但推荐) (1分钟)

#### 方法A: 项目级别（只在当前项目可用）

Skills已经在 `D:\annota\.claude\skills\` 中，无需额外操作。

#### 方法B: 全局安装（所有项目可用）

在PowerShell中执行：

```powershell
# 复制skills到全局目录
xcopy /E /I D:\annota\.claude\skills C:\Users\cjy\.claude\skills\annota

# 或使用robocopy
robocopy D:\annota\.claude\skills C:\Users\cjy\.claude\skills\annota /E
```

---

### 步骤5: 重启Claude Code (1分钟)

1. 完全关闭Claude Code
2. 重新打开Claude Code
3. MCP服务器应该自动连接

---

### 步骤6: 验证配置 (2分钟)

在Claude Code中测试：

```
列出我Zotero库中的最近10篇论文
```

或者：

```
搜索我Zotero库中标题包含"placement"的论文
```

**预期结果**: 
- Claude应该能访问你的Zotero库
- 列出论文标题、作者、年份等

---

## 🎯 使用方法

### 基础命令

#### 1. 搜索论文

```
搜索标题包含"EXPlace"的论文
```

#### 2. 查看论文元数据

```
显示这篇论文的详细信息: EXPlace_ICLR2026.pdf
```

#### 3. 提取PDF文本

```
提取这篇论文的全文: 
C:\Users\cjy\Zotero\storage\ABCD1234\paper.pdf
```

### Slash Commands (Skills)

#### `/annota-annotate` - 智能标注

```
/annota-annotate "C:/Users/cjy/Zotero/storage/XXX/paper.pdf"
```

功能：
- 自动高亮关键发现（绿色）
- 标注方法（黄色）
- 标注结论（蓝色）
- 添加解释性注释

#### `/annota-summarize` - 生成阅读笔记

```
/annota-summarize "C:/Users/cjy/Zotero/storage/XXX/paper.pdf"
```

生成结构化笔记：
- 论文贡献
- 方法概述
- 实验结果
- 局限性
- 保存到Zotero作为子笔记

#### `/annota-review` - 模拟审稿

```
/annota-review "C:/Users/cjy/Zotero/storage/XXX/paper.pdf" ICLR
```

生成审稿意见：
- 创新性评分
- 技术质量
- 实验完整性
- 写作清晰度
- 接受建议

---

## 🔧 高级配置

### 自定义高亮颜色

修改 `.claude/skills/annota-annotate.md` 中的颜色定义：

```yaml
colors:
  findings: green    # 发现
  methods: yellow    # 方法
  results: blue      # 结果
  limitations: red   # 局限
```

### 批量处理

```python
# 批量标注多篇论文
for paper in zotero_library:
    /annota-annotate paper.path
```

---

## 📖 实际应用场景

### 场景1: 快速阅读新论文

```
用户: 我刚下载了一篇关于chip placement的新论文，帮我快速了解它

Claude执行:
1. 搜索Zotero找到论文
2. 提取摘要和结论
3. 高亮关键发现
4. 生成结构化笔记
5. 保存到Zotero
```

### 场景2: 深度分析方法

```
用户: 解释PPAPlace论文第3页的公式

Claude执行:
1. 定位到第3页
2. 提取公式LaTeX
3. 添加解释注释
4. 与相关工作对比
```

### 场景3: 文献综述

```
用户: 对比EXPlace和PPAPlace的方法差异

Claude执行:
1. 提取两篇论文的方法部分
2. 生成对比表格
3. 高亮关键差异
4. 创建综述笔记
```

---

## 🐛 常见问题排查

### 问题1: Claude Code找不到MCP服务器

**症状**: 
```
Error: MCP server 'annota' not found
```

**解决方案**:
1. 检查配置文件路径: `C:\Users\cjy\.claude\config.json`
2. 验证JSON格式正确（使用JSONLint）
3. 确认Python路径存在: `D:\annota\.venv\Scripts\python.exe`
4. 重启Claude Code

### 问题2: 无法访问Zotero数据库

**症状**:
```
Error: Cannot open Zotero database
```

**解决方案**:
1. 确认Zotero已关闭（数据库被锁定）
2. 检查数据目录路径: `C:\Users\cjy\Zotero`
3. 验证 `zotero.sqlite` 文件存在
4. 检查文件权限

### 问题3: PDF提取失败

**症状**:
```
Error: Could not extract text from PDF
```

**解决方案**:
1. 确认PDF文件路径正确
2. 检查PDF是否损坏
3. 验证PyMuPDF安装: `pip install --upgrade pymupdf`
4. 尝试用其他PDF测试

### 问题4: Skills命令不可用

**症状**:
```
/annota-annotate command not found
```

**解决方案**:
1. 检查 `.claude/skills/` 目录存在
2. 验证skill文件格式正确
3. 重启Claude Code
4. 尝试全局安装skills

---

## 📊 项目结构

```
D:\annota\
├── .venv\                   # Python虚拟环境
│   └── Scripts\
│       └── python.exe       # Python解释器
│
├── .claude\
│   └── skills\              # Claude Code技能
│       ├── annota-annotate.md
│       ├── annota-summarize.md
│       └── annota-review.md
│
├── annota\                  # 主程序
│   ├── __init__.py
│   ├── server.py           # MCP服务器
│   └── ...
│
├── docs\                    # 文档
├── assets\                  # 示例图片
├── pyproject.toml          # 项目配置
├── README.md               # 项目说明
└── SETUP_GUIDE.md          # 本文件
```

---

## ✅ 配置完成检查清单

```
□ Python依赖已安装 (pymupdf, mcp)
□ Zotero数据目录已确认
□ MCP配置已添加到 ~/.claude/config.json
□ Claude Code已重启
□ Skills已安装（项目级或全局）
□ 测试命令成功执行
□ 可以访问Zotero库
□ 可以提取PDF文本
□ Slash commands可用
```

---

## 🎓 下一步

配置完成后，你可以：

1. **管理EXPlace项目的论文**:
   ```
   将这14篇placement论文导入Zotero
   为每篇生成结构化阅读笔记
   ```

2. **快速文献回顾**:
   ```
   对比PPAPlace和EXPlace的创新点
   高亮两篇论文中的方法差异
   ```

3. **辅助论文写作**:
   ```
   提取所有论文的实验结果
   生成Related Work对比表格
   ```

4. **自动化工作流**:
   ```
   监控新下载的PDF
   自动生成阅读笔记
   创建文献综述大纲
   ```

---

## 🔗 相关链接

- **Annota GitHub**: https://github.com/dengls24/annota
- **MCP Protocol**: https://modelcontextprotocol.io
- **Zotero**: https://www.zotero.org
- **PyMuPDF文档**: https://pymupdf.readthedocs.io

---

**配置完成！开始使用annota进行智能论文阅读吧！** 📚✨

**最后更新**: 2026-09-10  
**作者**: Claude Code Assistant
