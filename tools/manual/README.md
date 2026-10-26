# 사용자 매뉴얼 만들기

앱 화면이 바뀌면 아래 순서로 매뉴얼(PPT·PDF)을 다시 만든다. 결과물은 `docs/manual/`.

1. **화면 찍기** — GitHub → Actions → `manual` → Run workflow.
   윈도우 PC(1920×1080)에서 시연 기사(`demo_data.py`)로 앱을 조작하며 화면 14장과 위치표(`geometry.json`)를
   `manual-shots` 브랜치에 올린다. 개발 PC 에서는 `xvfb-run python tools/manual/capture.py 출력폴더`.
2. **PPT 만들기** — `manual-shots` 를 내려받은 폴더로
   `node tools/manual/build_deck.js <화면 폴더> <출력 폴더>` (부품: `npm install pptxgenjs react react-dom react-icons sharp`)
3. **마무리** — `python tools/manual/finish_deck.py <출력 폴더>/*.pptx`
   (모든 문단 '한글 단어 잘림 허용' 해제 = 어절 단위 줄바꿈, 한글 글꼴 칸을 한국어로)
4. **PDF** — Pretendard(`assets/fonts`의 Regular·SemiBold·Bold 3종)가 깔린 PC 의 PowerPoint 에서 파일 → 내보내기 → PDF.
   개발 PC 의 LibreOffice PDF 는 글꼴은 같지만 한글·영문 사이 간격이 조금 넓게 보여 미리보기용.

- 화면 속 기사는 시연 자료(실제 기사·인물 아님). 번호 표시 위치는 위치표에서 자동으로 계산한다.
- 자동 촬영이 안 되는 화면(윈도우 경고 창, 그룹웨어 편지쓰기)은 PPT 에 점선 자리표시자로 둔다 — 직접 찍어 넣고 자리표시자는 지운다.
