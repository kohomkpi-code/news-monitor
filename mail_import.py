"""그룹웨어에서 내려받은 '지난 보고 메일'(HTML) 읽기 — [보고 기록] 탭의 '기존 보고 메일 불러오기'.

메일 한 통 = 하루 보고. 파일에서 두 가지를 찾는다.
1) 보고일: 메일 제목의 '(261015)' → 2026-10-15. 없으면 '보낸일시 2026/10/15 09:34' 같은 글,
   그다음 파일 이름 안의 날짜(261015, 2026-10-15, 20261015) 순서로 찾는다. 끝내 못 찾으면 사람이 적는다.
2) 기사: 본문의 링크(<a href="http…">기사 제목</a>). 그룹웨어 자체 링크(gw.kohom.or.kr 등),
   메일 주소·자바스크립트 링크, 너무 짧은 글자의 링크는 뺀다. 매체명은 주소로 알아낸다(sources.py).
.html/.htm 외에 .mht/.eml(메일 저장 형식)도 안의 HTML 을 꺼내 읽는다.
"""

import datetime as dt
import email
import email.policy
import email.utils
import html
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sources import source_name

SKIP_HOST_WORDS = ("kohom.or.kr",)   # 그룹웨어·기관 홈페이지 링크는 기사가 아님
MIN_TITLE_LEN = 8

_A_RE = re.compile(r"<a\s[^>]*?href\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_SUBJECT_DATE_RE = re.compile(r"\((\d{2})(\d{2})(\d{2})\)\s*언론")
_SENT_RE = re.compile(r"(?:보낸\s*일시|보낸\s*날짜|발송\s*일시|Date)\s*[:：]?\s*(?:<[^>]+>\s*)*"
                      r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})(?:\s*\(?[월화수목금토일]?\)?\s*(\d{1,2}):(\d{2}))?",
                      re.IGNORECASE)
_FILE_DATES = [re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})"), re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")]


@dataclass
class MailReport:
    path: str
    day: dt.date | None
    time: str                       # "09:34" 또는 ""
    items: list[tuple[str, str, str]] = field(default_factory=list)  # (링크, 제목, 매체)
    note: str = ""                  # 날짜를 어디서 찾았는지 / 문제


def _decode(raw: bytes) -> str:
    head = raw[:3000].decode("ascii", "ignore").lower()
    m = re.search(r"charset\s*=\s*[\"']?([\w-]+)", head)
    tries = ([m.group(1)] if m else []) + ["utf-8", "cp949"]
    for enc in tries:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def read_html(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    if path.lower().endswith((".mht", ".mhtml", ".eml")):
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        part = msg.get_body(preferencelist=("html", "plain"))
        if part is not None:
            content = part.get_content()
            subject = msg.get("Subject", "")
            sent = ""
            try:
                when = email.utils.parsedate_to_datetime(msg.get("Date", ""))
                sent = when.astimezone(dt.timezone(dt.timedelta(hours=9))).strftime("%Y/%m/%d %H:%M")
            except (TypeError, ValueError):
                pass
            return f"<title>{html.escape(subject)}</title><p>보낸일시 {sent}</p>{content}"
    return _decode(raw)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub("", s))).strip()


def _ymd(y: str, m: str, d: str) -> dt.date | None:
    y_i = int(y) + (2000 if len(y) == 2 else 0)
    try:
        return dt.date(y_i, int(m), int(d))
    except ValueError:
        return None


def find_day(text: str, filename: str) -> tuple[dt.date | None, str, str]:
    """(보고일, 시각, 어디서 찾았는지)."""
    plain = _clean(text)
    m = _SUBJECT_DATE_RE.search(plain)
    sent = _SENT_RE.search(plain)
    time = f"{int(sent.group(4)):02d}:{sent.group(5)}" if sent and sent.group(4) else ""
    if m and (d := _ymd(*m.groups())):
        return d, time, "메일 제목"
    if sent and (d := _ymd(*sent.groups()[:3])):
        return d, time, "보낸일시"
    name = os.path.basename(filename)
    for rx in _FILE_DATES:
        fm = rx.search(name)
        if fm and (d := _ymd(*fm.groups())) and 2000 <= d.year <= 2100:
            return d, "", "파일 이름"
    return None, "", "날짜 못 찾음"


def find_articles(text: str) -> list[tuple[str, str, str]]:
    out, seen = [], set()
    for _, href, inner in _A_RE.findall(text):
        url = html.unescape(href).strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        host = urlparse(url).netloc.lower()
        if any(w in host for w in SKIP_HOST_WORDS):
            continue
        title = _clean(inner)
        if len(title) < MIN_TITLE_LEN or url in seen:
            continue
        seen.add(url)
        out.append((url, title, source_name(url)))
    return out


def parse_file(path: str) -> MailReport:
    try:
        text = read_html(path)
    except OSError as e:
        return MailReport(path, None, "", [], f"파일을 못 읽음: {e}")
    day, time, where = find_day(text, path)
    items = find_articles(text)
    note = where if items else "기사 링크를 못 찾음"
    return MailReport(path, day, time, items, note)
