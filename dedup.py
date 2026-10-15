"""중복 기사 정리.

1) 같은 링크 → 하나로 (여러 키워드에 걸린 기사는 키워드만 합친다)
2) 제목이 완전히 같은 기사 → 하나로
3) (옵션) 제목이 거의 같은 기사(보도자료를 여러 매체가 받아쓴 경우) → 가장 먼저 나온 것만
4) 제외어가 제목에 들어 있으면 뺀다
"""

import re
from difflib import SequenceMatcher

from naver_api import Article

_NORM_RE = re.compile(r"[^0-9a-z가-힣]+")


def normalize(title: str) -> str:
    """비교용 제목: 소문자, 기호·공백 제거. '[단독]', '(종합)' 같은 꼬리표도 뗀다."""
    t = re.sub(r"[\[\(【][^\]\)】]{1,10}[\]\)】]", " ", title)
    return _NORM_RE.sub("", t.lower())


def apply_exclude(articles: list[Article], exclude_words: list[str]) -> list[Article]:
    words = [w.strip() for w in exclude_words if w.strip()]
    if not words:
        return articles
    return [a for a in articles if not any(w in a.title for w in words)]


def dedupe(
    articles: list[Article],
    merge_similar: bool = True,
    threshold: float = 0.85,
) -> list[Article]:
    # 오래된 것부터 정렬하면 '최초 보도'가 남는다
    ordered = sorted(articles, key=lambda a: a.published)

    by_link: dict[str, Article] = {}
    by_title: dict[str, Article] = {}
    kept: list[Article] = []

    for art in ordered:
        key_link = art.link or art.naver_link
        key_title = normalize(art.title)

        dup = by_link.get(key_link) or by_title.get(key_title)
        if dup is None and merge_similar and key_title:
            for other in kept:
                ot = normalize(other.title)
                if abs(len(ot) - len(key_title)) > max(len(ot), len(key_title)) * (1 - threshold):
                    continue  # 길이 차이가 크면 비교 생략(속도)
                if SequenceMatcher(None, key_title, ot).ratio() >= threshold:
                    dup = other
                    break

        if dup is not None:
            for k in art.keywords:
                if k not in dup.keywords:
                    dup.keywords.append(k)
            if art.grade == "A":  # A·B 모두에 걸리면 A
                dup.grade = "A"
            continue

        by_link[key_link] = art
        by_title[key_title] = art
        kept.append(art)

    # 결과는 최신순으로
    kept.sort(key=lambda a: a.published, reverse=True)
    return kept
