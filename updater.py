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


def check_latest(timeout: int = 10) -> ReleaseInfo | None:
    """최신 Release 정보. 네트워크 오류나 Release 가 없으면 None."""
    try:
        resp = requests.get(API_LATEST, timeout=timeout,
                            headers={"Accept": "application/vnd.github+json"})
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
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


def apply_update(asset_url: str, progress=None) -> None:
    """새 exe 를 내려받고 교체용 배치 파일을 실행한 뒤 현재 앱을 종료한다."""
    if not is_frozen():
        raise RuntimeError("소스로 실행 중일 때는 자동 교체를 하지 않습니다.")

    current = sys.executable
    folder = os.path.dirname(current)
    new_path = os.path.join(folder, EXE_NAME.replace(".exe", ".new.exe"))
    download(asset_url, new_path, progress)

    bat = os.path.join(tempfile.gettempdir(), "newsmonitor_update.bat")
    pid = os.getpid()
    script = f"""@echo off
chcp 65001 >nul
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
move /y "{new_path}" "{current}" >nul
start "" "{current}"
del "%~f0"
"""
    with open(bat, "w", encoding="utf-8") as f:
        f.write(script)

    subprocess.Popen(["cmd", "/c", bat], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os._exit(0)
