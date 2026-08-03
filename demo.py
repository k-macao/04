#!/usr/bin/env python3
"""
合并功能演示脚本
展示所有合并功能的一站式 demo
"""
from pathlib import Path
import json
import tempfile
from merge import merge_files, merge_text_files, merge_json_files, merge_csv_files
from merge_algorithms import merge_two_sorted, merge_k_sorted, merge_sort

print("="*50)
print("文件合并工具演示 - 创建合并")
print("="*50)

# 1. 演示文本合并
print("\n1. 📄 文本文件合并")
print("-"*30)
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    (tmpdir / "1.txt").write_text("澳门\nMacao\n", encoding="utf-8")
    (tmpdir / "2.txt").write_text("科技\nUniversity\nMacao\n", encoding="utf-8")
    out = tmpdir / "merged.txt"
    merge_text_files([tmpdir/"1.txt", tmpdir/"2.txt"], out, deduplicate=True, add_filename_header=False)
    print(out.read_text(encoding="utf-8"))

# 2. 演示 JSON 合并
print("\n2. 📦 JSON 文件合并 (深合并)")
print("-"*30)
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    (tmpdir / "a.json").write_text(json.dumps({"course": "04", "students": ["Alice"], "meta": {"year": 2024}}))
    (tmpdir / "b.json").write_text(json.dumps({"students": ["Bob"], "meta": {"city": "Macao"}}))
    out = tmpdir / "merged.json"
    merge_json_files([tmpdir/"a.json", tmpdir/"b.json"], out, deep_merge=True)
    print(out.read_text())

# 3. 演示算法合并
print("\n3. 🧮 归并算法演示")
print("-"*30)
print(f"合并有序数组 [1,3,5] + [2,4,6] = {merge_two_sorted([1,3,5], [2,4,6])}")
print(f"合并 K 个有序数组 [[1,4],[2,5],[3,6]] = {merge_k_sorted([[1,4],[2,5],[3,6]])}")
print(f"归并排序 [5,1,4,2,8] = {merge_sort([5,1,4,2,8])}")

# 4. 演示项目中的 examples 文件合并
print("\n4. 📂 项目示例文件合并")
print("-"*30)
examples = Path("examples")
if examples.exists():
    txt_files = list(examples.glob("*.txt"))
    if len(txt_files) >= 2:
        out = Path("/tmp/demo_merged.txt")
        merge_files([str(p) for p in txt_files], out, strategy="auto")
        print(f"已合并 {txt_files} -> {out}")
        print(out.read_text(encoding="utf-8")[:200] + "...")

print("\n✅ 演示完成！")
print("="*50)
