// KOHOM 뉴스룸 사용자 매뉴얼 PPT 만들기 — 화면(capture.py 결과)과 위치표(geometry.json)로 슬라이드를 짓는다.
// 사용: node build_deck.js <화면 폴더> <출력 폴더>
//   필요한 부품: pptxgenjs, react, react-dom, react-icons, sharp (npm). 화면 폴더는 Actions 'manual' 결과(manual-shots 브랜치).
// 공단 PPT 표준: 16:9(13.33×7.5in), 흰 배경, 여백 0.6in, 에스코어 드림 7·5·4, 네이비·틸·앰버, 슬라이드당 그림 1장,
//   제목 왼쪽 번호 블록(0.7in) + 틸 키커, 제목 아래 선 없음, 아이콘은 Lucide(react-icons/lu), 모든 슬라이드에 발표자 노트.
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const lu = require("react-icons/lu");

const SHOTS = path.resolve(process.argv[2] || "manual_shots");
const OUT = path.resolve(process.argv[3] || ".");
const G = JSON.parse(fs.readFileSync(path.join(SHOTS, "geometry.json"), "utf8"));
const VER = G.app_version;
const DATE = "2026. 10. 26.";

const F = { xb: "S-Core Dream 7 ExtraBold", md: "S-Core Dream 5 Medium", rg: "S-Core Dream 4 Regular" };
const C = { navy: "1F3B5C", teal: "2E7D8C", amber: "E8A33D", card: "F3F6F9", tealBg: "E4F0F2", amberBg: "FBF3E4",
  text: "1E2A36", gray: "667385", line: "CBD5DF", white: "FFFFFF" };
const PART = { navy: C.navy, teal: C.teal, amber: C.amber };
const N = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧"];
const M = 0.6; // 여백
const SW = 13.333;

const iconCache = {};
async function icon(name, color = C.navy) {
  const key = name + color;
  if (!iconCache[key]) {
    const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(lu[name], { size: 256, color: "#" + color }));
    const png = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
    iconCache[key] = "image/png;base64," + png.toString("base64");
  }
  return iconCache[key];
}

function text(slide, t, o) {
  slide.addText(t, { isTextBox: true, margin: 0, valign: "top", fontFace: F.rg, fontSize: 14, color: C.text, ...o });
}

// 제목 영역: 번호 블록 + 키커 + 제목 + 부제 (제목 아래 선·띠 없음)
function header(slide, { no, part, kicker, title, sub }) {
  slide.addShape("roundRect", { x: M, y: 0.5, w: 0.7, h: 0.7, rectRadius: 0.12, fill: { color: PART[part] },
    line: { color: PART[part] }, objectName: "번호 블록" });
  text(slide, no, { x: M, y: 0.5, w: 0.7, h: 0.7, align: "center", valign: "middle", fontFace: F.xb, fontSize: 20, color: C.white });
  text(slide, kicker, { x: 1.5, y: 0.42, w: 11.2, h: 0.28, fontFace: F.md, fontSize: 10.5, color: C.teal });
  text(slide, title, { x: 1.5, y: 0.68, w: 11.2, h: 0.55, fontFace: F.xb, fontSize: 26, color: C.navy, valign: "middle" });
  if (sub) text(slide, sub, { x: 1.5, y: 1.25, w: 11.2, h: 0.3, fontSize: 12, color: C.gray });
}

// 화면 1장 + 번호 표시(앰버 테두리 + 번호 글자, 배지 도형 없음). marks: [[위치표 키, 번호], ...]
function shot(slide, name, box, marks = [], opts = {}) {
  const info = G.shots[name];
  const [iw, ih] = info.size;
  let w = box.w, h = (box.w * ih) / iw;
  if (h > box.h) { h = box.h; w = (box.h * iw) / ih; }
  const x = box.x + (opts.alignRight ? box.w - w : 0), y = box.y;
  const s = w / iw;
  slide.addImage({ path: path.join(SHOTS, name + ".png"), x, y, w, h, altText: opts.alt || name, objectName: "화면 " + name });
  slide.addShape("rect", { x, y, w, h, fill: { type: "none" }, line: { color: C.line, width: 0.75 }, objectName: "화면 테두리" });
  for (const [key, n] of marks) {
    const m = info.marks[key];
    if (!m) { console.warn("위치표 없음:", name, key); continue; }
    const rx = x + m[0] * s - 0.03, ry = y + m[1] * s - 0.03, rw = m[2] * s + 0.06, rh = m[3] * s + 0.06;
    slide.addShape("rect", { x: rx, y: ry, w: rw, h: rh, fill: { type: "none" }, line: { color: C.amber, width: 2.25 },
      objectName: "표시 " + N[n - 1] });
    const ly = ry - 0.3 < y ? ry + 0.02 : ry - 0.3; // 그림 위 끝이면 안쪽에
    const lx = Math.min(rx - 0.02, x + w - 0.32);
    text(slide, N[n - 1], { x: Math.max(x + 0.02, lx), y: ly, w: 0.32, h: 0.3, fontFace: F.xb, fontSize: 17, color: C.amber,
      valign: "middle", align: "left", objectName: "번호 " + N[n - 1] });
  }
  return { x, y, w, h };
}

// 오른쪽 설명: [번호, 머리, 본문]. 본문 14pt, 머리 15pt
function explain(slide, items, { x, y, w, gap = 0.16 }) {
  const perLine = Math.floor((w * 72) / 14 * 0.93);
  let cy = y;
  for (const [n, head, body] of items) {
    text(slide, (n ? N[n - 1] + " " : "") + head, { x, y: cy, w, h: 0.32, fontFace: F.md, fontSize: 15, color: C.navy });
    cy += 0.34;
    if (body) {
      const lines = body.split("\n").reduce((k, l) => k + Math.max(1, Math.ceil(l.length / perLine)), 0);
      const bh = lines * 0.27 + 0.04;
      text(slide, body, { x, y: cy, w, h: bh, fontSize: 14, color: C.text, lineSpacingMultiple: 1.05 });
      cy += bh;
    }
    cy += gap;
  }
  return cy;
}

