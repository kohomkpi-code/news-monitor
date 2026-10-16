"""기사 주소(링크) 하나로 제목·매체·날짜를 읽어 온다 — '기사 링크로 추가' 버튼용.

구글 검색에 안 잡혔지만 꼭 넣어야 할 기사를 사람이 직접 넣을 때 쓴다.
기사 페이지의 메타 정보(og:title, og:site_name, article:published_time)를 읽고,
없으면 <title> 과 도메인→매체명 표(sources.py)로 대신한다. 못 읽으면 사람이 직접 적는다.
"""

import datetime as dt
import html
import re
from dataclasses import dataclass

import requests

import google_news
from sources import source_name

KST = dt.timezone(dt.timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
_META_RE = re.compile(r"<meta\s[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([\w:.-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass
class PageInfo:
    url: str
    title: str
    source: str
    published: dt.datetime | None


def _metas(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in _META_RE.findall(text):
        attrs = {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4))
                 for m in _ATTR_RE.finditer(tag)}
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        if key and "content" in attrs and key not in out:
            out[key] = html.unescape(attrs["content"]).strip()
    return out


def parse_time(text: str) -> dt.datetime | None:
    text = (text or "").strip().replace("Z", "+00:00")
    for cand in (text, text[:19]):
        try:
            t = dt.datetime.fromisoformat(cand)
        except ValueError:
            continue
        return (t if t.tzinfo else t.replace(tzinfo=KST)).astimezone(KST)
    return None


def parse_page(url: str, text: str) -> PageInfo:
    meta = _metas(text)
    title = meta.get("og:title") or meta.get("twitter:title") or ""
    if not title:
        m = _TITLE_RE.search(text)
        title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
    source = meta.get("og:site_name") or source_name(url)
    # 제목 끝에 붙은 ' - 매체명', ' | 매체명' 떼기
    for sep in (" - ", " | ", " : "):
        if source and title.endswith(sep + source):
            title = title[: -len(sep + source)].strip()
    published = None
    for key in ("article:published_time", "og:article:published_time", "datepublished",
                "pubdate", "publishdate", "date", "dable:published_time"):
        if meta.get(key):
            published = parse_time(meta[key])
            if published:
                break
    return PageInfo(url=url, title=title, source=source, published=published)


def fetch(url: str) -> PageInfo:
    """실패하면 예외(requests.RequestException 등)."""
    url = url.strip()
    if google_news.is_google_link(url):
        url = google_news.resolve_link(url)
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding  # 국내 언론사는 euc-kr 인 곳도 있다
    return parse_page(resp.url or url, resp.text)
