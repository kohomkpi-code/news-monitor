"""앱 버전.

새 버전을 낼 때는 __version__ 숫자만 올리고 build.bat 으로 exe 를 만든다(dist\\NewsMonitor_v버전.exe).
그 exe 를 부서 계정 구글 드라이브의 'KOHOM뉴스룸_업데이트' 폴더에 올리면 각 PC 앱이 받아 간다(updater.py).
"""

__version__ = "1.3.0"

APP_NAME = "NewsMonitor"
APP_TITLE = "KOHOM 뉴스룸"


def versioned_exe_name(version: str) -> str:
    """버전이 들어간 exe 이름. 예: NewsMonitor_v1.3.0.exe — 업데이트 폴더에 이 이름으로 올린다."""
    return f"{APP_NAME}_v{version.strip().lstrip('vV')}.exe"
