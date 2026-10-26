"""사용자 매뉴얼용 화면 찍기 — 시연 기사로 앱을 차례로 조작하며 PNG 와 '위치표(geometry.json)'를 남긴다.

GitHub Actions 윈도우(manual.yml)에서 돌린다(실제 글꼴·배율). 개발 PC(리눅스, xvfb)에서도 돌아간다.
- 인터넷 조회는 시연 기사(demo_data.py)로 바꿔 치고, 대화상자(예/아니요)는 자동으로 '예'.
- 위치표: 화면마다 설명 번호를 붙일 곳(버튼·표·칸)의 [x, y, 너비, 높이] — 그림 왼쪽 위가 (0, 0).
  매뉴얼 PPT(build_deck.js)가 이 값으로 그림 위에 번호 표시를 얹는다.
- HTML 보고서 화면은 브라우저(윈도우: Edge, 리눅스: Chromium)로 찍고 버튼 위치도 같이 남긴다.
사용: python tools/manual/capture.py [출력 폴더]   (기본: manual_shots)
"""

import datetime as dt
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "manual_shots")
os.makedirs(OUT, exist_ok=True)
tmp = tempfile.mkdtemp()

import config  # noqa: E402
import demo_data  # noqa: E402
import feeds  # noqa: E402
import google_news  # noqa: E402
import history  # noqa: E402
import report  # noqa: E402
import updater  # noqa: E402
import webbrowser  # noqa: E402

config.CONFIG_PATH = os.path.join(tmp, "config.json")
history.HISTORY_PATH = os.path.join(tmp, "sent.json")
report.REPORT_DIR = os.path.join(tmp, "reports")
updater.check_latest = lambda timeout=10: "test"
opened: list[str] = []
webbrowser.open = lambda u: opened.append(u)
google_news.search_news = demo_data.fake_search
feeds.search_feeds = demo_data.fake_feeds
google_news.resolve_links = lambda urls, progress=None: {u: demo_data.real_link(u) for u in urls}
json.dump(demo_data.SENT_BEFORE, open(history.HISTORY_PATH, "w", encoding="utf-8"), ensure_ascii=False)

import app as appmod  # noqa: E402
from PIL import ImageGrab  # noqa: E402


class SyncThread:  # 조회·보고서 일을 바로 끝내게(화면 찍기 순서가 꼬이지 않게)
    def __init__(self, target, args=(), daemon=None):
        self.t, self.a = target, args

    def start(self):
        self.t(*self.a)


ORIG_THREAD = appmod.threading.Thread
appmod.threading.Thread = SyncThread
appmod.messagebox.askyesno = lambda *a, **k: True
appmod.messagebox.showinfo = appmod.messagebox.showwarning = lambda *a, **k: None

W, H = 1280, 800
a = appmod.App()
a.geometry(f"{W}x{H}+0+0")
GEO: dict[str, dict] = {}


def settle(n=4):
    for _ in range(n):
        a.update()
        time.sleep(0.12)


def box(w, base) -> list[int]:
    """위젯 w 의 [x, y, 너비, 높이] — base(창) 왼쪽 위 기준."""
    w.update_idletasks()
    return [w.winfo_rootx() - base.winfo_rootx(), w.winfo_rooty() - base.winfo_rooty(), w.winfo_width(), w.winfo_height()]


def find(root, text: str, cls: str | None = None):
    """글자가 text 로 시작하는 위젯(버튼·라벨) 하나."""
    stack = [root]
    while stack:
        w = stack.pop(0)
        try:
            t = str(w.cget("text"))
        except Exception:
            t = ""
        if t.startswith(text) and (cls is None or w.winfo_class() == cls):
            return w
        stack.extend(w.winfo_children())
    raise LookupError(text)


def union(*bs) -> list[int]:
    x0 = min(b[0] for b in bs); y0 = min(b[1] for b in bs)
    x1 = max(b[0] + b[2] for b in bs); y1 = max(b[1] + b[3] for b in bs)
    return [x0, y0, x1 - x0, y1 - y0]


def tree_col(tree, col: str, base) -> list[int]:
    """표 머리글 한 칸의 위치."""
    x0 = tree.winfo_rootx() - base.winfo_rootx()
    y0 = tree.winfo_rooty() - base.winfo_rooty()
    cols = ["#0"] + list(tree["columns"])
    x = x0
    for c in cols:
        wdt = tree.column(c, "width")
        if c == col:
            first = tree.get_children()
            head_h = tree.bbox(first[0])[1] if first and tree.bbox(first[0]) else 28
            return [x, y0, wdt, head_h]
        x += wdt
    raise LookupError(col)


