"""구글 뉴스 RSS 검색 (키 불필요).

네이버 검색 API 신규 발급이 끝나서(2026-07-31) 키 없이 쓸 수 있는 출처로 추가했다.
- 주소: https://news.google.com/rss/search?q=키워드 after:날짜 before:날짜&hl=ko&gl=KR&ceid=KR:ko
- 돌려받는 것은 JSON 이 아니라 RSS(XML). 기사 하나가 <item> 하나다.
- 제목 끝에 " - 매체명"이 붙어 오므로 떼고, 매체명은 <source> 에서 가져온다.
- 한 번에 최대 100건 정도만 준다. 빠짐없이 받아야 할 때(A 등급)는 100건이 꽉 차면
  기간을 반으로 나눠 다시 묻는다. B 등급은 한 번만 묻는다(요청 수·건수 줄이기).
- 결과는 네이버와 같은 Article 형태로 돌려주므로 중복제거·보고서는 그대로 쓴다.
- RSS 의 기사 링크는 구글을 거치는 주소(news.google.com/rss/articles/…)다.
  보고서에 넣을 기사만 resolve_links()로 언론사 원문 주소로 바꾼다(요청 수를 줄이려고).
  구글이 공식 제공하는 기능이 아니라서, 실패하면 구글 주소를 그대로 쓴다.
"""

import base64
import datetime as dt
import json
import re

import requests

import rss
from naver_api import Article, NaverApiError

RSS_URL = "https://news.google.com/rss/search"
PAGE_LIMIT = 100      # 구글이 한 번에 주는 최대 건수(대략)
MAX_SPLIT_DEPTH = 4   # 기간 나누기는 최대 4번까지(요청이 너무 많아지지 않게)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsMonitor"}

ARTICLE_PAGE = "https://news.google.com/rss/articles/{}"
BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_ID_RE = re.compile(r"news\.google\.com/(?:rss/)?articles/([^?/#]+)")
_SG_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]+)"')
_URL_BYTES_RE = re.compile(rb"https?://[\x21-\x7e]+")
_resolved: dict[str, str] = {}  # 구글 주소 → 원문 주소 (앱을 켜 둔 동안 기억)


def build_query(keyword: str, start_date: dt.date, end_date: dt.date) -> str:
    # after 는 하루 앞당겨 넉넉히 받는다(구글이 날짜를 미국 시간 기준으로 자를 수 있어서).
    # 정확한 기간은 받아 온 뒤 한국시간으로 다시 거른다.
    after = start_date - dt.timedelta(days=1)
    before = end_date + dt.timedelta(days=1)
    return f"{keyword} after:{after.isoformat()} before:{before.isoformat()}"


def parse_rss(xml_text: str | bytes, keyword: str) -> list[Article]:
    """RSS 문서를 Article 목록으로 바꾼다(기간 필터 전)."""
    out: list[Article] = []
    for it in rss.parse_items(xml_text, "구글 뉴스"):
        title, source = it.title, it.source
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)].rstrip()
        elif not source and " - " in title:
            title, source = (s.strip() for s in title.rsplit(" - ", 1))
        # 구글의 요약은 '제목 + 매체명'뿐이라 쓸모가 없어 비운다
        desc = "" if it.description.startswith(title[:15]) else it.description
        out.append(Article(
            title=title,
            link=it.link,
            naver_link="",
            source=source,
            published=it.published,
            description=desc,
            keywords=[keyword],
        ))
    return out


