"""매뉴얼 화면용 시연 기사 — 실제 기사가 아니다(실존 인물·특정 기관 비판 기사는 넣지 않는다).

등급(A·S·B·전문지·A?)·리스크·공고·같은 사안 묶음·빠지는 기사(제외 매체·제목 검증 실패·단순 행사)가
골고루 나오게 짰다. 조회 시각 기준 몇 시간 전 기사로 만든다.
"""

import datetime as dt

from naver_api import Article

K = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(K)

# (제목, 매체, 몇 시간 전)
GOOGLE = [
    ("주택관리공단, 영구임대단지 승강기 일제 점검 나서", "서울일보", 3),
    ("주택관리공단 임대주택 빈집 늘어…관리비 부담 커져", "연합뉴스", 5),
    ("주택관리공단 임대주택 빈집 증가…관리비 부담 가중", "뉴스1", 6),
    ("주택관리공단 경남지사, 지역 대학과 주거복지 협약", "경남도민일보", 9),
    ("주택관리공단, 청렴도 평가 2등급…한 단계 올라", "뉴시스", 7),
    ("LH 전세임대 석 달 넘게 임대료 체납 급증", "뉴스1", 4),
    ("영구임대주택 고독사 잇따라…주거복지사 배치 태부족", "한국일보", 6),
    ("공공임대 노후 단지 재정비…국토부 개정안 입법예고", "아주경제", 8),
    ("통합공공임대 입주자 모집…다음 달 접수", "지역신문", 2),
    ("LH 노사 교섭 결렬…조직 개편 논의 이어가", "한국경제", 6),
    ("국토부 산하기관 성비위 징계 잇따라", "뉴스핌", 10),
    ("공공기관 경영평가 결과 발표 앞두고 기관들 긴장", "머니투데이", 12),
    ("아파트 승강기 고장 잦아…교체 비용 부담", "서울신문", 11),
    ("충북지사, 지역 상인회와 상생협력 협약", "충청일보", 5),
    ("Housing market weekly update", "Vietnam.vn", 4),
    ("전통시장 화재 안전 점검 강화", "지역방송", 3),
    ("○○동 주민 한마당 축제 성료…임대주택 입주민 참여", "동네신문", 8),
]
FEEDS = [
    ("세대 내 소방점검, 입주민 참여율 저조", "아파트관리신문", 8),
    ("관리사무소 직원 휴게시설 개선 시급", "한국아파트신문", 9),
]

# 지난 보고 기록(보고 기록 탭이 비어 보이지 않게)
_day = lambda n: (NOW - dt.timedelta(days=n)).date().isoformat()
SENT_BEFORE = {
    f"https://demo.example/old/{i}": {"date": d, "time": "09:3" + str(i % 10), "title": t, "source": s,
                                      "url": f"https://demo.example/old/{i}", "main": f"https://demo.example/old/{i}"}
    for i, (d, t, s) in enumerate([
        (_day(3), "공공임대 관리비 공개 대상 확대", "아파트관리신문"),
        (_day(3), "주택관리공단, 취약계층 겨울나기 지원", "연합뉴스"),
        (_day(4), "LH 매입임대 공실 대책 마련", "뉴스1"),
        (_day(4), "공동주택 화재 안전 기준 강화", "서울신문"),
        (_day(5), "영구임대 단지 승강기 교체 사업 착수", "한국일보"),
    ])
}


def _art(title, source, hours, i):
    return Article(title, f"https://news.google.com/rss/articles/DEMO{i:03d}", "", source,
                   NOW - dt.timedelta(hours=hours), "", [])


def fake_search(keyword, start_date, end_date, split=True, query=None):
    """'주택관리공단'을 물을 때 시연 기사를 한꺼번에 준다(나머지 키워드는 0건). 앱이 제목으로 다시 확인해 등급을 매긴다."""
    if keyword != "주택관리공단":
        return []
    return [Article(**{**_art(t, s, h, i).__dict__, "keywords": [keyword]}) for i, (t, s, h) in enumerate(GOOGLE)]


def fake_feeds(feeds, grades, start_date, end_date, free=None):
    return [Article(t, f"https://www.aptn.co.kr/news/DEMO{i}", "", s, NOW - dt.timedelta(hours=h), "", [], "전문지")
            for i, (t, s, h) in enumerate(FEEDS)], []


def real_link(url):
    return url.replace("news.google.com/rss/articles", "www.demo-news.kr/article")


INSIGHT = {
    "리스크": "공단 관리 단지와 직결 — 사실관계 확인 후 대응 자료 준비",
    "기관 직접": "공단 활동 보도 — 홍보 자료로 활용",
    "정책·제도": "제도 변경 예정 — 관련 부서 공유",
    "모회사·부처": "모회사 동향 — 영향 검토",
    "공공기관 공통": "경영평가·청렴도 관련 — 대응 일정 확인",
}


def ai_answer(arts, request_map):
    """Claude 답변 흉내: 점수 높은 기사 5건을 '#선정 / 번호|분류|인사이트' 형식으로."""
    cand = sorted(((no, arts[iid]) for no, iid in request_map.items()), key=lambda x: -x[1].score)[:5]
    lines = ["오늘 후보를 판단 기준서에 따라 검토했습니다.", "", "#선정"]
    for no, a in cand:
        cat = a.auto_category if a.auto_category in INSIGHT else "기관 직접"
        lines.append(f"{no}|{cat}|{INSIGHT[cat]}")
    return "\n".join(lines)