def tree_row(tree, iid, base) -> list[int]:
    x, y, w, h = tree.bbox(iid)
    return [tree.winfo_rootx() - base.winfo_rootx() + x, tree.winfo_rooty() - base.winfo_rooty() + y, w, h]


def shot(name: str, marks: dict[str, list[int]], win=None):
    win = win or a
    settle()
    x, y = win.winfo_rootx(), win.winfo_rooty()
    img = ImageGrab.grab(bbox=(x, y, x + win.winfo_width(), y + win.winfo_height()))
    img.save(os.path.join(OUT, f"{name}.png"))
    GEO[name] = {"size": [img.width, img.height], "marks": marks}
    print("찍음:", name, img.size, list(marks))


def walk(root):
    out, stack = [], [root]
    while stack:
        w = stack.pop(0)
        out.append(w)
        stack.extend(w.winfo_children())
    return out


def dialog():
    return [x for x in a.winfo_children() if isinstance(x, appmod.tk.Toplevel)][-1]


settle()
# ---------------------------------------------------------------- 01 베이직: 조회 전
tabs = {n: box(w[0], a) for n, w in a.tab_widgets.items()}
shot("01_basic_empty", {
    "tabs": [tabs["basic"][0], tabs["basic"][1], tabs["settings"][0] + tabs["settings"][2] - tabs["basic"][0], tabs["basic"][3]],
    "update": box(find(a, "업데이트 확인"), a),
    "steps": box(a.step_cells[0][0].master.master.master, a),
    "period": box(a.period_groups[0].master, a),
    "search": box(a.basic_search_btn, a),
    "status": box(a.status_bar, a),
})

# ---------------------------------------------------------------- 02 베이직: 조회 중(정지 버튼)
a._search_buttons(busy=True)
a._set_status("구글 뉴스 검색 중 · 키워드 12/67 '공공임대' · 지금까지 148건 수집 · [■ 정지]로 멈출 수 있음",
              word="조회 중", kind="busy", progress=0.18)
shot("02_basic_busy", {"stop": box(a.basic_stop_btn, a), "status": box(a.status_bar, a)})
a._search_buttons(busy=False)

# ---------------------------------------------------------------- 03 베이직: 조회 결과
a._search("basic")
settle()
bt = a.basic.tree
bp = a.pages["basic"]
rows = a.basic.order()
second = rows[1]
bt.selection_set(second)
shot("03_basic_result", {
    "steps": box(a.step_cells[0][0].master.master.master, a),
    "count": union(box(a.basic_count[0], a), box(a.basic_count[1], a)),
    "legend": union(box(find(bp, "★"), a), box(find(bp, "직접 추가"), a)),
    "updown": box(find(bp, "▲").master, a),
    "reset": box(find(bp, "↻ 추천으로"), a),
    "addlink": box(find(bp, "＋ 기사 링크로"), a),
    "col_no": tree_col(bt, "no", a),
    "check": [bt.winfo_rootx() - a.winfo_rootx(), tree_row(bt, rows[0], a)[1], bt.column("#0", "width"),
              tree_row(bt, rows[0], a)[3] * 5],
    "row_selected": tree_row(bt, second, a),
    "report": box(a.basic_report_btn, a),
    "mark": box(a.basic_mark_btn, a),
    "foot": box(a.basic_foot, a),
    "status": box(a.status_bar, a),
})

# ---------------------------------------------------------------- 04 HTML 보고서(브라우저)
a._open_report(a.basic, keep_order=True)
settle()
report_path = opened[-1].replace("file:///", "")
if os.name != "nt":
    report_path = "/" + report_path.lstrip("/")
shutil_copy = os.path.join(OUT, "04_report.html")
with open(report_path, encoding="utf-8") as f, open(shutil_copy, "w", encoding="utf-8") as g:
    g.write(f.read())
