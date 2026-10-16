"""메일 본문용 HTML 보고서.

브라우저에서 열면 맨 위에 복사 버튼이 있다.
- [제목 복사]: 메일 제목, 예) (261015)언론보도  → 그룹웨어 편지쓰기 '제목' 칸에 Ctrl+V
- [본문 복사]: 기존 발송 양식(링크 걸린 기사 제목만 한 줄씩) 또는 분류·인사이트 포함 양식
  → 편지쓰기 본문에 Ctrl+V 하면 제목에 걸린 링크가 그대로 유지된다.
복사는 브라우저가 '드래그해서 Ctrl+C' 하는 것과 같은 방식으로 한다(서식·링크 유지).
그룹웨어 편집기는 CSS 를 일부 버리므로 모든 꾸밈은 인라인 style 로만 쓴다.
본문 글자 크기는 공단 메일 양식에 맞춰 16px(편집기 '크기' 16), 매체·인사이트는 13px.

AI 선정 결과(분류·인사이트)가 하나라도 있으면 키워드별 대신 분류별로 묶고,
제목 아래 줄에 '▸ 인사이트'를 단다. 없으면 예전처럼 키워드별로 묶는다.
"""

import datetime as dt
import html
import os

from config import app_dir
from naver_api import Article

REPORT_DIR = os.path.join(app_dir(), "reports")

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
CATEGORY_ORDER = ["리스크", "기관 직접", "모회사·부처", "정책·제도", "공공기관 공통", "업계·환경", "참고"]


DEFAULT_SUBJECT = "({날짜})언론보도"


def mail_subject(template: str, day: dt.date) -> str:
    """메일 제목. {날짜} 는 261015 처럼 연월일 6자리로 바뀐다."""
    return (template or DEFAULT_SUBJECT).replace("{날짜}", day.strftime("%y%m%d"))


def ordered_for_mail(articles: list[Article], keywords: list[str]) -> list[Article]:
    """보고서와 같은 순서: 분류가 있으면 분류 순서(리스크 먼저), 없으면 키워드 순서."""
    if any(a.category or a.insight for a in articles):
        rank = lambda a: (CATEGORY_ORDER.index(a.category) if a.category in CATEGORY_ORDER
                          else len(CATEGORY_ORDER))
    else:
        rank = lambda a: next((i for i, k in enumerate(keywords) if k in a.keywords), len(keywords))
    return sorted(articles, key=rank)  # 같은 묶음 안에서는 원래(표) 순서 유지


def build_simple_html(articles: list[Article]) -> str:
    """기존 발송 양식: 링크 걸린 기사 제목만 한 줄씩."""
    esc = html.escape
    lines = [
        f'<p style="margin:0 0 8px 0"><a href="{esc(a.link or a.naver_link)}" '
        f'style="color:#1a4b8f;text-decoration:none">{esc(a.title)}</a></p>'
        for a in articles
    ]
    return ('<div style="font-family:\'맑은 고딕\',Malgun Gothic,sans-serif;font-size:16px;line-height:1.6">'
            + "".join(lines) + "</div>")


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
    if any(a.category or a.insight for a in articles):
        return _build_by_category(articles, title, period)

    # 키워드 순서대로 묶기 (기사는 첫 번째 키워드 아래에만 넣는다)
    groups: dict[str, list[Article]] = {k: [] for k in keywords}
    for art in articles:
        key = next((k for k in keywords if k in art.keywords), art.keywords[0] if art.keywords else "기타")
        groups.setdefault(key, []).append(art)

    parts = [
        '<div style="font-family:\'맑은 고딕\',Malgun Gothic,sans-serif;font-size:16px;color:#222;line-height:1.6">',
        f'<p style="font-size:20px;font-weight:bold;margin:0 0 4px 0">{esc(title)} ({esc(period)})</p>',
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
                f' <span style="color:#777;font-size:13px">({esc(art.source_label)}, {art.published.strftime("%m.%d")})</span>'
                f'{extra}</li>'
            )
        parts.append("</ul>")

    if no == 0:
        parts.append('<p style="color:#777">해당 기간에 조회된 기사가 없습니다.</p>')

    parts.append("</div>")
    return "\n".join(parts)


def _item_html(art: Article, extra: str = "") -> str:
    esc = html.escape
    return (
        f'<a href="{esc(art.link or art.naver_link)}" style="color:#1a4b8f;text-decoration:none">{esc(art.title)}</a>'
        f' <span style="color:#777;font-size:13px">({esc(art.source_label)}, {art.published.strftime("%m.%d")})</span>'
        f'{extra}'
    )


