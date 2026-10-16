"""보고 완료 기사 기록 (sent_history.json).

'보고 완료로 기록' 버튼을 누르면 그날 보고한 기사가 저장되고,
다음 조회 때 '이미 보고한 기사 제외' 옵션으로 걸러진다. [보고 기록] 탭에서 날짜별로 본다.
3년이 지난 기록은 자동 삭제한다.

저장 형태 {링크: 정보}:
  {"date": "2026-10-16", "time": "09:41", "title": 제목, "source": 매체,
   "url": 원문 주소(알면), "main": 대표 기사 링크}
- 같은 사안으로 묶인 다른 매체 기사도 함께 기록한다(다음 조회에서 걸러지게). 그런 줄은 main 이
  대표 기사 링크라서, 화면에는 대표 기사만 한 줄로 보인다.
- v0.6 이하의 {링크: 날짜} 형태도 그대로 읽는다.
- 그룹웨어에서 내려받은 지난 보고 메일도 불러올 수 있다(import_day, mail_import.py).
- 기사 주소는 구글 경유 주소와 원문 주소가 달라 링크만으로는 못 맞출 때가 있어서,
  '이미 보고한 기사'는 제목으로도 한 번 더 확인한다(sent_titles).
"""

import datetime as dt
import json
import os

from config import app_dir

HISTORY_PATH = os.path.join(app_dir(), "sent_history.json")
KEEP_DAYS = 365 * 3  # 3년 — 불러온 지난 보고 메일도 오래 남게


def _normalize(link: str, v) -> dict:
    if isinstance(v, str):  # 예전 형태: 날짜만
        return {"date": v, "time": "", "title": "", "source": "", "url": "", "main": link}
    v = dict(v)
    v.setdefault("main", link)
    for k in ("date", "time", "title", "source", "url"):
        v.setdefault(k, "")
    return v


def load() -> dict[str, dict]:
    if not os.path.exists(HISTORY_PATH):
        return {}
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    cutoff = (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    out = {}
    for link, v in data.items():
        rec = _normalize(link, v)
        if rec["date"] >= cutoff:
            out[link] = rec
    return out


def save(data: dict[str, dict]) -> None:
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def mark_sent(entries: list[dict], when: dt.datetime | None = None) -> int:
    """entries = [{"link", "title", "source", "url", "main"}]. 새로 기록한 대표 기사 수를 돌려준다."""
    data = load()
    when = when or dt.datetime.now()
    added = 0
    for e in entries:
        link = e.get("link")
        if not link or link in data:
            continue
        data[link] = {"date": when.date().isoformat(), "time": when.strftime("%H:%M"),
                      "title": e.get("title", ""), "source": e.get("source", ""),
                      "url": e.get("url", ""), "main": e.get("main") or link}
        if data[link]["main"] == link:
            added += 1
    save(data)
    return added


def import_day(day: str, time: str, items: list[tuple[str, str, str]]) -> tuple[int, int]:
    """지난 보고 메일 한 통을 기록에 넣는다. items = [(링크, 제목, 매체)]. (추가 수, 이미 있던 수)."""
    data = load()
    added = skipped = 0
    for link, title, source in items:
        if link in data:
            skipped += 1
            continue
        data[link] = {"date": day, "time": time, "title": title, "source": source, "url": link, "main": link}
        added += 1
    save(data)
    return added, skipped


def sent_titles(data: dict[str, dict], normalize) -> set[str]:
    """보고한 기사 제목들(normalize 로 비교용으로 바꾼 것)."""
    return {normalize(r["title"]) for r in data.values() if len(r.get("title", "")) >= 8}


def is_sent(link: str | list[str], data: dict) -> bool:
    """링크 하나 또는 여러 개(같은 사안으로 묶인 기사들) 중 하나라도 보고했으면 True."""
    links = [link] if isinstance(link, str) else link
    return any(l in data for l in links)


def by_date(data: dict[str, dict]) -> dict[str, list[tuple[str, dict]]]:
    """{날짜: [(링크, 정보), ...]} — 대표 기사만, 날짜는 최근 순, 그날 안에서는 기록 순."""
    days: dict[str, list[tuple[str, dict]]] = {}
    for link, rec in data.items():
        if rec["main"] == link:
            days.setdefault(rec["date"], []).append((link, rec))
    for items in days.values():
        items.sort(key=lambda x: x[1]["time"])
    return dict(sorted(days.items(), reverse=True))


def remove(main_links: list[str]) -> int:
    """대표 기사 기록을 지운다(함께 묶여 기록된 기사도). 지운 대표 기사 수."""
    data = load()
    targets = set(main_links)
    before = sum(1 for l, r in data.items() if r["main"] == l and l in targets)
    data = {l: r for l, r in data.items() if l not in targets and r["main"] not in targets}
    save(data)
    return before
