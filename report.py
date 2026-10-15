"""메일 본문용 HTML 보고서.

브라우저에서 열면 맨 위에 복사 버튼이 있다.
- [제목 복사]: 메일 제목, 예) (261015)언론보도  → 그룹웨어 편지쓰기 '제목' 칸에 Ctrl+V
- [본문 복사]: 기존 발송 양식(링크 걸린 기사 제목만 한 줄씩) 또는 분류·인사이트 포함 양식
  → 편지쓰기 본문에 Ctrl+V 하면 제목에 걸린 링크가 그대로 유지된다.
복사는 브라우저가 '드래그해서 Ctrl+C' 하는 것과 같은 방식으로 한다(서식·링크 유지).
그룹웨어 편집기는 CSS 를 일부 버리므로 모든 꾸밈은 인라인 style 로만 쓴다.

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
    return ('<div style="font-family:\'맑은 고딕\',Malgun Gothic,sans-serif;font-size:12pt;line-height:1.6">'
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
                f' <span style="color:#777;font-size:10pt">({esc(art.source_label)}, {art.published.strftime("%m.%d")})</span>'
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
        f' <span style="color:#777;font-size:10pt">({esc(art.source_label)}, {art.published.strftime("%m.%d")})</span>'
        f'{extra}'
    )


def _build_by_category(articles: list[Article], title: str, period: str) -> str:
    """AI 선정 결과가 있을 때: 분류별 묶음 + 제목 아래 인사이트."""
    esc = html.escape
    groups: dict[str, list[Article]] = {c: [] for c in CATEGORY_ORDER}
    for art in articles:
        groups.setdefault(art.category or "참고", []).append(art)

    parts = [
        '<div style="font-family:\'맑은 고딕\',Malgun Gothic,sans-serif;font-size:11pt;color:#222;line-height:1.6">',
        f'<p style="font-size:14pt;font-weight:bold;margin:0 0 12px 0">{esc(title)} ({esc(period)}) · 총 {len(articles)}건 선정</p>',
    ]
    for cat, items in groups.items():
        if not items:
            continue
        parts.append(f'<p style="margin:14px 0 4px 0;font-weight:bold;color:#1F3B5C">■ {esc(cat)}</p>')
        parts.append('<ul style="margin:0 0 0 18px;padding:0">')
        for art in items:
            insight = ""
            if art.insight:
                insight = f'<br><span style="color:#777;font-size:10pt">▸ {esc(art.insight)}</span>'
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

_BTN = ("font-family:'맑은 고딕',Malgun Gothic,sans-serif;font-size:11pt;color:#fff;background:#1F3B5C;"
        "border:0;border-radius:4px;padding:6px 14px;cursor:pointer;margin-right:10px")
_LABEL = "font-family:'맑은 고딕',Malgun Gothic,sans-serif;font-size:10pt;color:#2E7D8C;font-weight:bold"
_BOX = "border:1px solid #d5dde5;border-radius:6px;padding:14px 16px;margin:0 0 18px 0"


def save_report(body_html: str, when: dt.datetime | None = None,
                subject: str = "", simple_html: str = "") -> str:
    """reports/ 폴더에 저장하고 파일 경로를 돌려준다.

    subject(메일 제목)와 simple_html(기존 양식 본문)이 있으면 복사 버튼을 단다.
    """
    os.makedirs(REPORT_DIR, exist_ok=True)
    when = when or dt.datetime.now()
    path = os.path.join(REPORT_DIR, when.strftime("%Y-%m-%d_%H%M") + ".html")
    esc = html.escape
    parts = [
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">',
        f"<title>{esc(subject or '언론보도 모니터링')}</title></head>",
        '<body style="margin:24px;background:#fff;max-width:960px">',
    ]
    if subject:
        parts.append(
            f'<div style="{_BOX};background:#F3F6F9">'
            f'<span style="{_LABEL}">메일 제목</span><br>'
            f'<button type="button" style="{_BTN};margin-top:6px" '
            f'onclick="copyText(document.getElementById(\'subject\').textContent, this)">제목 복사</button>'
            f'<span id="subject" style="font-family:Malgun Gothic,sans-serif;font-size:12pt">{esc(subject)}</span>'
            "</div>"
        )
    if simple_html:
        parts.append(
            f'<div style="{_BOX}"><span style="{_LABEL}">메일 본문 ① 기존 양식 (기사 제목만)</span><br>'
            f'<button type="button" style="{_BTN};margin:6px 0 12px 0" '
            f'onclick="copyHtml(\'body-simple\', this)">본문 복사</button>'
            f'<div id="body-simple">{simple_html}</div></div>'
        )
        parts.append(
            f'<div style="{_BOX}"><span style="{_LABEL}">메일 본문 ② 분류·인사이트 포함</span><br>'
            f'<button type="button" style="{_BTN};margin:6px 0 12px 0" '
            f'onclick="copyHtml(\'body-full\', this)">본문 복사</button>'
            f'<div id="body-full">{body_html}</div></div>'
        )
        parts.append(_PAGE_SCRIPT)
    else:
        parts.append(
            '<p style="font-family:Malgun Gothic,sans-serif;font-size:10pt;color:#888;'
            'border:1px dashed #bbb;padding:8px 12px">'
            "이 페이지에서 Ctrl+A → Ctrl+C 한 뒤 그룹웨어 편지쓰기 본문에 Ctrl+V 하세요. "
            "이 안내문은 붙여넣기 후 지우면 됩니다.</p>"
            f"{body_html}"
        )
    parts.append("</body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    return path
