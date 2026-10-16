"""내려받기 수 집계 — GitHub Actions(stats.yml)가 매일 돌려 stats 브랜치의 STATS.md 를 고친다.

GitHub 은 Release 첨부 파일마다 '내려받은 횟수'만 센다(누가 받았는지는 모름).
- 자동 업데이트도 새 버전 파일을 내려받으므로 1회로 센다.
  → '최신 버전 내려받기 수' ≈ 최신 버전을 쓰는 PC 수(대략).
- history.csv 에 날마다 누적 합계를 쌓아 두고, 하루 늘어난 수를 계산한다.
사용: python tools/download_stats.py <출력 폴더>   (출력 폴더에 이전 history.csv 가 있으면 이어 씀)
"""

import csv
import datetime as dt
import os
import sys

import requests

REPO = "kohomkpi-code/news-monitor"
KST = dt.timezone(dt.timedelta(hours=9))


def fetch_releases() -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    out, page = [], 1
    while True:
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases", headers=headers,
                         params={"per_page": 100, "page": page}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    rels = fetch_releases()
    rows = []
    for rel in rels:
        n = sum(a.get("download_count", 0) for a in rel.get("assets", []) if a["name"].lower().endswith(".exe"))
        rows.append((rel["tag_name"], rel.get("published_at", "")[:10], n))
    total = sum(r[2] for r in rows)
    today = dt.datetime.now(KST).date().isoformat()

    hist_path = os.path.join(out_dir, "history.csv")
    hist: dict[str, int] = {}
    if os.path.exists(hist_path):
        with open(hist_path, encoding="utf-8") as f:
            hist = {d: int(t) for d, t in csv.reader(f) if d != "date"}
    hist[today] = total
    with open(hist_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "total"])
        for d in sorted(hist):
            w.writerow([d, hist[d]])

    days = sorted(hist)
    daily = [(d, hist[d] - hist[days[i - 1]]) for i, d in enumerate(days) if i > 0][-14:]
    latest = rows[0] if rows else ("-", "-", 0)
    lines = [
        "# KOHOM 뉴스룸 — 내려받기 현황",
        "",
        f"기준: {dt.datetime.now(KST):%Y-%m-%d %H:%M} (매일 아침 자동 갱신)",
        "",
        f"- **전체 내려받기 합계: {total}회** (모든 버전, 자동 업데이트 포함)",
        f"- **최신 버전 {latest[0]} 내려받기: {latest[2]}회** ≈ 최신 버전으로 바꾼 PC 수(대략)",
        "",
        "> GitHub 은 '누가'가 아니라 '몇 번'만 셉니다. 한 PC 가 새 버전으로 자동 업데이트하면 1회로 세고,",
        "> 같은 사람이 여러 번 내려받으면 여러 번 셉니다.",
        "",
        "## 최근 하루별 증가 (최대 14일)",
        "",
        "| 날짜 | 늘어난 횟수 |",
        "|---|---|",
    ] + ([f"| {d} | {n} |" for d, n in reversed(daily)] or ["| (내일부터 쌓입니다) | |"]) + [
        "",
        "## 버전별",
        "",
        "| 버전 | 배포일 | 내려받기 |",
        "|---|---|---|",
    ] + [f"| {t} | {d} | {n} |" for t, d, n in rows]
    with open(os.path.join(out_dir, "STATS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"total={total} latest={latest}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "stats")
