# -*- coding: utf-8 -*-
"""全网热榜聚合：抓取各平台公开热榜（全部无需登录），合并写入 hot.json。

GitHub Actions（海外 IP，每 2 小时）与本机浏览器扩展（国内 IP，每小时）
共用同一套解析逻辑；每次只更新自己抓到的平台，合并写入，互不覆盖。
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "hot.json")


def now():
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M")


def get_json(url, referer=None):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
         "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def q(word):
    return urllib.parse.quote(str(word or ""))


def fetch_weibo():
    d = get_json("https://weibo.com/ajax/side/hotSearch", "https://weibo.com/")
    rows = []
    for i, it in enumerate(d["data"]["realtime"], 1):
        w = it.get("word") or ""
        if not w:
            continue
        rows.append({"rank": i, "title": w, "hot": it.get("num") or 0,
                     "url": "https://s.weibo.com/weibo?q=%23" + q(w) + "%23"})
    return rows


def fetch_douyin():
    d = get_json("https://aweme.snssdk.com/aweme/v1/hot/search/list/")
    rows = []
    for i, it in enumerate(d.get("data") or [], 1):
        w = it.get("word") or ""
        if not w:
            continue
        rows.append({"rank": i, "title": w, "hot": it.get("hot_value") or 0,
                     "url": "https://www.douyin.com/search/" + q(w)})
    return rows


def fetch_toutiao():
    d = get_json("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
                 "https://www.toutiao.com/")
    rows = []
    for i, it in enumerate(d.get("data") or [], 1):
        w = it.get("Title") or ""
        if not w:
            continue
        rows.append({"rank": i, "title": w, "hot": it.get("HotValue") or 0,
                     "url": it.get("Url") or ("https://www.toutiao.com/search/?keyword=" + q(w))})
    return rows


def fetch_baidu():
    d = get_json("https://top.baidu.com/api/board?platform=wise&tab=realtime",
                 "https://top.baidu.com/board?tab=realtime")
    content = (d["data"]["cards"] or [{}])[0].get("content") or []
    # 置顶项可能嵌套一层 content
    flat = []
    for c in content:
        if isinstance(c, dict) and c.get("content"):
            flat.extend(c["content"])
        else:
            flat.append(c)
    rows = []
    for i, it in enumerate(flat, 1):
        w = it.get("word") or ""
        if not w:
            continue
        rows.append({"rank": i, "title": w, "hot": it.get("hotScore") or 0,
                     "url": it.get("url") or ("https://www.baidu.com/s?wd=" + q(w))})
    return rows


def fetch_bili():
    d = get_json("https://s.search.bilibili.com/main/hotword", "https://www.bilibili.com/")
    rows = []
    for i, it in enumerate(d.get("list") or [], 1):
        w = it.get("show_name") or it.get("keyword") or ""
        if not w:
            continue
        rows.append({"rank": i, "title": w, "hot": it.get("score") or 0,
                     "url": "https://search.bilibili.com/all?keyword=" + q(w)})
    return rows


# 顺序即页面展示顺序
PLATFORMS = [
    ("weibo", "微博热搜", fetch_weibo),
    ("douyin", "抖音热点", fetch_douyin),
    ("bili", "B站热搜", fetch_bili),
    ("baidu", "百度热搜", fetch_baidu),
    ("toutiao", "头条热榜", fetch_toutiao),
]


def main():
    old = {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = {}
    plats = dict(old.get("platforms") or {})
    changed = False
    summary = []
    for key, label, fn in PLATFORMS:
        if fn is None:
            continue
        try:
            rows = fn()
            if not rows:
                raise RuntimeError("empty list")
        except Exception as e:
            summary.append("%s:FAIL" % key)
            continue
        prev = plats.get(key) or {}
        same = prev.get("items") == rows
        plats[key] = {
            "label": label,
            "updated_at": prev.get("updated_at") if same else now(),
            "items": rows,
        }
        if not same:
            changed = True
        summary.append("%s:%d" % (key, len(rows)))
    print(" ".join(summary))
    if not changed and old:
        print("no change, skip write")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now(), "platforms": plats}, f, ensure_ascii=False)
    print("hot.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
