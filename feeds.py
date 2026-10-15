"""전문지 RSS 직접 구독 (구글 뉴스가 잘 못 잡는 전문지 보완).

- 아파트관리신문·한국아파트신문·전기신문처럼 공동주택 관리 실무 기사가 많은 매체의
  RSS(최신 기사 목록)를 직접 받는다. 주소는 config.json 의 "extra_feeds" 에서 바꾼다.
- 전문지 RSS 는 '검색'이 아니라 '최신 글 전체'라서, 제목이나 요약에
  A/B 키워드가 들어간 기사만 남긴다.
- 키워드 맞추기 규칙(구글 검색과 비슷하게):
    LH 임대주택        → 'LH' 와 '임대주택' 이 모두 들어 있으면
    "공공임대 관리"     → 이 문구가 그대로 들어 있으면
    주택관리공단 OR 마이홈 → 둘 중 하나라도
    공공기관 ESG -주식  → '주식' 이 들어 있으면 제외
- 한 매체가 실패해도 나머지는 계속 받는다(실패한 매체 이름을 돌려준다).
"""

import datetime as dt
import re

import requests

import rss
from naver_api import Article, NaverApiError

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsMonitor"}
_TOKEN_RE = re.compile(r'-?"[^"]+"|\S+')


def keyword_matches(keyword: str, text: str) -> bool:
    """구글 검색식 키워드가 글(text)에 맞는지. 대소문자는 가리지 않는다."""
    text = text.lower()
    for alt in re.split(r"\s+OR\s+", keyword.strip()):
        tokens = _TOKEN_RE.findall(alt)
        must = [t.strip('"').lower() for t in tokens if not t.startswith("-")]
        must_not = [t[1:].strip('"').lower() for t in tokens if t.startswith("-") and len(t) > 1]
        must = [m for m in must if m]
        if must and all(m in text for m in must) and not any(n in text for n in must_not):
            return True
    return False


def fetch_feed(name: str, url: str) -> list[rss.RssItem]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        raise NaverApiError(f"{name}: 네트워크 오류 {e}") from e
    if resp.status_code != 200:
        raise NaverApiError(f"{name}: 오류({resp.status_code})")
    return rss.parse_items(resp.content, name)


def filter_items(items: list[rss.RssItem], feed_name: str, grades: dict[str, str],
                 start_date: dt.date, end_date: dt.date) -> list[Article]:
    """기간 안이고 키워드가 맞는 기사만 Article 로. grades = {키워드: "A" 또는 "B"}."""
    out: list[Article] = []
    for it in items:
        if not (start_date <= it.published.date() <= end_date):
            continue
        text = f"{it.title} {it.description}"
        matched = [kw for kw in grades if keyword_matches(kw, text)]
        if not matched:
            continue
        out.append(Article(
            title=it.title,
            link=it.link,
            naver_link="",
            source=feed_name,
            published=it.published,
            description=it.description,
            keywords=matched,
            grade="A" if any(grades[k] == "A" for k in matched) else "B",
        ))
    return out


def search_feeds(feeds: list[dict], grades: dict[str, str],
                 start_date: dt.date, end_date: dt.date) -> tuple[list[Article], list[str]]:
    """(기사 목록, 실패한 매체 이름 목록)."""
    found: list[Article] = []
    failed: list[str] = []
    for feed in feeds:
        name, url = feed.get("name", ""), feed.get("url", "")
        if not url:
            continue
        try:
            found.extend(filter_items(fetch_feed(name, url), name or url, grades, start_date, end_date))
        except NaverApiError:
            failed.append(name or url)
    return found, failed
