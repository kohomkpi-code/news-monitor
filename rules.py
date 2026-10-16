"""선정 규칙 — 무엇을 검색하고, 무엇을 빼고, 몇 점을 주고, 무엇을 추천할지.

v1.0 부터 규칙은 코드가 아니라 설정(config.json 의 "rules")에 있다. [선정 규칙] 탭에서 보고 고치며,
앱을 업데이트하지 않아도 다음 조회부터 바로 적용된다(환류 체계).
  결과 엑셀 내려받기 → Claude 에 '개선 요청문'과 함께 보냄 → Claude 가 돌려준 규칙(JSON)을
  [Claude 답변 붙여넣기]로 넣음 → 바뀐 점 미리보기 → 적용 → 변경 이력에 남음

키워드 3단:
- A 기관 직접: 제목에 있으면 무조건 후보(+50). 지사명은 같은 제목에 '공단'이 있을 때만 A.
- S 사업어: 공단 이름이 없어도 공단 업무를 가리키는 말(+30, 2개 이상 +40). 단지명도 S 로 본다.
- B 환경: 주거·공동주택 정책 환경(+10).
키워드 맞추기(matches): 띄어 쓴 말은 같은 순서로, 낱말 사이 20자 이내에 있으면 맞음(띄어쓰기 무관).
  '공동주택 관리비' → '공동주택 … 관리비'. 한 글자 낱말('군 관사')은 다음 낱말과 붙여 본다.
  구글식 "따옴표 문구", A OR B, -빼는말 도 그대로 쓸 수 있다.
"""

import copy
import datetime as dt
import json
import re
from urllib.parse import urlparse

# 기발송 메일 76건 백테스트(10-16)로 보탠 말 — 저장된 규칙에도 upgrade 로 보탠다
B_ADD_V4 = ["공공기관 경영공시", "공공기관 채용비리", "외부강의", "공공기관 개인정보", "이전 공공기관", "공공기관 지방이전",
            "공공기관 AI", "국토부 장관", "국토부 인사", "LH 조직", "LH 분리", "LH 개편", "LH 개혁", "LH 노사", "LH 노조",
            "LH 인사", "LH 사장", "LH 이사", "LH 인력", "청렴도", "공공주택 정책", "공공주택 공급", "임대주택 리츠",
            "노인복지주택", "주거 돌봄", "서비스 주택", "공동주택 AI", "집합건물 관리비", "관리비 회계", "전기차 충전시설",
            "그린리모델링", "아파트 승강기", "아파트 엘리베이터", "소방점검", "아파트 소방", "아파트 분리수거",
            "어린이놀이시설", "공동주택 책임보험"]
RISK_ADD_V4 = ["청렴도", "경영공시", "채용비리", "외부강의", "기강해이", "복무위반", "근무태만", "태부족", "갈등", "제자리",
               "쪼개지는", "빈손"]

