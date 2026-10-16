"""선정 규칙 — 무엇을 검색하고, 무엇을 빼고, 몇 점을 주고, 무엇을 추천할지.

v1.0 부터 규칙은 코드가 아니라 설정(config.json 의 "rules")에 있다. [선정 규칙] 탭에서 보고 고치며,
앱을 업데이트하지 않아도 다음 조회부터 바로 적용된다(환류 체계).
  결과 엑셀 내려받기 → Claude 에 '개선 요청문'과 함께 보냄 → Claude 가 돌려준 규칙(JSON)을
  [Claude 답변 붙여넣기]로 넣음 → 바뀐 점 미리보기 → 적용 → 변경 이력에 남음

키워드 3단:
- A 기관 직접: 제목에 있으면 무조건 후보(+50). 지사명은 같은 제목에 '공단'이 있을 때만 A.
- S 사업어: 공단 이름이 없어도 공단 업무를 가리키는 말(+30, 2개 이상 +40). 단지명도 S 로 본다.
- B 환경: 주거·공동주택 정책 환경(+10).
키워드 맞추기(matches): 띄어 쓴 말은 모두 들어 있으면 맞음(순서·띄어쓰기 무관).
  '공동주택 관리비' → '공동주택'과 '관리비'가 모두 있으면. 한 글자 낱말('군 관사')은 다음 낱말과 붙여 본다.
  구글식 "따옴표 문구", A OR B, -빼는말 도 그대로 쓸 수 있다.
"""

import copy
import datetime as dt
import json
import re

# ------------------------------------------------------------------ 기본 규칙 (v1.0.0)
DEFAULT_RULES = {
    # 검색 키워드
    "kw_a": ["주택관리공단", "KOHOM"],
    "kw_a_branch": ["서울지사", "인천지사", "경기남부지사", "경기북부지사", "강원지사", "충북지사", "대전충남지사",
                    "전북지사", "광주전남지사", "대구경북지사", "부산울산지사", "경남지사", "제주지사"],
    "kw_a_branch_with": "공단",
    "kw_s": ["영구임대", "국민임대", "행복주택", "공공임대주택", "공공임대 입주", "통합공공임대", "임대상가",
             "주거복지사", "주거상향", "쪽방", "고시원 주거", "관리비 대납", "공가", "빈집 임대", "임대주택 빈집",
             "입주자격", "부정입주", "임대료 체납", "임대주택 승계", "임대주택 상속", "임대주택 관리", "군 주거시설",
             "군 관사", "주한미군 시설", "소규모 공동주택 안전점검", "공동주택 안전점검", "에너지바우처",
             "장기수선충당금", "특별수선충당금", "혼합주택단지"],
    "complex_names": [],
    "kw_b": ["LH", "한국토지주택공사", "국토교통부 주거복지", "국토부 임대주택", "주거급여", "공동주택관리법",
             "공공주택특별법", "공동주택 관리비", "승강기 안전", "승강기 검사", "공동주택 화재", "스프링클러", "층간소음",
             "고독사", "돌봄통합", "노후 공공임대", "공공임대 재정비", "주택관리사", "주택관리업자", "공공기관 경영평가",
             "국토부 산하기관", "국감 LH", "공공기관 청렴도", "중대재해 공공기관", "지방공사 임대주택", "SH 임대주택",
             "iH 주거복지"],
    # 거르기
    "exact_search": True,       # 구글 뉴스에 따옴표(정확 검색)로 묻기
    "check_summary": True,      # S·B 는 요약까지 확인(A 는 제목만)
    "max_per_keyword": 30,      # A 를 뺀 키워드 하나당 최대 건수
    "exclude_words": ["분양", "청약", "시세", "투자", "주식", "매매", "전세사기 피해지원 신청"],
    "event_words": ["축제", "성료", "성황", "한마당", "바자회", "김장", "나눔 행사", "나눔행사", "봉사활동", "봉사단",
                    "잔치", "플리마켓", "벼룩시장", "발대식", "체육대회", "운동회", "음악회", "연탄", "송년"],
    "exclude_media": ["vietnam.vn", "laodong.vn", "voi.id", "cgtn.com", "unite.ai", "밴쿠버", "미주", "호주 톱뉴스",
                      "Calgary"],
    # 점수용 단어
    "parent_words": ["LH", "한국토지주택공사", "국토부", "국토교통부", "국토위"],
    "risk_words": ["사고", "화재", "붕괴", "누수", "사망", "숨져", "감사 -감사패 -감사장", "징계", "비위", "비리", "횡령", "소송",
                   "고발", "수사", "논란", "갑질", "폭언", "폭행", "부정", "체납", "공가", "빈집", "질타", "적발",
                   "위반", "솜방망이", "급증", "부실", "텅빈", "천차만별"],
    "policy_words": ["개정", "개정안", "입법예고", "시행", "시행령", "법안", "대책", "예산", "지침", "의무화",
                     "개편", "통과"],
    "policy_context": ["주거", "임대", "공동주택"],
    "dev_words": ["착공", "공급", "지구지정", "시공사", "도심복합", "공공복합", "재개발", "재건축", "분양 -분양전환",
                  "택지", "매입약정"],
    "specialist_press": ["아파트관리신문", "한국아파트신문", "대한경제", "한국주택경제신문"],
    "local_press": ["경남일보", "경남도민일보", "경남신문"],
    # 분류용 단어
    "cat_policy_words": ["주거급여", "공동주택관리법", "공공주택특별법", "승강기 검사", "스프링클러", "돌봄통합"],
    "cat_public_words": ["경영평가", "청렴도", "산하기관", "중대재해"],
    # 점수
    "w_a": 50, "w_s": 30, "w_s2": 40, "w_parent": 15, "w_b": 10, "w_risk": 20, "w_policy": 10,
    "w_multi_each": 2, "w_multi_max": 8, "w_specialist": 3, "w_local": 2, "w_recent": 3, "w_exclusive": 5,
    "w_dev": -15, "w_event_a": -20,
    # 추천
    "best_count": 5, "min_score": 30, "risk_first_max": 2, "a_min": 1, "per_category_max": 2,
}

