#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件合并工具 (File Merge Utility)

提供多种文件合并策略：
- 文本文件合并
- JSON 文件合并 (支持深合并字典、拼接列表)
- YAML 文件合并 (支持深合并，需 PyYAML)
- CSV 文件合并 (支持表头对齐)
- 二进制文件合并
- 通用自动检测合并

Usage:
    from merge import merge_files, merge_text_files, merge_json_files, merge_yaml_files, merge_csv_files

CLI:
    python merge.py text file1.txt file2.txt -o merged.txt
    python merge.py json data1.json data2.json -o merged.json --deep-merge
    python merge.py yaml a.yaml b.yaml -o merged.yaml
    python merge.py csv a.csv b.csv -o merged.csv
    python merge.py auto file1 file2 file3 -o merged_output
"""

import os
import json
import csv
import hashlib
import shutil
from pathlib import Path
from typing import List, Union, Dict, Any, Optional
from enum import Enum

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


class MergeStrategy(Enum):
    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    CSV = "csv"
    BINARY = "binary"
    AUTO = "auto"


def _ensure_parent_dir(path: Union[str, Path]):
    """确保输出文件的父目录存在"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def deep_merge_dicts(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """
    深度合并两个字典
    - 如果 key 在两边都是 dict，递归合并
    - 如果 key 在两边都是 list，拼接
    - 否则用 incoming 的值覆盖
    """
    result = base.copy()
    for key, val in incoming.items():
        if key in result:
            if isinstance(result[key], dict) and isinstance(val, dict):
                result[key] = deep_merge_dicts(result[key], val)
            elif isinstance(result[key], list) and isinstance(val, list):
                result[key] = result[key] + val
            else:
                # 冲突时， incoming 优先，但如果是数值可以尝试保留两者?
                result[key] = val
        else:
            result[key] = val
    return result


def merge_text_files(
    input_paths: List[Union[str, Path]],
    output_path: Union[str, Path],
    separator: str = "\n",
    encoding: str = "utf-8",
    deduplicate: bool = False,
    add_filename_header: bool = False,
    sort_lines: bool = False,
) -> Path:
    """
    合并多个文本文件

    Args:
        input_paths: 输入文件列表
        output_path: 输出文件路径
        separator: 文件之间的分隔符，默认换行
        encoding: 文件编码
        deduplicate: 是否去重
        add_filename_header: 是否在每个文件内容前添加文件名标题
        sort_lines: 是否对最终行排序

    Returns:
        输出文件 Path 对象
    """
    _ensure_parent_dir(output_path)
    output_path = Path(output_path)

    all_lines = []
    seen = set()

    for fpath in input_paths:
        fpath = Path(fpath)
        if not fpath.exists():
            raise FileNotFoundError(f"输入文件不存在: {fpath}")
        
        content = fpath.read_text(encoding=encoding)
        
        if add_filename_header:
            header = f"\n# === {fpath.name} ===\n"
            all_lines.append(header)
        
        lines = content.splitlines()
        
        if deduplicate:
            for line in lines:
                if line not in seen:
                    seen.add(line)
                    all_lines.append(line)
        else:
            all_lines.extend(lines)
        
        # 如果需要保留原始分隔符，在每个文件后加 separator
        # 这里我们已经按行合并，separator 会在最后 join 时处理
        # 但为了兼容文件间分隔，我们在文件间插入 separator 的行
        if separator != "\n" and separator.strip():
            all_lines.append(separator)

    if sort_lines:
        # 如果加了 header，就不能全局排序，需要更复杂的逻辑，这里简化：仅对非 header 行排序
        if not add_filename_header:
            all_lines = sorted(all_lines)
    
    # 去掉最后可能多加的 separator
    if all_lines and separator != "\n" and all_lines[-1] == separator:
        all_lines = all_lines[:-1]

    output_path.write_text("\n".join(all_lines) + "\n", encoding=encoding)
    return output_path


def merge_json_files(
    input_paths: List[Union[str, Path]],
    output_path: Union[str, Path],
    deep_merge: bool = True,
    merge_list_strategy: str = "concat",  # concat, unique, deep
    encoding: str = "utf-8",
    indent: int = 2,
) -> Path:
    """
    合并多个 JSON 文件

    Args:
        input_paths: JSON 文件列表
        output_path: 输出路径
        deep_merge: 是否深度合并字典
        merge_list_strategy: 列表合并策略
            - concat: 直接拼接
            - unique: 去重拼接
            - replace: 后者覆盖前者
        encoding: 编码
        indent: 输出 JSON 缩进

    Returns:
        输出文件 Path
    """
    _ensure_parent_dir(output_path)
    output_path = Path(output_path)

    if not input_paths:
        raise ValueError("input_paths 不能为空")

    merged_data: Any = None

    for i, fpath in enumerate(input_paths):
        fpath = Path(fpath)
        if not fpath.exists():
            raise FileNotFoundError(f"输入文件不存在: {fpath}")
        
        with open(fpath, 'r', encoding=encoding) as f:
            data = json.load(f)

        if merged_data is None:
            merged_data = data
            continue

        # 根据数据类型决定合并方式
        if isinstance(merged_data, dict) and isinstance(data, dict):
            if deep_merge:
                merged_data = deep_merge_dicts(merged_data, data)
            else:
                merged_data = {**merged_data, **data}
        elif isinstance(merged_data, list) and isinstance(data, list):
            if merge_list_strategy == "concat":
                merged_data = merged_data + data
            elif merge_list_strategy == "unique":
                # 简单去重，基于 json 转字符串
                seen = set(json.dumps(x, sort_keys=True, ensure_ascii=False) for x in merged_data)
                for item in data:
                    key = json.dumps(item, sort_keys=True, ensure_ascii=False)
                    if key not in seen:
                        merged_data.append(item)
                        seen.add(key)
            elif merge_list_strategy == "replace":
                merged_data = data
        else:
            # 类型不一致，转成列表
            merged_data = [merged_data, data]

    with open(output_path, 'w', encoding=encoding) as out:
        json.dump(merged_data, out, ensure_ascii=False, indent=indent)

    return output_path


def merge_yaml_files(
    input_paths: List[Union[str, Path]],
    output_path: Union[str, Path],
    deep_merge: bool = True,
    merge_list_strategy: str = "concat",
    encoding: str = "utf-8",
) -> Path:
    """
    合并多个 YAML 文件（需安装 PyYAML: pip install pyyaml）

    Args:
        input_paths: YAML 文件列表
        output_path: 输出路径
        deep_merge: 是否深合并嵌套字典
        merge_list_strategy: 列表合并策略 (concat / unique / replace)
        encoding: 编码

    Returns:
        输出文件 Path

    Raises:
        ImportError: 未安装 PyYAML 时抛出
    """
    if not _HAS_YAML:
        raise ImportError("合并 YAML 需要 PyYAML：pip install pyyaml")
    _ensure_parent_dir(output_path)
    output_path = Path(output_path)
    if not input_paths:
        raise ValueError("input_paths 不能为空")

    merged_data: Any = None
    for fpath in input_paths:
        fpath = Path(fpath)
        if not fpath.exists():
            raise FileNotFoundError(f"输入文件不存在: {fpath}")
        with open(fpath, 'r', encoding=encoding) as f:
            data = yaml.safe_load(f)
        if merged_data is None:
            merged_data = data
            continue
        if isinstance(merged_data, dict) and isinstance(data, dict):
            merged_data = deep_merge_dicts(merged_data, data) if deep_merge else {**merged_data, **data}
        elif isinstance(merged_data, list) and isinstance(data, list):
            if merge_list_strategy == "concat":
                merged_data = merged_data + data
            elif merge_list_strategy == "unique":
                seen = set(yaml.dump(x, sort_keys=True, allow_unicode=True) for x in merged_data)
                for item in data:
                    key = yaml.dump(item, sort_keys=True, allow_unicode=True)
                    if key not in seen:
                        merged_data.append(item)
                        seen.add(key)
            elif merge_list_strategy == "replace":
                merged_data = data
        else:
            merged_data = [merged_data, data]

    with open(output_path, 'w', encoding=encoding) as out:
        yaml.dump(merged_data, out, allow_unicode=True, sort_keys=False)
    return output_path


def merge_csv_files(
    input_paths: List[Union[str, Path]],
    output_path: Union[str, Path],
    encoding: str = "utf-8",
    deduplicate: bool = False,
    align_headers: bool = True,
) -> Path:
    """
    合并多个 CSV 文件
    支持表头不同的 CSV 自动对齐

    Args:
        input_paths: CSV 文件列表
        output_path: 输出路径
        encoding: 编码
        deduplicate: 是否按行去重
        align_headers: 是否对齐不同表头 (取所有表头并集)

    Returns:
        输出文件 Path
    """
    _ensure_parent_dir(output_path)
    output_path = Path(output_path)

    if not input_paths:
        raise ValueError("input_paths 不能为空")

    # 收集所有表头
    all_fieldnames = []
    if align_headers:
        field_set = []
        for fpath in input_paths:
            with open(fpath, 'r', encoding=encoding, newline='') as f:
                reader = csv.DictReader(f)
                if reader.fieldnames:
                    for fn in reader.fieldnames:
                        if fn not in field_set:
                            field_set.append(fn)
        all_fieldnames = field_set
    else:
        # 以第一个文件的表头为准
        with open(input_paths[0], 'r', encoding=encoding, newline='') as f:
            reader = csv.DictReader(f)
            all_fieldnames = reader.fieldnames or []

    seen_rows = set()
    rows_written = 0

    with open(output_path, 'w', encoding=encoding, newline='') as out_f:
        writer = csv.DictWriter(out_f, fieldnames=all_fieldnames, extrasaction='ignore')
        writer.writeheader()

        for fpath in input_paths:
            with open(fpath, 'r', encoding=encoding, newline='') as in_f:
                reader = csv.DictReader(in_f)
                for row in reader:
                    # 对齐缺失字段
                    if align_headers:
                        # 补全缺失字段为空
                        for fn in all_fieldnames:
                            if fn not in row:
                                row[fn] = ""

                    if deduplicate:
                        # 基于行内容哈希去重
                        row_tuple = tuple(sorted(row.items()))
                        row_hash = hashlib.md5(str(row_tuple).encode()).hexdigest()
                        if row_hash in seen_rows:
                            continue
                        seen_rows.add(row_hash)
                    
                    writer.writerow(row)
                    rows_written += 1

    return output_path


def merge_binary_files(
    input_paths: List[Union[str, Path]],
    output_path: Union[str, Path],
    chunk_size: int = 8192,
) -> Path:
    """二进制方式合并文件 (适用于图片、音频、视频、任意二进制)"""
    _ensure_parent_dir(output_path)
    output_path = Path(output_path)

    with open(output_path, 'wb') as out_f:
        for fpath in input_paths:
            fpath = Path(fpath)
            if not fpath.exists():
                raise FileNotFoundError(f"输入文件不存在: {fpath}")
            with open(fpath, 'rb') as in_f:
                shutil.copyfileobj(in_f, out_f, length=chunk_size)
    return output_path


def detect_file_type(file_path: Union[str, Path]) -> MergeStrategy:
    """根据扩展名自动检测文件类型"""
    ext = Path(file_path).suffix.lower()
    if ext == ".json":
        return MergeStrategy.JSON
    elif ext in {".yaml", ".yml"}:
        return MergeStrategy.YAML if _HAS_YAML else MergeStrategy.TEXT
    elif ext == ".csv":
        return MergeStrategy.CSV
    elif ext in {".txt", ".log", ".md", ".py", ".js", ".ts", ".html", ".css", ".xml", ".ini", ".cfg"}:
        return MergeStrategy.TEXT
    else:
        # 尝试读取前 1k 判断是否为文本
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                f.read(1024)
            return MergeStrategy.TEXT
        except UnicodeDecodeError:
            return MergeStrategy.BINARY


def merge_files(
    input_paths: List[Union[str, Path]],
    output_path: Union[str, Path],
    strategy: Union[str, MergeStrategy] = MergeStrategy.AUTO,
    **kwargs,
) -> Path:
    """
    通用文件合并入口，自动选择策略或按指定策略合并

    Args:
        input_paths: 输入文件列表
        output_path: 输出文件
        strategy: 合并策略 auto/text/json/yaml/csv/binary
        **kwargs: 传递给具体合并函数的额外参数

    Returns:
        输出 Path
    """
    if not input_paths:
        raise ValueError("input_paths 不能为空")

    if isinstance(strategy, str):
        strategy = MergeStrategy(strategy.lower())

    if strategy == MergeStrategy.AUTO:
        # 以第一个文件的类型为准
        detected = detect_file_type(input_paths[0])
        strategy = detected

    if strategy == MergeStrategy.TEXT:
        return merge_text_files(input_paths, output_path, **kwargs)
    elif strategy == MergeStrategy.JSON:
        return merge_json_files(input_paths, output_path, **kwargs)
    elif strategy == MergeStrategy.YAML:
        return merge_yaml_files(input_paths, output_path, **kwargs)
    elif strategy == MergeStrategy.CSV:
        return merge_csv_files(input_paths, output_path, **kwargs)
    elif strategy == MergeStrategy.BINARY:
        return merge_binary_files(input_paths, output_path, **kwargs)
    else:
        raise ValueError(f"不支持的策略: {strategy}")


def merge_folders(
    input_dirs: List[Union[str, Path]],
    output_dir: Union[str, Path],
    recursive: bool = True,
    conflict_strategy: str = "merge",  # merge, overwrite, skip
):
    """
    合并文件夹：把多个文件夹的内容合并到一个输出文件夹
    如果文件同名且是可合并类型，则尝试合并

    Args:
        input_dirs: 输入文件夹列表
        output_dir: 输出文件夹
        recursive: 是否递归处理子文件夹
        conflict_strategy: 冲突策略
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for in_dir in input_dirs:
        in_dir = Path(in_dir)
        if not in_dir.is_dir():
            raise NotADirectoryError(f"不是文件夹: {in_dir}")

        pattern = "**/*" if recursive else "*"
        for src_path in in_dir.glob(pattern):
            if src_path.is_dir():
                continue

            rel_path = src_path.relative_to(in_dir)
            dest_path = output_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if not dest_path.exists():
                shutil.copy2(src_path, dest_path)
            else:
                if conflict_strategy == "overwrite":
                    shutil.copy2(src_path, dest_path)
                elif conflict_strategy == "skip":
                    continue
                elif conflict_strategy == "merge":
                    # 尝试合并文件
                    try:
                        detect = detect_file_type(dest_path)
                        # 先备份目标到临时，合并后写回
                        tmp_merged = dest_path.with_suffix(dest_path.suffix + ".merged.tmp")
                        if detect == MergeStrategy.JSON:
                            merge_json_files([dest_path, src_path], tmp_merged)
                        elif detect == MergeStrategy.YAML:
                            merge_yaml_files([dest_path, src_path], tmp_merged)
                        elif detect == MergeStrategy.CSV:
                            merge_csv_files([dest_path, src_path], tmp_merged)
                        elif detect == MergeStrategy.TEXT:
                            merge_text_files([dest_path, src_path], tmp_merged, deduplicate=False)
                        else:
                            # 二进制直接跳过或覆盖
                            continue
                        shutil.move(tmp_merged, dest_path)
                    except Exception as e:
                        print(f"[WARN] 合并失败 {rel_path}: {e}，跳过")
                        continue
    return output_dir


