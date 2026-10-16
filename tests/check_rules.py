"""선정 기준 검증 — 실제 기사 제목으로 점수·분류·추천이 기대대로 나오는지 (기본 규칙 기준).

기본 규칙(rules.DEFAULT_RULES)을 바꾸면 이 시험이 깨질 수 있다. 일부러 바꾼 것이면 기대값을 함께 고친다.
사용: python tests/check_rules.py   (저장소 맨 위 폴더에서)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import datetime as dt
import rules, ranking, dedup
from naver_api import Article
KST = dt.timezone(dt.timedelta(hours=9))
now = dt.datetime(2026, 10, 16, 14, 0, tzinfo=KST)
old = now - dt.timedelta(hours=30)   # 24시간 가점 없이(최악의 경우) 계산
r = rules.normalize(None)

def art(title, source="테스트일보", t=old, desc=""):
    return Article(title, "https://x/" + str(abs(hash(title))), "", source, t, desc, [])

def run(title, **k):
    a = art(title, **k)
    kh = ranking.keyword_hits(a, r)
    ok = bool(kh["A"] + kh["S"] + kh["B"])
    if ok:
        a.grade = "A" if kh["A"] else "S" if kh["S"] else "B"
        ranking.evaluate(a, r, now)
    return a, ok, kh

cases = [
 (1, "LH 빈집 늘자 '관리비 대납'만 올해 168억…5년 새 70% 급증", lambda a, ok: ok and a.auto_category == "리스크" and a.score >= 60, "리스크, 60점 이상"),
 (2, "8년 넘게 텅빈 익산 임대상가…LH, 사후관리 부실 도마", lambda a, ok: ok and a.auto_category == "리스크" and a.score >= 60, "리스크, 60점 이상"),
 (3, "영구임대주택 자살·고독사 236건…주거복지사 배치 '천차만별'", lambda a, ok: ok and a.auto_category in ("리스크", "기관 직접") and a.score >= 55, "리스크/기관 직접, 55점 이상"),
 (4, "국토부 산하기관 성비위 징계 41건…'조직 관리 실패'", lambda a, ok: ok and a.auto_category in ("공공기관 공통", "리스크") and 35 <= a.score <= 50, "공공기관 공통/리스크, 35~50점"),
 (5, "[단독] '소셜 믹스' 겉도는 통합공공임대…70% 중산층 배정도", lambda a, ok: ok and a.auto_category == "정책·제도" and a.score >= 35, "정책·제도, 35점 이상"),
 (6, "LH, AI 대전환 선포식…'주거 혁신 앞당길 것'", lambda a, ok: ok and a.auto_category == "모회사·부처" and 20 <= a.score <= 35, "모회사·부처, 20~35점"),
 (7, "박지효 송파구의원 '노후 빌라·다세대주택 주거환경 개선 지원해야'", lambda a, ok: not ok, "검증 실패로 빠짐"),
 (8, "파기될 뻔한 한강버스 수사의뢰서, '브로커와 뇌물 의혹' 담겼다", lambda a, ok: not ok, "후보에서 빠짐"),
 (9, "전통시장 화재 안전…'디지털 기술로 강화한다'", lambda a, ok: not ok, "후보에서 빠짐"),
 (10, "LH, 신길4 등 3개 지구 도심 공공복합사업 속도 낸다…", lambda a, ok: ok and a.auto_category == "모회사·부처" and a.score <= 10, "모회사·부처, 10점 이하"),
 (11, "전북특별자치도, 가정형 베란다 태양광 보급 확대 나선다", lambda a, ok: not ok, "후보에서 빠짐"),
 (12, "민요부터 요들송까지…분당하얀6단지에 찾아온 음악 선물", lambda a, ok: not ok, "검증 실패로 빠짐"),
]
results = []
for no, title, check, want in cases:
    a, ok, kh = run(title)
    passed = check(a, ok)
    results.append(passed)
    got = f"{a.score}점 · {a.auto_category}" if ok else "빠짐(검증 실패)"
    print(f"{no:>2} {'통과' if passed else '실패'} | {got:<16} | 기대: {want} | {title[:40]}")
    if ok:
        print("      근거:", ranking.score_line(a))

# 12-2: 단지명을 넣으면 S 로 잡힌다
r2 = dict(r); r2["complex_names"] = ["분당하얀6단지"]
a = art("민요부터 요들송까지…분당하얀6단지에 찾아온 음악 선물"); kh = ranking.keyword_hits(a, r2)
assert kh["S"] == ["분당하얀6단지"], kh
print("12-2 단지명 넣으면 S:", kh["S"])

# 10-2: 같은 사안 6건 → 1묶음
lh = ["LH, 신길4 등 3개 지구 도심 공공복합사업 속도 낸다…",
      "LH, 신길·녹번·송중 도심복합사업 본격 추진",
      "신길4구역 등 3곳 도심공공복합사업 사업계획 승인",
      "LH 도심복합사업 3곳 사업승인…5032가구 공급",
      "녹번역·송중동·신길4 도심복합 5032가구 공급 속도",
      "국토부·LH, 신길4·녹번 도심 공공주택 복합사업 3곳 승인"]
others = ["영구임대 고독사 대책 발표", "공동주택 관리비 공개 대상 확대", "주택관리공단 경남지사 산학협력 협약",
          "층간소음 분쟁 해마다 늘어", "승강기 안전 점검 강화", "LH 임대주택 하자 소송 패소", "주거급여 기준 인상",
          "행복주택 입주자 모집", "국토부 공공임대 재정비 계획", "LH 사장 국감 출석"]
pool = [art(t, t=now - dt.timedelta(hours=i)) for i, t in enumerate(lh)] + \
       [art(t, t=now - dt.timedelta(hours=i + 2)) for i, t in enumerate(others)]
for a in pool:
    a.keywords = ["LH"]
out = dedup.dedupe(pool, True, 0.85, rules.search_grades(r))
groups = [a for a in out if a.title in lh]
print(f"10-2 같은 사안 6건 → {len(groups)}묶음 (묶인 {sum(len(a.others) for a in groups)}건), 다른 기사 {len(out) - len(groups)}/{len(others)} 그대로")
results.append(len(groups) == 1 and len(out) - len(groups) == len(others))

# 13: 하루치 목록 → 추천 5건 구성
day = [art(t, t=now - dt.timedelta(hours=2)) for t, _, _ in [(c[1], 0, 0) for c in cases[:6]]]
day += [art("주택관리공단, 영구임대 단지 승강기 일제 점검", t=now - dt.timedelta(hours=3)),
        art("공공기관 경영평가 결과 발표…국토부 산하기관 등급 하락", t=now - dt.timedelta(hours=4)),
        art("LH 임대주택 하자 소송 잇따라", t=now - dt.timedelta(hours=5)),
        art("층간소음 분쟁 해마다 늘어", t=now - dt.timedelta(hours=6)),
        art("국토부, 공동주택관리법 시행령 개정…관리비 공개 대상 확대", t=now - dt.timedelta(hours=7))]
cand = []
for a in day:
    kh = ranking.keyword_hits(a, r)
    if kh["A"] + kh["S"] + kh["B"]:
        a.grade = "A" if kh["A"] else "S" if kh["S"] else "B"
        ranking.evaluate(a, r, now)
        cand.append(a)
best = ranking.pick_best(cand, r)
cats = [a.auto_category for a in best]
print("13 후보:"); [print("   ", a.score, a.auto_category, "★" if a in best else " ", a.title) for a in sorted(cand, key=lambda a: -a.score)]
from collections import Counter
c = Counter(cats)
ok13 = (c["리스크"] == 2 and c["기관 직접"] == 1 and c["정책·제도"] == 1
        and c["모회사·부처"] + c["공공기관 공통"] == 1 and len(best) == 5)
print("13", "통과" if ok13 else "실패", dict(c))
results.append(ok13)

# 매칭 규칙
assert rules.matches("군 관사", "육군 군관사 노후") and rules.matches("공동주택 관리비", "관리비 오른 공동주택")
assert not rules.matches("분양 -분양전환", "임대 분양전환 가격") and rules.matches("분양 -분양전환", "LH 분양 일정")
assert rules.google_query("공동주택 관리비", True) == '"공동주택" "관리비"' and rules.google_query("군 관사", True) == '"군 관사"'
assert rules.google_query("주택관리공단 OR 마이홈", True) == "주택관리공단 OR 마이홈"
# 규칙 파일·변경 이력
txt = "답변입니다\n```json\n" + rules.to_json(dict(r, w_s=35)) + "\n```\n끝"
new = rules.normalize(rules.from_text(txt)); assert new["w_s"] == 35
print("diff:", rules.diff(r, dict(new, kw_s=new["kw_s"] + ["관리사무소"])))
print("ALL", "PASS" if all(results) else "FAIL", f"{sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