# ------------------------------------------------------------------ 화면에 보일 이름·설명
# (키, 이름, 설명) — [선정 규칙] 탭과 엑셀 '규칙' 시트, 변경 이력이 같이 쓴다
LIST_FIELDS = {
    "kw_a": ("A 기관 직접", "제목에 있으면 무조건 후보"),
    "kw_a_branch": ("A 지사명", "같은 제목에 '공단'이 있을 때만 A"),
    "complex_names": ("단지명 (S로 봄)", "공단 단지 이름 · 비워 두면 안 씀"),
    "kw_s": ("S 사업어", "공단 이름 없이도 공단 업무를 가리키는 말"),
    "kw_b": ("B 환경", "주거·공동주택 정책 환경"),
    "exclude_words": ("제외어", "제목에 있으면 제외 · B에만(A·S는 예외)"),
    "event_words": ("단순 행사어", "A는 감점, 나머지는 제외"),
    "exclude_media": ("제외 매체", "매체명·주소에 들어 있으면 제외"),
    "parent_words": ("모회사·부처어", "LH·국토부 등"),
    "risk_words": ("리스크어", "A·S·모회사어와 함께 있을 때만 가점"),
    "policy_words": ("정책어", "S·모회사어·조건어와 함께 있을 때만 가점"),
    "policy_context": ("정책 조건어", "정책어 가점이 붙는 주제어"),
    "dev_words": ("공급·개발어", "S가 없으면 감점 · '-말'은 예외"),
    "specialist_press": ("전문지", "매체명에 들어 있으면 가점"),
    "local_press": ("본사 지역지", "A 기사일 때만 가점"),
    "cat_policy_words": ("분류: 정책·제도어", "법령·제도 이름"),
    "cat_public_words": ("분류: 공공기관 공통어", "경영평가·청렴도 등"),
}
NUMBER_FIELDS = {
    "w_a": ("A 기관 직접", "점"), "w_s": ("S 사업어 1개", "점"), "w_s2": ("S 사업어 2개 이상", "점"),
    "w_parent": ("모회사·부처어", "점"), "w_b": ("B 환경", "점"), "w_risk": ("리스크어", "점"),
    "w_policy": ("정책어", "점"), "w_multi_each": ("여러 매체 1건당", "점"), "w_multi_max": ("여러 매체 최대", "점"),
    "w_specialist": ("전문지", "점"), "w_local": ("본사 지역지", "점"), "w_recent": ("최근 24시간", "점"),
    "w_exclusive": ("[단독] 기사", "점"), "w_dev": ("공급·개발 (감점)", "점"), "w_event_a": ("A 행사 (감점)", "점"),
    "best_count": ("추천 건수", "건"), "min_score": ("추천 최소 점수", "점"), "risk_first_max": ("리스크 먼저 최대", "건"),
    "a_min": ("공단(A) 최소", "건"), "per_category_max": ("같은 분류 최대", "건"), "max_per_keyword": ("키워드당 최대", "건"),
}
FLAG_FIELDS = {
    "exact_search": "구글 뉴스 정확 검색 (따옴표로 묻기)",
    "check_summary": "S·B 키워드는 요약까지 확인 (A는 제목만)",
}
TEXT_FIELDS = {"kw_a_branch_with": ("지사명과 함께 있어야 하는 말", "")}
CATEGORIES = ["리스크", "기관 직접", "모회사·부처", "정책·제도", "공공기관 공통", "업계·환경"]

RULES_FORMAT = "kohom-newsroom-rules"


def normalize(saved: dict | None) -> dict:
    """저장된 규칙 + 기본값(빠진 항목). 형식이 틀린 값은 기본값으로."""
    r = copy.deepcopy(DEFAULT_RULES)
    for k, v in (saved or {}).items():
        if k not in DEFAULT_RULES:
            continue
        d = DEFAULT_RULES[k]
        if isinstance(d, bool):
            r[k] = bool(v)
        elif isinstance(d, int):
            try:
                r[k] = int(v)
            except (TypeError, ValueError):
                pass
        elif isinstance(d, list) and isinstance(v, list):
            r[k] = list(dict.fromkeys(str(x).strip() for x in v if str(x).strip()))
        elif isinstance(d, str) and isinstance(v, str):
            r[k] = v.strip()
    return r