async function card(slide, { x, y, w, h, title, body, iconName, fill = C.card, iconColor = C.navy, big = false }) {
  slide.addShape("roundRect", { x, y, w, h, rectRadius: 0.1, fill: { color: fill }, line: { color: fill }, objectName: "카드 " + title });
  if (big) { // 아이콘이 주인공: 0.65in, 왼쪽 세로 가운데
    slide.addImage({ data: await icon(iconName, iconColor), x: x + 0.25, y: y + (h - 0.65) / 2, w: 0.65, h: 0.65, altText: title });
    text(slide, title, { x: x + 1.1, y: y + 0.22, w: w - 1.3, h: 0.4, fontFace: F.md, fontSize: 20, color: C.navy });
    if (body) text(slide, body, { x: x + 1.1, y: y + 0.66, w: w - 1.3, h: h - 0.8, fontSize: 14, color: C.text });
    return;
  }
  if (iconName) slide.addImage({ data: await icon(iconName, iconColor), x: x + 0.22, y: y + 0.2, w: 0.35, h: 0.35, altText: title });
  text(slide, title, { x: x + (iconName ? 0.67 : 0.22), y: y + 0.18, w: w - 0.9, h: 0.4, fontFace: F.md, fontSize: 17, color: C.navy,
    valign: "middle" });
  if (body) text(slide, body, { x: x + 0.22, y: y + 0.68, w: w - 0.44, h: h - 0.8, fontSize: 14, color: C.text,
    paraSpaceAfter: 4 });
}

function bullets(lines) { // 카드 본문 줄들(글머리표)
  return lines.map((l, i) => ({ text: l, options: { bullet: { indent: 12 }, breakLine: i < lines.length - 1 } }));
}

function table(slide, rows, { x, y, w, colW, fontSize = 12, rowH = 0.42 }) {
  const head = rows[0].map(t => ({ text: t, options: { bold: false, fontFace: F.md, color: C.white, fill: { color: C.navy } } }));
  const body = rows.slice(1).map((r, i) => r.map(t => ({ text: t, options: { fill: { color: i % 2 ? C.white : C.card } } })));
  slide.addTable([head, ...body], { x, y, w, colW, fontFace: F.rg, fontSize, color: C.text, valign: "middle",
    border: { type: "solid", pt: 0.5, color: C.line }, rowH, margin: [0.04, 0.1, 0.04, 0.1], autoPage: false });
}

function placeholder(slide, { x, y, w, h, label }) {
  slide.addShape("rect", { x, y, w, h, fill: { color: C.white }, line: { color: C.gray, width: 1.25, dashType: "dash" },
    objectName: "자리표시자" });
  text(slide, label, { x: x + 0.3, y: y + h / 2 - 0.5, w: w - 0.6, h: 1.0, align: "center", valign: "middle", fontSize: 14,
    color: C.gray });
}