appmod.threading.Thread = ORIG_THREAD  # 브라우저 도구는 진짜 스레드가 필요
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            if os.name == "nt":
                browser = p.chromium.launch(channel="msedge")
            else:  # 개발 PC: 미리 깔린 Chromium(PW_CHROMIUM 경로)
                browser = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM") or None)
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 900}, device_scale_factor=1)
        page.goto("file:///" + report_path.replace("\\", "/").lstrip("/"))
        page.wait_for_timeout(500)

        def bb(sel):
            r = page.locator(sel).first.bounding_box()
            return [round(r["x"]), round(r["y"]), round(r["width"]), round(r["height"])]
        marks = {"subject_copy": bb("text=제목 복사"), "body1": bb("#body-simple")}
        try:
            marks["body2"] = bb("#body-full")
        except Exception:
            pass
        copies = page.locator("text=본문 복사")
        if copies.count():
            r = copies.first.bounding_box()
            marks["body1_copy"] = [round(r["x"]), round(r["y"]), round(r["width"]), round(r["height"])]
        page.screenshot(path=os.path.join(OUT, "04_report.png"), full_page=False)
        GEO["04_report"] = {"size": [1100, 900], "marks": marks}
        print("찍음: 04_report", list(marks))
        browser.close()
except Exception as e:  # 브라우저가 없으면 건너뜀(매뉴얼에 자리표시)
    print("보고서 화면 못 찍음:", repr(e))
appmod.threading.Thread = SyncThread

# ---------------------------------------------------------------- 05 보고 기록
a._mark_sent(a.basic)
a._select_tab("history")
settle()
recs = a.rec_tree.get_children()
if recs:
    a.rec_tree.selection_set(recs[0])
shot("05_history", {
    "import": box(find(a.pages["history"], "＋ 지난 보고 메일"), a),
    "days": box(a.day_tree, a),
    "records": box(a.rec_tree, a),
    "reopen": box(find(a.pages["history"], "이 날 보고서 다시 열기"), a),
    "remove": box(a.remove_btn, a),
})

# ---------------------------------------------------------------- 06 프로: 조회 결과
a._select_tab("pro")
settle()
pt = a.pro.tree
shot("06_pro_result", {
    "options": box(a.exclude_sent_var and find(a.pages["pro"], "이미 보고한 기사 제외").master, a),
    "period": box(a.period_groups[1].master, a),
    "stop_search": [box(a.stop_btn, a)[0], box(a.stop_btn, a)[1],
                    box(a.search_btn, a)[0] + box(a.search_btn, a)[2] - box(a.stop_btn, a)[0], box(a.search_btn, a)[3]],
    "keywords": box(a.kw_summary.master, a),
    "select_tools": box(find(a.pages["pro"], "전체 선택").master, a),
    "pick": box(a.pick_box.master, a),
    "order_tools": box(find(a.pages["pro"], "☑ 선택 항목").master.master, a),
    "col_grade": tree_col(pt, "grade", a),
    "col_score": tree_col(pt, "score", a),
    "col_category": tree_col(pt, "category", a),
    "excel": box(find(a.pages["pro"], "⤓ 결과 엑셀로"), a),
    "ai_steps": [box(find(a.pages["pro"], "① AI 선별"), a)[0], box(find(a.pages["pro"], "① AI 선별"), a)[1],
                 box(find(a.pages["pro"], "④ 보고 완료로"), a)[0] + box(find(a.pages["pro"], "④ 보고 완료로"), a)[2]
                 - box(find(a.pages["pro"], "① AI 선별"), a)[0], box(find(a.pages["pro"], "① AI 선별"), a)[3]],
})

# ---------------------------------------------------------------- 07 AI 선정 결과 붙여넣기 창
a._copy_request()
answer = demo_data.ai_answer(a.arts, a.request_map)
a._open_paste()
d = dialog()
d.geometry("+60+60")
boxes = []
stack = [d]
while stack:
    w = stack.pop()
    if w.winfo_class() == "Text":
        boxes.append(w)
    stack.extend(w.winfo_children())
boxes[0].insert("1.0", answer)
boxes[0].event_generate("<KeyRelease>")
shot("07_paste_dialog", {"text": box(boxes[0], d), "apply": box(find(d, "적용"), d)}, win=d)
find(d, "적용").invoke()
settle()

# ---------------------------------------------------------------- 08 프로: AI 선정 반영 후(순서 정하기)
a._checked_to_top(a.pro)
first = a.pro.order()[0]
pt.selection_set(a.pro.order()[1])
shot("08_pro_after_ai", {
    "order_tools": box(find(a.pages["pro"], "☑ 선택 항목").master.master, a),
    "col_no": tree_col(pt, "no", a),
    "col_category": tree_col(pt, "category", a),
    "top_rows": [tree_row(pt, first, a)[0], tree_row(pt, first, a)[1], tree_row(pt, first, a)[2],
                 tree_row(pt, first, a)[3] * len(a.pro.checked_iids())],
    "report": box(find(a.pages["pro"], "③ HTML 보고서"), a),
})

