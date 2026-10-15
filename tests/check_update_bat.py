"""자동 업데이트의 exe 바꿔치기(배치 파일)를 실제 윈도우에서 시험한다.

GitHub Actions(윈도우)에서 exe 를 만든 뒤 Release 를 올리기 전에 돌린다. 실패하면 배포를 멈춘다.
상황 재현:
- 한글과 공백이 든 폴더 (예: 'OneDrive - 공단')
- 앱(안쪽 프로세스)이 끝난 뒤에도 다른 프로세스(바깥 프로세스 역할)가 4초간 exe 를 붙잡고 있음
시험 두 가지:
1) 새 이름으로 설치: NewsMonitor.exe → NewsMonitor_v9.9.9.exe 가 생기고 옛 파일은 지워져야 함
2) 같은 이름 덮어쓰기: NewsMonitor_v9.9.9.exe 를 같은 이름의 새 파일로 바꿔야 함
"""

import os
import subprocess
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import updater  # noqa: E402


def run_case(label: str, cur_name: str, target_name: str) -> str:
    folder = os.path.join(tempfile.mkdtemp(), "OneDrive - 공단 시험")
    os.makedirs(folder)
    new = os.path.join(folder, "NewsMonitor.new.exe")
    cur = os.path.join(folder, cur_name)
    target = os.path.join(folder, target_name)
    log = os.path.join(folder, "update_log.txt")
    with open(new, "w") as f:
        f.write("NEW")
    with open(cur, "w") as f:
        f.write("OLD")

    bat = os.path.join(tempfile.gettempdir(), f"newsmonitor_update_test_{label}.bat")
    with open(bat, "w", encoding="ascii", newline="\r\n") as f:
        f.write(updater._UPDATE_BAT)

    holder = subprocess.Popen([sys.executable, "-c", f"import time; f = open({cur!r}, 'rb'); time.sleep(4)"])
    app = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
    time.sleep(0.5)
    started = time.time()
    cmd = f'cmd /d /s /c ""{bat}" "{new}" "{cur}" {app.pid} "{log}" "{target}" norun"'
    r = subprocess.run(cmd, timeout=150, capture_output=True, text=True, errors="replace")
    holder.wait()

    log_text = open(log).read().strip() if os.path.exists(log) else "(로그 없음)"
    with open(target) as f:
        content = f.read()
    assert content == "NEW", f"{label}: 새 파일이 아님 ({content})"
    assert not os.path.exists(new), f"{label}: 내려받은 파일이 남아 있음"
    if cur != target:
        assert not os.path.exists(cur), f"{label}: 옛 exe 가 남아 있음"
    assert "OK" in log_text, f"{label}: {log_text}"
    return f"{label} {time.time() - started:.1f}초 [{log_text}] 종료코드 {r.returncode}"


def main():
    results = [
        run_case("새이름", "NewsMonitor.exe", "NewsMonitor_v9.9.9.exe"),
        run_case("같은이름", "NewsMonitor_v9.9.9.exe", "NewsMonitor_v9.9.9.exe"),
    ]
    print("::notice title=업데이트 교체 시험 통과::" + " / ".join(results))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # GitHub 화면의 주석(annotation)으로 남겨 원인을 바로 볼 수 있게
        print(f"::error title=업데이트 교체 시험 실패::{type(e).__name__}: {e}".replace("\n", " | "))
        traceback.print_exc()
        sys.exit(1)
