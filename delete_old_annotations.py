#!/usr/bin/env python3
"""删除旧的坐标标注，只保留文字级标注"""

import sys
sys.path.insert(0, 'd:/annota')

from annota.zotero_db import delete_annotations_batch

# 需要保留的文字级标注 itemID: 173-182
keep_ids = {173, 174, 175, 176, 177, 178, 179, 180, 181, 182}

# 需要删除的旧标注 itemID
delete_ids = [
    137, 138, 139, 140, 141, 142, 143, 144, 145, 146,
    147, 148, 149, 150, 151, 152, 153, 155, 156, 157,
    158, 159, 160, 161, 162, 163, 164, 165, 166, 167,
    168, 169, 170
]

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

print(f"\n✅ 完成！请重启 Zotero 或按 Ctrl+Shift+R 刷新查看。")
