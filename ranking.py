"""추천 5건(베스트 5) 자동 선정 — AI 없이 규칙으로 점수를 매긴다.

점수(높을수록 추천):
- 등급: 직접 추가 100, A(주택관리공단 기사) 40
- 키워드 우선순위: 키워드 칸 맨 위 키워드일수록 높음(최대 20)
- 여러 매체가 다룬 사안('외 N건'): 1건당 4점(최대 20) — 많이 보도될수록 중요한 이슈
- 여러 키워드에 걸린 기사: 키워드 1개 더할 때마다 3점(최대 9)
- 리스크 단어(사고·감사·징계·국정감사 지적 등): 15점 / 정책 단어(개정·시행·입법예고 등): 6점
- 아파트 관리 전문지(아파트관리신문·한국아파트신문): 5점
- 최근 24시간 안 기사: 3점
고르기: 점수 순으로 뽑되 공단(A) 기사는 2건까지, 그 밖에는 같은 키워드에서 2건까지
         (한쪽으로 쏠리지 않게). 직접 추가한 기사는 5건과 별도로 항상 포함.
규칙은 출발점이다. 담당자가 체크를 더하고 빼서 최종 결정한다.
"""

import datetime as dt

from naver_api import Article

RISK_WORDS = ["사고", "화재", "붕괴", "누수", "사망", "숨져", "감사 결과", "감사에서", "감사원 감사", "징계", "비위", "비리", "횡령", "소송",
              "고발", "수사", "논란", "갑질", "폭언", "폭행", "부정", "체납", "공가", "빈집", "지적", "질타",
              "적발", "위반", "민원", "피해", "취약", "솜방망이"]
POLICY_WORDS = ["개정", "개정안", "입법예고", "시행", "시행령", "법안", "대책", "발표", "예산", "제도", "지침",
                "기준", "의무화", "도입", "확대", "개편", "통과"]
SPECIALIST_SOURCES = ["아파트관리신문", "한국아파트신문"]
PER_KEYWORD = 2


def score_parts(art: Article, keyword_rank: int, n_keywords: int, now: dt.datetime) -> dict[str, int]:
    """점수 항목별 점수(내려받기 파일에 근거로 남긴다). 합계가 score()."""
    p = {"등급": 100 if art.grade == "직접" else 40 if art.grade == "A" else 0,
         "키워드 순위": round(20 * max(0, n_keywords - keyword_rank) / n_keywords) if n_keywords else 0,
         "여러 매체": min(len(art.others), 5) * 4,
         "여러 키워드": min(max(len(art.keywords) - 1, 0), 3) * 3,
         "리스크 단어": 15 if hit_words(art.title, RISK_WORDS) else 0,
         "정책 단어": 6 if hit_words(art.title, POLICY_WORDS) else 0,
         "전문지": 5 if art.source in SPECIALIST_SOURCES else 0,
         "최근 24시간": 3 if now - art.published <= dt.timedelta(hours=24) else 0}
    return p


def hit_words(title: str, words: list[str]) -> list[str]:
    return [w for w in words if w in title]


def score(art: Article, keyword_rank: int, n_keywords: int, now: dt.datetime) -> int:
    return sum(score_parts(art, keyword_rank, n_keywords, now).values())


def pick_best(articles: list[Article], keyword_rank, n: int = 5) -> list[Article]:
    """직접 추가한 기사 전부 + 나머지에서 점수 순 n 건. keyword_rank(키워드) → 순위(0 이 최우선)."""
    ordered = sorted(articles, key=lambda a: (-a.score, -a.published.timestamp()))
    manual = [a for a in ordered if a.grade == "직접"]
    picked: list[Article] = []
    used: dict[str, int] = {}
    for a in ordered:
        if len(picked) >= n:
            break
        if a.grade == "직접":
            continue
        # 같은 묶음에서는 PER_KEYWORD 건까지: A 등급(공단 기사)은 한 묶음, 나머지는 대표 키워드별
        group = "A" if a.grade == "A" else (min(a.keywords, key=keyword_rank) if a.keywords else "")
        if used.get(group, 0) >= PER_KEYWORD:
            continue
        used[group] = used.get(group, 0) + 1
        picked.append(a)
    for a in ordered:  # 묶음 제한 때문에 n 건이 안 차면 나머지로 채운다
        if len(picked) >= n:
            break
        if a.grade != "직접" and not any(a is p for p in picked):
            picked.append(a)
    return manual + picked
