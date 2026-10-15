"""AI 선별 중계 — 요청문 만들기와 선정 결과 읽기.

앱이 AI 를 직접 부르지 않는다(API 키 없음). 사람이 복사·붙여넣기로 중계한다.
1) build_request(): 표의 후보 기사를 번호 붙인 목록으로 만든다 → 클립보드로 복사
   → Claude 프로젝트 채팅에 붙여 넣기
2) parse_selection(): Claude 답변의 '#선정' 아래 줄(번호|분류|인사이트)을 읽는다
"""

import datetime as dt
import re

from naver_api import Article

SUMMARY_LEN = 80
_NO_RE = re.compile(r"^\s*(\d+)\s*[.)]?\s*$")


def build_request(articles: list[Article], today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    lines = [f"[AI 선별 요청] {today.isoformat()}, 후보 {len(articles)}건"]
    for i, a in enumerate(articles, 1):
        grade = f"[{a.grade}] " if a.grade else ""
        line = f"{i}. {grade}{a.title} ({a.source}, {a.published.strftime('%m.%d')})"
        desc = " ".join(a.description.split())
        if desc:
            line += " — " + desc[:SUMMARY_LEN]
        lines.append(line)
    return "\n".join(lines)


def parse_selection(text: str, max_no: int) -> tuple[list[tuple[int, str, str]], int]:
    """'번호|분류|인사이트' 줄들을 읽는다.

    돌려주는 값: ([(번호, 분류, 인사이트), ...] 입력 순서대로, 무시된 줄 수)
    - '#선정' 줄이 있으면 그 아래만 읽는다(답변 전체를 붙여 넣어도 되게).
    - 빈 줄은 그냥 넘기고, 형식이 틀리거나 번호가 1~max_no 밖이거나 같은 번호가
      또 나온 줄은 '무시된 줄'로 센다.
    """
    lines = text.splitlines()
    marks = [i for i, l in enumerate(lines) if l.strip().startswith("#선정")]
    if marks:
        lines = lines[marks[0] + 1:]

    picked: list[tuple[int, str, str]] = []
    seen: set[int] = set()
    ignored = 0
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#선정"):
            continue
        parts = [p.strip() for p in line.split("|", 2)]
        m = _NO_RE.match(parts[0])
        if len(parts) < 2 or not m:
            ignored += 1
            continue
        no = int(m.group(1))
        if not (1 <= no <= max_no) or no in seen:
            ignored += 1
            continue
        seen.add(no)
        picked.append((no, parts[1], parts[2] if len(parts) > 2 else ""))
    return picked, ignored