// ------------------------------------------------------------------ 상세 매뉴얼
async function buildManual() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = "KOHOM 뉴스룸 사용자 매뉴얼";
  pres.author = "주택관리공단 전략과";
  pres.theme = { headFontFace: F.xb, bodyFontFace: F.rg };
  const CONTENT = { x: M, y: 1.75, w: SW - 2 * M, h: 7.5 - 1.75 - 0.55 };
  const SHOT = { x: M, y: 1.8, w: 7.55, h: 5.1 };
  const RIGHT = { x: 8.55, y: 1.85, w: SW - 8.55 - M };

  // 표지
  pres.addSection({ title: "표지·목차" });
  let s = pres.addSlide({ sectionTitle: "표지·목차" });
  s.background = { color: C.navy };
  s.addShape("rect", { x: 1.0, y: 2.0, w: 0.16, h: 2.7, fill: { color: C.amber }, line: { color: C.amber }, objectName: "앰버 세로 블록" });
  text(s, "언론보도 모니터링 앱", { x: 1.45, y: 2.0, w: 10, h: 0.4, fontFace: F.md, fontSize: 16, color: "C9D6E3" });
  text(s, "KOHOM 뉴스룸 사용자 매뉴얼", { x: 1.45, y: 2.45, w: 11, h: 0.95, fontFace: F.xb, fontSize: 44, color: C.white, valign: "middle" });
  text(s, "설치부터 매일 보고, AI 선별, 선정 규칙 환류까지", { x: 1.45, y: 3.5, w: 10, h: 0.4, fontSize: 16, color: "DCE5EE" });
  text(s, `${DATE} · 앱 v${VER} 기준 · 주택관리공단 전략과`, { x: 1.45, y: 4.2, w: 10, h: 0.35, fontSize: 12, color: "C9D6E3" });
  text(s, "※ 화면은 설명을 위한 시연 기사로 촬영했습니다. 실제 화면의 기사·건수는 다를 수 있으며, 수치·문구는 앱 화면이 우선합니다",
    { x: 1.0, y: 6.75, w: 11.3, h: 0.3, fontSize: 9.5, color: "AFC0D1" });
  s.addNotes("표지. 이 매뉴얼은 KOHOM 뉴스룸 v" + VER + " 화면을 기준으로 합니다. 화면 속 기사는 시연용으로 만든 것입니다.");

  // 목차
  s = pres.addSlide({ sectionTitle: "표지·목차" });
  header(s, { no: "00", part: "navy", kicker: "목차", title: "이 매뉴얼의 순서", sub: "처음 쓰는 직원은 01·02만 읽어도 매일 보고를 할 수 있습니다" });
  const toc = [
    ["01 시작하기", "설치·첫 실행·화면 구성", "LuDownload"],
    ["02 베이직", "조회 → 추천 확인 → 보고서 → 기록", "LuNewspaper"],
    ["03 프로", "AI 선별·순서 정하기·결과 엑셀", "LuSparkles"],
    ["04 선정 규칙", "키워드·점수·추천 기준과 환류", "LuSlidersHorizontal"],
    ["05 설정", "기사 출처·전문지·보고서·공휴일", "LuSettings"],
    ["06 문제 해결", "자주 묻는 것·확인 필요 사항", "LuWrench"],
  ];
  for (let i = 0; i < 6; i++) {
    const cx = M + (i % 3) * 4.1, cy = 1.95 + Math.floor(i / 3) * 2.45;
    await card(s, { x: cx, y: cy, w: 3.88, h: 2.2, title: toc[i][0], body: toc[i][1], iconName: toc[i][2], big: true,
      fill: i >= 5 ? C.amberBg : i >= 2 ? C.tealBg : C.card, iconColor: i >= 5 ? C.amber : i >= 2 ? C.teal : C.navy });
  }
  s.addNotes("목차. 01~02는 모든 사용자, 03~05는 언론보도 담당자, 06은 문제가 생겼을 때 봅니다.");

  // 01 시작하기
  pres.addSection({ title: "01 시작하기" });
  s = pres.addSlide({ sectionTitle: "01 시작하기" });
  header(s, { no: "01", part: "navy", kicker: "시작하기 · 한눈에 보기", title: "앱이 하는 일: 모으고, 거르고, 골라서, 보고서로",
    sub: "구글 뉴스·전문지에서 기사를 모아 선정 규칙으로 점수를 매기고, 추천 5건을 메일 보고서로 만듭니다" });
  const flow = [
    ["모으기", "구글 뉴스·전문지 RSS에서 키워드로", "LuSearch"],
    ["거르기", "제목 확인·제외 매체·행사·이미 보고", "LuFilter"],
    ["점수·분류", "공단·사업어·리스크로 점수", "LuGauge"],
    ["추천 ★", "리스크 먼저, 분류 고루 5건", "LuStar"],
    ["보고서", "메일에 붙일 제목·본문 복사", "LuMail"],
    ["기록", "보낸 기사는 다음 조회에서 빠짐", "LuHistory"],
  ];
  const fw = 1.78, fg = 0.29;
  for (let i = 0; i < 6; i++) {
    const fx = M + i * (fw + fg);
    await card(s, { x: fx, y: 2.0, w: fw, h: 2.35, title: flow[i][0], iconName: flow[i][2] });
    text(s, flow[i][1], { x: fx + 0.2, y: 2.7, w: fw - 0.4, h: 1.5, fontSize: 14 });
    if (i < 5) s.addShape("line", { x: fx + fw + 0.03, y: 3.17, w: fg - 0.06, h: 0, line: { color: C.amber, width: 3, endArrowType: "triangle" } });
  }
  await card(s, { x: M, y: 4.75, w: SW - 2 * M, h: 1.75, fill: C.tealBg, iconName: "LuRepeat", iconColor: C.teal,
    title: "환류: 규칙은 앱이 아니라 담당자가 고칩니다",
    body: "결과 엑셀을 내려받아 Claude에 보내면 규칙 개선안(JSON)이 돌아옵니다. [선정 규칙] 탭에 붙여 넣으면 바뀔 항목을 보여 준 뒤 적용하고, 변경 이력에 남습니다. 앱을 업데이트하지 않아도 다음 조회부터 바로 반영됩니다." });
  s.addNotes("앱 전체 흐름. 모으기부터 기록까지 6단계이고, 아래 환류는 담당자가 규칙을 개선하는 고리입니다. 자세한 것은 04장.");

  s = pres.addSlide({ sectionTitle: "01 시작하기" });
  header(s, { no: "01", part: "navy", kicker: "시작하기 · 설치", title: "설치와 첫 실행", sub: "설치 프로그램이 없는 exe 파일 하나입니다. 폴더에 넣고 실행하면 됩니다" });
  const inst = [
    ["내려받기", ["GitHub Releases 또는 공문 안내 경로", "파일: NewsMonitor_v버전.exe", "C:\\NewsMonitor 같은 폴더에 넣기"], "LuDownload"],
    ["윈도우 경고가 뜰 때", ["경고 창에서 [추가 정보] → [실행]", "또는 파일 오른쪽 클릭 → 속성 → '차단 해제' 체크", "코드 서명이 없어 뜨는 안내입니다"], "LuShieldAlert"],
    ["설정·기록 저장 위치", ["exe 옆에 config.json(설정·규칙)", "sent_history.json(보고 기록)", "reports\\ (보고서) — 내 PC에만 저장"], "LuFolderOpen"],
    ["업데이트", ["켤 때 새 버전을 알려 줌 → [예]", "GitHub이 막힌 PC: 안내 창이 뜸", "→ 공문 경로에서 새 파일로 바꾸기"], "LuRefreshCw"],
  ];
  for (let i = 0; i < 4; i++) {
    const cx = M + (i % 2) * 3.82, cy = 1.85 + Math.floor(i / 2) * 2.6;
    await card(s, { x: cx, y: cy, w: 3.66, h: 2.42, title: inst[i][0], body: bullets(inst[i][1]), iconName: inst[i][2],
      fill: i === 1 ? C.amberBg : C.card, iconColor: i === 1 ? C.amber : C.navy });
  }
  placeholder(s, { x: 8.4, y: 1.85, w: SW - 8.4 - M, h: 5.02,
    label: "[화면 넣을 자리]\n윈도우 'PC 보호' 경고 창\n(추가 정보 → 실행)\n\n담당자 PC에서 처음 실행할 때 찍어 넣기\n권장 크기 4.3 × 5.0in" });
  s.addNotes("설치. 윈도우 경고(SmartScreen)는 자동 촬영 PC에서 뜨지 않아 화면을 넣지 못했습니다. 처음 실행할 때 경고 창을 찍어(Win+Shift+S) 오른쪽 점선 자리에 넣고 자리표시자는 지워 주세요. 권장 크기 4.3×5.0in.");

  s = pres.addSlide({ sectionTitle: "01 시작하기" });
  header(s, { no: "01", part: "navy", kicker: "시작하기 · 화면 구성", title: "화면 구성: 탭 5개와 상태줄", sub: "위쪽 탭으로 일을 고르고, 아래 상태줄에서 진행 상황을 봅니다" });
  shot(s, "01_basic_empty", SHOT, [["tabs", 1], ["update", 2], ["steps", 3], ["search", 4], ["status", 5]]);
  explain(s, [
    [1, "탭", "베이직(매일 보고) · 프로(AI 선별) · 보고 기록 · 선정 규칙 · 설정"],
    [2, "업데이트 확인", "새 버전이 있으면 받아서 스스로 바꿉니다"],
    [3, "단계 표시", "베이직의 ①~④ 중 지금 할 일이 진하게"],
    [4, "조회", "다음에 누를 버튼 하나만 진한 색"],
    [5, "상태줄", "진행 중·완료·오류(빨강)를 한 줄로 알려 줌"],
  ], RIGHT);
  s.addNotes("화면 구성. 탭은 베이직·프로·보고 기록·선정 규칙·설정 다섯 개입니다. 처음 켜면 베이직 탭이 열립니다.");

  // 02 베이직
  pres.addSection({ title: "02 베이직" });
  s = pres.addSlide({ sectionTitle: "02 베이직" });
  header(s, { no: "02", part: "navy", kicker: "베이직 · ① 조회", title: "① 조회: 기간은 자동, [조회]만 누르기",
    sub: "기간은 직전 영업일 오전 9시부터 지금까지로 자동 설정됩니다(공휴일 반영)" });
  shot(s, "02_basic_busy", SHOT, [["stop", 1], ["status", 2]]);
  explain(s, [
    [0, "기간", "[자동]이 기본. 필요하면 [오늘]·[최근 3일]이나 날짜를 직접 고칩니다"],
    [0, "[① 조회]", "구글 뉴스와 전문지에서 키워드별로 기사를 모읍니다(1~2분)"],
    [1, "■ 정지", "설정을 빠뜨렸다면 누르세요. 지금 묻는 키워드 하나가 끝나면 멈춥니다"],
    [2, "상태줄", "몇 번째 키워드인지, 지금까지 몇 건 모았는지 보여 줍니다"],
  ], RIGHT);
  s.addNotes("조회. 키워드가 67개라 1~2분 걸릴 수 있습니다(추정). 정지는 조회 중에만 켜집니다. 멈추면 모은 결과는 비웁니다.");

  s = pres.addSlide({ sectionTitle: "02 베이직" });
  header(s, { no: "02", part: "navy", kicker: "베이직 · ② 추천 확인", title: "② ★추천 확인하고 순서 정하기",
    sub: "추천 5건이 미리 선택됩니다. 더하고 빼고, 끌어서 순서를 정하면 그 순서대로 보고서에 실립니다" });
  shot(s, "03_basic_result", SHOT, [["check", 1], ["col_no", 2], ["row_selected", 3], ["updown", 4], ["reset", 5], ["addlink", 6]]);
  explain(s, [
    [1, "선택 칸", "☑ 누르면 넣고 빼기. ★는 앱 추천"],
    [2, "순번", "조회 때 매긴 고정 번호(정렬해도 그대로)"],
    [3, "끌어 놓기", "제목 칸을 누른 채 위아래로 끌어 순서 변경"],
    [4, "▲ ▼", "줄을 누른 뒤 한 칸씩 이동(Ctrl+↑↓)"],
    [5, "추천으로 되돌리기", "고친 선택을 처음 추천대로"],
    [6, "기사 링크로 추가", "검색에 없는 기사를 주소로 넣기"],
  ], { ...RIGHT, gap: 0.08 });
  s.addNotes("추천 확인. 줄 바탕색: 연한 주황 = 공단(A) 기사, 연한 청록 = 직접 추가. 기사 제목을 더블클릭하면 원문이 열립니다. 끌어 놓기는 체크 칸이 아닌 곳을 잡고 끕니다.");

  s = pres.addSlide({ sectionTitle: "02 베이직" });
  header(s, { no: "02", part: "navy", kicker: "베이직 · ③ 보고서", title: "③ HTML 보고서 열고 복사하기",
    sub: "[③ HTML 보고서 열기]를 누르면 브라우저에 메일용 보고서가 열립니다" });
  if (G.shots["04_report"]) {
    shot(s, "04_report", SHOT, [["subject_copy", 1], ["body1_copy", 2], ["body1", 3], ["body2", 4]]);
  } else {
    placeholder(s, { ...SHOT, label: "[보고서 화면]" });
  }
  explain(s, [
    [1, "제목 복사", "편지쓰기 '제목' 칸에 붙여넣기. 예: (261026)언론보도"],
    [2, "본문 복사", "본문 ①·② 중 하나를 골라 복사"],
    [3, "본문 ① 기존 양식", "링크 걸린 기사 제목만, 표 순서대로"],
    [4, "본문 ② 분류 포함", "분류·키워드별 묶음과 매체·날짜, AI 인사이트"],
  ], RIGHT);
  s.addNotes("보고서. 복사한 본문은 글자 크기 16px로 그룹웨어에 붙습니다. 원문 주소를 못 찾은 기사는 구글 경유 주소로 들어갑니다.");

  s = pres.addSlide({ sectionTitle: "02 베이직" });
  header(s, { no: "02", part: "navy", kicker: "베이직 · ③ 메일 보내기", title: "그룹웨어 편지쓰기에 붙여넣기",
    sub: "제목과 본문을 붙여 넣고 받는 사람을 지정해 보냅니다" });
  placeholder(s, { x: M, y: 1.85, w: 7.55, h: 5.0,
    label: "[화면 넣을 자리]\n그룹웨어 편지쓰기 화면\n(제목·본문에 붙여 넣은 모습)\n\n권장 크기 7.5 × 5.0in" });
  await card(s, { x: 8.55, y: 1.85, w: SW - 8.55 - M, h: 2.5, title: "붙여넣기 순서", iconName: "LuClipboardPaste",
    body: bullets(["보고서 [제목 복사] → 제목 칸 Ctrl+V", "[본문 복사] → 본문 칸 Ctrl+V", "받는 사람 지정 → 보내기"]) });
  await card(s, { x: 8.55, y: 4.55, w: SW - 8.55 - M, h: 2.3, title: "보낸 뒤 꼭", iconName: "LuCircleCheck", fill: C.amberBg, iconColor: C.amber,
    body: bullets(["앱으로 돌아와 [④ 보고 완료로 기록]", "기록해야 다음 조회에서 빠집니다"]) });
  s.addNotes("그룹웨어 화면은 사내 시스템이라 자동 촬영을 못 했습니다. 편지쓰기 화면을 찍어 왼쪽 점선 자리에 넣고 자리표시자는 지워 주세요.");

  s = pres.addSlide({ sectionTitle: "02 베이직" });
  header(s, { no: "02", part: "navy", kicker: "베이직 · ④ 기록", title: "④ 보고 완료로 기록 · 보고 기록 탭",
    sub: "보낸 기사는 날짜별로 3년 보관되고, 다음 조회에서 자동으로 빠집니다" });
  shot(s, "05_history", SHOT, [["days", 1], ["records", 2], ["reopen", 3], ["remove", 4], ["import", 5]]);
  explain(s, [
    [1, "보고일 목록", "날짜를 누르면 그날 보낸 기사"],
    [2, "기사 목록", "더블클릭하면 원문이 열립니다"],
    [3, "보고서 다시 열기", "그날 메일 본문을 다시 복사"],
    [4, "기록 취소", "잘못 기록한 기사 → 다음 조회에 다시 나옴"],
    [5, "지난 보고 메일 불러오기", "그룹웨어에서 저장한 메일(HTML·EML)을 기록으로"],
  ], RIGHT);
  s.addNotes("보고 기록. [④ 보고 완료로 기록]을 누르면 이 탭에 쌓입니다. 앱을 쓰기 전에 보낸 메일도 불러올 수 있습니다.");

  // 03 프로
  pres.addSection({ title: "03 프로" });
  s = pres.addSlide({ sectionTitle: "03 프로" });
  header(s, { no: "03", part: "teal", kicker: "프로 · 화면", title: "프로 탭: 후보 전체를 보고 직접 고르기",
    sub: "언론보도 담당자용. 등급·점수·분류를 보고 고르며, AI 선별을 함께 쓸 수 있습니다" });
  shot(s, "06_pro_result", SHOT, [["options", 1], ["keywords", 2], ["select_tools", 3], ["order_tools", 4], ["col_grade", 5], ["ai_steps", 6]]);
  explain(s, [
    [1, "조회 조건", "이미 보고한 기사 제외·같은 사안 묶기·단순 행사 제외"],
    [2, "키워드 요약", "고치려면 [선정 규칙에서 고치기 ›]"],
    [3, "선택 도구", "전체·★추천만·키워드별로 선택"],
    [4, "순서", "선택 항목 맨 위로, ▲▼, 끌어 놓기"],
    [5, "등급·점수·분류", "머리글을 누르면 그 열로 정렬"],
    [6, "①~④ 단계", "AI 선별 → 보고서 → 기록"],
  ], { ...RIGHT, gap: 0.08 });
  s.addNotes("프로 탭. 처음에는 후보 전체가 선택된 채로 나옵니다. 베이직과 같은 기사를 보지만 선택은 따로입니다.");

  s = pres.addSlide({ sectionTitle: "03 프로" });
  header(s, { no: "03", part: "teal", kicker: "프로 · 읽는 법", title: "등급·분류 읽는 법", sub: "등급은 '왜 후보가 됐는지', 분류는 '무엇에 관한 기사인지'입니다" });
  table(s, [
    ["등급", "뜻", "기본 점수"],
    ["A", "제목에 '주택관리공단'(또는 KOHOM)", "+50"],
    ["A?", "지사명만 있고 공단 이름은 없음 — 공단 기사인지 확인(추천 안 함)", "+20"],
    ["S", "공단 업무를 가리키는 말(영구임대·공공임대·주거급여 등)", "+30 (2개 +40)"],
    ["B", "주거·공동주택 정책 환경(LH·층간소음·경영평가 등)", "+10"],
    ["전문지", "아파트관리신문·한국아파트신문 — 키워드 없이도 후보", "+15"],
    ["직접", "[기사 링크로 추가]로 넣은 기사 — 항상 포함", "—"],
  ], { x: M, y: 1.85, w: 7.3, colW: [0.95, 4.95, 1.4], fontSize: 12, rowH: 0.62 });
  table(s, [
    ["분류(위부터)", "조건"],
    ["리스크", "리스크어(사고·체납·징계 등) + 공단 관련 주제"],
    ["기관 직접", "공단(A) 기사"],
    ["정책·제도", "개정·시행령 등 정책어, 주거급여 등"],
    ["모회사·부처", "LH·국토부 관련"],
    ["공공기관 공통", "경영평가·청렴도·산하기관"],
    ["업계·환경", "그 밖(공고 기사 포함)"],
  ], { x: 8.2, y: 1.85, w: SW - 8.2 - M, colW: [1.55, SW - 8.2 - M - 1.55], fontSize: 12, rowH: 0.62 });
  s.addNotes("등급과 분류. 점수는 선정 규칙 탭에서 바꿀 수 있습니다. 리스크어는 공단 관련 주제와 함께 있을 때만 점수가 붙어, 일반 뉴스의 '화재'·'수사'에는 붙지 않습니다.");

  s = pres.addSlide({ sectionTitle: "03 프로" });
  header(s, { no: "03", part: "teal", kicker: "프로 · AI 선별", title: "AI 선별: 요청문 복사 → Claude → 결과 붙여넣기",
    sub: "앱이 AI를 직접 부르지 않습니다. 담당자가 복사·붙여넣기로 이어 줍니다" });
  shot(s, "07_paste_dialog", { x: M, y: 1.95, w: 7.3, h: 4.9 }, [["text", 3], ["apply", 4]]);
  explain(s, [
    [1, "[① AI 선별 요청문 복사]", "선택된 기사들이 순번과 함께 복사됩니다"],
    [2, "Claude 프로젝트에 붙여넣기", "판단 기준서가 들어 있는 프로젝트 채팅에 Ctrl+V → 보내기"],
    [3, "[② 선정 결과 붙여넣기]", "답변의 '#선정' 아래 줄(번호|분류|인사이트)을 붙여 넣기"],
    [4, "[적용]", "고른 기사만 선택되고 분류·인사이트가 붙어 맨 위로"],
  ], RIGHT);
  s.addNotes("AI 선별. 번호는 표의 '순번'과 같아서, Claude가 말하는 번호를 표에서 바로 찾을 수 있습니다. 답변 전체를 붙여 넣어도 됩니다.");

  s = pres.addSlide({ sectionTitle: "03 프로" });
  header(s, { no: "03", part: "teal", kicker: "프로 · 순서와 보고서", title: "순서를 정하면 그대로 보고서에",
    sub: "선택한 기사를 맨 위로 모은 뒤 중요한 순서로 끌어 놓습니다" });
  shot(s, "08_pro_after_ai", SHOT, [["order_tools", 1], ["col_no", 2], ["top_rows", 3], ["report", 4]]);
  explain(s, [
    [1, "순서 줄", "[☑ 선택 항목 맨 위로] · [▲ 위로] · [▼ 아래로]"],
    [2, "순번", "AI가 말한 번호와 같은 번호"],
    [3, "선택한 기사", "끌어 놓아 중요한 순서로"],
    [4, "[③ HTML 보고서 열기]", "본문 ①은 표 순서 그대로, ②는 분류 묶음을 처음 나오는 순서로"],
  ], RIGHT);
  s.addNotes("순서 정하기. 보고서는 표에 보이는 순서(체크한 기사만)를 따릅니다. 정렬 머리글을 누르면 순서가 다시 바뀌니, 순서를 정한 뒤에는 머리글을 누르지 마세요.");

  s = pres.addSlide({ sectionTitle: "03 프로" });
  header(s, { no: "03", part: "teal", kicker: "프로 · 결과 엑셀", title: "결과 엑셀: 앱 판단과 내 판단을 나란히",
    sub: "프로 탭 왼쪽 아래 [⤓ 결과 엑셀로 내려받기] — 규칙 개선(환류)의 재료입니다" });
  table(s, [
    ["시트", "담긴 것", "쓰는 곳"],
    ["조회결과", "표의 기사 전부, 프로·베이직 최종 선택, ★추천, 등급·점수·항목별 점수, 점수 근거, 분류", "앱 판단 vs 사람 판단 비교"],
    ["빠진 기사", "제외 매체·제목 검증 실패·제외어·행사·이미 보고·같은 사안 묶음과 그 이유", "놓친 기사 찾기"],
    ["조회 조건", "기간·검색 방식·전문지·옵션·건수 흐름", "그날 조건 확인"],
    ["선정 규칙", "조회한 그때의 규칙 전체(규칙 JSON 포함)", "Claude가 고칠 원본"],
  ], { x: M, y: 1.95, w: SW - 2 * M, colW: [1.6, 7.0, SW - 2 * M - 8.6], fontSize: 13, rowH: 0.75 });
  await card(s, { x: M, y: 5.95, w: SW - 2 * M, h: 0.95, fill: C.tealBg, iconName: "LuFileSpreadsheet", iconColor: C.teal,
    title: "파일 이름: KOHOM뉴스룸_조회결과_날짜_시분.xlsx — 네이버 키 같은 비밀값은 넣지 않습니다" });
  s.addNotes("결과 엑셀. 며칠 치를 모아 Claude에 보내면 개선안이 더 정확합니다. 엑셀 화면은 자동 촬영 PC에 엑셀이 없어 표로 대신했습니다.");

  // 04 선정 규칙
  pres.addSection({ title: "04 선정 규칙" });
  s = pres.addSlide({ sectionTitle: "04 선정 규칙" });
  header(s, { no: "04", part: "teal", kicker: "선정 규칙 · 화면", title: "선정 규칙 탭: 키워드·점수·추천 기준",
    sub: "고치고 [규칙 저장]을 누르면 다음 조회부터 적용됩니다. 앱 업데이트가 필요 없습니다" });
  shot(s, "09_rules_top", SHOT, [["kw_a", 1], ["kw_s", 2], ["kw_b", 3], ["request", 4], ["files", 5], ["save", 6]]);
  explain(s, [
    [1, "A 기관 직접", "제목에 있으면 무조건 후보"],
    [2, "S 사업어", "공단 업무를 가리키는 말"],
    [3, "B 환경", "주거·공동주택 정책 환경"],
    [4, "환류 버튼", "개선 요청문 복사 · Claude 답변 붙여넣기"],
    [5, "규칙 파일", "내보내기·불러오기(다른 PC와 공유)·기본값으로"],
    [6, "규칙 저장", "저장하면 변경 이력에 남음"],
  ], { ...RIGHT, gap: 0.08 });
  s.addNotes("키워드 쓰는 법: 한 줄에 하나. 띄어 쓴 말은 같은 순서로 20자 안에 있으면 맞음(공동주택 관리비). 같은 뜻은 OR로 한 줄에(승강기 OR 엘리베이터). -말은 빼기(임대주택 -민간임대). \"따옴표\"는 문구 그대로.");

  s = pres.addSlide({ sectionTitle: "04 선정 규칙" });
  header(s, { no: "04", part: "teal", kicker: "선정 규칙 · 점수와 추천", title: "점수와 추천 기준도 숫자 칸에서",
    sub: "가중치 숫자와 단어 목록을 고치면 점수·분류·★추천이 바로 다시 계산됩니다" });
  shot(s, "10_rules_score", SHOT, [["weights", 1], ["words", 2]]);
  explain(s, [
    [1, "가중치", "A 50 · S 30 · 모회사 20 · B 10 · 리스크 20 · 정책 10 · 공고 −25 등"],
    [2, "단어 목록", "리스크어는 공단 관련 주제와 함께일 때만 점수"],
    [0, "⑤ 추천(아래쪽)", "추천 5건 · 최소 30점 · 리스크 먼저 2건 · 공단 최소 1건 · 같은 분류 2건(업계·환경 1건)"],
  ], RIGHT);
  s.addNotes("점수와 추천 기준. 감점은 음수로 적습니다. 공고 기사(공단 기사 제외)와 지사명만 있는 기사(A?)는 추천하지 않습니다.");

  s = pres.addSlide({ sectionTitle: "04 선정 규칙" });
  header(s, { no: "04", part: "teal", kicker: "선정 규칙 · 환류", title: "환류: 결과 엑셀 → Claude → 규칙 붙여넣기",
    sub: "앱의 판단과 담당자의 판단이 어긋난 곳이 곧 규칙을 고칠 곳입니다" });
  shot(s, "11_rules_preview", { x: 7.05, y: 1.95, w: SW - 7.05 - M, h: 4.9 }, [["apply", 5]], { alignRight: true });
  const loop = [
    ["프로 탭 [⤓ 결과 엑셀로 내려받기]", "며칠 치를 모으면 더 정확"],
    ["선정 규칙 [개선 요청문 복사]", "지금 규칙(JSON)이 함께 복사됨"],
    ["Claude 대화창에 붙여넣기 + 엑셀 첨부", "개선 요청문이 답변 형식을 알려 줌"],
    ["[Claude 답변 붙여넣기] → [다음]", "바뀔 항목을 먼저 보여 줌"],
    ["[적용]", "저장 + 변경 이력에 '언제·무엇을' 남김"],
  ];
  let ly = 1.95;
  for (let i = 0; i < 5; i++) {
    text(s, N[i] + " " + loop[i][0], { x: M, y: ly, w: 6.2, h: 0.36, fontFace: F.md, fontSize: 15, color: C.navy });
    text(s, loop[i][1], { x: M + 0.36, y: ly + 0.38, w: 5.9, h: 0.3, fontSize: 14, color: C.gray });
    ly += 0.98;
  }
  s.addNotes("환류. 변경 이력은 선정 규칙 탭 맨 아래에 최근 3건, 전체는 [변경 이력 보기]. 마음에 안 들면 [기본값으로]나 규칙 파일 불러오기로 되돌릴 수 있습니다.");

  // 05 설정
  pres.addSection({ title: "05 설정" });
  s = pres.addSlide({ sectionTitle: "05 설정" });
  header(s, { no: "05", part: "teal", kicker: "설정", title: "설정: 기사 출처·보고서·공휴일", sub: "바꾼 값은 [설정 저장]을 눌러야 적용됩니다" });
  shot(s, "13_settings", SHOT, [["source", 1], ["report_title", 2], ["rules_link", 3], ["holidays", 4], ["save", 5]]);
  explain(s, [
    [1, "기사 출처", "구글 뉴스(키 불필요)가 기본. 전문지 RSS 함께 조회"],
    [2, "보고서", "메일 제목 {날짜} → 261026 · 보고서 제목"],
    [3, "선정 규칙", "키워드·점수는 선정 규칙 탭에서"],
    [4, "공휴일", "자동 기간 계산용. 임시공휴일은 한 줄 추가"],
    [5, "설정 저장", "이 PC의 config.json에만 저장"],
  ], RIGHT);
  s.addNotes("설정. 네이버 API는 키가 있을 때만 씁니다(신규 발급 종료). 모든 값은 이 PC에만 저장되고 어디로도 보내지 않습니다.");

  s = pres.addSlide({ sectionTitle: "05 설정" });
  header(s, { no: "05", part: "teal", kicker: "설정 · 전문지 고르기", title: "전문지 고르기: 홈페이지 주소만 넣으면",
    sub: "[설정] → [전문지 고르기 ›]. RSS 주소를 몰라도 홈페이지 주소로 찾아 연결까지 확인합니다" });
  shot(s, "14_feeds", { x: M, y: 1.95, w: 7.3, h: 4.9 }, [["list", 1], ["input", 2], ["add", 3], ["check", 4]]);
  explain(s, [
    [1, "매체 목록", "첫 칸을 눌러 켜고 끄기"],
    [2, "매체·주소 칸", "예: www.aptn.co.kr (매체 칸은 비워도 됨)"],
    [3, "＋ 추가", "/rss/allArticle.xml을 붙여 찾아 줌"],
    [4, "연결 확인", "RSS가 받아지는지 바로 확인"],
  ], RIGHT);
  s.addNotes("전문지 고르기. 국내 신문사 다수가 같은 기사관리 프로그램을 써서 홈페이지 주소 + /rss/allArticle.xml이 RSS 주소입니다. 안 되면 신문사 홈페이지 맨 아래 RSS 메뉴에서 주소를 복사해 넣습니다.");

  // 06 문제 해결
  pres.addSection({ title: "06 문제 해결" });
  s = pres.addSlide({ sectionTitle: "06 문제 해결" });
  header(s, { no: "06", part: "amber", kicker: "문제 해결", title: "이럴 때는 이렇게", sub: "상태줄이 빨갛게 바뀌면 오류입니다. 아래에서 찾아보세요" });
  table(s, [
    ["증상", "원인", "조치"],
    ["처음 실행 때 윈도우 경고", "코드 서명이 없는 프로그램", "[추가 정보] → [실행], 또는 속성 → 차단 해제"],
    ["업데이트 확인 실패 안내", "GitHub 접속이 막힌 PC", "공문 경로에서 새 exe를 받아 바꾸기(설정·기록 유지)"],
    ["'호출이 너무 많습니다(429)'", "짧은 시간에 구글에 많이 물음", "잠시 뒤 다시 조회. 계속되면 키워드 줄이기"],
    ["조회가 오래 걸림", "키워드가 많음(지금 67개)", "■ 정지 후 기간 줄이기, 효과 없는 키워드 빼기"],
    ["'전문지 조회 실패: ○○'", "RSS 주소가 바뀜·막힘", "전문지 고르기에서 [연결 확인] → 주소 다시 찾기"],
    ["엉뚱한 기사가 추천됨", "규칙이 그날 기사와 안 맞음", "결과 엑셀 → Claude 환류로 빼는 말(-○○) 추가"],
    ["보고한 기사가 또 나옴", "④ 보고 완료로 기록을 안 함", "보낸 뒤 꼭 기록. 지난 메일은 불러오기로"],
  ], { x: M, y: 1.85, w: SW - 2 * M, colW: [3.0, 3.6, SW - 2 * M - 6.6], fontSize: 13, rowH: 0.6 });
  s.addNotes("문제 해결. 해결이 안 되면 상태줄 문구와 화면을 찍어 전략과로 보내 주세요.");

  s = pres.addSlide({ sectionTitle: "06 문제 해결" });
  header(s, { no: "06", part: "amber", kicker: "확인 필요 사항", title: "확인 필요 사항", sub: "이 매뉴얼에서 확인하지 못했거나 추정한 내용입니다" });
  const todo = [
    ["미확인 — 화면", ["윈도우 경고 창(설치 장), 그룹웨어 편지쓰기(메일 보내기 장)는 자동 촬영이 안 돼 자리표시자로 둠 — 담당자 PC에서 찍어 넣고 자리표시자 삭제",
      "결과 엑셀 화면은 표로 대신함"]],
    ["(추정) — 시간·글꼴", ["조회 시간 1~2분은 키워드 67개 기준 추정",
      "이 PPT는 에스코어 드림 글꼴로 지정 — 글꼴이 없는 PC에서는 대체 글꼴로 보여 줄바꿈이 다를 수 있음"]],
    ["시연 자료", ["화면 속 기사·건수·날짜는 설명용 시연 자료(실제 기사 아님)",
      "앱 v" + VER + " 기준 — 앱이 바뀌면 Actions 'manual'로 화면을 다시 찍어 갱신"]],
    ["전문지", ["대한경제·한국주택경제신문 RSS 주소 미확인", "전기신문 RSS는 꺼 둠(전문지 고르기에서 켤 수 있음)"]],
  ];
  for (let i = 0; i < 4; i++) {
    const cx = M + (i % 2) * 6.12, cy = 1.85 + Math.floor(i / 2) * 2.55;
    await card(s, { x: cx, y: cy, w: 5.94, h: 2.38, title: todo[i][0], body: bullets(todo[i][1]), iconName: i ? "LuInfo" : "LuTriangleAlert",
      fill: C.amberBg, iconColor: C.amber });
  }
  s.addNotes("확인 필요 사항. 자리표시자 2곳은 보고 전 화면을 넣거나 지워 주세요.");

  const file = path.join(OUT, "2026_KOHOM뉴스룸_사용자매뉴얼_설명자료.pptx");
  await pres.writeFile({ fileName: file });
  return file;
}

