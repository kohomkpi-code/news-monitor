@echo off
chcp 65001 >nul
rem ============================================================
rem  KOHOM 뉴스룸 exe 만들기 (부서 Windows PC 용, GitHub 없이)
rem  1) 필요한 부품 설치  2) 시험(선정 규칙·보고 기록 공유·업데이트)  3) exe 만들기  4) 교체 시험
rem  결과: dist\NewsMonitor_v버전.exe  → 부서 구글 드라이브 'KOHOM뉴스룸_업데이트' 폴더에 올린다
rem  필요: Python 3.12 (python.org, 설치 때 'Add python.exe to PATH' 체크)
rem ============================================================
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

where python >nul 2>&1
if errorlevel 1 (
  echo [오류] Python 이 없습니다. python.org 에서 Python 3.12 를 설치하세요^(설치 첫 화면 'Add python.exe to PATH' 체크^).
  goto fail
)

echo.
echo [1/4] 부품 설치 중...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail

echo.
echo [2/4] 시험 중...
for %%f in (*.py) do (
  python -m py_compile "%%f"
  if errorlevel 1 goto fail
)
python tests\check_rules.py
if errorlevel 1 goto fail
python tests\check_history.py
if errorlevel 1 goto fail

for /f "usebackq delims=" %%v in (`python -c "import version; print(version.__version__)"`) do set VER=%%v
echo.
echo [3/4] exe 만드는 중... (v%VER%)
python -m PyInstaller --noconfirm --clean --onefile --windowed --name NewsMonitor_v%VER% --add-data "assets/fonts;assets/fonts" app.py
if errorlevel 1 goto fail

echo.
echo [4/4] 자동 업데이트 교체 시험 중...
python tests\check_update_bat.py
if errorlevel 1 goto fail

echo.
echo ============================================================
echo  완료: dist\NewsMonitor_v%VER%.exe
echo  이 파일을 부서 구글 드라이브 'KOHOM뉴스룸_업데이트' 폴더에 올리면
echo  각 PC 앱이 켤 때 새 버전을 받아 갑니다. (변경 내용은 같은 폴더 '변경내용.txt')
echo ============================================================
start "" explorer "%~dp0dist"
pause
exit /b 0

:fail
echo.
echo [실패] 위의 오류 내용을 Claude 에게 보여 주세요. exe 는 만들어지지 않았습니다.
pause
exit /b 1
