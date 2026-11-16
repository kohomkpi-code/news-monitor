# KOHOM 뉴스룸 — Claude 작업 안내

이 폴더는 주택관리공단 언론보도 모니터링 앱(KOHOM 뉴스룸, 윈도우 exe)의 소스다. 작업 전에 이 파일을 먼저 읽는다.
v1.3.0부터 **GitHub를 쓰지 않는다.** exe는 부서 Windows PC에서 `build.bat`으로 만들고, 부서 공용 구글 계정의
구글 드라이브에 올려 배포한다. 사람이 보는 관리 순서는 `docs/관리자_안내서.md`.

## 사용자와 대화 규칙
- 사용자: 주택관리공단 전략과(비개발자). 설명은 **쉬운 한국어로, 결론 먼저, 짧게**.
- 확인 질문은 꼭 필요한 것 하나만. 나머지는 추천안으로 바로 진행한다.
- 사용자가 할 일은 번호를 매겨 "어느 화면 어느 버튼"까지 적는다.
- 코드·대화·문서에 업무 자료·비밀번호·중계함 암호·계정 주소를 넣지 않는다(암호는 각 PC의 config.json·연결 파일에만).
- PPT를 만들 때는 사용자의 PPT 제작 표준(글꼴 Pretendard Bold·SemiBold·Regular, 네이비 1F3B5C·틸 2E7D8C·앰버 E8A33D, 발표자 노트,
  '미확인'·'(추정)' 표시와 마지막 장 '확인 필요 사항', 배포용 PDF)을 따른다. 매뉴얼 PPT 제작 도구는 `tools/manual/`.

## 구조 한눈에
- 화면 `app.py`(tkinter) · 디자인 `theme.py` · 표 `result_table.py`
- 조회: `google_news.py`·`feeds.py`·`naver_api.py` → 거르기 `dedup.py` → 점수·분류·추천 `ranking.py`(규칙 `rules.py`)
- 보고서 `report.py` · 엑셀 `export.py` · AI 선별·규칙 개선 요청문 `selection.py`
- 보고 기록 `history.py` · 공유(중계함·공유 폴더·연결 파일) `history_share.py` · 중계함 대본 `relay_script.py`
- 업데이트 `updater.py`(중계함으로 확인·내려받기·교체) · 설정 `config.py` · 버전 `version.py`
- 자세한 설계: `docs/manual/KOHOM뉴스룸_설계문서.md` · 사용법: `docs/manual/KOHOM뉴스룸_사용자매뉴얼_텍스트.md`
- 지난 결정의 이유: `docs/개발일지.md` · 버전별 변경: `CHANGELOG.md`

## 중계함(부서 구글 계정의 Apps Script 웹 앱)
- `relay_script.py`의 `SCRIPT`가 대본이다. 앱 [설정] → [중계함 대본 복사]가 암호를 넣어 복사한다.
- 하는 일: 보고 기록 주고받기(`sync`), 새 버전 알려 주기(`latest`), exe 조각 내려 주기(`chunk`, 4MB).
- 부서 드라이브 폴더: `KOHOM뉴스룸_보고기록`(PC마다 `보고기록_PC이름.json`), `KOHOM뉴스룸_업데이트`(`NewsMonitor_v버전.exe`, `변경내용.txt`).
- **대본을 바꾸면 `RELAY_VERSION`을 올리고**, 관리자 안내서의 "중계함 대본 다시 올리기" 순서를 사용자에게 안내한다
  ([배포 관리] → 연필 → 새 버전 → [배포]. [새 배포]를 누르면 주소가 바뀌어 모든 PC 연결 파일을 다시 나눠야 함).
- 옛 대본에 없는 요청은 `bad_action` → 앱이 "대본을 다시 복사해 배포"라고 알린다.

## 새 버전 내는 순서(매번)
1. 코드를 고친다. 화면을 바꿨으면 버튼 이름이 매뉴얼과 맞는지 본다.
2. `version.py`의 `__version__`을 올린다(작은 수정 1.3.0→1.3.1, 기능 추가 1.3.x→1.4.0).
3. `CHANGELOG.md` 맨 위에 `## v버전 (날짜) 한 줄 제목` + 바뀐 점(사용자 말로). `docs/개발일지.md`에 결정 이유.
4. 매뉴얼이 바뀌는 기능이면 `docs/manual/`의 텍스트 매뉴얼·설계 문서도 고친다.
5. `build.bat` 실행(더블클릭 또는 `cmd /c build.bat`). 시험이 하나라도 실패하면 exe가 만들어지지 않는다 — 고치고 다시.
   - `tests/check_rules.py` 선정 규칙 52개, `tests/check_history.py` 공유·업데이트(node가 있으면 중계함 대본까지),
     `tests/check_update_bat.py` exe 교체.
   - 기본 규칙(`rules.DEFAULT_RULES`)을 일부러 바꿨으면 기대값을 함께 고치고 ※로 표시. 기본 규칙을 바꾸면
     `RULES_VERSION`을 올리고 `rules_history.py`에 이전 기본값을 남겨 `upgrade()`가 직접 고친 항목을 지키게 한다.
6. 사용자에게 안내: `dist\NewsMonitor_v버전.exe`를 부서 드라이브 `KOHOM뉴스룸_업데이트` 폴더에 올리고, `변경내용.txt`를
   CHANGELOG 맨 위 항목으로 바꾸기. 소스 폴더를 압축해 `KOHOM뉴스룸_소스` 폴더에 백업.
7. 옛 exe는 업데이트 폴더에 남겨도 된다(앱은 버전 숫자가 가장 큰 것만 받음). 정리하려면 최신 2개만 남긴다.

## 지켜 온 원칙
- 설정 파일(config.json)을 옮길 때는 `config.load()`에 단계별 이전 코드를 둔다. 사용자가 고친 값은 지킨다.
- 직원이 할 일을 늘리지 않는다: 새 기능은 기본값으로 바로 돌고, 설정이 필요하면 연결 파일·기본값으로 대신한다.
- 비밀값(네이버 키, 중계함 암호)은 결과 엑셀·규칙 파일·요청문·로그에 넣지 않는다.
- 화면 글꼴은 Pretendard(`assets/fonts`, SIL OFL). 색은 `theme.py` 토큰만 쓴다.