# ------------------------------------------------------------------ 기본 규칙 (v1.0.3)
DEFAULT_RULES = {
    # 검색 키워드
    "kw_a": ["주택관리공단", "KOHOM"],
    "kw_a_branch": ["서울지사", "인천지사", "경기남부지사", "경기북부지사", "강원지사", "충북지사", "대전충남지사",
                    "전북지사", "광주전남지사", "대구경북지사", "부산울산지사", "경남지사", "제주지사"],
    "kw_a_branch_with": "주택관리공단",  # '공단'만으로는 국민건강보험공단 서울지사 등도 걸린다
    "kw_s": ["영구임대", "국민임대", "행복주택", "공공임대주택", "공공임대 입주", "통합공공임대", "임대상가",
             "주거복지사", "주거상향", "고시원 주거", "관리비 대납", "공가", "빈집 임대", "임대주택 빈집",
             "입주자격", "부정입주", "임대료 체납", "임대주택 승계", "임대주택 상속", "군 주거시설",
             "군 관사", "주한미군 시설", "소규모 공동주택 안전점검", "공동주택 안전점검",
             "장기수선충당금", "특별수선충당금", "혼합주택단지", "쪽방 주거상향", "쪽방촌 주거", "노후 공공임대",
             "공공임대 재정비", "임대주택 노후", "임대주택 안전", "임대주택 화재", "임대주택 승강기", "관리비 체납",
             "임대주택 관리비", "임대주택 입주민", "영구임대상가", "공공임대 관리", "주거급여", "임대주택 부정",
             "임대주택 받은", "임대주택 입주자", "공공임대 입주민"],
    "complex_names": ["분당하얀6단지", "번동3단지", "아산읍내단지", "하얀마을6단지", "월평2동 임대"],
    "kw_b": ["LH", "한국토지주택공사", "국토교통부 주거복지", "국토부 임대주택", "공동주택관리법",
             "공공주택특별법", "공동주택 관리비", "승강기 안전", "승강기 검사", "공동주택 화재", "스프링클러", "층간소음",
             "고독사", "돌봄통합", "주택관리사", "주택관리업자", "공공기관 경영평가",
             "국토부 산하기관", "국감 LH", "공공기관 청렴도", "중대재해 공공기관", "지방공사 임대주택", '"SH 임대주택"',
             "SH공사", "서울주택도시공사", "인천도시공사", "에너지바우처", "전세임대", "매입임대", "임대주택 고독사",
             "아파트 관리소장", *B_ADD_V4],
    # 거르기
    "exact_search": True,       # 구글 뉴스에 따옴표(정확 검색)로 묻기
    "check_summary": True,      # B 는 요약까지 확인
    "check_summary_s": False,   # S 는 제목만(요약에서 맞으면 오탐이 많았다)
    "max_per_keyword": 30,      # A 를 뺀 키워드 하나당 최대 건수
    "exclude_words": ["분양", "청약", "시세", "투자", "주식", "매매", "전세사기 피해지원 신청"],
    "event_words": ["축제", "성료", "성황", "한마당", "바자회", "김장", "나눔 행사", "나눔행사", "봉사활동", "봉사단",
                    "잔치", "플리마켓", "벼룩시장", "발대식", "체육대회", "운동회", "음악회", "연탄", "송년"],
    "exclude_media": ["vietnam.vn", "laodong.vn", "voi.id", "cgtn.com", "unite.ai", "밴쿠버", "미주", "호주 톱뉴스",
                      "Calgary", "SeattleN", "시애틀", "애틀랜타", "뉴욕", "LA", "토론토", "호주", "시카고", "한인"],
    # 점수용 단어
    "parent_words": ["LH", "한국토지주택공사", "국토부", "국토교통부", "국토위"],
    "risk_words": ["사고", "화재", "붕괴", "누수", "사망", "숨져", "감사 -감사패 -감사장", "징계", "비위", "비리", "횡령", "소송",
                   "고발", "수사", "논란", "갑질", "폭언", "폭행", "부정", "체납", "공가", "빈집", "질타", "적발",
                   "위반", "솜방망이", "급증", "부실", "텅빈", "천차만별", "증가", "미달", "없어", "불편",
                   "취약 -취약계층", *RISK_ADD_V4],
    "risk_context_extra": ["임대주택", "공공임대", "공동주택", "입주민", "관리사무소"],
    "policy_words": ["개정", "개정안", "입법예고", "시행", "시행령", "법안", "대책", "예산", "지침", "의무화",
                     "개편", "통과"],
    "policy_context": ["주거", "임대", "공동주택"],
    "dev_words": ["착공", "공급", "지구지정", "시공사", "도심복합", "공공복합", "재개발", "재건축", "분양 -분양전환",
                  "택지", "매입약정"],
    "routine_words": ["모집", "접수", "공고 -공고히", "정정", "안내", "예방접종", "공모", "단신", "센터]", "동향]",
                      "모집 공고", "입주자 모집", "현장접수"],
    "specialist_press": ["아파트관리신문", "한국아파트신문", "전기신문", "대한경제", "한국주택경제신문"],
    "specialist_free_press": ["아파트관리신문", "한국아파트신문", "전기신문"],  # 키워드 없이도 후보(실무 기사)
    "local_press": ["경남일보", "경남도민일보", "경남신문"],
    # 분류
    "category_order": ["리스크", "기관 직접", "정책·제도", "모회사·부처", "공공기관 공통", "업계·환경"],
    "cat_policy_words": ["주거급여", "공동주택관리법", "공공주택특별법", "승강기 검사", "스프링클러", "돌봄통합"],
    "cat_public_words": ["경영평가", "청렴도", "산하기관", "중대재해"],
    # 점수
    "w_a": 50, "w_s": 30, "w_s2": 40, "w_parent": 20, "w_b": 10, "w_risk": 20, "w_policy": 10,
    "w_multi_each": 2, "w_multi_max": 8, "w_specialist": 3, "w_local": 2, "w_recent": 3, "w_exclusive": 5,
    "w_dev": -15, "w_event_a": -20, "w_routine": -25, "w_specialist_base": 15, "w_branch_only": 20,
    # 추천
    "best_count": 5, "min_score": 30, "risk_first_max": 2, "a_min": 1, "per_category_max": 2, "industry_max": 1,
}

