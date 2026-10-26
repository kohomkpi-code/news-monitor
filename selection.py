"""AI 선별 중계 — 요청문 만들기와 선정 결과 읽기.

앱이 AI 를 직접 부르지 않는다(API 키 없음). 사람이 복사·붙여넣기로 중계한다.
1) build_request(): 표의 후보 기사를 번호 붙인 목록으로 만든다 → 클립보드로 복사
   번호는 표의 '순번'(조회 때 매긴 고정 번호)이라, Claude 가 말하는 번호를 표에서 바로 찾을 수 있다.
   → Claude 프로젝트 채팅에 붙여 넣기
2) parse_selection(): Claude 답변의 '#선정' 아래 줄(번호|분류|인사이트)을 읽는다
"""

import datetime as dt
import re

import rules as R
from naver_api import Article

SUMMARY_LEN = 80
_NO_RE = re.compile(r"^\s*(\d+)\s*[.)]?\s*$")


def build_request(articles: list[Article], today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    lines = [f"[AI 선별 요청] {today.isoformat()}, 후보 {len(articles)}건"]
    for i, a in enumerate(articles, 1):
        grade = f"[{a.grade}] " if a.grade else ""
        line = f"{a.no or i}. {grade}{a.title} ({a.source_label}, {a.published.strftime('%m.%d')})"
        desc = " ".join(a.description.split())
        if desc:
            line += " — " + desc[:SUMMARY_LEN]
        lines.append(line)
    return "\n".join(lines)


def parse_selection(text: str, max_no: int | set[int]) -> tuple[list[tuple[int, str, str]], int]:
    """'번호|분류|인사이트' 줄들을 읽는다.

    돌려주는 값: ([(번호, 분류, 인사이트), ...] 입력 순서대로, 무시된 줄 수)
    - '#선정' 줄이 있으면 그 아래만 읽는다(답변 전체를 붙여 넣어도 되게).
    - 빈 줄은 그냥 넘기고, 형식이 틀리거나 번호가 1~max_no 밖(max_no 가 번호 묶음이면 그 안에 없음)이거나
      같은 번호가 또 나온 줄은 '무시된 줄'로 센다.
    """
    valid = max_no if isinstance(max_no, set) else set(range(1, max_no + 1))
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
        if no not in valid or no in seen:
            ignored += 1
            continue
        seen.add(no)
        picked.append((no, parts[1], parts[2] if len(parts) > 2 else ""))
    return picked, ignored


def build_rules_request(rules_now: dict, version: str) -> str:
    """[선정 규칙] 탭 '개선 요청문': 결과 엑셀과 함께 Claude 에 보내면, 고친 규칙(JSON)을 돌려받는다."""
    return "\n".join([
        f"[KOHOM 뉴스룸 v{version} 선정 규칙 개선 요청]",
        "첨부한 엑셀은 이 앱의 조회 결과입니다(시트: 조회결과·빠진 기사·조회 조건·선정 규칙).",
        "'프로 선택'·'베이직 선택' 열이 담당자의 최종 판단이고, '★추천'·'점수'·'자동 분류'·'점수 근거'가 앱의 판단입니다.",
        "",
        "1. 앱 판단과 담당자 판단이 어긋난 기사를 찾아, 원인을 규칙 항목(키워드·단어 목록·점수·추천 기준)으로 설명해 주세요.",
        "2. '빠진 기사' 시트에서 빠지면 안 되었던 기사, 표에 남았지만 빠졌어야 할 기사(해외·무관 매체 등)를 알려 주세요.",
        "3. 고칠 점을 표로 요약하고, 마지막에 고친 규칙 전체를 JSON 코드 블록 하나로 주세요.",
        "   - 아래 '지금 규칙'과 같은 형식, 같은 키 이름. 바꾼 값만이 아니라 전체를 주세요.",
        "   - 키워드 맞추기: 띄어 쓴 말은 같은 순서로, 낱말 사이 20자 이내에 있으면 맞음(띄어쓰기 무관), \"따옴표\"는 그대로, A OR B, -빼는말.",
        "   - '공공기관'·'국정감사' 같은 범용어 하나는 수백 건을 끌어오므로 피하고, 필요하면 '공공기관 경영평가'처럼 묶어 주세요.",
        "   - 검색 키워드가 늘면 조회가 느려지므로, 늘린 만큼 효과 없는 키워드는 빼 주세요.",
        "",
        "지금 규칙:",
        "```json",
        R.to_json(rules_now),
        "```",
    ])
