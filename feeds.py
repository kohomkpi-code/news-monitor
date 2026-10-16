"""전문지 RSS 직접 구독 (구글 뉴스가 잘 못 잡는 전문지 보완).

- 아파트관리신문·한국아파트신문·전기신문처럼 공동주택 관리 실무 기사가 많은 매체의
  RSS(최신 기사 목록)를 직접 받는다. 매체·주소·사용 여부는 [설정] 탭 → [전문지 고르기]에서
  정한다(config.json 의 "extra_feeds": [{"name", "url", "on"}]).
- 전문지 RSS 는 '검색'이 아니라 '최신 글 전체'라서, 제목이나 요약에
  검색 키워드(A·S·B)가 들어간 기사만 남긴다.
- 키워드 맞추기 규칙(구글 검색과 비슷하게):
    LH 임대주택        → 'LH' 다음 20자 안에 '임대주택' 이 있으면(같은 순서)
    "공공임대 관리"     → 이 문구가 그대로 들어 있으면
    주택관리공단 OR 마이홈 → 둘 중 하나라도
    공공기관 ESG -주식  → '주식' 이 들어 있으면 제외
- 한 매체가 실패해도 나머지는 계속 받는다(실패한 매체 이름을 돌려준다).
- 홈페이지 주소만 알아도 된다: 국내 신문사 다수가 쓰는 기사관리 프로그램은 RSS 주소가
  '홈페이지 + /rss/allArticle.xml' 이라서, discover() 가 그 주소(https/http, www 있고 없고)를
  차례로 시도해 받아지는 것을 찾는다. 매체 이름도 RSS 의 제목에서 가져온다.
"""

import datetime as dt
import re
from urllib.parse import urlparse

import requests

import rss
import rules
from naver_api import Article, NaverApiError

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsMonitor"}
RSS_PATH = "/rss/allArticle.xml"


def keyword_matches(keyword: str, text: str) -> bool:
    """구글 검색식 키워드가 글(text)에 맞는지(rules.matches: 대소문자·띄어쓰기 무시)."""
    return rules.matches(keyword, text)


def _fetch_raw(name: str, url: str, timeout: int = 15) -> bytes:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
    except requests.RequestException as e:
        raise NaverApiError(f"{name}: 네트워크 오류 {type(e).__name__}") from e
    if resp.status_code != 200:
        raise NaverApiError(f"{name}: 오류({resp.status_code})")
    return resp.content


def fetch_feed(name: str, url: str) -> list[rss.RssItem]:
    return rss.parse_items(_fetch_raw(name, url), name)


def looks_like_rss(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".xml", ".rss")) or "/rss" in path or "/feed" in path


def rss_candidates(text: str) -> list[str]:
    """홈페이지(또는 RSS) 주소 → 시도해 볼 RSS 주소들. 'www.aptn.co.kr' 처럼 http 없이 써도 된다."""
    t = text.strip()
    if not t:
        return []
    if not re.match(r"https?://", t, re.IGNORECASE):
        t = "https://" + t
    host = urlparse(t).netloc
    if not host or "." not in host:
        return []
    if looks_like_rss(t):
        return [t]
    hosts = [host, host[4:] if host.startswith("www.") else "www." + host]
    out = []
    for scheme in ("https", "http"):
        for h in hosts:
            u = f"{scheme}://{h}{RSS_PATH}"
            if u not in out:
                out.append(u)
    return out


def _summary(items: list[rss.RssItem]) -> str:
    newest = max(it.published for it in items)
    return f"정상 · 기사 {len(items)}건 (최신 {newest:%m.%d})"


def discover(text: str) -> tuple[str | None, str, str]:
    """홈페이지/RSS 주소 → (받아지는 RSS 주소 또는 None, RSS 제목(매체 이름 후보), 결과 문구)."""
    cands = rss_candidates(text)
    if not cands:
        return None, "", "주소를 알아볼 수 없습니다 (예: www.aptn.co.kr)"
    last = ""
    for url in cands:
        try:
            raw = _fetch_raw("", url, timeout=10)
            items = rss.parse_items(raw, "")
        except NaverApiError as e:
            last = str(e).split(": ", 1)[-1]
            continue
        if items:
            title = re.split(r"\s+[-|:]\s+", rss.channel_title(raw))[0].strip()
            return url, title, _summary(items)
    return None, "", f"RSS 를 찾지 못함({last or '기사 없음'}) — 홈페이지 맨 아래 'RSS' 메뉴의 주소를 직접 넣어 주세요"


def check_feed(name: str, url: str) -> str:
    """연결 확인: 받아지면 '정상 · 기사 N건 (최신 MM.DD)', 아니면 실패 이유."""
    try:
        items = fetch_feed(name, url)
    except NaverApiError as e:
        return f"실패 · {str(e).split(': ', 1)[-1][:60]}"
    if not items:
        return "받아지지만 기사가 없음 (RSS 주소 확인)"
    return _summary(items)


def filter_items(items: list[rss.RssItem], feed_name: str, grades: dict[str, str],
                 start_date: dt.date, end_date: dt.date, keep_all: bool = False) -> list[Article]:
    """기간 안이고 키워드가 맞는 기사만 Article 로. grades = {키워드: 등급}. keep_all 이면 키워드 없어도(면제 전문지)."""
    out: list[Article] = []
    for it in items:
        if not (start_date <= it.published.date() <= end_date):
            continue
        text = f"{it.title} {it.description}"
        matched = [kw for kw in grades if keyword_matches(kw, text)]
        if not matched and not keep_all:
            continue
        out.append(Article(
            title=it.title,
            link=it.link,
            naver_link="",
            source=feed_name,
            published=it.published,
            description=it.description,
            keywords=matched,
            grade=next((g for g in ("A", "S", "B") if any(grades[k] == g for k in matched)), "전문지"),
        ))
    return out


def search_feeds(feeds: list[dict], grades: dict[str, str],
                 start_date: dt.date, end_date: dt.date, free: list[str] | None = None) -> tuple[list[Article], list[str]]:
    """(기사 목록, 실패한 매체 이름 목록). free = 키워드 면제 전문지 이름들(그 매체 RSS 는 기간 안 기사 전부)."""
    found: list[Article] = []
    failed: list[str] = []
    for feed in feeds:
        name, url = feed.get("name", ""), feed.get("url", "")
        if not url or not feed.get("on", True):  # 꺼 둔 매체는 건너뜀
            continue
        try:
            is_free = any(m and m in name for m in (free or []))
            found.extend(filter_items(fetch_feed(name, url), name or url, grades, start_date, end_date, keep_all=is_free))
        except NaverApiError:
            failed.append(name or url)
    return found, failed
