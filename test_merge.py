#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试：文件合并工具与归并算法测试
"""

import json
import csv
import tempfile
import unittest
from pathlib import Path

from merge import (
    merge_text_files,
    merge_json_files,
    merge_csv_files,
    merge_binary_files,
    merge_files,
    deep_merge_dicts,
    merge_folders,
    detect_file_type,
    MergeStrategy,
)
from merge_algorithms import (
    merge_two_sorted,
    merge_k_sorted,
    merge_sort,
    merge_intervals,
    merge_dictionaries,
)


class TestTextMerge(unittest.TestCase):
    def test_text_merge_basic_and_dedup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            f1 = tmpdir / "a.txt"
            f2 = tmpdir / "b.txt"
            f1.write_text("hello\nworld\n", encoding="utf-8")
            f2.write_text("foo\nbar\nworld\n", encoding="utf-8")
            out = tmpdir / "merged.txt"

            merge_text_files([f1, f2], out, deduplicate=False)
            self.assertEqual(
                out.read_text(encoding="utf-8").strip().splitlines(),
                ["hello", "world", "foo", "bar", "world"],
            )

            merge_text_files([f1, f2], out, deduplicate=True)
            self.assertEqual(
                out.read_text(encoding="utf-8").strip().splitlines(),
                ["hello", "world", "foo", "bar"],
            )

    def test_text_merge_header_and_sort(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            f1 = tmpdir / "a.txt"
            f2 = tmpdir / "b.txt"
            f1.write_text("banana\napple\n", encoding="utf-8")
            f2.write_text("cherry\n", encoding="utf-8")
            out = tmpdir / "merged_sort.txt"

            merge_text_files([f1, f2], out, sort_lines=True)
            lines = out.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(lines, ["apple", "banana", "cherry"])

            out_hdr = tmpdir / "merged_hdr.txt"
            merge_text_files([f1, f2], out_hdr, add_filename_header=True)
            content = out_hdr.read_text(encoding="utf-8")
            self.assertIn("# === a.txt ===", content)
            self.assertIn("# === b.txt ===", content)


class TestJsonMerge(unittest.TestCase):
    def test_json_deep_merge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            f1 = tmpdir / "a.json"
            f2 = tmpdir / "b.json"
            f1.write_text(
                json.dumps({"name": "Alice", "skills": ["python"], "meta": {"age": 20}}, ensure_ascii=False),
                encoding="utf-8",
            )
            f2.write_text(
                json.dumps({"name": "Bob", "skills": ["java"], "meta": {"city": "Macao"}, "extra": 1}, ensure_ascii=False),
                encoding="utf-8",
            )
            out = tmpdir / "merged.json"

            merge_json_files([f1, f2], out, deep_merge=True)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "Bob")
            self.assertEqual(data["skills"], ["python", "java"])
            self.assertEqual(data["meta"], {"age": 20, "city": "Macao"})
            self.assertEqual(data["extra"], 1)

    def test_json_list_strategies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            f1 = tmpdir / "c.json"
            f2 = tmpdir / "d.json"
            f1.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            f2.write_text(json.dumps([3, 4, 5]), encoding="utf-8")

            out_concat = tmpdir / "concat.json"
            merge_json_files([f1, f2], out_concat, merge_list_strategy="concat")
            self.assertEqual(json.loads(out_concat.read_text()), [1, 2, 3, 3, 4, 5])

            out_unique = tmpdir / "unique.json"
            merge_json_files([f1, f2], out_unique, merge_list_strategy="unique")
            self.assertEqual(json.loads(out_unique.read_text()), [1, 2, 3, 4, 5])

            out_replace = tmpdir / "replace.json"
            merge_json_files([f1, f2], out_replace, merge_list_strategy="replace")
            self.assertEqual(json.loads(out_replace.read_text()), [3, 4, 5])


class TestCsvMerge(unittest.TestCase):
    def test_csv_align_headers_and_dedup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            f1 = tmpdir / "a.csv"
            f2 = tmpdir / "b.csv"

            with open(f1, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["id", "name"])
                w.writeheader()
                w.writerow({"id": "1", "name": "Alice"})
                w.writerow({"id": "2", "name": "Bob"})

            with open(f2, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["id", "name", "city"])
                w.writeheader()
                w.writerow({"id": "3", "name": "Carol", "city": "Macao"})
                w.writerow({"id": "1", "name": "Alice", "city": "Zhuhai"})

            out = tmpdir / "merged.csv"
            merge_csv_files([f1, f2], out, deduplicate=True, align_headers=True)

            with open(out, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            self.assertEqual(reader.fieldnames, ["id", "name", "city"])
            self.assertEqual(len(rows), 4)


class TestBinaryAndAutoMerge(unittest.TestCase):
    def test_binary_merge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            f1 = tmpdir / "b1.bin"
            f2 = tmpdir / "b2.bin"
            f1.write_bytes(b"\x00\x01\x02")
            f2.write_bytes(b"\x03\x04\x05")
            out = tmpdir / "merged.bin"

            merge_binary_files([f1, f2], out)
            self.assertEqual(out.read_bytes(), b"\x00\x01\x02\x03\x04\x05")

    def test_auto_detect_and_merge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            f1 = tmpdir / "a.txt"
            f2 = tmpdir / "b.txt"
            f1.write_text("line1\n", encoding="utf-8")
            f2.write_text("line2\n", encoding="utf-8")
            out = tmpdir / "out.txt"

            self.assertEqual(detect_file_type(f1), MergeStrategy.TEXT)
            merge_files([f1, f2], out, strategy="auto")
            self.assertEqual(out.read_text(encoding="utf-8").strip().splitlines(), ["line1", "line2"])


class TestFolderMerge(unittest.TestCase):
    def test_folder_merge(self):
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

            merged_json = json.loads((out_dir / "common.json").read_text())
            self.assertEqual(merged_json["a"], 1)
            self.assertEqual(merged_json["c"], 2)
            self.assertEqual(merged_json["b"], [1, 2])
            self.assertTrue((out_dir / "only_in_1.txt").exists())
            self.assertTrue((out_dir / "only_in_2.txt").exists())


class TestMergeAlgorithms(unittest.TestCase):
    def test_merge_two_sorted(self):
        self.assertEqual(merge_two_sorted([1, 3, 5], [2, 4, 6]), [1, 2, 3, 4, 5, 6])
        self.assertEqual(merge_two_sorted([5, 3, 1], [6, 4, 2], reverse=True), [6, 5, 4, 3, 2, 1])

    def test_merge_k_sorted(self):
        self.assertEqual(
            merge_k_sorted([[1, 4, 7], [2, 5, 8], [3, 6, 9]]),
            [1, 2, 3, 4, 5, 6, 7, 8, 9],
        )
        self.assertEqual(merge_k_sorted([]), [])

    def test_merge_sort(self):
        self.assertEqual(merge_sort([5, 2, 8, 1, 9, 3]), [1, 2, 3, 5, 8, 9])

    def test_merge_intervals(self):
        self.assertEqual(
            merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]]),
            [[1, 6], [8, 10], [15, 18]],
        )

    def test_merge_dictionaries(self):
        d1 = {"a": 1, "b": {"x": 10}}
        d2 = {"b": {"y": 20}, "c": 3}
        self.assertEqual(merge_dictionaries(d1, d2), {"a": 1, "b": {"x": 10, "y": 20}, "c": 3})


if __name__ == "__main__":
    unittest.main()
