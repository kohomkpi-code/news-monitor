"""메일 본문용 HTML 보고서.

브라우저에서 열어 전체 선택(Ctrl+A) → 복사(Ctrl+C) → 그룹웨어 편지쓰기에
붙여넣기(Ctrl+V) 하면 제목에 걸린 링크가 그대로 유지된다.
그룹웨어 편집기는 CSS 를 일부 버리므로 모든 꾸밈은 인라인 style 로만 쓴다.
"""

import datetime as dt
import html
import os

from config import app_dir
from naver_api import Article

REPORT_DIR = os.path.join(app_dir(), "reports")

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _md(d: dt.date) -> str:
    return f"{d.month}.{d.day}({WEEKDAY_KO[d.weekday()]})"


def build_html(
    articles: list[Article],
    keywords: list[str],
    start_date: dt.date,
    end_date: dt.date,
    title: str = "언론보도 모니터링",
) -> str:
    esc = html.escape
    period = _md(start_date) if start_date == end_date else f"{_md(start_date)} ~ {_md(end_date)}"

    # 키워드 순서대로 묶기 (기사는 첫 번째 키워드 아래에만 넣는다)
    groups: dict[str, list[Article]] = {k: [] for k in keywords}
    for art in articles:
        key = next((k for k in keywords if k in art.keywords), art.keywords[0] if art.keywords else "기타")
        groups.setdefault(key, []).append(art)

    parts = [
        '<div style="font-family:\'맑은 고딕\',Malgun Gothic,sans-serif;font-size:11pt;color:#222;line-height:1.6">',
        f'<p style="font-size:14pt;font-weight:bold;margin:0 0 4px 0">{esc(title)} ({esc(period)})</p>',
        f'<p style="margin:0 0 12px 0;color:#555">총 {len(articles)}건 · 제목을 클릭하면 기사로 연결됩니다.</p>',
    ]

    no = 0
    for key, items in groups.items():
        if not items:
            continue
        parts.append(
            f'<p style="margin:14px 0 4px 0;font-weight:bold;color:#1F3B5C">■ {esc(key)} ({len(items)}건)</p>'
        )
        parts.append('<ul style="margin:0 0 0 18px;padding:0">')
        for art in items:
            no += 1
            extra = ""
            others = [k for k in art.keywords if k != key]
            if others:
                extra = f' <span style="color:#999">[{esc(", ".join(others))}]</span>'
            parts.append(
                f'<li style="margin:0 0 3px 0">'
                f'<a href="{esc(art.link or art.naver_link)}" style="color:#1a4b8f;text-decoration:none">{esc(art.title)}</a>'
                f' <span style="color:#777;font-size:10pt">({esc(art.source)}, {art.published.strftime("%m.%d")})</span>'
                f'{extra}</li>'
            )
        parts.append("</ul>")

    if no == 0:
        parts.append('<p style="color:#777">해당 기간에 조회된 기사가 없습니다.</p>')

    parts.append("</div>")
    return "\n".join(parts)


def save_report(body_html: str, when: dt.datetime | None = None) -> str:
    """reports/ 폴더에 저장하고 파일 경로를 돌려준다."""
    os.makedirs(REPORT_DIR, exist_ok=True)
    when = when or dt.datetime.now()
    path = os.path.join(REPORT_DIR, when.strftime("%Y-%m-%d_%H%M") + ".html")
    doc = (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
        "<title>언론보도 모니터링</title></head>"
        '<body style="margin:24px;background:#fff">'
        '<p style="font-family:Malgun Gothic,sans-serif;font-size:10pt;color:#888;'
        'border:1px dashed #bbb;padding:8px 12px">'
        "이 페이지에서 Ctrl+A → Ctrl+C 한 뒤 그룹웨어 편지쓰기 본문에 Ctrl+V 하세요. "
        "이 안내문은 붙여넣기 후 지우면 됩니다.</p>"
        f"{body_html}</body></html>"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
