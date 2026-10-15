"""중복 기사 정리.

1) 같은 링크 → 하나로 (여러 키워드에 걸린 기사는 키워드만 합친다)
2) 제목이 완전히 같은 기사 → 하나로
3) (옵션) 같은 사안 기사 → 가장 먼저 나온 것만 남기고 나머지는 '외 N건'으로 붙여 둔다
   - 제목이 거의 같은 기사(보도자료를 여러 매체가 받아쓴 경우)
   - 제목은 달라도 같은 행사·사건(예: '월평2동 온마을축제'를 세 매체가 각자 제목으로 보도):
     이틀 안에 나온 기사끼리, 흔하지 않은 낱말(지명·행사명 등)을 2개 이상 같이 쓰면 같은 사안으로 본다.
     흔한 낱말(검색 키워드, 그날 기사 다수에 나오는 말, '개최'·'지원' 같은 말)은 세지 않는다.
4) 제외어가 제목에 들어 있으면 뺀다 / 행사성 단어가 들어 있으면 뺀다
"""

import re
from difflib import SequenceMatcher

from naver_api import Article

_NORM_RE = re.compile(r"[^0-9a-z가-힣]+")
_WORD_RE = re.compile(r"[0-9a-z가-힣]+")
_JOSA = ("으로", "에서", "에게", "까지", "부터", "은", "는", "이", "가", "을", "를", "에", "의", "도", "로", "와", "과")
_COMMON = set("""
위한 위해 관련 대한 통해 지원 추진 개최 열어 진행 실시 강화 확대 나서 기자 사업 정부 정책 오늘 올해 지역 주민
단독 종합 속보 포토 사진 영상 기고 칼럼 사설 인터뷰 전국 시민 국민 의원 장관 대표 위원장 발표 계획 방안 필요
""".split())
SAME_STORY_DAYS = 2      # 이 기간 안에 나온 기사끼리만 같은 사안으로 묶는다
SAME_STORY_SHARED = 2    # 흔하지 않은 낱말을 이만큼 같이 쓰면 같은 사안


def normalize(title: str) -> str:
    """비교용 제목: 소문자, 기호·공백 제거. '[단독]', '(종합)' 같은 꼬리표도 뗀다."""
    t = re.sub(r"[\[\(【][^\]\)】]{1,10}[\]\)】]", " ", title)
    return _NORM_RE.sub("", t.lower())


def words(text: str) -> set[str]:
    """제목의 낱말들(두 글자 이상, 숫자로 시작하는 것 제외, 끝의 조사는 뗀다)."""
    out = set()
    for w in _WORD_RE.findall(text.lower()):
        for j in _JOSA:
            if len(w) > len(j) + 1 and w.endswith(j):
                w = w[: -len(j)]
                break
        if len(w) >= 2 and not w[0].isdigit():
            out.add(w)
    return out


def apply_exclude(articles: list[Article], exclude_words: list[str]) -> list[Article]:
    words_ = [w.strip() for w in exclude_words if w.strip()]
    if not words_:
        return articles
    return [a for a in articles if not any(w in a.title for w in words_)]


def _common_words(articles: list[Article], keywords: list[str]) -> set[str]:
    """같은 사안 판정에서 세지 않을 낱말: 검색 키워드, 그날 기사 여러 곳에 나오는 말."""
    common = set(_COMMON)
    for k in keywords:
        common |= words(k.replace('"', " "))
    df: dict[str, int] = {}
    for a in articles:
        for w in words(a.title):
            df[w] = df.get(w, 0) + 1
    limit = max(4, len(articles) // 20)  # 기사 5% 넘게(최소 4건) 나오는 말은 흔한 말
    common |= {w for w, n in df.items() if n >= limit}
    return common


def dedupe(
    articles: list[Article],
    merge_similar: bool = True,
    threshold: float = 0.85,
    keywords: list[str] | None = None,
) -> list[Article]:
    # 오래된 것부터 정렬하면 '최초 보도'가 남는다
    ordered = sorted(articles, key=lambda a: a.published)
    common = _common_words(ordered, keywords or []) if merge_similar else set()

    by_link: dict[str, Article] = {}
    by_title: dict[str, Article] = {}
    kept: list[Article] = []
    kept_words: dict[int, set[str]] = {}

    for art in ordered:
        key_link = art.link or art.naver_link
        key_title = normalize(art.title)
        my_words = words(art.title) - common

        dup = by_link.get(key_link) or by_title.get(key_title)
        if dup is None and merge_similar and key_title:
            for other in kept:
                ot = normalize(other.title)
                if abs(len(ot) - len(key_title)) <= max(len(ot), len(key_title)) * (1 - threshold):
                    if SequenceMatcher(None, key_title, ot).ratio() >= threshold:
                        dup = other
                        break
                if (abs((art.published - other.published).days) <= SAME_STORY_DAYS
                        and len(my_words & kept_words[id(other)]) >= SAME_STORY_SHARED):
                    dup = other
                    break

        if dup is not None:
            for k in art.keywords:
                if k not in dup.keywords:
                    dup.keywords.append(k)
            if art.grade == "A":  # A·B 모두에 걸리면 A
                dup.grade = "A"
            if key_link != (dup.link or dup.naver_link):
                dup.others.append((art.source, art.title, key_link))
            dup.others.extend(art.others)
            continue

        by_link[key_link] = art
        by_title[key_title] = art
        kept.append(art)
        kept_words[id(art)] = my_words

    # 결과는 최신순으로
    kept.sort(key=lambda a: a.published, reverse=True)
    return kept
