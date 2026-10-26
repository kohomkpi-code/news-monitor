"""앱 버전과 GitHub 저장소 정보.

새 버전을 배포할 때는 __version__ 숫자만 올리면 된다.
GitHub Actions가 이 값을 읽어 'v0.1.0' 같은 태그로 Release를 만든다.
"""

__version__ = "1.0.7"

APP_NAME = "NewsMonitor"
APP_TITLE = "KOHOM 뉴스룸"
GITHUB_REPO = "kohomkpi-code/news-monitor"
EXE_NAME = "NewsMonitor.exe"   # v0.3.1 이하가 자동 업데이트로 찾는 이름(호환용으로 계속 올림)


def versioned_exe_name(version: str) -> str:
    """버전이 들어간 exe 이름. 예: NewsMonitor_v0.4.0.exe (v0.4.0 부터 이 이름으로 배포·설치)."""
    return f"{APP_NAME}_v{version.strip().lstrip('vV')}.exe"
