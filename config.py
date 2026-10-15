"""설정(config.json) 관리.

- 설정 파일은 exe(또는 app.py)와 같은 폴더에 생긴다.
- 네이버 Client ID/Secret 은 이 파일에만 저장되고 GitHub 에는 올라가지 않는다(.gitignore).
- source: 기사 출처. "google"(구글 뉴스, 키 불필요) 또는 "naver"(네이버, 키 필요).
- keywords_a(기관 직접, 무조건 후보) / keywords_b(정책·환경, 후보) 두 등급으로 나눈다.
  예전 "keywords" 는 두 목록을 합친 값으로 자동으로 맞춘다(하위 호환).
- extra_feeds: 전문지 RSS 주소 목록. 주소가 바뀌면 여기만 고친다.
"""

import json
import os
import sys

DEFAULT_CONFIG = {
    "source": "google",        # google | naver
    "client_id": "",
    "client_secret": "",
    "keywords_a": ["주택관리공단", "KOHOM", "주택관리공단 지사", "주택관리공단 사장"],
    "keywords_b": [
        "LH 임대주택", "LH 조직개편", "LH 노조", "LH 사장", "국토부 주거복지", "국토위 국정감사",
        "공공임대주택", "영구임대", "국민임대", "행복주택", "임대주택 부정입주", "임대주택 빈집",
        "주거급여", "주거복지사", "주거상향", "공동주택관리법", "공공주택특별법", "공동주택 관리비",
        "승강기 안전", "스프링클러 공동주택", "층간소음", "관리직원 폭언", "고독사", "돌봄통합법",
        "에너지바우처", "군 주거시설", "군 관사", "소규모 공동주택 안전점검", "중대재해처벌법 공공기관",
        "공공기관 경영평가", "공공기관 청렴도", "공공기관 채용비리", "공공기관 경영공시",
    ],
    "keywords": [],            # keywords_a + keywords_b (자동)
    "exclude_words": ["분양", "청약", "시세", "투자", "주식", "매매", "전세사기 피해지원 신청"],
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
    cfg.update(saved)
    cfg["keywords"] = all_keywords(cfg)
    return cfg


def all_keywords(cfg: dict) -> list[str]:
    """A 다음 B 순서로 합친 키워드 (중복 제거)."""
    return list(dict.fromkeys(cfg.get("keywords_a", []) + cfg.get("keywords_b", [])))


def save(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
