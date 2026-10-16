"""선정 기준 검증 — 실제 기사 제목으로 점수·분류·추천이 기대대로 나오는지 (기본 규칙 기준).

기본 규칙(rules.DEFAULT_RULES)을 바꾸면 이 시험이 깨질 수 있다. 일부러 바꾼 것이면 기대값을 함께 고친다.
사용: python tests/check_rules.py   (저장소 맨 위 폴더에서). 하나라도 실패하면 끝 코드 1 → 빌드 중단.
- 1부: 10-16 14:00 조회 검토 지시서(v1.0.0). 14:54 검토로 규칙이 바뀐 항목은 기대값을 새 규칙에 맞춤(표시 '※').
- 2부: 10-16 14:54 조회 검토 지시서(v1.0.2)의 실제 제목 12개와 베스트 5.
- 3부: 15:10 추가 지시(v1.0.1) — 매칭·제외 매체·약칭, 저장된 규칙 갱신.
- 4부: 기발송 메일 76건 백테스트 지시(v1.0.3) — 키워드 면제 전문지, 지사명만(A?), 가중치.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import datetime as dt
from collections import Counter

import dedup
import ranking
import rules
from naver_api import Article

KST = dt.timezone(dt.timedelta(hours=9))
now = dt.datetime(2026, 10, 16, 15, 0, tzinfo=KST)
r = rules.normalize(None)
results: list[bool] = []


def art(title, hours=30, others=0, desc="", source="테스트일보"):
    a = Article(title, "https://x/" + title, "", source, now - dt.timedelta(hours=hours), desc, [])
    a.others = [("m", "t", "l")] * others
    return a


def judge(a, rr=r):
    """조회 단계와 같게: 제목 검증 → 등급 → 점수. 빠지면 None."""
    kh = ranking.keyword_hits(a, rr)
    if kh["A"] + kh["S"] + kh["B"]:
        a.grade = "A" if kh["A"] else "S" if kh["S"] else "B"
    elif kh["A?"]:
        a.grade = "A?"
    elif any(m in a.source for m in rr["specialist_free_press"]):
        a.grade = "전문지"
    else:
        return None
    ranking.evaluate(a, rr, now)
    return a


def row(no, title, ok, a, want):
    results.append(ok)
    got = f"{a.score}점 · {a.auto_category}" if a else "빠짐(검증 실패)"
    print(f"{no:>4} {'통과' if ok else '실패'} | {got:<16} | 기대: {want} | {title[:42]}")
    if a:
        print("        근거:", ranking.score_line(a))


def between(a, lo, hi):
    return a is not None and lo <= a.score <= hi


print("── 1부: 14:00 검토(v1.0.0) ── (24시간 가점 없이)")
P1 = [
    ("LH 빈집 늘자 '관리비 대납'만 올해 168억…5년 새 70% 급증", lambda a: a and a.auto_category == "리스크" and a.score >= 60, "리스크, 60 이상"),
    ("8년 넘게 텅빈 익산 임대상가…LH, 사후관리 부실 도마", lambda a: a and a.auto_category == "리스크" and a.score >= 60, "리스크, 60 이상"),
    ("영구임대주택 자살·고독사 236건…주거복지사 배치 '천차만별'", lambda a: a and a.auto_category in ("리스크", "기관 직접") and a.score >= 55, "리스크, 55 이상"),
    ("국토부 산하기관 성비위 징계 41건…'조직 관리 실패'", lambda a: a and a.auto_category in ("공공기관 공통", "리스크") and between(a, 35, 50), "리스크/공공기관 공통, 35~50"),
    ("[단독] '소셜 믹스' 겉도는 통합공공임대…70% 중산층 배정도", lambda a: a and a.auto_category in ("업계·환경", "정책·제도") and a.score >= 35, "※업계·환경(S만으론 정책 아님), 35 이상"),
    ("LH, AI 대전환 선포식…'주거 혁신 앞당길 것'", lambda a: a and a.auto_category == "모회사·부처" and between(a, 20, 35), "모회사·부처, 20~35"),
    ("박지효 송파구의원 '노후 빌라·다세대주택 주거환경 개선 지원해야'", lambda a: a is None, "검증 실패로 빠짐"),
    ("파기될 뻔한 한강버스 수사의뢰서, '브로커와 뇌물 의혹' 담겼다", lambda a: a is None, "빠짐"),
    ("전통시장 화재 안전…'디지털 기술로 강화한다'", lambda a: a is None, "빠짐"),
    ("LH, 신길4 등 3개 지구 도심 공공복합사업 속도 낸다…", lambda a: a and a.auto_category == "모회사·부처" and a.score <= 15, "※모회사·부처, 15 이하(모회사어 20점)"),
    ("전북특별자치도, 가정형 베란다 태양광 보급 확대 나선다", lambda a: a is None, "빠짐"),
    ("민요부터 요들송까지…분당하얀6단지에 찾아온 음악 선물", lambda a: a and a.hits["S"] == ["분당하얀6단지"], "※단지명 기본값 → S"),
]
for i, (t, check, want) in enumerate(P1, 1):
    a = judge(art(t))
    row(f"1-{i}", t, bool(check(a)), a, want)

# 같은 사안 6건 → 1묶음
lh = ["LH, 신길4 등 3개 지구 도심 공공복합사업 속도 낸다…", "LH, 신길·녹번·송중 도심복합사업 본격 추진",
      "신길4구역 등 3곳 도심공공복합사업 사업계획 승인", "LH 도심복합사업 3곳 사업승인…5032가구 공급",
      "녹번역·송중동·신길4 도심복합 5032가구 공급 속도", "국토부·LH, 신길4·녹번 도심 공공주택 복합사업 3곳 승인"]
others = ["영구임대 고독사 대책 발표", "공동주택 관리비 공개 대상 확대", "주택관리공단 경남지사 산학협력 협약",
          "층간소음 분쟁 해마다 늘어", "승강기 안전 점검 강화", "LH 임대주택 하자 소송 패소", "주거급여 기준 인상",
          "행복주택 입주자 모집", "국토부 공공임대 재정비 계획", "LH 사장 국감 출석"]
pool = [art(t, hours=i) for i, t in enumerate(lh)] + [art(t, hours=i + 2) for i, t in enumerate(others)]
out = dedup.dedupe(pool, True, 0.85, rules.search_grades(r))
groups = [a for a in out if a.title in lh]
ok = len(groups) == 1 and len(out) - len(groups) == len(others)
results.append(ok)
print(f"1-13 {'통과' if ok else '실패'} | 같은 사안 6건 → {len(groups)}묶음, 다른 기사 {len(out) - len(groups)}/{len(others)} 그대로")

print("\n── 2부: 14:54 검토(v1.0.2) ── (2시간 전 기사 = 24시간 가점 포함)")
P2 = [
    ("LH 전세임대 6만가구 석 달 넘게 임대료 체납…607억원", 0, lambda a: a and a.auto_category == "리스크" and a.score >= 70, "리스크, 70 이상"),
    ("SH 임대주택 화재 28% 증가·사망자 2.7배…복기왕 \"안전대책 점검해야\"", 3, lambda a: a and a.auto_category == "리스크" and a.score >= 45, "리스크, 45 이상, 베스트 5"),
    ("국토부 산하기관 13곳서 성비위 41건", 0, lambda a: a and a.auto_category in ("리스크", "공공기관 공통") and between(a, 40, 60), "리스크/공공기관 공통, 50 안팎"),
    ("울주복지재단·주택관리공단, 행정마을 주거환경 개선 봉사", 0, lambda a: a and a.auto_category == "기관 직접" and between(a, 40, 60), "기관 직접, 50 안팎"),
    ("공공임대주택에 무너진 LH 재정, 이재명 정부 어떤 답 내놓을까", 0, lambda a: a and a.auto_category == "모회사·부처" and between(a, 45, 65), "모회사·부처, 55 안팎"),
    ("LH 부산모라 통합공공임대 94호 모집…28일부터 접수", 0, lambda a: a and a.auto_category == "업계·환경" and a.score <= 40, "업계·환경, 40 이하"),
    ("월세 10만~20만 원…해남 청년공공임대주택 40세대 입주자 모집", 0, lambda a: a and a.auto_category == "업계·환경" and a.score <= 25, "업계·환경, 25 이하"),
    ("서울시, 20일부터 노숙인·쪽방 주민 1천 9백명에 독감 예방 무료접종", 0, lambda a: a is None, "빠짐(S 없음)"),
    ("한전 부산울산본부-부산시, 소상공인 에너지바우처 사용처 확대 협약", 0, lambda a: a and a.auto_category == "업계·환경" and a.score <= 15, "업계·환경, 15 이하"),
    ("\"내 집 마련보다 주거비 관리\"…미래 계획 세우는 임대주택 수요", 0, lambda a: a is None or a.score <= 10, "빠짐 또는 10 이하"),
    ("[기획 下] 노후 공공임대 34곳 재정비 추진…22곳 '법적 장벽' 넘을까", 0, lambda a: a and a.auto_category in ("업계·환경", "정책·제도") and a.score >= 35, "업계·환경/정책·제도, 35 이상"),
    ("공공임대주택은 '층간소음 기준 미달' 해도 괜찮나? \"민원 생기면 보완\"", 0, lambda a: a and a.auto_category == "리스크" and between(a, 45, 65), "리스크, 55 안팎"),
]
day = []
for i, (t, n_others, check, want) in enumerate(P2, 1):
    a = judge(art(t, hours=2, others=n_others))
    row(f"2-{i}", t, bool(check(a)), a, want)
    if a:
        day.append(a)
best = ranking.pick_best(day, r)
names = [a.title for a in best]
has = lambda key: any(key in n for n in names)
ok = has("임대료 체납") and has("SH 임대주택 화재") and has("주택관리공단") and (has("층간소음") or has("LH 재정")) \
    and not has("94호 모집") and len(best) == 5
results.append(ok)
print(f"2-13 {'통과' if ok else '실패'} | 베스트 5: " + " / ".join(f"{a.title[:14]}({a.score}·{a.auto_category})" for a in best))
n_risk = sum(1 for a in day if a.auto_category == "리스크")
print(f"        리스크 {n_risk}건 중 {sum(1 for a in best if a.auto_category == '리스크')}건 추천 — 나머지는 표에서 확인")

print("\n── 3부: 15:10 추가(v1.0.1) ──")
checks = []
checks.append(("여러 낱말: 같은 순서·20자 이내", rules.matches("공동주택 관리비", "서울 공동주택 관리비 공개")
               and not rules.matches("공동주택 관리비", "관리비 오른 공동주택")
               and not rules.matches("임대주택 노후", "노후 기업 사택 활용해 임대주택 30가구 공급")
               and not rules.matches("공공임대 입주", "공공임대 " + "가" * 19 + " 입주")
               and rules.match_span("공공임대 입주", "LH, 공공임대 아파트 신규 입주자 모집") == "공공임대 아파트 신규 입주"))
checks.append(("한 글자 낱말·빼는 말·검색어", rules.matches("군 관사", "육군 군관사 노후")
               and not rules.matches("분양 -분양전환", "임대 분양전환 가격") and rules.matches("분양 -분양전환", "LH 분양 일정")
               and rules.google_query("공동주택 관리비", True) == '"공동주택" "관리비"'
               and rules.google_query("주택관리공단 OR 마이홈", True) == "주택관리공단 OR 마이홈"))
em = r["exclude_media"]
checks.append(("해외 한인 매체 제외(영문은 낱말로)", rules.media_hit(em, "SeattleN", "https://news.google.com/rss/articles/CBMiLA") == "SeattleN"
               and rules.media_hit(em, "LA중앙일보", "") == "LA" and rules.media_hit(em, "Platum", "") is None
               and rules.media_hit(em, "한국경제", "https://www.hankyung.com/la/1") is None))
kh = ranking.keyword_hits(art("Sh수협은행 소상공인 혜택", desc="임대주택 입주민도 대상"), r)
checks.append(("'Sh수협은행'은 안 걸림, 'SH 임대주택'은 걸림", not (kh["A"] + kh["S"] + kh["B"])
               and '"SH 임대주택"' in ranking.keyword_hits(art("SH 임대주택 화재 늘어"), r)["B"]
               and "SH공사" in ranking.keyword_hits(art("SH공사, 임대주택 하자 보수 지연"), r)["B"]))
a = judge(art("주거비 걱정…LH 임대주택 하자 보수", desc="공동주택 관리비 인상"))
checks.append(("요약에서만 맞은 B 는 '(요약)' 표시", a is not None and "공동주택 관리비(요약)" in ranking.score_line(a)))
checks.append(("지사명은 '주택관리공단'과 함께일 때만 A", ranking.keyword_hits(art("국민건강보험공단 서울지사 개소"), r)["A"] == []
               and ranking.keyword_hits(art("주택관리공단 서울지사, 봉사"), r)["A"] != []))
# 저장된 옛 규칙(v1.0.0)에 갱신분 보태기
old = rules.normalize(None)
old.update(kw_a_branch_with="공단", exclude_media=["vietnam.vn", "내 매체"], complex_names=[],
           kw_s=[w for w in old["kw_s"] if w not in ("쪽방 주거상향", "임대주택 화재")] + ["쪽방", "에너지바우처"],
           kw_b=[k for k in old["kw_b"] if k not in ('"SH 임대주택"', "SH공사", "서울주택도시공사", "인천도시공사")]
           + ["SH 임대주택", "iH 주거복지", "노후 공공임대", "내 키워드"])
up = rules.upgrade(old, 1)
checks.append(("옛 규칙 갱신(직접 고친 것은 유지)", up["kw_a_branch_with"] == "주택관리공단" and "쪽방" not in up["kw_s"]
               and "임대주택 화재" in up["kw_s"] and "노후 공공임대" not in up["kw_b"] and '"SH 임대주택"' in up["kw_b"]
               and "인천도시공사" in up["kw_b"] and "내 키워드" in up["kw_b"] and "내 매체" in up["exclude_media"]
               and "SeattleN" in up["exclude_media"] and up["complex_names"] == r["complex_names"]
               and rules.upgrade(up, 1) == up and rules.upgrade(r, 1) == r))
txt = "답변입니다\n```json\n" + rules.to_json(dict(r, w_s=35)) + "\n```\n끝"
checks.append(("Claude 답변에서 규칙 꺼내기", rules.normalize(rules.from_text(txt))["w_s"] == 35))
for i, (name, ok) in enumerate(checks, 1):
    results.append(bool(ok))
    print(f"3-{i:<2} {'통과' if ok else '실패'} | {name}")

print("\n── 4부: 기발송 메일 백테스트(v1.0.3) ── (여러 매체·24시간 가점 없이, ±5)")
near = lambda a, x: a is not None and abs(a.score - x) <= 5
P4 = [
    ("숨져도 재산 늘어도 파악 불가…임대주택 부정 입주 심각", "테스트일보", lambda a: a and a.auto_category == "리스크" and a.score >= 45, "리스크, 50 이상"),
    ("세대 내 소방점검 믿을 수 없다 '75%'…원점에서 제도 재검토해야", "아파트관리신문", lambda a: near(a, 25), "전문지 후보, 25 안팎"),
    ("국토부 핵심 공기업 LH와 HUG, 청렴도 나란히 '4등급'", "테스트일보", lambda a: a and a.auto_category == "리스크" and a.score >= 45, "리스크, 50 이상"),
    ("17년 만에 다시 쪼개지는 LH…174조 부채·9000명 조직 어디로", "테스트일보", lambda a: a and a.auto_category in ("리스크", "모회사·부처") and a.score >= 40, "리스크/모회사·부처, 45 이상"),
    ("주거급여에 관리비 추가…취약계층 체납 비극 없도록", "테스트일보", lambda a: a and a.auto_category == "리스크" and a.score >= 55, "리스크, 60 이상"),
    ("충북지사-괴산시장 상인회, 상생협력 업무협약 체결", "테스트일보", lambda a: a and a.grade == "A?" and near(a, 20), "A?, 20, 추천 제외"),
    ("공공기관 경영공시 지적 5년간 5042건…1년전보다 11% 증가", "테스트일보", lambda a: a and a.auto_category in ("리스크", "공공기관 공통") and a.score >= 25, "리스크/공공기관 공통, 30 이상"),
    ("[단독] 공공주택 공급 속도전에 野 제동…'재산권 침해' 공방", "테스트일보", lambda a: a and a.auto_category == "업계·환경" and near(a, 15), "업계·환경, 15 안팎"),
    ("한강버스 리베이트 의혹 간부, 서울시 감사 중에도 SH 임원 '영전'", "테스트일보", lambda a: a is None or a.score <= 20, "후보 제외 또는 20 이하"),
]
day4 = []
for i, (t, src, check, want) in enumerate(P4, 1):
    a = judge(art(t, source=src))
    row(f"4-{i}", t, bool(check(a)), a, want)
    if a:
        day4.append(a)
best4 = ranking.pick_best(day4, r)
ok = not any(a.grade == "A?" for a in best4)
results.append(ok)
print(f"4-10 {'통과' if ok else '실패'} | 지사명만(A?)은 추천 안 함 — 추천: " + " / ".join(a.title[:12] for a in best4))
ok = rules.matches("부정입주", "임대주택 부정 입주 심각") and rules.matches("부정 입주", "부정입주 적발")
results.append(ok)
print(f"4-11 {'통과' if ok else '실패'} | 띄어쓰기 무시(부정입주 = 부정 입주)")

print("\nALL", "PASS" if all(results) else "FAIL", f"{sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