# ------------------------------------------------------------------ 화면에 보일 이름·설명
# (키, 이름, 설명) — [선정 규칙] 탭과 엑셀 '규칙' 시트, 변경 이력이 같이 쓴다
LIST_FIELDS = {
    "kw_a": ("A 기관 직접", "제목에 있으면 무조건 후보"),
    "kw_a_branch": ("A 지사명", "아래 '함께 있어야 하는 말'과 같은 제목에 있을 때만 A"),
    "complex_names": ("단지명 (S로 봄)", "언론에 자주 나오는 우리 단지명을 넣으세요"),
    "specialist_free_press": ("키워드 면제 전문지", "이 매체 기사는 키워드 없이도 후보"),
    "kw_s": ("S 사업어", "공단 업무를 가리키는 말 · 제목만 확인"),
    "kw_b": ("B 환경", "주거·공동주택 정책 환경"),
    "exclude_words": ("제외어", "제목에 있으면 제외 · B에만(A·S는 예외)"),
    "event_words": ("단순 행사어", "A는 감점, 나머지는 제외"),
    "exclude_media": ("제외 매체", "매체명(영문은 낱말로)·주소에 있으면 제외"),
    "parent_words": ("모회사·부처어", "LH·국토부 등"),
    "risk_words": ("리스크어", "아래 리스크 조건어 등과 함께일 때만 가점"),
    "risk_context_extra": ("리스크 조건어", "A·S·모회사어·B 외에 리스크 가점을 여는 말"),
    "policy_words": ("정책어", "S·모회사어·조건어와 함께일 때"),
    "policy_context": ("정책 조건어", "정책어 가점을 여는 말"),
    "dev_words": ("공급·개발어", "S 없으면 감점 · -말은 예외"),
    "routine_words": ("일상 공고어", "A가 아니면 감점"),
    "specialist_press": ("전문지", "매체명에 들어 있으면 가점"),
    "local_press": ("본사 지역지", "A 기사일 때만 가점"),
    "category_order": ("분류 순서", "위에서부터 처음 맞는 분류 · 이름은 그대로"),
    "cat_policy_words": ("분류: 정책·제도어", "법령·제도 이름"),
    "cat_public_words": ("분류: 공공기관 공통어", "경영평가·청렴도 등"),
}
NUMBER_FIELDS = {
    "w_a": ("A 기관 직접", "점"), "w_s": ("S 사업어 1개", "점"), "w_s2": ("S 사업어 2개 이상", "점"),
    "w_parent": ("모회사·부처어", "점"), "w_b": ("B 환경", "점"), "w_risk": ("리스크어", "점"),
    "w_policy": ("정책어", "점"), "w_multi_each": ("여러 매체 1건당", "점"), "w_multi_max": ("여러 매체 최대", "점"),
    "w_specialist": ("전문지", "점"), "w_local": ("본사 지역지", "점"), "w_recent": ("최근 24시간", "점"),
    "w_exclusive": ("[단독] 기사", "점"), "w_dev": ("공급·개발 (감점)", "점"), "w_event_a": ("A 행사 (감점)", "점"),
    "w_routine": ("일상 공고 (감점)", "점"), "w_specialist_base": ("면제 전문지 기본", "점"),
    "w_branch_only": ("지사명만 (A?)", "점"),
    "best_count": ("추천 건수", "건"), "min_score": ("추천 최소 점수", "점"), "risk_first_max": ("리스크 먼저 최대", "건"),
    "a_min": ("공단(A) 최소", "건"), "per_category_max": ("같은 분류 최대", "건"), "industry_max": ("업계·환경 최대", "건"),
    "max_per_keyword": ("키워드당 최대", "건"),
}
FLAG_FIELDS = {
    "exact_search": "구글 뉴스 정확 검색 (따옴표로 묻기)",
    "check_summary": "B 키워드는 요약까지 확인",
    "check_summary_s": "S 사업어도 요약까지 확인 (끄면 제목만)",
}
TEXT_FIELDS = {"kw_a_branch_with": ("지사명과 함께 있어야 하는 말", "")}
CATEGORIES = ["리스크", "기관 직접", "모회사·부처", "정책·제도", "공공기관 공통", "업계·환경"]