def _build_by_category(articles: list[Article], title: str, period: str) -> str:
    """AI 선정 결과가 있을 때: 분류별 묶음 + 제목 아래 인사이트."""
    esc = html.escape
    groups: dict[str, list[Article]] = {c: [] for c in CATEGORY_ORDER}
    for art in articles:
        groups.setdefault(art.category or "참고", []).append(art)

    parts = [
        '<div style="font-family:\'맑은 고딕\',Malgun Gothic,sans-serif;font-size:16px;color:#222;line-height:1.6">',
        f'<p style="font-size:20px;font-weight:bold;margin:0 0 12px 0">{esc(title)} ({esc(period)}) · 총 {len(articles)}건 선정</p>',
    ]
    for cat, items in groups.items():
        if not items:
            continue
        parts.append(f'<p style="margin:14px 0 4px 0;font-weight:bold;color:#1F3B5C">■ {esc(cat)}</p>')
        parts.append('<ul style="margin:0 0 0 18px;padding:0">')
        for art in items:
            insight = ""
            if art.insight:
                insight = f'<br><span style="color:#777;font-size:13px">▸ {esc(art.insight)}</span>'
            parts.append(f'<li style="margin:0 0 6px 0">{_item_html(art)}{insight}</li>')
        parts.append("</ul>")
    parts.append("</div>")
    return "\n".join(parts)


_PAGE_SCRIPT = """
<script>
function flash(btn, ok) {
  var old = btn.getAttribute('data-label') || btn.textContent;
  btn.setAttribute('data-label', old);
  btn.textContent = ok ? '복사됨 ✓  그룹웨어에 Ctrl+V' : '복사 실패 — 아래 내용을 드래그해 Ctrl+C';
  btn.style.background = ok ? '#2E7D8C' : '#E8A33D';
  setTimeout(function () { btn.textContent = old; btn.style.background = '#1F3B5C'; }, 2500);
}
function copyText(text, btn) {
  var ta = document.createElement('textarea');
  ta.value = text; ta.style.position = 'fixed'; ta.style.top = '-1000px';
  document.body.appendChild(ta); ta.select();
  var ok = false;
  try { ok = document.execCommand('copy'); } catch (e) {}
  document.body.removeChild(ta);
  if (!ok && navigator.clipboard) {
    navigator.clipboard.writeText(text).then(function () { flash(btn, true); }, function () { flash(btn, false); });
    return;
  }
  flash(btn, ok);
}
function copyHtml(id, btn) {
  var el = document.getElementById(id);
  var range = document.createRange(); range.selectNodeContents(el);
  var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
  var ok = false;
  try { ok = document.execCommand('copy'); } catch (e) {}
  sel.removeAllRanges();
  if (!ok && navigator.clipboard && window.ClipboardItem) {
    navigator.clipboard.write([new ClipboardItem({
      'text/html': new Blob([el.innerHTML], {type: 'text/html'}),
      'text/plain': new Blob([el.innerText], {type: 'text/plain'})
    })]).then(function () { flash(btn, true); }, function () { flash(btn, false); });
    return;
  }
  flash(btn, ok);
}
</script>
"""

# 페이지 틀(복사되지 않는 부분) — 디자인 시안 3g. 복사되는 본문(점선 상자 안)은 위 함수들이 만든 그대로.
_FONT = "font-family:'Pretendard','맑은 고딕','Malgun Gothic',sans-serif"
_BTN = (f"{_FONT};font-size:14px;font-weight:700;color:#fff;background:#1F3B5C;border:0;border-radius:0;"
        "padding:9px 18px;cursor:pointer;min-width:112px;text-align:left")
_CARD = "background:#fff;border:1px solid #DFE4EA;margin:0 0 16px 0"
_CARD_HEAD = ("display:flex;align-items:center;justify-content:space-between;padding:12px 16px;"
              "border-bottom:1px solid #E8ECF0")
_CARD_TITLE = f"{_FONT};font-size:15px;font-weight:700;color:#1F3B5C"
_CARD_DESC = f"{_FONT};font-size:13px;color:#5B6673;margin-left:8px;font-weight:400"
_DASHED = "border:1px dashed #CBD3DC;padding:14px 18px;margin:16px"
WEEKDAY = "월화수목금토일"


