"""설정(config.json) 관리.

- 설정 파일은 exe(또는 app.py)와 같은 폴더에 생긴다.
- 네이버 Client ID/Secret 은 이 파일에만 저장되고 GitHub 에는 올라가지 않는다(.gitignore).
- source: 기사 출처. "google"(구글 뉴스, 키 불필요) 또는 "naver"(네이버, 키 필요).
- rules: 선정 규칙(키워드 A·S·B, 제외어, 점수, 추천 …). 기본값과 설명은 rules.py, [선정 규칙] 탭에서 고친다.
  rules_log: 규칙을 바꾼 이력(언제, 어떻게, 무엇을). "keywords" 는 검색 키워드 전체(A→S→B, 자동).
- v1.0.0 에서 예전 키워드(keywords_a/b)·제외어·행사 단어·추천 건수를 rules 로 옮겼다.
  키워드는 새 3단 기본값으로 바꾸고, 예전 A·B 목록은 keywords_backup_v2 에 남겨 둔다.
- extra_feeds: 추가 RSS 매체 [{"name", "url", "on"}]. [설정] 탭 → [전문지 고르기]에서 고친다.
"""

import json
import os
import sys

import rules
from calendar_kr import DEFAULT_HOLIDAYS

DEFAULT_CONFIG = {
    "source": "google",        # google | naver
    "client_id": "",
    "client_secret": "",
    "keywords_version": 3,     # 기본 키워드 체계가 바뀌면 올린다(v1.0.0: A·S·B 3단 → rules)
    "feeds_version": 2,        # 기본 전문지 목록이 바뀌면 올린다(v0.9.2: 전기신문 제외)
    "rules": rules.DEFAULT_RULES,
    "rules_log": [],
    "keywords": [],            # 검색 키워드 전체 A→S→B (자동)
    "exclude_events": True,    # 단순 행사 기사 제외 (A 는 빼지 않고 감점)
    "use_feeds": True,         # 전문지 RSS 함께 조회
    "extra_feeds": [
        {"name": "아파트관리신문", "url": "https://www.aptn.co.kr/rss/allArticle.xml", "on": True},
        {"name": "한국아파트신문", "url": "https://www.hapt.co.kr/rss/allArticle.xml", "on": True},
    ],
    "days_back": 2,            # (v0.6 부터 안 씀: 조회 기간은 '직전 영업일 9시~'로 자동)
    "holidays": DEFAULT_HOLIDAYS,  # 공휴일 — 자동 조회 기간 계산용([설정] 탭에서 수정)
    "last_tab": "basic",       # 마지막으로 본 탭
    "last_search_at": "",      # 마지막 조회 시각
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
    if saved and saved.get("keywords_version", 1) < 2:
        # v0.5.0: 담당자 수기 검색 목록으로 바뀜 → 그 전 A·B 는 버린다
        for key in ("keywords_a", "keywords_b", "keywords"):
            saved.pop(key, None)
    if saved and "rules" not in saved:
        # v1.0.0: 규칙을 rules 로 모음. 키워드는 새 3단 기본값, 제외어·행사 단어·추천 건수는 쓰던 값을 옮긴다.
        r = rules.normalize(None)
        for old, new in (("exclude_words", "exclude_words"), ("event_words", "event_words"), ("best_count", "best_count")):
            if old in saved:
                r[new] = saved[old]
        if saved.get("keywords_a") or saved.get("keywords_b"):
            saved["keywords_backup_v2"] = {"A": saved.get("keywords_a", []), "B": saved.get("keywords_b", [])}
        saved["rules"] = r
    for key in ("keywords_a", "keywords_b", "exclude_words", "event_words", "best_count", "b_max_per_keyword",
                "keywords_collapsed"):
        saved.pop(key, None)
    if saved:
        saved["keywords_version"] = DEFAULT_CONFIG["keywords_version"]
    if saved and saved.get("feeds_version", 1) < 2:
        # v0.9.2: 전기신문을 기본 전문지에서 뺌 — 저장된 목록에서도 뺀다(직접 추가한 매체는 그대로)
        saved["extra_feeds"] = [f for f in saved.get("extra_feeds", []) if "electimes.com" not in f.get("url", "")]
        saved["feeds_version"] = DEFAULT_CONFIG["feeds_version"]
    cfg.update(saved)
    cfg["rules"] = rules.normalize(cfg.get("rules"))
    cfg["keywords"] = all_keywords(cfg)
    return cfg


def all_keywords(cfg: dict) -> list[str]:
    """검색 키워드 전체: A(지사명 포함) → S → B 순서."""
    return list(rules.search_grades(cfg["rules"]))


def save(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