# ------------------------------------------------------------------ 키워드 맞추기
_TOKEN_RE = re.compile(r'-?"[^"]+"|\S+')


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _parts(alt: str) -> tuple[list[str], list[str]]:
    """검색식 한 덩어리 → (있어야 할 말, 없어야 할 말). 한 글자 낱말은 다음 낱말과 붙인다."""
    must, must_not = [], []
    pending = ""
    for t in _TOKEN_RE.findall(alt):
        if t.startswith("-") and len(t) > 1:
            must_not.append(_squash(t[1:].strip('"')))
            continue
        w = _squash(t.strip('"'))
        if not w:
            continue
        if pending:
            w, pending = pending + w, ""
        if len(w) == 1 and not t.startswith('"'):
            pending = w
            continue
        must.append(w)
    if pending:
        must.append(pending)
    return must, must_not


def matches(keyword: str, text: str) -> bool:
    """키워드가 글에 맞는지. 대소문자·띄어쓰기는 가리지 않는다."""
    text = _squash(text)
    for alt in re.split(r"\s+OR\s+", keyword.strip()):
        must, must_not = _parts(alt)
        if must and all(m in text for m in must) and not any(n in text for n in must_not):
            return True
    return False


def hits(words: list[str], text: str) -> list[str]:
    return [w for w in words if matches(w, text)]


def google_query(keyword: str, exact: bool) -> str:
    """구글 뉴스에 물을 검색어. exact 면 낱말마다 따옴표('LH 임대' → '"LH" "임대"').
    이미 따옴표·OR·빼는말을 쓴 키워드는 그대로 둔다."""
    if not exact or '"' in keyword or " OR " in keyword or re.search(r"(^|\s)-\S", keyword):
        return keyword
    out, pending = [], ""
    for w in keyword.split():
        w = pending + (" " if pending else "") + w
        pending = ""
        if len(w) == 1:
            pending = w
            continue
        out.append(f'"{w}"')
    if pending:
        out.append(f'"{pending}"')
    return " ".join(out)


# ------------------------------------------------------------------ 검색 목록
def a_keywords(r: dict) -> list[str]:
    """A 키워드 + '공단 서울지사' 처럼 함께 있어야 하는 말을 붙인 지사명."""
    w = r.get("kw_a_branch_with", "").strip()
    return list(dict.fromkeys(r["kw_a"] + [f"{w} {b}" if w else b for b in r["kw_a_branch"]]))


def s_keywords(r: dict) -> list[str]:
    return list(dict.fromkeys(r["kw_s"] + r["complex_names"]))


def search_grades(r: dict) -> dict[str, str]:
    """검색할 키워드 → 등급(A/S/B), 이 순서대로 검색한다. 여러 등급에 있으면 높은 쪽."""
    grades: dict[str, str] = {}
    for g, words in (("A", a_keywords(r)), ("S", s_keywords(r)), ("B", r["kw_b"])):
        for k in words:
            grades.setdefault(k, g)
    return grades


# ------------------------------------------------------------------ 규칙 파일·변경 이력
def to_json(r: dict) -> str:
    return json.dumps({"format": RULES_FORMAT, "rules": r}, ensure_ascii=False, indent=1)


def from_text(text: str) -> dict:
    """규칙 파일 내용이나 Claude 답변(앞뒤에 글이 있어도 됨)에서 규칙을 꺼낸다. 못 찾으면 ValueError."""
    for m in re.finditer(r"\{", text):
        try:
            data, _ = json.JSONDecoder().raw_decode(text[m.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            body = data.get("rules", data)
            if isinstance(body, dict) and any(k in DEFAULT_RULES for k in body):
                return body
    raise ValueError("규칙(JSON)을 찾지 못했습니다.")


def label(key: str) -> str:
    for table in (LIST_FIELDS, NUMBER_FIELDS, TEXT_FIELDS):
        if key in table:
            return table[key][0]
    return FLAG_FIELDS.get(key, key)


def diff(old: dict, new: dict) -> list[str]:
    """바뀐 점을 사람이 읽을 문장으로. 예) 'S 사업어: +관리사무소 −쪽방', '추천 최소 점수: 30 → 25'."""
    out = []
    for k in DEFAULT_RULES:
        a, b = old.get(k), new.get(k)
        if a == b:
            continue
        if isinstance(DEFAULT_RULES[k], list):
            add = [x for x in b if x not in a]
            rem = [x for x in a if x not in b]
            bits = [f"+{x}" for x in add] + [f"−{x}" for x in rem]
            out.append(f"{label(k)}: " + (" ".join(bits) if bits else "순서 바뀜"))
        elif isinstance(DEFAULT_RULES[k], bool):
            out.append(f"{label(k)}: {'켬' if b else '끔'}")
        else:
            out.append(f"{label(k)}: {a} → {b}")
    return out


def log_entry(changes: list[str], how: str, when: dt.datetime) -> dict:
    return {"at": when.strftime("%Y-%m-%d %H:%M"), "how": how, "changes": changes}
