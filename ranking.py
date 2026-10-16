"""점수·분류·추천 — 규칙(rules.py, [선정 규칙] 탭)대로 계산한다. AI 없이 규칙만으로.

점수(제목 기준, 가중치는 규칙에서 바꿀 수 있다):
- A 기관 직접 +50 · S 사업어 +30(2개 이상 +40) · 모회사·부처어 +15 · B 환경 +10
- 리스크어 +20: A·S·모회사어가 같은 제목에 있을 때만 (주제와 무관한 '화재'·'수사'에 점수를 주지 않게)
- 정책어 +10: S·모회사어·정책 조건어(주거·임대·공동주택)가 같은 제목에 있을 때만
- 여러 매체가 다룬 사안 1건당 +2(최대 +8) · 전문지 +3 · 본사 지역지 +2(A 일 때만) · 최근 24시간 +3 · [단독] +5
- 공급·개발어 −15(S 가 없을 때) · A 기사의 단순 행사어 −20 (A 가 아니면 행사 기사는 조회 단계에서 빠진다)
분류(위에서부터 처음 맞는 것): 리스크(A·S·모회사어 + 리스크어) → 기관 직접(A) → 모회사·부처(모회사어, S 없이)
  → 정책·제도(정책어 가점·정책·제도어·S) → 공공기관 공통(공공기관 공통어) → 업계·환경
추천: 리스크 먼저(최대 2) → 공단(A) 최소 1 → 점수순. 같은 분류는 2건까지, 최소 점수 미만은 추천 안 함
  (5건이 안 차면 그 수만큼만). 직접 추가한 기사는 별도로 항상 포함.
규칙은 출발점이다. 담당자가 체크를 더하고 빼서 최종 결정하고, 어긋난 것은 규칙 개선으로 환류한다.
"""

import datetime as dt
import re

import rules as R
from naver_api import Article

_EXCLUSIVE_RE = re.compile(r"[\[\(<【]\s*단독\s*[\]\)>】]")
MANUAL_SCORE = 100


def keyword_hits(a: Article, r: dict) -> dict[str, list[str]]:
    """걸린 검색 키워드: A 는 제목만, S·B 는 (설정에 따라) 요약까지."""
    text = f"{a.title} {a.description}" if r["check_summary"] else a.title
    return {"A": R.hits(R.a_keywords(r), a.title), "S": R.hits(R.s_keywords(r), text), "B": R.hits(r["kw_b"], text)}


def evaluate(a: Article, r: dict, now: dt.datetime) -> None:
    """점수(a.score), 항목별 점수(a.parts), 걸린 말(a.hits), 자동 분류(a.auto_category)를 채운다."""
    t = a.title
    kh = keyword_hits(a, r)
    h = {"S": kh["S"], "모회사": R.hits(r["parent_words"], t), "리스크": R.hits(r["risk_words"], t),
         "정책": R.hits(r["policy_words"], t), "개발": R.hits(r["dev_words"], t), "행사": R.hits(r["event_words"], t)}
    a.hits = h
    is_a, s, parent = bool(kh["A"]), kh["S"], bool(h["모회사"])
    policy_ok = bool(h["정책"]) and (bool(s) or parent or bool(R.hits(r["policy_context"], t)))
    risk_ok = bool(h["리스크"]) and (is_a or bool(s) or parent)
    p = {
        "A 기관": r["w_a"] if is_a else 0,
        "S 사업어": (r["w_s2"] if len(s) >= 2 else r["w_s"]) if s else 0,
        "모회사·부처": r["w_parent"] if parent else 0,
        "B 환경": r["w_b"] if kh["B"] else 0,
        "리스크": r["w_risk"] if risk_ok else 0,
        "정책": r["w_policy"] if policy_ok else 0,
        "여러 매체": min(len(a.others) * r["w_multi_each"], r["w_multi_max"]),
        "전문지": r["w_specialist"] if any(m in a.source for m in r["specialist_press"]) else 0,
        "지역지": r["w_local"] if is_a and any(m in a.source for m in r["local_press"]) else 0,
        "최근 24시간": r["w_recent"] if now - a.published <= dt.timedelta(hours=24) else 0,
        "단독": r["w_exclusive"] if _EXCLUSIVE_RE.search(t) else 0,
        "공급·개발": r["w_dev"] if h["개발"] and not s else 0,
        "행사": r["w_event_a"] if h["행사"] and is_a else 0,
    }
    if a.grade == "직접":
        p = {"직접 추가": MANUAL_SCORE, **p}
    a.parts = p
    a.score = sum(p.values())
    if risk_ok:
        cat = "리스크"
    elif is_a:
        cat = "기관 직접"
    elif parent and not s:
        cat = "모회사·부처"
    elif policy_ok or s or R.hits(r["cat_policy_words"], t):
        cat = "정책·제도"
    elif R.hits(r["cat_public_words"], t):
        cat = "공공기관 공통"
    else:
        cat = "업계·환경"
    a.auto_category = cat


def score_line(a: Article) -> str:
    """점수 근거 한 줄: 'A 기관 50 + S 사업어 30(영구임대) + 리스크 20(고독사) = 100'."""
    words = {"S 사업어": a.hits.get("S"), "모회사·부처": a.hits.get("모회사"), "리스크": a.hits.get("리스크"),
             "정책": a.hits.get("정책"), "공급·개발": a.hits.get("개발"), "행사": a.hits.get("행사")}
    bits = []
    for k, v in a.parts.items():
        if v:
            w = words.get(k)
            bits.append(f"{k} {v:+d}" + (f"({', '.join(w[:3])})" if w else ""))
    return " ".join(bits).lstrip("+") + f" = {a.score}"


def pick_best(articles: list[Article], r: dict) -> list[Article]:
    """직접 추가한 기사 전부 + 규칙대로 고른 추천(최대 best_count 건)."""
    n = r["best_count"]
    manual = [a for a in articles if a.grade == "직접"]
    cand = sorted((a for a in articles if a.grade != "직접" and a.score >= r["min_score"]),
                  key=lambda a: (-a.score, -a.published.timestamp()))
    picked: list[Article] = []
    per_cat: dict[str, int] = {}

    def take(a: Article) -> bool:
        cat = a.auto_category
        if len(picked) >= n or any(a is p for p in picked) or per_cat.get(cat, 0) >= r["per_category_max"]:
            return False
        picked.append(a)
        per_cat[cat] = per_cat.get(cat, 0) + 1
        return True

    risk = 0
    for a in cand:  # ① 리스크 먼저
        if a.auto_category == "리스크" and risk < r["risk_first_max"] and take(a):
            risk += 1
    n_a = sum(1 for a in picked if a.grade == "A")
    for a in cand:  # ② 공단(A) 기사 최소 건수
        if n_a >= r["a_min"]:
            break
        if a.grade == "A" and take(a):
            n_a += 1
    for a in cand:  # ③ 나머지는 점수순
        take(a)
    return manual + picked