RULES_FORMAT = "kohom-newsroom-rules"
RULES_VERSION = 4  # 기본 규칙을 고쳐 이미 저장된 규칙에도 보태야 할 때 올린다(upgrade)


def upgrade(r: dict, from_version: int) -> dict:
    """저장된 규칙에 새 버전의 기본 규칙 수정분을 보탠다(사용자가 고친 것은 그대로).
    v2(1.0.1): 해외 한인 매체 제외 추가, 짧은 약칭 SH·iH 를 기관 이름으로(‘Sh수협은행’이 걸려서).
    v3(1.0.2): 14:54 조회 검토 — S 오탐 정리·안전 기사 S 추가, B 보강, 리스크어 추가, 단지명, 지사명은 '주택관리공단'과 함께.
    새 항목(일상 공고어·리스크 조건어·분류 순서 등)은 normalize 가 기본값으로 채운다."""
    r = copy.deepcopy(r)

    def add(key: str, words: list[str]):
        r[key] += [w for w in words if w not in r[key]]

    if from_version < 2:
        swap = {"SH 임대주택": ["SH공사 임대주택", "서울주택도시공사 임대주택"], "SH": ["SH공사", "서울주택도시공사"],
                "iH 주거복지": ["인천도시공사 주거복지"], "iH": ["인천도시공사"]}
        r["kw_b"] = list(dict.fromkeys(x for k in r["kw_b"] for x in swap.get(k, [k])))
        r["exclude_media"] += [m for m in ["SeattleN", "시애틀", "애틀랜타", "뉴욕", "LA", "토론토", "호주", "시카고", "한인"]
                               if m not in r["exclude_media"]]
    if from_version < 3:
        if r["kw_a_branch_with"] == "공단":
            r["kw_a_branch_with"] = "주택관리공단"
        r["kw_s"] = [w for w in r["kw_s"] if w not in ("쪽방", "에너지바우처", "임대주택 관리")]
        add("kw_s", ["쪽방 주거상향", "쪽방촌 주거", "노후 공공임대", "공공임대 재정비", "임대주택 노후", "임대주택 안전",
                     "임대주택 화재", "임대주택 승강기", "관리비 체납", "임대주택 관리비", "임대주택 입주민", "영구임대상가",
                     "공공임대 관리"])
        add("complex_names", DEFAULT_RULES["complex_names"])
        swap = {"SH공사 임대주택": ['"SH 임대주택"', "SH공사"], "SH 임대주택": ['"SH 임대주택"'], "서울주택도시공사 임대주택": ["서울주택도시공사"],
                "인천도시공사 주거복지": ["인천도시공사"], "SH": ["SH공사", "서울주택도시공사"], "iH": ["인천도시공사"],
                "iH 주거복지": ["인천도시공사"], "노후 공공임대": [], "공공임대 재정비": []}  # 뒤의 둘은 S 로 옮김
        r["kw_b"] = list(dict.fromkeys(x for k in r["kw_b"] for x in swap.get(k, [k])))
        add("kw_b", ["에너지바우처", "전세임대", "매입임대", "임대주택 고독사", "아파트 관리소장"])
        add("risk_words", ["증가", "미달", "없어", "불편", "취약 -취약계층"])
        add("specialist_press", ["전기신문"])
    if from_version < 4:
        # 기발송 메일 76건 백테스트 — 주거급여는 B → S, 모회사어 15 → 20(기본값 그대로 쓰던 경우만), 공고 감점 −20 → −25
        r["kw_b"] = [w for w in r["kw_b"] if w != "주거급여"]
        add("kw_s", ["주거급여", "임대주택 부정", "임대주택 받은", "임대주택 입주자", "공공임대 입주민", "영구임대상가"])
        add("kw_b", B_ADD_V4)
        add("risk_words", RISK_ADD_V4)
        if r["w_parent"] == 15:
            r["w_parent"] = 20
        if r["w_routine"] == -20:
            r["w_routine"] = -25
    return r