// ------------------------------------------------------------------ 한 장 요약
async function buildSummary() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = "KOHOM 뉴스룸 한 장 요약";
  pres.author = "주택관리공단 전략과";
  pres.theme = { headFontFace: F.xb, bodyFontFace: F.rg };
  pres.addSection({ title: "한 장 요약" });
  let s = pres.addSlide({ sectionTitle: "한 장 요약" });
  header(s, { no: "01", part: "amber", kicker: "KOHOM 뉴스룸 · 한 장 요약", title: "매일 언론보도 보고, 버튼 네 번이면 끝",
    sub: `베이직 탭 기준 · 앱 v${VER} · 설치는 exe 파일 하나(윈도우 경고가 뜨면 [추가 정보] → [실행])` });
  const steps = [
    ["① 조회", ["기간은 자동(직전 영업일 9시~)", "[① 조회] 누르기", "잘못 눌렀으면 ■ 정지"], "LuSearch"],
    ["② 추천 확인", ["★추천 5건이 미리 선택", "☑로 넣고 빼기", "제목을 끌어 순서 정하기"], "LuStar"],
    ["③ 보고서", ["[③ HTML 보고서 열기]", "[제목 복사]·[본문 복사]", "그룹웨어 편지쓰기에 붙여넣기"], "LuMail"],
    ["④ 기록", ["메일을 보낸 뒤", "[④ 보고 완료로 기록]", "다음 조회에서 자동 제외"], "LuCircleCheck"],
  ];
  const w = (SW - 2 * M - 3 * 0.3) / 4;
  for (let i = 0; i < 4; i++) {
    const x = M + i * (w + 0.3);
    await card(s, { x, y: 1.95, w, h: 2.75, title: steps[i][0], body: bullets(steps[i][1]), iconName: steps[i][2] });
    if (i < 3) s.addShape("line", { x: x + w + 0.03, y: 3.3, w: 0.24, h: 0, line: { color: C.amber, width: 3, endArrowType: "triangle" } });
  }
  const tips = [
    ["업데이트", "켤 때 새 버전 알림 → [예]. GitHub이 막힌 PC는 공문 경로에서 새 파일로", "LuRefreshCw"],
    ["기사 추가", "검색에 없는 기사는 [＋ 기사 링크로 추가]에 주소 붙여넣기", "LuNewspaper"],
    ["지난 기록", "[보고 기록] 탭에서 날짜별 확인·보고서 다시 열기", "LuHistory"],
  ];
  const tw = (SW - 2 * M - 2 * 0.3) / 3;
  for (let i = 0; i < 3; i++) {
    await card(s, { x: M + i * (tw + 0.3), y: 4.95, w: tw, h: 1.95, title: tips[i][0], body: tips[i][1], iconName: tips[i][2], fill: C.tealBg,
      iconColor: C.teal });
  }
  s.addNotes("한 장 요약. 전 직원 배포용. 자세한 내용은 사용자 매뉴얼(상세)을 보세요.");
  const file = path.join(OUT, "2026_KOHOM뉴스룸_한장요약_설명자료.pptx");
  await pres.writeFile({ fileName: file });
  return file;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  console.log(await buildManual());
  console.log(await buildSummary());
})();