def _card(title: str, desc: str, button: str, content: str) -> str:
    return (f'<div style="{_CARD}"><div style="{_CARD_HEAD}">'
            f'<div><span style="{_CARD_TITLE}">{title}</span><span style="{_CARD_DESC}">{desc}</span></div>'
            f'{button}</div><div style="{_DASHED}">{content}</div></div>')


def save_report(body_html: str, when: dt.datetime | None = None,
                subject: str = "", simple_html: str = "",
                day: dt.date | None = None, count: int | None = None) -> str:
    """reports/ 폴더에 저장하고 파일 경로를 돌려준다.

    subject(메일 제목)와 simple_html(기존 양식 본문)이 있으면 복사 버튼을 단다.
    body_html 이 비어 있으면 ① 기존 양식만 싣는다(보고 기록에서 다시 열 때).
    day·count 는 페이지 머리('10월 16일(금) 보고 · 5건')에 쓴다.
    """
    os.makedirs(REPORT_DIR, exist_ok=True)
    when = when or dt.datetime.now()
    path = os.path.join(REPORT_DIR, when.strftime("%Y-%m-%d_%H%M") + ".html")
    esc = html.escape
    day = day or when.date()
    parts = [
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">',
        f"<title>{esc(subject or '언론보도 보고서')}</title></head>",
        f'<body style="margin:0;background:#F4F6F8;{_FONT};color:#1E2833">',
        '<div style="max-width:800px;margin:0 auto;padding:32px 24px 40px">',
    ]
    if not simple_html:  # 예전 방식(복사 버튼 없음)
        parts.append(
            f'<p style="{_FONT};font-size:13px;color:#5B6673;border:1px dashed #CBD3DC;padding:8px 12px;background:#fff">'
            "이 페이지에서 Ctrl+A → Ctrl+C 한 뒤 그룹웨어 편지쓰기 본문에 Ctrl+V 하세요.</p>"
            f'<div style="background:#fff;padding:16px">{body_html}</div></div></body></html>')
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(parts))
        return path

    n_text = f" · {count}건" if count is not None else ""
    steps = [("[제목 복사] → 편지쓰기 '제목' 칸에 붙여넣기"),
             ("본문 ①·② 중 하나를 [본문 복사] → 본문에 붙여넣기" if body_html else "[본문 복사] → 본문에 붙여넣기"),
             ("발송한 뒤 앱에서 [④ 보고 완료로 기록]")]
    parts.append(
        '<div style="border-top:2px solid #1F3B5C;padding-top:14px">'
        f'<div style="font-size:13px;font-weight:700;color:#2E7D8C">언론보도 보고서 · 메일용</div>'
        f'<div style="font-size:26px;font-weight:800;color:#1F3B5C;margin:6px 0 16px">'
        f'{day.month}월 {day.day}일({WEEKDAY[day.weekday()]}) 보고{n_text}</div></div>'
        '<div style="display:flex;background:#fff;border:1px solid #DFE4EA;margin:0 0 16px 0">'
        + "".join(
            f'<div style="flex:1;display:flex;gap:10px;padding:14px 16px;font-size:13px;line-height:1.5;color:#3F4A57;'
            f'{"border-left:1px solid #E8ECF0;" if i else ""}">'
            f'<span style="flex:none;width:22px;height:22px;background:#1F3B5C;color:#fff;font-weight:700;'
            f'text-align:center;line-height:22px">{i + 1}</span><span>{esc(t)}</span></div>'
            for i, t in enumerate(steps))
        + "</div>")
    if subject:
        btn = (f'<button type="button" style="{_BTN}" '
               f'onclick="copyText(document.getElementById(\'subject\').textContent, this)">제목 복사</button>')
        parts.append(_card("메일 제목", "편지쓰기 제목 칸", btn,
                           f'<span id="subject" style="font-family:Malgun Gothic,sans-serif;font-size:16px">{esc(subject)}</span>'))
    btn1 = f'<button type="button" style="{_BTN}" onclick="copyHtml(\'body-simple\', this)">본문 복사</button>'
    parts.append(_card("본문 ① 기존 양식", "링크 걸린 기사 제목만", btn1, f'<div id="body-simple">{simple_html}</div>'))
    if body_html:
        btn2 = f'<button type="button" style="{_BTN}" onclick="copyHtml(\'body-full\', this)">본문 복사</button>'
        parts.append(_card("본문 ② 분류·인사이트 포함", "기관별 묶음 · 매체 · 태그", btn2,
                           f'<div id="body-full">{body_html}</div>'))
    parts.append("</div>" + _PAGE_SCRIPT + "</body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    return path