# ========== CLI ==========
def main():
    import argparse

    parser = argparse.ArgumentParser(description="文件合并工具 - 支持文本/JSON/YAML/CSV/二进制")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # text
    p_text = subparsers.add_parser("text", help="合并文本文件")
    p_text.add_argument("inputs", nargs="+", help="输入文件")
    p_text.add_argument("-o", "--output", required=True, help="输出文件")
    p_text.add_argument("--separator", default="\n", help="分隔符")
    p_text.add_argument("--deduplicate", action="store_true", help="去重")
    p_text.add_argument("--header", action="store_true", help="添加文件名标题")
    p_text.add_argument("--sort", action="store_true", help="排序")

    # json
    p_json = subparsers.add_parser("json", help="合并 JSON 文件")
    p_json.add_argument("inputs", nargs="+", help="输入文件")
    p_json.add_argument("-o", "--output", required=True, help="输出文件")
    p_json.add_argument("--deep-merge", action="store_true", default=True, help="深合并")
    p_json.add_argument("--no-deep-merge", dest="deep_merge", action="store_false", help="不深合并")
    p_json.add_argument("--list-strategy", choices=["concat", "unique", "replace"], default="concat")

    # yaml
    p_yaml = subparsers.add_parser("yaml", help="合并 YAML 文件")
    p_yaml.add_argument("inputs", nargs="+", help="输入文件")
    p_yaml.add_argument("-o", "--output", required=True, help="输出文件")
    p_yaml.add_argument("--deep-merge", action="store_true", default=True, help="深合并")
    p_yaml.add_argument("--no-deep-merge", dest="deep_merge", action="store_false", help="不深合并")
    p_yaml.add_argument("--list-strategy", choices=["concat", "unique", "replace"], default="concat")

    # csv
    p_csv = subparsers.add_parser("csv", help="合并 CSV 文件")
    p_csv.add_argument("inputs", nargs="+", help="输入文件")
    p_csv.add_argument("-o", "--output", required=True, help="输出文件")
    p_csv.add_argument("--deduplicate", action="store_true", help="去重")
    p_csv.add_argument("--no-align", dest="align_headers", action="store_false", help="不对齐表头")

    # auto
    p_auto = subparsers.add_parser("auto", help="自动检测合并")
    p_auto.add_argument("inputs", nargs="+", help="输入文件")
    p_auto.add_argument("-o", "--output", required=True, help="输出文件")
    p_auto.add_argument("--strategy", choices=["text", "json", "yaml", "csv", "binary", "auto"], default="auto")

    # folder
    p_folder = subparsers.add_parser("folder", help="合并文件夹")
    p_folder.add_argument("inputs", nargs="+", help="输入文件夹")
    p_folder.add_argument("-o", "--output", required=True, help="输出文件夹")
    p_folder.add_argument("--conflict", choices=["merge", "overwrite", "skip"], default="merge")

    args = parser.parse_args()

    try:
        if args.command == "text":
            out = merge_text_files(
                args.inputs,
                args.output,
                separator=args.separator,
                deduplicate=args.deduplicate,
                add_filename_header=args.header,
                sort_lines=args.sort,
            )
        elif args.command == "json":
            out = merge_json_files(
                args.inputs,
                args.output,
                deep_merge=args.deep_merge,
                merge_list_strategy=args.list_strategy,
            )
        elif args.command == "yaml":
            out = merge_yaml_files(
                args.inputs,
                args.output,
                deep_merge=args.deep_merge,
                merge_list_strategy=args.list_strategy,
            )
        elif args.command == "csv":
            out = merge_csv_files(
                args.inputs,
                args.output,
                deduplicate=args.deduplicate,
                align_headers=args.align_headers if hasattr(args, 'align_headers') else True,
            )
        elif args.command == "auto":
            out = merge_files(args.inputs, args.output, strategy=args.strategy)
        elif args.command == "folder":
            out = merge_folders(args.inputs, args.output, conflict_strategy=args.conflict)
        
        print(f"✅ 合并完成: {out}")
    except Exception as e:
        print(f"❌ 合并失败: {e}")
        raise


if __name__ == "__main__":
    main()
