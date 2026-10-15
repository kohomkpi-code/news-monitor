"""설정(config.json) 관리.

- 설정 파일은 exe(또는 app.py)와 같은 폴더에 생긴다.
- 네이버 Client ID/Secret 은 이 파일에만 저장되고 GitHub 에는 올라가지 않는다(.gitignore).
- source: 기사 출처. "google"(구글 뉴스, 키 불필요) 또는 "naver"(네이버, 키 필요).
"""

import json
import os
import sys

DEFAULT_CONFIG = {
    "source": "google",        # google | naver
    "client_id": "",
    "client_secret": "",
    "keywords": ["주택관리공단", "임대주택 관리", "공공임대 유지보수"],
    "exclude_words": [],
    "days_back": 1,            # 기본 조회 기간: 오늘로부터 며칠 전까지
    "exclude_sent": True,      # 이미 보고한 기사 제외
    "merge_similar": True,     # 제목이 거의 같은 기사 묶기
    "similar_threshold": 0.85, # 유사 제목 판정 기준 (0~1)
    "report_title": "언론보도 모니터링",
}


def app_dir() -> str:
    """exe 로 실행 중이면 exe 가 있는 폴더, 아니면 소스 파일이 있는 폴더."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(app_dir(), "config.json")


def load() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass  # 깨진 설정 파일은 기본값으로 대체
    return cfg


def save(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
