"""구글 뉴스 RSS 검색 (키 불필요).

네이버 검색 API 신규 발급이 끝나서(2026-07-31) 키 없이 쓸 수 있는 출처로 추가했다.
- 주소: https://news.google.com/rss/search?q=키워드 after:날짜 before:날짜&hl=ko&gl=KR&ceid=KR:ko
- 돌려받는 것은 JSON 이 아니라 RSS(XML). 기사 하나가 <item> 하나다.
- 제목 끝에 " - 매체명"이 붙어 오므로 떼고, 매체명은 <source> 에서 가져온다.
- 한 번에 최대 100건 정도만 준다. 100건이 꽉 차면 기간을 반으로 나눠 다시 묻는다.
- 결과는 네이버와 같은 Article 형태로 돌려주므로 중복제거·보고서는 그대로 쓴다.
"""

import datetime as dt
import xml.etree.ElementTree as ET

import requests

from naver_api import Article, NaverApiError, clean_text, parse_pubdate

RSS_URL = "https://news.google.com/rss/search"
KST = dt.timezone(dt.timedelta(hours=9))
PAGE_LIMIT = 100      # 구글이 한 번에 주는 최대 건수(대략)
MAX_SPLIT_DEPTH = 4   # 기간 나누기는 최대 4번까지(요청이 너무 많아지지 않게)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsMonitor"}


def build_query(keyword: str, start_date: dt.date, end_date: dt.date) -> str:
    # after 는 하루 앞당겨 넉넉히 받는다(구글이 날짜를 미국 시간 기준으로 자를 수 있어서).
    # 정확한 기간은 받아 온 뒤 한국시간으로 다시 거른다.
    after = start_date - dt.timedelta(days=1)
    before = end_date + dt.timedelta(days=1)
    return f"{keyword} after:{after.isoformat()} before:{before.isoformat()}"


def parse_rss(xml_text: str | bytes, keyword: str) -> list[Article]:
    """RSS 문서를 Article 목록으로 바꾼다(기간 필터 전)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise NaverApiError(f"구글 뉴스 응답을 읽을 수 없습니다: {e}") from e

    out: list[Article] = []
    for item in root.iter("item"):
        title = clean_text(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        source = clean_text(item.findtext("source") or "")
        pub = item.findtext("pubDate")
        if not title or not link or not pub:
            continue
        try:
            published = parse_pubdate(pub).astimezone(KST)
        except (TypeError, ValueError):
            continue

        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)].rstrip()
        elif not source and " - " in title:
            title, source = (s.strip() for s in title.rsplit(" - ", 1))

        out.append(Article(
            title=title,
            link=link,
            naver_link="",
            source=source,
            published=published,
            description=clean_text(item.findtext("description") or ""),
            keywords=[keyword],
        ))
    return out


def _fetch(keyword: str, start_date: dt.date, end_date: dt.date) -> list[Article]:
    params = {"q": build_query(keyword, start_date, end_date), "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    try:
        resp = requests.get(RSS_URL, params=params, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        raise NaverApiError(f"네트워크 오류(구글 뉴스): {e}") from e
    if resp.status_code == 429:
        raise NaverApiError("구글 뉴스 호출이 너무 많습니다(429). 잠시 후 다시 시도하세요.")
    if resp.status_code != 200:
        raise NaverApiError(f"구글 뉴스 오류({resp.status_code}): {resp.text[:200]}")
    return parse_rss(resp.content, keyword)


def _search_range(keyword: str, start_date: dt.date, end_date: dt.date, depth: int) -> list[Article]:
    items = _fetch(keyword, start_date, end_date)
    if len(items) >= PAGE_LIMIT and start_date < end_date and depth < MAX_SPLIT_DEPTH:
        mid = start_date + (end_date - start_date) // 2
        return (_search_range(keyword, start_date, mid, depth + 1)
                + _search_range(keyword, mid + dt.timedelta(days=1), end_date, depth + 1))
    return items


def search_news(keyword: str, start_date: dt.date, end_date: dt.date) -> list[Article]:
    """키워드 하나로 기간(한국시간 기준) 내 기사를 가져온다."""
    results, seen = [], set()
    for art in _search_range(keyword, start_date, end_date, 0):
        if not (start_date <= art.published.date() <= end_date):
            continue
        if art.link in seen:  # 기간을 나눠 물으면 경계에서 겹칠 수 있다
            continue
        seen.add(art.link)
        results.append(art)
    return results
