#!/usr/bin/env python3
# -*- coding: utf-8 -*-！
"""
纯快讯提取脚本
每个数据源只提取 1 条最新内容，不做任何分析
"""

import json
import re
import urllib.request
from datetime import datetime

FEED_SPECS = [
    ("MKTNews 快讯", ["https://api.mktnews.net/api/flash?limit=5"]),
    ("华尔街见闻 快讯", ["https://api-ddc-wscn.awtmt.com/market/lives?channel=global-channel&limit=5"]),
    ("华尔街见闻 最新", ["https://api-ddc-wscn.awtmt.com/apiv1/content/articles?limit=5&plat=pc"]),
    ("华尔街见闻 最热", ["https://api-ddc-wscn.awtmt.com/apiv1/content/articles/hot?limit=5&plat=pc"]),
    ("财联社 电报", ["https://www.cls.cn/nodeapi/telegraphList?app=CailianpressWeb&os=web&sv=8.4.6&rn=5"]),
    ("财联社 深度", ["https://www.cls.cn/api/depth/home/assembled/1000?app=CailianpressWeb&os=web&sv=8.4.6&rn=5"]),
    ("财联社 热门", ["https://www.cls.cn/v1/articles/hot?app=CailianpressWeb&os=web&sv=8.4.6&rn=5"]),
    ("雪球 热门股票", []),  # 专用流程
    ("格隆汇 事件", ["https://www.gelonghui.com/api/fastnews/v2/getFastNewsList?limit=5"]),
    ("法布财经 快讯", []),  # 占位
    ("法布财经 头条", []),  # 占位
    ("金十数据", ["https://www.jin10.com/flash_newest.js"]),
]

TITLE_KEYS = ["title", "content", "digest", "summary", "brief", "name", "description"]

def fetch(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        return None

def extract_one(payload, source):
    """从任意 JSON 中提取第一条标题"""
    if isinstance(payload, dict):
        for key in ["data", "list", "items", "result", "news", "lives"]:
            if key in payload:
                payload = payload[key]
                break
    if isinstance(payload, list) and payload:
        for row in payload:
            for k in TITLE_KEYS:
                if isinstance(row, dict) and k in row:
                    title = str(row[k]).strip()
                    if len(title) >= 4:
                        return f"{source}：{title}"
    return f"{source}：（提取失败）"

def main():
    print(f"【快讯提取】{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    
    for name, urls in FEED_SPECS:
        if not urls:
            print(f"{name}：（无公开端点）")
            continue
            
        item = None
        for url in urls:
            body = fetch(url)
            if not body:
                continue
            try:
                data = json.loads(body)
                item = extract_one(data, name)
                if item and "失败" not in item:
                    break
            except Exception:
                # 金十数据特殊处理
                if "jin10" in url:
                    m = re.search(r'[\{\[]', body)
                    if m:
                        try:
                            data = json.loads(body[m.start():].rstrip(';\n '))
                            item = extract_one(data, name)
                            if item:
                                break
                        except Exception:
                            pass
        print(item or f"{name}：（提取失败）")

if __name__ == "__main__":
    main()
