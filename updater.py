"""GitHub Releases 를 확인해 새 버전이 있으면 내려받고 스스로 교체한다.

흐름:
1. https://api.github.com/repos/<저장소>/releases/latest 에서 최신 태그(v0.2.0 등) 확인
2. 현재 버전보다 높으면 첨부된 NewsMonitor.exe 를 옆에 'NewsMonitor.new.exe' 로 내려받음
3. 작은 배치 파일(.bat)을 만들어 실행: 앱 종료를 기다렸다가 exe 를 바꿔치기하고 다시 실행
   (실행 중인 exe 는 윈도우가 덮어쓰기를 막기 때문에 이렇게 한다)

소스(app.py)로 실행 중일 때는 교체하지 않고 Release 페이지만 열어 준다.
"""

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

import requests

from version import EXE_NAME, GITHUB_REPO, __version__

API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"


@dataclass
class ReleaseInfo:
    version: str
    asset_url: str | None
    page_url: str
    notes: str


def _parse(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    out = []
    for p in v.split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def is_newer(remote: str, local: str = __version__) -> bool:
    return _parse(remote) > _parse(local)


class UpdateCheckError(Exception):
    """업데이트 확인 실패 이유(상태 표시줄에 보여 줌)."""


def _latest_by_redirect(timeout: int) -> ReleaseInfo:
    """API 가 막혔을 때(예: 같은 인터넷 주소를 쓰는 사람이 많아 시간당 60회 한도 초과)
    github.com/…/releases/latest 가 최신 태그 주소로 넘겨 주는 것을 이용한다."""
    resp = requests.get(f"{RELEASES_PAGE}/latest", timeout=timeout, allow_redirects=False)
    loc = resp.headers.get("Location", "")
    if resp.status_code not in (301, 302) or "/tag/" not in loc:
        raise UpdateCheckError(f"GitHub 응답 {resp.status_code}")
    tag = loc.rsplit("/tag/", 1)[1]
    return ReleaseInfo(
        version=tag,
        asset_url=f"{RELEASES_PAGE}/download/{tag}/{EXE_NAME}",
        page_url=loc,
        notes="",
    )


def check_latest(timeout: int = 10) -> ReleaseInfo:
    """최신 Release 정보. 실패하면 UpdateCheckError(이유)."""
    try:
        resp = requests.get(API_LATEST, timeout=timeout,
                            headers={"Accept": "application/vnd.github+json"})
    except requests.exceptions.SSLError as e:
        raise UpdateCheckError("보안 인증서 확인 실패(회사 보안장비)") from e
    except requests.RequestException as e:
        raise UpdateCheckError(f"네트워크 오류: {type(e).__name__}") from e
    if resp.status_code != 200:
        try:
            return _latest_by_redirect(timeout)
        except requests.RequestException as e:
            raise UpdateCheckError(f"GitHub 응답 {resp.status_code}") from e
    data = resp.json()
    asset_url = None
    for a in data.get("assets", []):
        if a.get("name", "").lower() == EXE_NAME.lower():
            asset_url = a.get("browser_download_url")
            break
    return ReleaseInfo(
        version=data.get("tag_name", ""),
        asset_url=asset_url,
        page_url=data.get("html_url", RELEASES_PAGE),
        notes=(data.get("body") or "").strip(),
    )


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def download(url: str, dest: str, progress=None) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if progress and total:
                        progress(done / total)


# 교체용 배치 파일. 경로는 글자로 써 넣지 않고 인자(%1~%4)로 넘긴다
# (한글·공백이 든 경로도 깨지지 않게). 파일 자체는 영문만 쓴다.
# 다섯 번째 인자 norun 은 시험용(교체만 하고 앱은 안 켬): tests/check_update_bat.py
_UPDATE_BAT = r"""@echo off
set "NEW=%~1"
set "CUR=%~2"
set "WAITPID=%~3"
set "LOG=%~4"
set n=0
:wait
tasklist /FI "PID eq %WAITPID%" 2>nul | find "%WAITPID%" >nul
if not errorlevel 1 (
  ping -n 2 127.0.0.1 >nul
  goto wait
)
:move
move /y "%NEW%" "%CUR%" >nul 2>&1
if not errorlevel 1 goto ok
set /a n+=1
if %n% geq 60 goto fail
ping -n 2 127.0.0.1 >nul
goto move
:fail
>>"%LOG%" echo %date% %time% FAIL could not replace exe after 60 tries
goto run
:ok
>>"%LOG%" echo %date% %time% OK replaced after %n% retries
:run
if "%~5"=="norun" goto end
start "" "%CUR%"
:end
(goto) 2>nul & del "%~f0"
"""


def apply_update(asset_url: str, progress=None) -> None:
    """새 exe 를 내려받고 교체용 배치 파일을 실행한 뒤 현재 앱을 종료한다.

    exe(PyInstaller 한 파일 방식)는 실행하면 프로세스가 두 개 뜬다: 압축을 푸는 '바깥'과
    실제 앱인 '안쪽'. 안쪽이 끝나도 바깥이 잠깐 exe 를 붙잡고 있어서, 곧바로 바꿔치기하면
    실패한다(v0.3.0 까지의 버그 → 옛 버전이 다시 켜짐). 그래서 성공할 때까지 1초 간격으로
    최대 60번 다시 시도하고, 결과를 exe 옆 update_log.txt 에 남긴다.
    """
    if not is_frozen():
        raise RuntimeError("소스로 실행 중일 때는 자동 교체를 하지 않습니다.")

    current = sys.executable
    folder = os.path.dirname(current)
    new_path = os.path.join(folder, EXE_NAME.replace(".exe", ".new.exe"))
    log_path = os.path.join(folder, "update_log.txt")
    download(asset_url, new_path, progress)

    bat = os.path.join(tempfile.gettempdir(), "newsmonitor_update.bat")
    with open(bat, "w", encoding="ascii", newline="\r\n") as f:
        f.write(_UPDATE_BAT)

    # cmd /s /c "…" : 바깥 따옴표 한 쌍만 벗기므로 안쪽 경로 따옴표가 그대로 살아남는다
    cmdline = f'cmd /d /s /c ""{bat}" "{new_path}" "{current}" {os.getpid()} "{log_path}""'
    subprocess.Popen(cmdline, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os._exit(0)
