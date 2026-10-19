"""점수·분류·추천 — 규칙(rules.py, [선정 규칙] 탭)대로 계산한다. AI 없이 규칙만으로.

점수(제목 기준, 가중치는 규칙에서 바꿀 수 있다):
- A 기관 직접 +50 · S 사업어 +30(2개 이상 +40, 제목만) · 모회사·부처어 +15 · B 환경 +10(요약까지)
- 리스크어 +20: A·S·모회사어·B(제목)·리스크 조건어(임대주택·공공임대 …)가 같은 제목에 있을 때만
  (한강버스·전통시장 같은 일반 뉴스의 '화재'·'수사'에는 점수를 주지 않게)
- 정책어 +10: S·모회사어·정책 조건어(주거·임대·공동주택)가 같은 제목에 있을 때만
- 여러 매체가 다룬 사안 1건당 +2(최대 +8) · 전문지 +3 · 본사 지역지 +2(A 일 때만) · 최근 24시간 +3 · [단독] +5
- 공급·개발어 −15(S·리스크어·정책어가 없고, 걸린 키워드 자체가 그 말을 품지 않을 때)
  · 일상 공고어(모집·접수·공고) −25(A 가 아닐 때) · A 기사의 단순 행사어 −20
- 키워드 면제 전문지(아파트관리신문 등) 기사는 키워드 없이도 후보, 기본 +15(일반 전문지 +3 대신). 리스크·정책 가점 조건도 연다.
- 지사명만 있고 '주택관리공단'이 없는 제목은 등급 'A?', +20, 점수 근거에 '공단 여부 확인'. 추천에는 넣지 않는다.
분류(규칙의 '분류 순서'에서 처음 맞는 것, 기본): 리스크 → 기관 직접(A) → 정책·제도(정책어 가점·정책·제도어)
  → 모회사·부처(모회사어) → 공공기관 공통(공공기관 공통어) → 업계·환경(나머지)
  S 사업어만으로는 정책·제도가 아니다. A 가 아닌 공고 기사는 리스크가 아니면 업계·환경.
추천: 리스크 먼저(최대 2) → 공단(A) 최소 1 → 점수순. 같은 분류 2건까지(업계·환경은 1건), 최소 점수 미만은 추천 안 함
  S 사업어 2개는 서로 다른 글자를 잡았을 때만(공공임대주택 = 1개). 지사명만(A?)·일상 공고(A 제외)는 추천 안 함
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
    full = f"{a.title} {a.description}"
    a_hits = R.hits(R.a_keywords(r), a.title)
    return {"A": a_hits,
            # 지사명만(같은 제목에 '주택관리공단' 없음) — A 가 아니라 'A?'
            "A?": [] if a_hits else R.hits(r["kw_a_branch"], a.title),
            "S": R.hits(R.s_keywords(r), full if r["check_summary_s"] else a.title),
            "B": R.hits(r["kw_b"], full if r["check_summary"] else a.title)}


def evaluate(a: Article, r: dict, now: dt.datetime) -> None:
    """점수(a.score), 항목별 점수(a.parts), 걸린 말(a.hits), 자동 분류(a.auto_category)를 채운다."""
    t = a.title
    kh = keyword_hits(a, r)
    full = f"{t} {a.description}"
    b_title = R.hits(kh["B"], t)
    h = {"A": kh["A"], "S": kh["S"], "B": kh["B"], "모회사": R.hits(r["parent_words"], t),
         "리스크": R.hits(r["risk_words"], t), "정책": R.hits(r["policy_words"], t), "개발": R.hits(r["dev_words"], t),
         "공고": R.hits(r["routine_words"], t), "행사": R.hits(r["event_words"], t),
         # 키워드가 맞은 구간(원래 글 그대로) — 점수 근거에 보여 준다. 요약에서만 맞은 것은 '(요약)'
         "구간": {**R.spans(kh["A"], t), **R.spans(kh["S"] + kh["B"], full)},
         "요약": [w for w in kh["S"] + kh["B"] if not R.matches(w, t)]}
    a.hits = h
    h["A?"] = kh["A?"]
    is_a, s, parent = bool(kh["A"]), kh["S"], bool(h["모회사"])
    free = any(m and m in a.source for m in r["specialist_free_press"])
    routine = bool(h["공고"]) and not is_a
    policy_ok = bool(h["정책"]) and (bool(s) or parent or free or bool(R.hits(r["policy_context"], t)))
    risk_ok = bool(h["리스크"]) and (is_a or bool(s) or parent or free or bool(b_title)
                                    or bool(R.hits(r["risk_context_extra"], t)))
    # 공급·개발 감점: S·리스크어·정책어가 없을 때만. '공공주택 공급'처럼 걸린 키워드가 그 말을 품으면 감점하지 않는다
    kw_text = R._squash(" ".join(kh["S"] + kh["B"]))
    dev = [w for w in h["개발"] if R._squash(w.split(" -")[0]) not in kw_text]
    dev_cut = bool(dev) and not s and not h["리스크"] and not h["정책"]
    p = {
        "A 기관": r["w_a"] if is_a else 0,
        "S 사업어": (r["w_s2"] if R.distinct_count(s, full if r["check_summary_s"] else t) >= 2 else r["w_s"]) if s else 0,
        "모회사·부처": r["w_parent"] if parent else 0,
        "B 환경": r["w_b"] if kh["B"] else 0,
        "리스크": r["w_risk"] if risk_ok else 0,
        "정책": r["w_policy"] if policy_ok else 0,
        "여러 매체": min(len(a.others) * r["w_multi_each"], r["w_multi_max"]),
        "전문지 기본": r["w_specialist_base"] if free else 0,
        "전문지": r["w_specialist"] if not free and any(m in a.source for m in r["specialist_press"]) else 0,
        "지사명만": r["w_branch_only"] if kh["A?"] else 0,
        "지역지": r["w_local"] if is_a and any(m in a.source for m in r["local_press"]) else 0,
        "최근 24시간": r["w_recent"] if now - a.published <= dt.timedelta(hours=24) else 0,
        "단독": r["w_exclusive"] if _EXCLUSIVE_RE.search(t) else 0,
        "공급·개발": r["w_dev"] if dev_cut else 0,
        "공고": r["w_routine"] if routine else 0,
        "행사": r["w_event_a"] if h["행사"] and is_a else 0,
    }
    if a.grade == "직접":
        p = {"직접 추가": MANUAL_SCORE, **p}
    a.parts = p
    a.score = sum(p.values())
    fits = {"리스크": risk_ok, "기관 직접": is_a,
            "정책·제도": not routine and (policy_ok or bool(R.hits(r["cat_policy_words"], t))),
            "모회사·부처": not routine and parent,
            "공공기관 공통": not routine and bool(R.hits(r["cat_public_words"], t)),
            "업계·환경": True}
    a.auto_category = next(c for c in r["category_order"] + ["업계·환경"] if fits.get(c))


def score_line(a: Article) -> str:
    """점수 근거 한 줄: 'A 기관 +50(주택관리공단) S 사업어 +30(공공임대 입주「공공임대 아파트 입주」) … = 100'.
    여러 낱말 키워드는 제목에서 실제로 맞은 구간을 「」 안에 보여 준다."""
    h = a.hits
    spans = h.get("구간", {})
    words = {"A 기관": h.get("A"), "S 사업어": h.get("S"), "B 환경": h.get("B"), "모회사·부처": h.get("모회사"),
             "리스크": h.get("리스크"), "정책": h.get("정책"), "공급·개발": h.get("개발"), "공고": h.get("공고"),
             "행사": h.get("행사"), "지사명만": [f"{b} — 공단 여부 확인" for b in h.get("A?", [])]}
    in_summary = set(h.get("요약", []))

    def show(w: str) -> str:
        sp = spans.get(w)
        out = f"{w}「{sp}」" if sp and R._squash(sp) != R._squash(w) else w
        return out + "(요약)" if w in in_summary else out

    bits = []
    for k, v in a.parts.items():
        if v:
            w = words.get(k)
            bits.append(f"{k} {v:+d}" + (f"({', '.join(show(x) for x in w[:3])})" if w else ""))
    return " ".join(bits).lstrip("+") + f" = {a.score}"


def pick_best(articles: list[Article], r: dict) -> list[Article]:
    """직접 추가한 기사 전부 + 규칙대로 고른 추천(최대 best_count 건)."""
    n = r["best_count"]
    manual = [a for a in articles if a.grade == "직접"]
    # 'A?'(지사명만)는 공단 기사인지 사람이 확인해야 하므로, 일상 공고(A 제외)는 임원 보고 대상이 아니므로 추천하지 않는다
    cand = sorted((a for a in articles if a.grade not in ("직접", "A?") and a.score >= r["min_score"]
                   and not (a.parts.get("공고") and a.grade != "A")),
                  key=lambda a: (-a.score, -a.published.timestamp()))
    picked: list[Article] = []
    per_cat: dict[str, int] = {}

    def take(a: Article) -> bool:
        cat = a.auto_category
        limit = r["industry_max"] if cat == "업계·환경" else r["per_category_max"]  # 가장 넓은 분류라 더 적게
        if len(picked) >= n or any(a is p for p in picked) or per_cat.get(cat, 0) >= limit:
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
