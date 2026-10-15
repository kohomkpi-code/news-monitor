"""네이버 뉴스 검색 API 호출.

API 문서: https://developers.naver.com/docs/serviceapi/search/news/news.md
- 한 번에 최대 100건, start 는 최대 1000 → 키워드당 최대 1,000건까지 조회 가능
- 날짜 필터가 없어서 최신순(sort=date)으로 받아 오다가 조회 시작일보다
  오래된 기사만 나오는 페이지에서 멈춘다.
"""

import datetime as dt
import email.utils
import html
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

from sources import source_name

API_URL = "https://openapi.naver.com/v1/search/news.json"
PAGE_SIZE = 100
MAX_START = 1000

_TAG_RE = re.compile(r"<[^>]+>")


class NaverApiError(Exception):
    """API 호출 실패 시 사용자에게 보여줄 메시지를 담는다."""


@dataclass
class Article:
    title: str
    link: str            # 언론사 원문 링크 (없으면 네이버 링크)
    naver_link: str
    source: str          # 매체명
    published: dt.datetime
    description: str
    keywords: list = field(default_factory=list)  # 이 기사를 찾아낸 키워드들
    grade: str = ""      # 키워드 등급: "A"(기관 직접) / "B"(정책·환경)
    category: str = ""   # AI 선정 분류 (예: 리스크, 기관 직접)
    insight: str = ""    # AI 선정 한 줄 인사이트

    @property
    def date_str(self) -> str:
        return self.published.strftime("%Y-%m-%d")


def clean_text(text: str) -> str:
    """<b>태그와 &quot; 같은 HTML 특수문자를 보통 글자로 되돌린다."""
    return html.unescape(_TAG_RE.sub("", text)).strip()


def parse_pubdate(text: str) -> dt.datetime:
    # 예: "Tue, 14 Oct 2026 09:00:00 +0900"
    return email.utils.parsedate_to_datetime(text)


def _to_article(item: dict, keyword: str) -> Article:
    original = item.get("originallink") or item.get("link", "")
    naver = item.get("link", "")
    return Article(
        title=clean_text(item.get("title", "")),
        link=original,
        naver_link=naver,
        source=source_name(original),
        published=parse_pubdate(item["pubDate"]),
        description=clean_text(item.get("description", "")),
        keywords=[keyword],
    )


def search_news(
    keyword: str,
    client_id: str,
    client_secret: str,
    start_date: dt.date,
    end_date: dt.date,
) -> list[Article]:
    """키워드 하나로 기간 내 기사를 모두 가져온다."""
    if not client_id or not client_secret:
        raise NaverApiError("네이버 Client ID / Secret 이 설정되지 않았습니다. [설정] 버튼에서 입력하세요.")

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    results: list[Article] = []
    start = 1

    while start <= MAX_START:
        params = {"query": keyword, "display": PAGE_SIZE, "start": start, "sort": "date"}
        try:
            resp = requests.get(API_URL, headers=headers, params=params, timeout=15)
        except requests.RequestException as e:
            raise NaverApiError(f"네트워크 오류: {e}") from e

        if resp.status_code == 401:
            raise NaverApiError("인증 실패(401): Client ID / Secret 을 확인하세요.")
        if resp.status_code == 429:
            raise NaverApiError("호출 한도 초과(429): 잠시 후 다시 시도하세요.")
        if resp.status_code != 200:
            raise NaverApiError(f"API 오류({resp.status_code}): {resp.text[:200]}")

        items = resp.json().get("items", [])
        if not items:
            break

        all_older = True
        for item in items:
            try:
                art = _to_article(item, keyword)
            except (KeyError, TypeError, ValueError):
                continue
            d = art.published.date()
            if d > end_date:
                all_older = False
                continue
            if d < start_date:
                continue
            all_older = False
            results.append(art)

        if all_older or len(items) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return results


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host
