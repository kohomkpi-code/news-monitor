"""GitHub Releases 를 확인해 새 버전이 있으면 내려받고 스스로 교체한다.

흐름:
1. https://api.github.com/repos/<저장소>/releases/latest 에서 최신 태그(v0.2.0 등) 확인
2. 현재 버전보다 높으면 첨부된 NewsMonitor.exe 를 옆에 'NewsMonitor.new.exe' 로 내려받음
3. 작은 배치 파일(.bat)을 만들어 실행: 앱 종료를 기다렸다가 새 exe 를 버전 이름
   (NewsMonitor_v0.4.0.exe)으로 놓고, 옛 exe 를 지운 뒤 새 것을 실행
   (실행 중인 exe 는 윈도우가 덮어쓰기를 막기 때문에 이렇게 한다)

소스(app.py)로 실행 중일 때는 교체하지 않고 Release 페이지만 열어 준다.
"""

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass

import requests

from version import EXE_NAME, GITHUB_REPO, __version__, versioned_exe_name

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
        asset_url=f"{RELEASES_PAGE}/download/{tag}/{versioned_exe_name(tag)}",
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
    # 버전 이름(NewsMonitor_v0.4.0.exe)을 먼저 찾고, 없으면 예전 이름(NewsMonitor.exe)
    assets = {a.get("name", "").lower(): a.get("browser_download_url") for a in data.get("assets", [])}
    asset_url = (assets.get(versioned_exe_name(data.get("tag_name", "")).lower())
                 or assets.get(EXE_NAME.lower()))
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


# 교체용 배치 파일. 경로는 글자로 써 넣지 않고 인자로 넘긴다(한글·공백이 든 경로도 깨지지 않게).
#   %1 새 exe(내려받은 것)  %2 지금 exe  %3 기다릴 프로세스 번호  %4 기록 파일  %5 새 exe 를 둘 이름
#   %6 norun 이면 교체만 하고 실행 안 함(시험용: tests/check_update_bat.py)
_UPDATE_BAT = r"""@echo off
set "NEW=%~1"
set "CUR=%~2"
set "WAITPID=%~3"
set "LOG=%~4"
set "TARGET=%~5"
if "%TARGET%"=="" set "TARGET=%CUR%"
set n=0
set m=0
:wait
tasklist /FI "PID eq %WAITPID%" 2>nul | find "%WAITPID%" >nul
if not errorlevel 1 (
  ping -n 2 127.0.0.1 >nul
  goto wait
)
:move
move /y "%NEW%" "%TARGET%" >nul 2>&1
if not errorlevel 1 goto moved
set /a n+=1
if %n% geq 60 goto fail
ping -n 2 127.0.0.1 >nul
goto move
:moved
if /i "%TARGET%"=="%CUR%" goto ok
:delold
del /f /q "%CUR%" >nul 2>&1
if not exist "%CUR%" goto ok
set /a m+=1
if %m% geq 60 goto oldleft
ping -n 2 127.0.0.1 >nul
goto delold
:oldleft
>>"%LOG%" echo %date% %time% WARN new exe installed, old exe could not be deleted
goto run
:fail
>>"%LOG%" echo %date% %time% FAIL could not place new exe after 60 tries
set "TARGET=%CUR%"
goto run
:ok
>>"%LOG%" echo %date% %time% OK installed new exe, retries move %n% delete %m%
:run
if "%~6"=="norun" goto end
start "" "%TARGET%"
:end
(goto) 2>nul & del "%~f0"
"""

_EXE_RE = re.compile(r"^NewsMonitor(_v[0-9.]+)?\.exe$", re.IGNORECASE)


def apply_update(asset_url: str, progress=None) -> None:
    """새 exe 를 내려받고 교체용 배치 파일을 실행한 뒤 현재 앱을 종료한다.

    exe(PyInstaller 한 파일 방식)는 실행하면 프로세스가 두 개 뜬다: 압축을 푸는 '바깥'과
    실제 앱인 '안쪽'. 안쪽이 끝나도 바깥이 잠깐 exe 를 붙잡고 있어서, 곧바로 바꾸면
    실패한다(v0.3.0 까지의 버그). 그래서 성공할 때까지 1초 간격으로 최대 60번 다시 시도하고,
    결과를 exe 옆 update_log.txt 에 남긴다.
    새 exe 는 내려받은 파일 이름(NewsMonitor_v0.4.0.exe 등)으로 두고 옛 exe 는 지운다.
    """
    if not is_frozen():
        raise RuntimeError("소스로 실행 중일 때는 자동 교체를 하지 않습니다.")

    current = sys.executable
    folder = os.path.dirname(current)
    new_path = os.path.join(folder, "NewsMonitor.new.exe")
    log_path = os.path.join(folder, "update_log.txt")
    name = os.path.basename(asset_url.split("?")[0])
    target = os.path.join(folder, name) if _EXE_RE.match(name) else current
    download(asset_url, new_path, progress)

    bat = os.path.join(tempfile.gettempdir(), "newsmonitor_update.bat")
    with open(bat, "w", encoding="ascii", newline="\r\n") as f:
        f.write(_UPDATE_BAT)

    # cmd /s /c "…" : 바깥 따옴표 한 쌍만 벗기므로 안쪽 경로 따옴표가 그대로 살아남는다
    cmdline = (f'cmd /d /s /c ""{bat}" "{new_path}" "{current}" {os.getpid()} '
               f'"{log_path}" "{target}""')
    subprocess.Popen(cmdline, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os._exit(0)
