#!/usr/bin/env python3
"""删除PPAPlace旧的坐标标注，只保留文字级标注"""

import sys
import os
sys.path.insert(0, 'd:/annota')

# 设置环境变量
os.environ['ZOTERO_DATA_DIR'] = r'C:\Users\cjy\Zotero'

from annota.zotero_db import delete_annotations_batch

# 需要保留的文字级标注 itemID: 183-191
keep_ids = {183, 184, 185, 186, 187, 188, 189, 190, 191}

# 需要删除的旧标注 itemID: 77-84
delete_ids = [77, 78, 79, 80, 81, 82, 83, 84]

print(f"准备删除 {len(delete_ids)} 个旧标注...")
print(f"保留的文字级标注: {sorted(keep_ids)}")
print(f"\n开始删除...")

result = delete_annotations_batch(delete_ids)
print(f"\n删除结果:")
print(f"  成功删除: {result.get('deleted_count', 0)} 个")
if result.get('failed'):
    print(f"  失败: {len(result['failed'])} 个")
    for item in result['failed']:
        print(f"    - itemID {item['id']}: {item['error']}")

print(f"\n完成！请重启 Zotero 或按 Ctrl+Shift+R 刷新查看。")
