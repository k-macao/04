#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文件合并工具
"""
import json
import csv
import tempfile
from pathlib import Path
from merge import (
    merge_text_files,
    merge_json_files,
    merge_csv_files,
    merge_files,
    deep_merge_dicts,
    merge_folders,
)

def test_text_merge():
    print("=== 测试文本合并 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        f1 = tmpdir / "a.txt"
        f2 = tmpdir / "b.txt"
        f1.write_text("hello\nworld\n", encoding="utf-8")
        f2.write_text("foo\nbar\nworld\n", encoding="utf-8")
        out = tmpdir / "merged.txt"

        merge_text_files([f1, f2], out, deduplicate=False)
        print(f"普通合并:\n{out.read_text()}")

        merge_text_files([f1, f2], out, deduplicate=True)
        print(f"去重合并:\n{out.read_text()}")

        merge_text_files([f1, f2], out, add_filename_header=True)
        print(f"带标题合并:\n{out.read_text()}")
    print("✅ 文本合并测试通过\n")


def test_json_merge():
    print("=== 测试 JSON 合并 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        f1 = tmpdir / "a.json"
        f2 = tmpdir / "b.json"
        f1.write_text(json.dumps({"name": "Alice", "skills": ["python"], "meta": {"age": 20}}, ensure_ascii=False), encoding="utf-8")
        f2.write_text(json.dumps({"name": "Bob", "skills": ["java"], "meta": {"city": "Macao"}, "extra": 1}, ensure_ascii=False), encoding="utf-8")
        out = tmpdir / "merged.json"

        merge_json_files([f1, f2], out, deep_merge=True)
        print(f"深合并结果:\n{out.read_text(encoding='utf-8')}")

        # 列表合并
        f3 = tmpdir / "c.json"
        f4 = tmpdir / "d.json"
        f3.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        f4.write_text(json.dumps([3, 4, 5]), encoding="utf-8")
        out2 = tmpdir / "merged_list.json"
        merge_json_files([f3, f4], out2, merge_list_strategy="unique")
        print(f"列表去重合并:\n{out2.read_text()}")
    print("✅ JSON 合并测试通过\n")


def test_csv_merge():
    print("=== 测试 CSV 合并 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        f1 = tmpdir / "a.csv"
        f2 = tmpdir / "b.csv"

        with open(f1, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=["id", "name"])
            w.writeheader()
            w.writerow({"id": "1", "name": "Alice"})
            w.writerow({"id": "2", "name": "Bob"})

        with open(f2, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=["id", "name", "city"])
            w.writeheader()
            w.writerow({"id": "3", "name": "Carol", "city": "Macao"})
            w.writerow({"id": "1", "name": "Alice", "city": "Zhuhai"})  # 重复测试

        out = tmpdir / "merged.csv"
        merge_csv_files([f1, f2], out, deduplicate=False, align_headers=True)
        print(f"对齐表头合并:\n{out.read_text(encoding='utf-8')}")

        out2 = tmpdir / "merged_dedup.csv"
        merge_csv_files([f1, f2], out2, deduplicate=True, align_headers=True)
        print(f"去重合并:\n{out2.read_text(encoding='utf-8')}")

    print("✅ CSV 合并测试通过\n")


def test_auto_merge():
    print("=== 测试自动检测合并 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        f1 = tmpdir / "a.txt"
        f2 = tmpdir / "b.txt"
        f1.write_text("line1\n")
        f2.write_text("line2\n")
        out = tmpdir / "out.txt"
        merge_files([f1, f2], out, strategy="auto")
        print(out.read_text())
    print("✅ 自动合并测试通过\n")


def test_folder_merge():
    print("=== 测试文件夹合并 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        dir1 = tmpdir / "dir1"
        dir2 = tmpdir / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        (dir1 / "common.json").write_text(json.dumps({"a": 1, "b": [1]}))
        (dir2 / "common.json").write_text(json.dumps({"c": 2, "b": [2]}))
        (dir1 / "only_in_1.txt").write_text("hello from 1")
        (dir2 / "only_in_2.txt").write_text("hello from 2")

        out_dir = tmpdir / "merged_dir"
        merge_folders([dir1, dir2], out_dir, conflict_strategy="merge")
        print(f"合并后文件夹内容: {list(out_dir.iterdir())}")
        print(f"common.json: {(out_dir / 'common.json').read_text()}")
    print("✅ 文件夹合并测试通过\n")


if __name__ == "__main__":
    test_text_merge()
    test_json_merge()
    test_csv_merge()
    test_auto_merge()
    test_folder_merge()
    print("🎉 所有测试通过！")
