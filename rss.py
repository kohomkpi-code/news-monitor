"""RSS(XML) 문서 읽기 — 구글 뉴스와 전문지 RSS 가 함께 쓰는 공통 부분.

RSS 는 기사 하나가 <item> 하나이고, 그 안에 제목(title)·링크(link)·날짜(pubDate)·
요약(description)·매체명(source, 구글만)이 들어 있다. 여기서는 글자만 꺼내 정리하고,
구글 제목 꼬리 떼기나 키워드 거르기 같은 출처별 처리는 각 모듈이 한다.
"""

import datetime as dt
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from naver_api import NaverApiError, clean_text, parse_pubdate

KST = dt.timezone(dt.timedelta(hours=9))
# 표준(RFC) 날짜가 아닐 때 시도할 형식. 국내 언론사 CMS 는 '2026-10-15 09:00:00' 을 많이 쓴다.
_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")


@dataclass
class RssItem:
    title: str
    link: str
    published: dt.datetime   # 한국시간
    description: str
    source: str              # <source> 글자 (없으면 빈 문자열)


def parse_date(text: str) -> dt.datetime:
    text = text.strip()
    try:
        return parse_pubdate(text)
    except (TypeError, ValueError):
        pass
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"날짜 형식을 알 수 없음: {text}")


def channel_title(xml_text: str | bytes) -> str:
    """RSS 맨 위 <channel><title> — 보통 매체 이름. 못 읽으면 빈 문자열."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    return clean_text(root.findtext("channel/title") or "")


def parse_items(xml_text: str | bytes, where: str = "RSS") -> list[RssItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise NaverApiError(f"{where} 응답을 읽을 수 없습니다: {e}") from e

    out: list[RssItem] = []
    for item in root.iter("item"):
        title = clean_text(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate")
        if not title or not link or not pub:
            continue
        try:
            published = parse_date(pub)
        except (TypeError, ValueError):
            continue
        if published.tzinfo is None:  # 시간대가 없으면 한국시간으로 본다
            published = published.replace(tzinfo=KST)
        out.append(RssItem(
            title=title,
            link=link,
            published=published.astimezone(KST),
            description=clean_text(item.findtext("description") or ""),
            source=clean_text(item.findtext("source") or ""),
        ))
    return out
