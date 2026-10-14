"""보고 완료 기사 기록 (sent_history.json).

'보고 완료로 기록' 버튼을 누르면 그날 보고한 기사 링크가 저장되고,
다음 조회 때 '이미 보고한 기사 제외' 옵션으로 걸러진다.
90일이 지난 기록은 자동 삭제한다.
"""

import datetime as dt
import json
import os

from config import app_dir

HISTORY_PATH = os.path.join(app_dir(), "sent_history.json")
KEEP_DAYS = 90


def load() -> dict[str, str]:
    """{링크: 보고한 날짜} 형태."""
    if not os.path.exists(HISTORY_PATH):
        return {}
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    cutoff = (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    return {k: v for k, v in data.items() if v >= cutoff}


def save(data: dict[str, str]) -> None:
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)


def mark_sent(links: list[str]) -> int:
    data = load()
    today = dt.date.today().isoformat()
    added = 0
    for link in links:
        if link and link not in data:
            data[link] = today
            added += 1
    save(data)
    return added


def is_sent(link: str, data: dict[str, str]) -> bool:
    return link in data
