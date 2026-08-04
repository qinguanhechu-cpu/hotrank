# -*- coding: utf-8 -*-
"""抓取小红书热搜词榜单，输出 data.json 供 index.html 展示。

- GitHub Actions 环境：cookie 从环境变量 XHS_COOKIE 读取
- 本地环境：从同目录 config.json 读取 cookie
用法：python3 fetch_json.py [--check]
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
OUT_PATH = os.path.join(BASE_DIR, "data.json")

BASE_URL = "https://ali.sqllb.com/api/qky2/nr/app/xh/v2"
BASE_QKY = "https://ali.sqllb.com/api/qky/xdnphb/nr/app/xhs"
N_TOKEN = "35c430ef650b459ba2b9c1409148d929"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36")

CATEGORIES = [
    "美妆", "美容个护", "鞋包潮玩", "穿搭打扮", "美食", "母婴育儿",
    "旅游出行", "家居家装", "教育", "生活", "运动健身", "兴趣爱好",
    "影视综", "婚嫁", "摄影摄像", "萌宠", "情感星座", "科技互联网",
    "资讯", "健康养生", "科学科普", "职场", "交通工具", "其他",
]
TOP_N = 100


class CookieExpired(Exception):
    pass


def get_cookie():
    env = os.environ.get("XHS_COOKIE", "").strip()
    if env:
        return env
    # 本地：先看同目录，再看上级目录的 config.json（repo 目录内不放 cookie，避免误传 GitHub）
    for p in (CONFIG_PATH, os.path.join(BASE_DIR, "..", "config.json")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                ck = json.load(f).get("cookie", "")
            if ck:
                return ck
    raise CookieExpired("未找到 cookie：Actions 需配置 XHS_COOKIE secret，本地需 config.json")


def post(cookie, path, body, base=None):
    req = urllib.request.Request(
        (base or BASE_URL) + path, data=json.dumps(body).encode("utf-8"), method="POST")
    for k, v in {
        "Content-Type": "application/json", "N-Token": N_TOKEN, "Cookie": cookie,
        "Origin": "https://ali.sqllb.com",
        "Referer": "https://ali.sqllb.com/xh/content/termsRank/heat",
        "User-Agent": UA,
    }.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise CookieExpired("HTTP %s，cookie 可能已失效" % e.code)
    if resp.get("code") != 2000:
        raise CookieExpired("code=%s，cookie 可能已失效" % resp.get("code"))
    return resp["data"]


def main():
    cookie = get_cookie()
    if "--check" in sys.argv:
        t = post(cookie, "/rank/time", {"rankType": 1})
        print("cookie ok, latest day:", (t.get("dayList") or ["?"])[0])
        return 0

    day = post(cookie, "/rank/time", {"rankType": 1})["dayList"][0]
    items = {}
    for cat in CATEGORIES:
        data = post(cookie, "/rank/hotWordHotList", {
            "typeV1": cat, "typeV2": "", "rankType": "day", "rankDate": day,
            "recentType": "", "size": TOP_N, "start": 1,
            "isNew": "", "isBoom": "", "sort": "hot_score",
        })
        rows = []
        for rank, it in enumerate(data.get("list") or [], 1):
            try:
                change = round(float(it.get("hotScoreChangeRate") or 0) * 100, 1)
            except (TypeError, ValueError):
                change = None
            labels = it.get("noteLabel") or []
            rows.append({
                "rank": rank,
                "word": it.get("hotWord") or "",
                "hot": it.get("hotScore") or 0,
                "notes": it.get("noteCount") or 0,
                "change": change,
                "new": str(it.get("isNew")) == "1",
                "label": labels[0].get("label") if labels else "",
            })
        items[cat] = rows
        time.sleep(0.5)

    traffic = []
    tdata = post(cookie, "/official/rank/tsActivities",
                 {"time": "7d", "size": 100, "accountType": [], "useridList": [], "start": 1})
    for a in tdata.get("list") or []:
        traffic.append({
            "title": a.get("title") or "",
            "type": a.get("accountType") or "",
            "nick": a.get("nickname") or "",
            "time": (a.get("createTime") or "")[:10],
            "topics": [
                {"name": t.get("topicName") or "",
                 "hot": int(t.get("hotNoteCount") or 0),
                 "view": int(t.get("viewNum") or 0)}
                for t in a.get("topics") or []
            ],
        })
    time.sleep(0.5)

    tdates = post(cookie, "/rank/trafficRankDate", {}, base=BASE_QKY)
    tday = (tdates or [""])[0]
    trows = []
    if tday:
        tdata2 = post(cookie, "/rank/topicTraffic",
                      {"type": "", "recordTime": tday, "sort": "interactive_num",
                       "start": 1, "size": 100}, base=BASE_QKY)
        for t in tdata2.get("list") or []:
            trows.append({
                "name": t.get("topicName") or "",
                "type": t.get("topicsType") or "",
                "intro": t.get("topicIntroduction") or "",
                "view": int(float(t.get("viewAdd") or 0)),
                "discuss": int(float(t.get("discussAdd") or 0)),
                "notes": int(float(t.get("noteNum") or 0)),
                "inter": int(float(t.get("interactiveNum") or 0)),
            })
    time.sleep(0.5)

    now = datetime.now(timezone(timedelta(hours=8)))
    out = {
        "rank_date": day,
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "categories": CATEGORIES,
        "items": items,
        "traffic": traffic,
        "topics_traffic": {"date": tday, "list": trows},
    }
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, encoding="utf-8") as f:
                old = json.load(f)
            old_cmp = {k: v for k, v in old.items() if k != "generated_at"}
            new_cmp = {k: v for k, v in out.items() if k != "generated_at"}
            if old_cmp == new_cmp:
                out["generated_at"] = old["generated_at"]
        except Exception:
            pass
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    total = sum(len(v) for v in items.values())
    print("ok: rank_date=%s rows=%d -> %s" % (day, total, OUT_PATH))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CookieExpired as e:
        print("COOKIE_EXPIRED:", e)
        sys.exit(2)
