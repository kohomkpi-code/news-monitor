"""새 버전 확인·내려받기·스스로 교체 — 부서 구글 드라이브의 중계함(relay_script.py)을 통해 (v1.3.0~, GitHub 안 씀).

흐름:
1. 중계함에 'latest' 를 물어 업데이트 폴더(부서 계정 드라이브 'KOHOM뉴스룸_업데이트')에서 버전이 가장 큰
   NewsMonitor_v1.3.1.exe 의 버전·크기·확인값(SHA-256)을 받는다
2. 지금 버전보다 높으면 'chunk' 로 4MB 씩 받아 옆에 'NewsMonitor.new.exe' 로 저장하고 크기·확인값을 맞춰 본다
3. 작은 배치 파일(.bat)을 만들어 실행: 앱 종료를 기다렸다가 새 exe 를 버전 이름으로 놓고, 옛 exe 를 지운 뒤 새 것을 실행
   (실행 중인 exe 는 윈도우가 덮어쓰기를 막기 때문에 이렇게 한다)
중계함 주소·암호는 [설정]의 보고 기록 공유(중계함) 값을 함께 쓴다. 소스(app.py)로 실행 중일 때는 교체하지 않는다.
"""

import base64
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass

import requests

from history_share import RELAY_ERRORS
from version import __version__


@dataclass
class ReleaseInfo:
    version: str      # '' = 업데이트 폴더에 올린 파일 없음
    name: str = ""    # NewsMonitor_v1.3.1.exe
    size: int = 0
    sha256: str = ""
    chunks: int = 0
    notes: str = ""   # 업데이트 폴더의 '변경내용.txt'


def _parse(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    out = []
    for p in v.split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def is_newer(remote: str, local: str = __version__) -> bool:
    return bool(remote) and _parse(remote) > _parse(local)


class UpdateCheckError(Exception):
    """업데이트 확인·내려받기 실패 이유(상태 표시줄·안내창에 보여 줌)."""


def _post(url: str, key: str, payload: dict, timeout: int) -> dict:
    try:
        resp = requests.post(url, json={"key": key, **payload}, timeout=timeout)
    except requests.exceptions.SSLError as e:
        raise UpdateCheckError("보안 인증서 확인 실패(회사 보안장비)") from e
    except requests.RequestException as e:
        raise UpdateCheckError(f"중계함에 연결하지 못했습니다({type(e).__name__})") from e
    try:
        body = resp.json()
    except ValueError as e:
        raise UpdateCheckError(f"중계함 답이 이상합니다(HTTP {resp.status_code})") from e
    if not isinstance(body, dict) or not body.get("ok"):
        err = body.get("error", "") if isinstance(body, dict) else ""
        raise UpdateCheckError(RELAY_ERRORS.get(err, f"중계함 오류: {err or '알 수 없음'}"))
    return body


def check_latest(url: str, key: str, timeout: int = 30) -> ReleaseInfo:
    """업데이트 폴더의 최신 파일 정보. 실패하면 UpdateCheckError(이유)."""
    if not url.strip() or not key.strip():
        raise UpdateCheckError("중계함 연결이 없습니다([설정] → 보고 기록 공유 → 중계함)")
    b = _post(url.strip(), key.strip(), {"action": "latest"}, timeout)
    return ReleaseInfo(version=str(b.get("version") or ""), name=str(b.get("name") or ""),
                       size=int(b.get("size") or 0), sha256=str(b.get("sha256") or "").lower(),
                       chunks=int(b.get("chunks") or 0), notes=str(b.get("notes") or "").strip())


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def download(info: ReleaseInfo, url: str, key: str, dest: str, progress=None) -> None:
    """조각을 차례로 받아 dest 에 저장하고 크기·확인값을 맞춰 본다(다르면 지우고 UpdateCheckError)."""
    h = hashlib.sha256()
    done = 0
    with open(dest, "wb") as f:
        for i in range(info.chunks):
            b = _post(url.strip(), key.strip(), {"action": "chunk", "name": info.name, "index": i}, timeout=180)
            data = base64.b64decode(b.get("data", ""))
            f.write(data)
            h.update(data)
            done += len(data)
            if progress and info.size:
                progress(min(done / info.size, 1.0))
    if done != info.size or h.hexdigest() != info.sha256:
        os.remove(dest)
        raise UpdateCheckError("내려받은 파일이 드라이브에 올린 파일과 다릅니다 — 잠시 뒤 다시 시도")


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


def apply_update(info: ReleaseInfo, url: str, key: str, progress=None) -> None:
    """새 exe 를 내려받고 교체용 배치 파일을 실행한 뒤 현재 앱을 종료한다.

    exe(PyInstaller 한 파일 방식)는 실행하면 프로세스가 두 개 뜬다: 압축을 푸는 '바깥'과
    실제 앱인 '안쪽'. 안쪽이 끝나도 바깥이 잠깐 exe 를 붙잡고 있어서, 곧바로 바꾸면
    실패한다(v0.3.0 까지의 버그). 그래서 성공할 때까지 1초 간격으로 최대 60번 다시 시도하고,
    결과를 exe 옆 update_log.txt 에 남긴다.
    새 exe 는 올린 파일 이름(NewsMonitor_v1.3.1.exe 등)으로 두고 옛 exe 는 지운다.
    """
    if not is_frozen():
        raise RuntimeError("소스로 실행 중일 때는 자동 교체를 하지 않습니다.")

    current = sys.executable
    folder = os.path.dirname(current)
    new_path = os.path.join(folder, "NewsMonitor.new.exe")
    log_path = os.path.join(folder, "update_log.txt")
    target = os.path.join(folder, info.name) if _EXE_RE.match(info.name) else current
    download(info, url, key, new_path, progress)

    bat = os.path.join(tempfile.gettempdir(), "newsmonitor_update.bat")
    with open(bat, "w", encoding="ascii", newline="\r\n") as f:
        f.write(_UPDATE_BAT)

    # cmd /s /c "…" : 바깥 따옴표 한 쌍만 벗기므로 안쪽 경로 따옴표가 그대로 살아남는다
    cmdline = (f'cmd /d /s /c ""{bat}" "{new_path}" "{current}" {os.getpid()} '
               f'"{log_path}" "{target}""')
    subprocess.Popen(cmdline, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os._exit(0)
