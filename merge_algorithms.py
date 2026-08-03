#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
归并相关算法实现
- 合并两个有序数组/列表
- 归并排序
- 合并 K 个有序列表
- 合并区间
"""

from typing import List, TypeVar, Callable, Any
import heapq

T = TypeVar('T')

def merge_two_sorted(a: List[T], b: List[T], key: Callable[[T], Any] = None, reverse=False) -> List[T]:
    """
    合并两个有序列表，返回新的有序列表
    时间复杂度 O(n+m)
    
    Args:
        a, b: 两个已排序的列表
        key: 可选的排序键函数
        reverse: 是否降序
    
    Example:
        >>> merge_two_sorted([1,3,5], [2,4,6])
        [1, 2, 3, 4, 5, 6]
    """
    i = j = 0
    merged = []
    
    def get_key(x):
        return key(x) if key else x
    
    while i < len(a) and j < len(b):
        ka, kb = get_key(a[i]), get_key(b[j])
        if reverse:
            if ka >= kb:
                merged.append(a[i]); i+=1
            else:
                merged.append(b[j]); j+=1
        else:
            if ka <= kb:
                merged.append(a[i]); i+=1
            else:
                merged.append(b[j]); j+=1
    
    # 剩余
    merged.extend(a[i:])
    merged.extend(b[j:])
    return merged


def merge_k_sorted(lists: List[List[T]]) -> List[T]:
    """
    合并 K 个有序列表，使用最小堆，时间 O(N log K)
    
    Args:
        lists: K 个有序列表的列表
    
    Example:
        >>> merge_k_sorted([[1,4,7],[2,5,8],[3,6,9]])
        [1,2,3,4,5,6,7,8,9]
    """
    heap = []
    result = []
    
    # 初始化堆： (值, 列表索引, 元素索引)
    for idx, lst in enumerate(lists):
        if lst:
            heapq.heappush(heap, (lst[0], idx, 0))
    
    while heap:
        val, list_idx, elem_idx = heapq.heappop(heap)
        result.append(val)
        if elem_idx + 1 < len(lists[list_idx]):
            next_val = lists[list_idx][elem_idx + 1]
            heapq.heappush(heap, (next_val, list_idx, elem_idx + 1))
    
    return result


def merge_sort(arr: List[T], key: Callable[[T], Any] = None, reverse=False) -> List[T]:
    """归并排序实现，稳定排序，O(n log n)"""
    if len(arr) <= 1:
        return arr[:]
    
    mid = len(arr) // 2
    left = merge_sort(arr[:mid], key=key, reverse=reverse)
    right = merge_sort(arr[mid:], key=key, reverse=reverse)
    
    return merge_two_sorted(left, right, key=key, reverse=reverse)


def merge_intervals(intervals: List[List[int]]) -> List[List[int]]:
    """
    合并重叠区间，LeetCode 经典题
    
    Example:
        >>> merge_intervals([[1,3],[2,6],[8,10],[15,18]])
        [[1,6],[8,10],[15,18]]
    """
    if not intervals:
        return []
    
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]
    
    for current in intervals[1:]:
        last = merged[-1]
        if current[0] <= last[1]:  # 重叠
            last[1] = max(last[1], current[1])
        else:
            merged.append(current)
    
    return merged


def merge_dictionaries(*dicts, deep=True):
    """合并多个字典的快捷方法"""
    from merge import deep_merge_dicts
    if not dicts:
        return {}
    result = dicts[0].copy()
    for d in dicts[1:]:
        if deep:
            result = deep_merge_dicts(result, d)
        else:
            result.update(d)
    return result


if __name__ == "__main__":
    print("=== 测试合并两个有序数组 ===")
    print(merge_two_sorted([1,3,5,7], [2,4,6,8]))
    print(merge_two_sorted([1,2,3], [], reverse=False))

    print("\n=== 测试合并 K 个有序数组 ===")
    print(merge_k_sorted([[1,4,7],[2,5,8],[3,6,9]]))
    print(merge_k_sorted([[1,3,5],[1,2,3],[6]]))

    print("\n=== 测试归并排序 ===")
    print(merge_sort([5,2,8,1,9,3,7,4,6]))
    print(merge_sort(["banana","apple","cherry"], key=lambda x: len(x)))

    print("\n=== 测试合并区间 ===")
    print(merge_intervals([[1,3],[2,6],[8,10],[15,18]]))
    print(merge_intervals([[1,4],[4,5]]))