def media_hit(entries: list[str], source: str, link: str) -> str | None:
    """제외 매체 목록에 걸리면 그 말. 주소 꼴('vietnam.vn')은 매체명·주소에서,
    영문('LA')은 매체명에서 낱말로만(‘Platum’의 la 는 아님), 한글은 매체명 안에 들어 있으면."""
    src = (source or "").lower()
    host = urlparse(link or "").netloc.lower()
    for m in entries:
        ml = m.lower().strip()
        if not ml:
            continue
        if "." in ml:
            if ml in host or ml in src:
                return m
        elif re.fullmatch(r"[a-z0-9 ]+", ml):
            if re.search(rf"(?<![a-z]){re.escape(ml)}(?![a-z])", src):
                return m
        elif ml in src:
            return m
    return None


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
    # 분류 순서: 아는 이름만, 빠진 분류는 기본 순서대로 뒤에
    order = [c for c in r["category_order"] if c in CATEGORIES]
    r["category_order"] = order + [c for c in DEFAULT_RULES["category_order"] if c not in order]
    return r


# ------------------------------------------------------------------ 키워드 맞추기
_TOKEN_RE = re.compile(r'-?"[^"]+"|\S+')
MAX_GAP = 20  # 여러 낱말 키워드: 앞 낱말이 끝난 뒤 이 글자 수(띄어쓰기 포함) 안에 다음 낱말이 있어야 맞음


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


def _squash_map(text: str) -> tuple[str, list[int]]:
    """띄어쓰기를 빼고 소문자로 바꾼 글 + 글자마다 원래 글에서의 위치."""
    out, idx = [], []
    for i, ch in enumerate(text):
        if ch.isspace():
            continue
        for c in ch.lower():
            out.append(c)
            idx.append(i)
    return "".join(out), idx


def _in_order(s: str, idx: list[int], parts: list[str]) -> tuple[int, int] | None:
    """parts 가 이 순서로, 앞 낱말 끝에서 MAX_GAP 글자(원래 글 기준, 띄어쓰기 포함) 안에 다음 낱말이 있는
    첫 구간 (시작, 끝) — s 는 띄어쓰기를 뺀 글, idx 는 s 의 글자마다 원래 글에서의 위치."""
    pos = s.find(parts[0])
    while pos != -1:
        end, ok = pos + len(parts[0]), True
        for p in parts[1:]:
            nxt = s.find(p, end)
            if nxt == -1 or idx[nxt] - idx[end - 1] - 1 > MAX_GAP:
                ok = False
                break
            end = nxt + len(p)
        if ok:
            return pos, end
        pos = s.find(parts[0], pos + 1)
    return None


def match_span(keyword: str, text: str) -> str | None:
    """키워드가 글에 맞으면 맞은 구간(원래 글 그대로), 아니면 None.
    여러 낱말 키워드는 같은 순서로, 낱말 사이가 MAX_GAP 글자 이내일 때만 맞음
    ('임대주택 노후'는 '노후 기업 사택 활용해 임대주택'에 안 맞음). 대소문자·띄어쓰기는 가리지 않는다."""
    s, idx = _squash_map(text)
    for alt in re.split(r"\s+OR\s+", keyword.strip()):
        must, must_not = _parts(alt)
        if not must or any(n in s for n in must_not):
            continue
        found = _in_order(s, idx, must)
        if found:
            b, e = found
            return text[idx[b]: idx[e - 1] + 1]
    return None


def matches(keyword: str, text: str) -> bool:
    return match_span(keyword, text) is not None


def spans(words: list[str], text: str) -> dict[str, str]:
    """걸린 말 → 맞은 구간 (점수 근거에 보여 줄 것)."""
    out = {}
    for w in words:
        sp = match_span(w, text)
        if sp is not None:
            out[w] = sp
    return out


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