def _fetch(keyword: str, start_date: dt.date, end_date: dt.date) -> list[Article]:
    params = {"q": build_query(keyword, start_date, end_date), "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    try:
        resp = requests.get(RSS_URL, params=params, headers=HEADERS, timeout=15)
    except requests.exceptions.SSLError as e:
        raise NaverApiError("보안 인증서 확인 실패(구글 뉴스): 회사 보안장비가 접속을 검사하는 것으로 보입니다.\n"
                            f"전산 담당에 이 메시지를 전달해 주세요.\n\n{e}") from e
    except requests.RequestException as e:
        raise NaverApiError(f"네트워크 오류(구글 뉴스): {e}") from e
    if resp.status_code == 429:
        raise NaverApiError("구글 뉴스 호출이 너무 많습니다(429). 잠시 후 다시 시도하세요.")
    if resp.status_code != 200:
        raise NaverApiError(f"구글 뉴스 오류({resp.status_code}): {resp.text[:200]}")
    return parse_rss(resp.content, keyword)


def _search_range(keyword: str, start_date: dt.date, end_date: dt.date, depth: int,
                  split: bool = True) -> list[Article]:
    items = _fetch(keyword, start_date, end_date)
    if split and len(items) >= PAGE_LIMIT and start_date < end_date and depth < MAX_SPLIT_DEPTH:
        mid = start_date + (end_date - start_date) // 2
        return (_search_range(keyword, start_date, mid, depth + 1)
                + _search_range(keyword, mid + dt.timedelta(days=1), end_date, depth + 1))
    return items


def search_news(keyword: str, start_date: dt.date, end_date: dt.date, split: bool = True) -> list[Article]:
    """키워드 하나로 기간(한국시간 기준) 내 기사를 가져온다. split=False 면 한 번만 묻는다."""
    results, seen = [], set()
    for art in _search_range(keyword, start_date, end_date, 0, split):
        if not (start_date <= art.published.date() <= end_date):
            continue
        if art.link in seen:  # 기간을 나눠 물으면 경계에서 겹칠 수 있다
            continue
        seen.add(art.link)
        results.append(art)
    return results


# ------------------------------------------------------------ 원문 주소 찾기
def is_google_link(url: str) -> bool:
    return bool(_ID_RE.search(url or ""))


def _decode_old_format(art_id: str) -> str | None:
    """예전 형식은 주소 안에 원문 주소가 그대로 암호화 없이(base64) 들어 있다."""
    try:
        raw = base64.urlsafe_b64decode(art_id + "=" * (-len(art_id) % 4))
    except (ValueError, TypeError):
        return None
    m = _URL_BYTES_RE.search(raw)
    return m.group().decode("ascii") if m else None


def _parse_batch_response(text: str) -> str | None:
    """구글 응답(앞에 )]}' 가 붙은 JSON)에서 원문 주소를 꺼낸다."""
    start = text.find("[")
    if start < 0:
        return None
    rows, _ = json.JSONDecoder().raw_decode(text[start:])
    for row in rows:
        if isinstance(row, list) and len(row) > 2 and row[0] == "wrb.fr" and isinstance(row[2], str):
            inner = json.loads(row[2])
            if len(inner) > 1 and isinstance(inner[1], str) and inner[1].startswith("http"):
                return inner[1]
    return None


def _decode_new_format(art_id: str) -> str | None:
    """요즘 형식은 구글에 한 번 더 물어야 한다: 기사 페이지에서 서명값을 읽고 → 변환 요청."""
    page = requests.get(ARTICLE_PAGE.format(art_id), headers=HEADERS, timeout=10)
    sg, ts = _SG_RE.search(page.text), _TS_RE.search(page.text)
    if page.status_code != 200 or not sg or not ts:
        return None
    req = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
           f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{art_id}",{ts.group(1)},"{sg.group(1)}"]')
    resp = requests.post(
        BATCH_URL,
        data={"f.req": json.dumps([[["Fbv4je", req, None, "generic"]]])},
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    return _parse_batch_response(resp.text)


def cached_link(url: str) -> str:
    """이미 찾아 둔 원문 주소(없으면 빈 문자열). 인터넷에 묻지 않는다."""
    return _resolved.get(url, "")


def resolve_link(url: str) -> str:
    """구글 주소를 언론사 원문 주소로 바꾼다. 실패하면 받은 주소를 그대로 돌려준다."""
    m = _ID_RE.search(url or "")
    if not m:
        return url
    if url in _resolved:
        return _resolved[url]
    art_id = m.group(1)
    direct = _decode_old_format(art_id)
    if not direct:
        try:
            direct = _decode_new_format(art_id)
        except (requests.RequestException, ValueError, IndexError, TypeError):
            direct = None
    if direct and not is_google_link(direct):
        _resolved[url] = direct
        return direct
    return url


def resolve_links(urls: list[str], progress=None) -> dict[str, str]:
    """여러 주소를 한꺼번에. progress(완료 수, 전체 수)로 진행 상황을 알린다."""
    out: dict[str, str] = {}
    targets = [u for u in dict.fromkeys(urls) if is_google_link(u)]
    for i, u in enumerate(targets, 1):
        out[u] = resolve_link(u)
        if progress:
            progress(i, len(targets))
    return out
