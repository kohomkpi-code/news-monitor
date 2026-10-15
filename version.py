"""앱 버전과 GitHub 저장소 정보.

새 버전을 배포할 때는 __version__ 숫자만 올리면 된다.
GitHub Actions가 이 값을 읽어 'v0.1.0' 같은 태그로 Release를 만든다.
"""

__version__ = "0.3.0"

APP_NAME = "NewsMonitor"
APP_TITLE = "언론보도 모니터링"
GITHUB_REPO = "kohomkpi-code/news-monitor"
EXE_NAME = "NewsMonitor.exe"
