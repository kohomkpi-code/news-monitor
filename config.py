"""설정(config.json) 관리.

- 설정 파일은 exe(또는 app.py)와 같은 폴더에 생긴다.
- 네이버 Client ID/Secret 은 이 파일에만 저장되고 GitHub 에는 올라가지 않는다(.gitignore).
- source: 기사 출처. "google"(구글 뉴스, 키 불필요) 또는 "naver"(네이버, 키 필요).
- keywords_a(기관 직접, 무조건 후보) / keywords_b(정책·환경, 후보) 두 등급으로 나눈다.
  B 는 담당자가 수기로 검색하던 목록이고, 적힌 순서가 우선순위다(표 정렬·AI 요청문 순서).
  B 키워드로 찾은 기사라도 제목·요약에 A 키워드가 있으면 A 로 올린다.
  예전 "keywords" 는 두 목록을 합친 값으로 자동으로 맞춘다(하위 호환).
- extra_feeds: 전문지 RSS 주소 목록. 주소가 바뀌면 여기만 고친다.
- event_words: 단순 행사 기사를 거르는 단어(제목에 있으면 A 등급이라도 뺀다). [설정]에서 고친다.
"""

import json
import os
import sys

DEFAULT_CONFIG = {
    "source": "google",        # google | naver
    "client_id": "",
    "client_secret": "",
    "keywords_version": 2,     # 기본 키워드 목록이 바뀌면 올린다(옛 목록을 새 기본값으로 교체)
    "keywords_a": ["주택관리공단"],
    "keywords_b": [
        "주택관리", "LH", "한국토지주택공사", "공기업", "공공기관", "국토교통부", "국토교통위원회",
        "공정거래위원회", "동반성장", "국정감사", "경영평가", "주거복지", "SH공사", "도시공사",
        "기획재정부", "재정경제부", "기획예산처", "감사원", "거버넌스", "재정건전성", "부채비율",
        "영구임대", "임대아파트", "아파트 관리비", "취약계층", "임차인",
    ],
    "b_max_per_keyword": 50,   # B 키워드 하나당 최대 건수(구글이 주는 순서대로). A 는 제한 없음
    "keywords": [],            # keywords_a + keywords_b (자동)
    "exclude_words": ["분양", "청약", "시세", "투자", "주식", "매매", "전세사기 피해지원 신청"],
    "exclude_events": True,    # 단순 행사 기사 제외 (A 등급에도 적용)
    "event_words": [
        "축제", "성료", "성황", "한마당", "바자회", "김장", "나눔 행사", "나눔행사", "봉사활동", "봉사단",
        "잔치", "플리마켓", "벼룩시장", "발대식", "체육대회", "운동회", "음악회", "연탄", "송년",
    ],
    "use_feeds": True,         # 전문지 RSS 함께 조회
    "extra_feeds": [
        {"name": "아파트관리신문", "url": "https://www.aptn.co.kr/rss/allArticle.xml"},
        {"name": "한국아파트신문", "url": "https://www.hapt.co.kr/rss/allArticle.xml"},
        {"name": "전기신문", "url": "https://www.electimes.com/rss/allArticle.xml"},
    ],
    "days_back": 2,            # 기본 조회 기간: 최근 3일(연휴 뒤 누락 방지)
    "exclude_sent": True,      # 이미 보고한 기사 제외
    "merge_similar": True,     # 제목이 거의 같은 기사 묶기
    "similar_threshold": 0.85, # 유사 제목 판정 기준 (0~1)
    "report_title": "언론보도 모니터링(임원용)",
    "mail_subject": "({날짜})언론보도",  # {날짜} → 261015 (보고서를 연 날)
}


def app_dir() -> str:
    """exe 로 실행 중이면 exe 가 있는 폴더, 아니면 소스 파일이 있는 폴더."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(app_dir(), "config.json")


def load() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    saved: dict = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError):
            saved = {}  # 깨진 설정 파일은 기본값으로 대체
    if saved and "keywords_a" not in saved:
        # v0.3.0 이전 설정 파일: 키워드·제외어·기간·보고서 제목은 새 기본값을 쓰고
        # 출처·네이버 키·체크 옵션 같은 나머지는 그대로 살린다.
        for key in ("keywords", "exclude_words", "days_back", "report_title"):
            saved.pop(key, None)
    if saved and saved.get("keywords_version", 1) < DEFAULT_CONFIG["keywords_version"]:
        # 기본 키워드 목록이 바뀜(v0.5.0: 담당자 수기 검색 목록) → A·B 를 새 기본값으로
        for key in ("keywords_a", "keywords_b", "keywords", "keywords_version"):
            saved.pop(key, None)
    cfg.update(saved)
    cfg["keywords"] = all_keywords(cfg)
    return cfg


def all_keywords(cfg: dict) -> list[str]:
    """A 다음 B 순서로 합친 키워드 (중복 제거)."""
    return list(dict.fromkeys(cfg.get("keywords_a", []) + cfg.get("keywords_b", [])))


def save(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
