"""[프로] 탭의 조회 결과 내려받기 (엑셀 .xlsx 한 파일).

목적: 앱이 고른 결과(등급·점수·분류·키워드)와 담당자의 최종 선택을 함께 남겨,
Claude 등에 붙여 "점수 규칙·키워드·제외어를 어떻게 고치면 좋을까"를 물어볼 수 있게 한다.

시트 4개:
1) 조회결과   — 표에 나온 기사 전부(표 순서), 최종 선택 여부, 자동 분류, 점수 항목별 내역과 근거 한 줄
2) 빠진 기사  — 제외 매체·제목 검증 실패·제외어·단순 행사·이미 보고·같은 사안 묶음으로 빠진 기사와 그 이유
3) 조회 조건  — 기간, 검색 방식, 옵션, 건수 흐름
4) 선정 규칙  — 조회한 그때의 규칙(키워드·단어 목록·점수·추천) 표, 그리고 규칙 JSON 전체
   (Claude 가 이 JSON 을 고쳐 돌려주면 [선정 규칙] 탭 → [Claude 답변 붙여넣기]로 바로 넣을 수 있다)
네이버 Client ID/Secret 같은 비밀값은 넣지 않는다.
"""

import datetime as dt

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import ranking
import rules as R
from naver_api import Article

HEAD_FILL = PatternFill("solid", fgColor="1F3B5C")
HEAD_FONT = Font(bold=True, color="FFFFFF")
A_FILL = PatternFill("solid", fgColor="FBF3E4")
MANUAL_FILL = PatternFill("solid", fgColor="E4F0F2")
PART_KEYS = ["A 기관", "지사명만", "S 사업어", "모회사·부처", "B 환경", "리스크", "정책", "여러 매체", "전문지 기본", "전문지", "지역지",
             "최근 24시간", "단독", "공급·개발", "공고", "행사"]


def _sheet(ws, heads: list[tuple[str, int]], rows: list[list], fills: list | None = None):
    for c, (head, width) in enumerate(heads, 1):
        cell = ws.cell(row=1, column=c, value=head)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = width
    for r, row in enumerate(rows, 2):
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            if fills and fills[r - 2]:
                cell.fill = fills[r - 2]
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(heads))}{len(rows) + 1}"


def _when(a: Article) -> str:
    return a.published.strftime("%Y-%m-%d %H:%M")


def save_xlsx(path: str, shown: list[tuple[Article, bool, bool]], dropped: list[tuple[str, str, Article]],
              conditions: list[tuple[str, str]], rules: dict) -> None:
    """shown = [(기사, 프로 선택, 베이직 선택)] 표 순서대로. dropped = [(이유, 걸린 말, 기사)]. rules = 조회 때 규칙."""
    wb = Workbook()

    ws = wb.active
    ws.title = "조회결과"
    heads = [("순번", 6), ("프로 선택", 9), ("베이직 선택", 10), ("★추천", 7), ("등급", 6), ("점수", 6),
             ("자동 분류", 11), ("AI 분류", 10), ("AI 인사이트", 30), ("키워드", 22), ("날짜", 16), ("매체", 16),
             ("묶인 기사 수", 9), ("제목", 60), ("점수 근거", 50), ("요약", 40), ("링크", 40)]
    heads += [(f"점수:{k}", 9) for k in PART_KEYS]
    heads += [("걸린 S 사업어", 16), ("걸린 모회사어", 12), ("걸린 리스크어", 14), ("걸린 정책어", 12), ("걸린 공급·개발어", 14),
              ("걸린 공고어", 12)]
    rows, fills = [], []
    for n, (a, pro_on, basic_on) in enumerate(shown, 1):
        h = a.hits or {}
        rows.append([n, "O" if pro_on else "", "O" if basic_on else "", "★" if a.best else "", a.grade, a.score,
                     a.auto_category, a.category, a.insight, ", ".join(a.keywords), _when(a), a.source, len(a.others),
                     a.title, ranking.score_line(a) if a.parts else "", a.description, a.link or a.naver_link]
                    + [a.parts.get(k, 0) for k in PART_KEYS]
                    + [", ".join(h.get(k, [])) for k in ("S", "모회사", "리스크", "정책", "개발", "공고")])
        fills.append(MANUAL_FILL if a.grade == "직접" else A_FILL if a.grade == "A" else None)
    _sheet(ws, heads, rows, fills)

    ws = wb.create_sheet("빠진 기사")
    rows = [[reason, words, a.grade, ", ".join(a.keywords), _when(a), a.source, a.title, a.link or a.naver_link, ""]
            for reason, words, a in dropped]
    # 같은 사안으로 묶여 대표 기사 밑에 들어간 기사들 — 매체·제목·링크만 안다
    for n, (a, *_rest) in enumerate(shown, 1):
        for source, title, link in a.others:
            rows.append(["같은 사안 묶음", "", "", "", "", source, title, link, f"{n}번 기사에 묶임"])
    _sheet(ws, [("빠진 이유", 22), ("걸린 말", 16), ("등급", 6), ("키워드", 22), ("날짜", 16), ("매체", 16),
                ("제목", 60), ("링크", 40), ("비고", 18)], rows)

    ws = wb.create_sheet("조회 조건")
    _sheet(ws, [("항목", 22), ("값", 100)], [list(c) for c in conditions])
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        row[0].alignment = Alignment(wrap_text=True, vertical="top")

    ws = wb.create_sheet("선정 규칙")
    rows = [["설명", "", line.strip()] for line in (ranking.__doc__ or "").splitlines() if line.strip()]
    for k, v in rules.items():
        shown_v = ", ".join(v) if isinstance(v, list) else ("켬" if v is True else "끔" if v is False else v)
        rows.append([R.label(k), k, shown_v])
    rows.append(["", "", ""])
    rows.append(["규칙 JSON", "", "아래 줄들을 이어 붙이면 규칙 파일입니다. 고친 JSON 을 앱의 [선정 규칙] → "
                                 "[Claude 답변 붙여넣기]에 넣으면 바뀐 점을 보여 준 뒤 적용합니다."])
    rows += [["", "", line] for line in R.to_json(rules).splitlines()]
    _sheet(ws, [("항목", 22), ("키", 18), ("값", 120)], rows)
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=3):
        row[0].alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(path)


def default_name(when: dt.datetime) -> str:
    return f"KOHOM뉴스룸_조회결과_{when:%Y%m%d_%H%M}.xlsx"