# ---------------------------------------------------------------- 09~11 선정 규칙
a._select_tab("rules")
settle()
rp = a.pages["rules"]
sp = [w for w in rp.winfo_children() if isinstance(w, appmod.theme.ScrollPanel)][0]
shot("09_rules_top", {
    "loop": box(find(rp, "환류:").master, a),
    "request": box(find(rp, "개선 요청문 복사"), a),
    "paste": box(find(rp, "Claude 답변 붙여넣기"), a),
    "kw_a": box(a.rule_lists["kw_a"].master.master, a),
    "kw_s": box(a.rule_lists["kw_s"].master.master, a),
    "kw_b": box(a.rule_lists["kw_b"].master.master, a),
    "save": box(find(rp, "규칙 저장"), a),
    "files": [box(find(rp, "규칙 파일 불러오기"), a)[0], box(find(rp, "규칙 파일 불러오기"), a)[1],
              box(find(rp, "기본값으로"), a)[0] + box(find(rp, "기본값으로"), a)[2] - box(find(rp, "규칙 파일 불러오기"), a)[0],
              box(find(rp, "규칙 파일 불러오기"), a)[3]],
})
# 점수 칸으로 내리기
target = find(rp, "③ 점수")
sp.canvas.yview_moveto(0)
settle()
y_in = target.winfo_rooty() - sp.inner.winfo_rooty()
sp.canvas.yview_moveto(max(0, (y_in - 120) / max(1, sp.inner.winfo_height())))
settle()
shot("10_rules_score", {
    "weights": union(box(find(rp, "③ 점수"), a), box(find(rp, "A 행사 (감점)"), a),
                     [box(find(rp, "③ 점수"), a)[0], box(find(rp, "③ 점수"), a)[1], 860, 10]),
    "words": box(a.rule_lists["risk_words"].master.master.master, a),
})
# Claude 개선안 붙여넣기 → 미리보기 창
new_rules = dict(a.cfg["rules"], w_s=35, kw_b=a.cfg["rules"]["kw_b"] + ["임대주택 하자 OR 공공임대 하자"])
import rules as R  # noqa: E402
a._paste_rules()
d = dialog()
stack, texts = [d], []
while stack:
    w = stack.pop()
    if w.winfo_class() == "Text":
        texts.append(w)
    stack.extend(w.winfo_children())
texts[0].insert("1.0", "검토 결과 아래처럼 고치기를 권합니다.\n```json\n" + R.to_json(new_rules) + "\n```")
find(d, "다음").invoke()
settle()
d = dialog()
d.geometry("+60+60")
shot("11_rules_preview", {"apply": box(find(d, "적용"), d)}, win=d)
find(d, "적용").invoke()
settle()
sp.canvas.yview_moveto(1.0)
settle()
shot("12_rules_log", {"log": box(a.rules_log_label.master, a), "log_btn": box(a.rules_log_btn, a)})

# ---------------------------------------------------------------- 13~14 설정
a._select_tab("settings")
settle()
sg = a.pages["settings"]
shot("13_settings", {
    "source": box(find(sg, "구글 뉴스 (키 필요 없음)").master.master, a),
    "feeds": box(find(sg, "전문지 고르기"), a),
    "report_title": box(a.subject_preview.master, a),
    "rules_link": box(find(sg, "선정 규칙 열기"), a),
    "holidays": box(a.holiday_text.master.master, a),
    "save": box(find(sg, "설정 저장"), a),
})
a._open_feeds()
d = dialog()
d.geometry("+60+60")
settle()
ents = []
stack = [d]
while stack:
    w = stack.pop(0)
    if w.winfo_class() == "TEntry":
        ents.append(w)
    stack.extend(w.winfo_children())
shot("14_feeds", {
    "list": box([w for w in walk(d) if w.winfo_class() == "Treeview"][0], d),
    "input": union(box(find(d, "매체", "TLabel"), d), box(find(d, "홈페이지 또는 RSS"), d), box(ents[-1], d)),
    "add": box(find(d, "＋ 추가"), d),
    "check": box(find(d, "연결 확인"), d),
}, win=d)
d.destroy()

with open(os.path.join(OUT, "geometry.json"), "w", encoding="utf-8") as f:
    json.dump({"app_version": appmod.__version__, "captured": dt.datetime.now().isoformat(timespec="minutes"),
               "pt_px": a.winfo_fpixels("1p"), "shots": GEO}, f, ensure_ascii=False, indent=1)
print("끝:", sorted(os.listdir(OUT)))
a.destroy()
