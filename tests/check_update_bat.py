"""자동 업데이트의 exe 바꿔치기(배치 파일)를 실제 윈도우에서 시험한다.

GitHub Actions(윈도우)에서 exe 를 만든 뒤 Release 를 올리기 전에 돌린다. 실패하면 배포를 멈춘다.
상황 재현:
- 한글과 공백이 든 폴더 (예: 'OneDrive - 공단')
- 앱(안쪽 프로세스)이 끝난 뒤에도 다른 프로세스(바깥 프로세스 역할)가 4초간 exe 를 붙잡고 있음
→ 배치 파일이 기다렸다가 결국 새 파일로 바꾸고 update_log.txt 에 OK 를 남기면 통과.
"""

import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import updater  # noqa: E402

folder = os.path.join(tempfile.mkdtemp(), "OneDrive - 공단 시험")
os.makedirs(folder)
new = os.path.join(folder, "NewsMonitor.new.exe")
cur = os.path.join(folder, "NewsMonitor.exe")
log = os.path.join(folder, "update_log.txt")
with open(new, "w") as f:
    f.write("NEW")
with open(cur, "w") as f:
    f.write("OLD")

bat = os.path.join(tempfile.gettempdir(), "newsmonitor_update_test.bat")
with open(bat, "w", encoding="ascii", newline="\r\n") as f:
    f.write(updater._UPDATE_BAT)

holder = subprocess.Popen([sys.executable, "-c", f"import time; f = open({cur!r}, 'rb'); time.sleep(4)"])
app = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
time.sleep(0.5)
started = time.time()
cmd = f'cmd /d /s /c ""{bat}" "{new}" "{cur}" {app.pid} "{log}" norun"'
subprocess.run(cmd, timeout=120, check=True)
holder.wait()

with open(cur) as f:
    content = f.read()
with open(log) as f:
    log_text = f.read()
print(f"걸린 시간 {time.time() - started:.1f}초 / 로그: {log_text.strip()}")
assert content == "NEW", f"교체 실패: {content}"
assert not os.path.exists(new), "새 파일이 남아 있음"
assert "OK" in log_text, log_text
print("업데이트 교체 시험 통과")
