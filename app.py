"""언론보도 모니터링 앱 — 화면(GUI).

화면은 이 파일(과 표를 그리는 result_table.py)에만 있고, 실제 일(검색·중복제거·추천·보고서·
업데이트)은 각각의 모듈이 한다. 화면과 일을 분리해 두면 나중에 화면을 바꾸거나
자동 실행 버전을 만들 때 아래 모듈들을 그대로 쓸 수 있다.

탭 세 개:
- 베이직: 누구나. [조회] 한 번이면 기간은 자동(직전 영업일 9시~), 추천 5건이 선택된 채로 나온다.
          체크를 더하고 빼서 → 보고서 열기 → 메일 붙여넣기 → 보고 완료로 기록.
- 프로:   키워드·제외어·기간 직접 설정, 키워드별 선택, AI 선별 중계(요청문 복사·선정 결과 붙여넣기).
- 보고 기록: '보고 완료로 기록'한 기사를 날짜별로 본다. 그날 보고서 다시 열기, 잘못 기록한 것 취소.
- 설정:   출처, 전문지 RSS, 메일 제목, 행사 단어, 공휴일 등.
조회 기간(베이직·프로 공통)은 앱을 켜면 '직전 영업일 9시 ~ 오늘'로 자동으로 채워지고, 고칠 수 있다.
두 탭은 같은 조회 결과를 보지만 선택(☑)은 따로 가진다.
"""

import dataclasses
import datetime as dt
import os
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

# 회사 보안장비가 HTTPS 를 검사하면서 자체 인증서로 바꿔 끼우면, Python 은 자기 인증서 목록만
# 믿어서 접속을 거부한다(CERTIFICATE_VERIFY_FAILED). 브라우저처럼 윈도우 인증서 저장소를 믿게 한다.
# requests 를 쓰는 모듈(google_news·naver_api·updater)보다 먼저 실행해야 한다.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:  # 실패해도 기존 방식으로 동작
    pass

import article_fetch
import calendar_kr
import config
import dedup
import feeds
import google_news
import history
import mail_import
import naver_api
import ranking
import report
import selection
import updater
from naver_api import Article, NaverApiError
from result_table import ResultTable
from version import APP_TITLE, __version__

FONT = ("맑은 고딕", 10)
FONT_BOLD = ("맑은 고딕", 10, "bold")
FONT_BIG = ("맑은 고딕", 12, "bold")
KST = calendar_kr.KST
SOURCE_LABELS = {"google": "구글 뉴스", "naver": "네이버"}
TABS = ["basic", "pro", "history", "settings"]


def parse_start(text: str) -> dt.datetime:
    """'2026-10-15 09:00' 또는 '2026-10-15'(0시)."""
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    raise ValueError(text)


def parse_date(text: str) -> dt.date:
    return dt.datetime.strptime(text.strip()[:10], "%Y-%m-%d").date()


def url_key(a: Article) -> str:
    return a.link or a.naver_link


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} v{__version__}")
        self.geometry("1180x780")
        self.minsize(980, 640)
        self.option_add("*Font", FONT)
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=26, font=FONT)
        style.configure("Treeview.Heading", font=FONT_BOLD)
        style.configure("Big.TButton", font=FONT_BIG, padding=(16, 6))
        style.configure("TNotebook.Tab", font=FONT_BOLD, padding=(18, 6))

        self.cfg = config.load()
        self.arts: dict[str, Article] = {}        # 줄 id → 기사 (두 탭이 함께 씀)
        self.next_id = 0
        self.request_map: dict[int, str] = {}     # 'AI 선별 요청문'의 번호 → 줄 id
        self.pick_targets: dict[str, tuple[str, str]] = {}  # 키워드별 선택 목록 문구 → ("grade"/"kw", 값)
        self.period: tuple[dt.datetime, dt.date] | None = None  # 마지막 조회 기간
        self.searching = False

        self._build_ui()
        self._load_config_into_ui()
        self.after(1500, self._check_update_silently)

    # ------------------------------------------------------------------ UI
    @staticmethod
    def _text_box(parent, title: str, height: int = 5, side: str = "left") -> tk.Text:
        frame = ttk.LabelFrame(parent, text=f" {title} ")
        frame.pack(side=side, fill="both", expand=True, padx=4)
        text = tk.Text(frame, height=height, width=20, font=FONT)
        sb = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=4)
        text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        return text

    def _build_ui(self):
        head = ttk.Frame(self)
        head.pack(fill="x", padx=10, pady=(6, 0))
        ttk.Label(head, text=APP_TITLE, font=FONT_BIG, foreground="#1F3B5C").pack(side="left")
        ttk.Label(head, text=f"v{__version__}", foreground="#2E7D8C", font=FONT_BOLD).pack(side="left", padx=(6, 0), pady=(3, 0))
        ttk.Button(head, text="업데이트 확인", command=self._check_update).pack(side="right", padx=4)

        self.status_var = tk.StringVar(value="준비됨")
        ttk.Label(self, textvariable=self.status_var, foreground="#1F3B5C", anchor="w").pack(
            side="bottom", fill="x", padx=10, pady=(0, 6))

        # 조회 기간: 베이직·프로 두 탭이 같은 칸을 함께 쓴다
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)
        self.tab_basic = ttk.Frame(self.nb, padding=6)
        self.tab_pro = ttk.Frame(self.nb, padding=6)
        self.tab_history = ttk.Frame(self.nb, padding=6)
        self.tab_settings = ttk.Frame(self.nb, padding=10)
        self.nb.add(self.tab_basic, text="  베이직  ")
        self.nb.add(self.tab_pro, text="  프로  ")
        self.nb.add(self.tab_history, text="  보고 기록  ")
        self.nb.add(self.tab_settings, text="  설정  ")
        self._build_basic(self.tab_basic)
        self._build_pro(self.tab_pro)
        self._build_history(self.tab_history)
        self._build_settings(self.tab_settings)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_basic(self, tab):
        ttk.Label(tab, text="① 조회  →  ② ★추천 기사 확인 (☑ 눌러 더하기·빼기)  →  ③ 보고서 열기 → 메일에 붙여넣기  →  ④ 보고 완료로 기록",
                  foreground="#2E7D8C", font=FONT_BOLD).pack(anchor="w", pady=(0, 6))
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="① 조회", style="Big.TButton", command=lambda: self._search("basic")).pack(side="left")
        ttk.Label(row, text="기간").pack(side="left", padx=(14, 4))
        ttk.Entry(row, textvariable=self.start_var, width=17).pack(side="left")
        ttk.Label(row, text="~").pack(side="left", padx=2)
        ttk.Entry(row, textvariable=self.end_var, width=11).pack(side="left")
        ttk.Button(row, text="자동", width=5, command=self._set_auto_period).pack(side="left", padx=(6, 2))
        ttk.Button(row, text="오늘", width=5, command=lambda: self._set_period(0)).pack(side="left", padx=2)
        ttk.Button(row, text="최근 3일", width=8, command=lambda: self._set_period(2)).pack(side="left", padx=2)
        self.basic_period_var = tk.StringVar()
        ttk.Button(row, text="＋ 기사 링크로 추가", command=self._open_add_link).pack(side="right")
        ttk.Button(row, text="★추천으로 되돌리기", command=lambda: self._select_best(self.basic)).pack(side="right", padx=6)

        self.basic = ResultTable(tab, ["chk", "best", "date", "source", "title"], self.arts,
                                 self._keyword_rank, self._open_article, self._set_status)
        self.basic.frame.pack(fill="both", expand=True)

        bottom = ttk.Frame(tab)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Button(bottom, text="③ HTML 보고서 열기 (메일용)", style="Big.TButton",
                   command=lambda: self._open_report(self.basic, keep_order=True)).pack(side="left")
        ttk.Button(bottom, text="④ 보고 완료로 기록", style="Big.TButton",
                   command=lambda: self._mark_sent(self.basic)).pack(side="left", padx=8)
        ttk.Label(bottom, textvariable=self.basic_period_var, foreground="#888").pack(side="right")

    def _build_pro(self, tab):
        pad = {"pady": 3}
        # 기간
        top = ttk.Frame(tab)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="기간").pack(side="left")
        ttk.Entry(top, textvariable=self.start_var, width=17).pack(side="left", padx=(6, 2))
        ttk.Label(top, text="~").pack(side="left")
        ttk.Entry(top, textvariable=self.end_var, width=12).pack(side="left", padx=(2, 10))
        ttk.Button(top, text="자동 (직전 영업일 9시~)", command=self._set_auto_period).pack(side="left", padx=2)
        for label, days in (("오늘", 0), ("최근 3일", 2), ("최근 7일", 6)):
            ttk.Button(top, text=label, width=9,
                       command=lambda d=days: self._set_period(d)).pack(side="left", padx=2)

        # 키워드 A / B / 제외어
        mid = ttk.Frame(tab)
        mid.pack(fill="x", **pad)
        self.kw_a_text = self._text_box(mid, "A 기관 직접 (무조건 포함) · 한 줄에 하나")
        self.kw_b_text = self._text_box(mid, "B 정책·환경 (위가 우선) · 한 줄에 하나")
        self.ex_text = self._text_box(mid, "제외어 (제목에 있으면 제외, A는 예외) · 한 줄에 하나")

        # 옵션 + 조회
        opt = ttk.Frame(tab)
        opt.pack(fill="x", **pad)
        self.exclude_sent_var = tk.BooleanVar()
        self.merge_similar_var = tk.BooleanVar()
        self.exclude_events_var = tk.BooleanVar()
        ttk.Checkbutton(opt, text="이미 보고한 기사 제외", variable=self.exclude_sent_var).pack(side="left")
        ttk.Checkbutton(opt, text="같은 사안 기사 묶기", variable=self.merge_similar_var).pack(side="left", padx=10)
        ttk.Checkbutton(opt, text="단순 행사 기사 제외 (단어는 [설정])",
                        variable=self.exclude_events_var).pack(side="left")
        self.search_btn = ttk.Button(opt, text="  조  회  ", command=lambda: self._search("pro"))
        self.search_btn.pack(side="right")

        # 선택 도구
        sel = ttk.Frame(tab)
        sel.pack(fill="x", **pad)
        ttk.Button(sel, text="전체 선택", command=lambda: self.pro.set_all(True)).pack(side="left")
        ttk.Button(sel, text="전체 해제", command=lambda: self.pro.set_all(False)).pack(side="left", padx=2)
        ttk.Button(sel, text="★추천만", command=lambda: self._select_best(self.pro)).pack(side="left", padx=2)
        ttk.Separator(sel, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(sel, text="키워드별").pack(side="left")
        self.pick_var = tk.StringVar()
        self.pick_box = ttk.Combobox(sel, textvariable=self.pick_var, state="readonly", width=24)
        self.pick_box.pack(side="left", padx=6)
        ttk.Button(sel, text="☑ 선택", command=lambda: self._pick(True)).pack(side="left", padx=2)
        ttk.Button(sel, text="☐ 해제", command=lambda: self._pick(False)).pack(side="left", padx=2)
        ttk.Button(sel, text="이것만", command=self._pick_only).pack(side="left", padx=2)
        ttk.Button(sel, text="＋ 기사 링크로 추가", command=self._open_add_link).pack(side="right")

        self.pro = ResultTable(tab, ["chk", "best", "grade", "score", "category", "keyword", "date", "source", "title"],
                               self.arts, self._keyword_rank, self._open_article, self._set_status)
        self.pro.frame.pack(fill="both", expand=True, pady=3)

        # 하단: 하루 흐름 순서대로 번호를 붙인 버튼
        bottom = ttk.Frame(tab)
        bottom.pack(fill="x", pady=(3, 0))
        ttk.Button(bottom, text="① AI 선별 요청문 복사", command=self._copy_request).pack(side="left")
        ttk.Button(bottom, text="② 선정 결과 붙여넣기", command=self._open_paste).pack(side="left", padx=6)
        ttk.Button(bottom, text="③ HTML 보고서 열기 (메일용)",
                   command=lambda: self._open_report(self.pro)).pack(side="left")
        ttk.Button(bottom, text="④ 보고 완료로 기록", command=lambda: self._mark_sent(self.pro)).pack(side="left", padx=6)
        ttk.Label(bottom, text="표 머리글 클릭 → 모아서 정렬", foreground="#888").pack(side="right")

    def _build_settings(self, tab):
        left = ttk.Frame(tab)
        left.pack(side="left", fill="y", anchor="n")
        right = ttk.Frame(tab)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))

        r = 0
        ttk.Label(left, text="기사 출처").grid(row=r, column=0, sticky="w", pady=4)
        self.source_var = tk.StringVar()
        src = ttk.Frame(left)
        src.grid(row=r, column=1, sticky="w", padx=(10, 0))
        ttk.Radiobutton(src, text="구글 뉴스 (키 불필요)", value="google", variable=self.source_var).pack(side="left")
        ttk.Radiobutton(src, text="네이버 (키 필요)", value="naver", variable=self.source_var).pack(side="left", padx=(14, 0))
        r += 1
        self.feeds_var = tk.BooleanVar()
        names = ", ".join(f.get("name", "") for f in self.cfg.get("extra_feeds", []))
        ttk.Checkbutton(left, text=f"전문지 RSS 함께 조회 ({names})", variable=self.feeds_var).grid(
            row=r, column=1, sticky="w", padx=(10, 0), pady=4)
        self.setting_vars: dict[str, tk.StringVar] = {}
        for label, key, secret in [
            ("네이버 Client ID", "client_id", False),
            ("네이버 Client Secret", "client_secret", True),
            ("메일 제목 ({날짜}→261015)", "mail_subject", False),
            ("보고서 제목", "report_title", False),
            ("추천 건수 (베이직)", "best_count", False),
            ("B 키워드당 최대 건수", "b_max_per_keyword", False),
        ]:
            r += 1
            ttk.Label(left, text=label).grid(row=r, column=0, sticky="w", pady=4)
            v = tk.StringVar()
            self.setting_vars[key] = v
            ttk.Entry(left, textvariable=v, width=40, show="*" if secret else "").grid(
                row=r, column=1, sticky="w", pady=4, padx=(10, 0))
        r += 1
        ttk.Label(left, text="네이버 Client ID/Secret 은 '네이버'를 고를 때만 필요합니다.\n"
                             "모든 값은 이 PC 의 config.json 에만 저장됩니다.",
                  foreground="#666").grid(row=r, column=0, columnspan=2, sticky="w", pady=(8, 4))
        r += 1
        ttk.Button(left, text="설정 저장", style="Big.TButton", command=self._save_settings).grid(
            row=r, column=1, sticky="e", pady=(12, 0))

        self.event_text = self._text_box(right, "단순 행사 단어 (제목에 있으면 A 등급이라도 제외) · 한 줄에 하나",
                                         height=8, side="top")
        self.holiday_text = self._text_box(
            right, "공휴일 (자동 기간 계산용) · 임시공휴일은 'YYYY-MM-DD 이름' 한 줄 추가",
            height=10, side="top")

    def _build_history(self, tab):
        ttk.Label(tab, text=f"'보고 완료로 기록'한 기사와 불러온 지난 보고 메일을 날짜별로 봅니다. 기록은 {history.KEEP_DAYS // 365}년 보관합니다. "
                            "기록을 취소하면 다음 조회에 다시 나옵니다.", foreground="#2E7D8C").pack(anchor="w", pady=(0, 6))
        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.day_tree = ttk.Treeview(left, columns=("day", "n"), show="headings", selectmode="browse", height=20)
        self.day_tree.heading("day", text="보고일")
        self.day_tree.heading("n", text="건수")
        self.day_tree.column("day", width=130, anchor="center", stretch=False)
        self.day_tree.column("n", width=56, anchor="center", stretch=False)
        dsb = ttk.Scrollbar(left, orient="vertical", command=self.day_tree.yview)
        self.day_tree.configure(yscrollcommand=dsb.set)
        dsb.pack(side="right", fill="y")
        self.day_tree.pack(side="left", fill="y")
        self.day_tree.bind("<<TreeviewSelect>>", lambda e: self._show_history_day())

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.rec_tree = ttk.Treeview(right, columns=("time", "source", "title"), show="headings", selectmode="extended")
        for col, head, width, stretch in (("time", "기록 시각", 80, False), ("source", "매체", 130, False),
                                          ("title", "제목 (더블클릭: 기사 열기)", 600, True)):
            self.rec_tree.heading(col, text=head)
            self.rec_tree.column(col, width=width, stretch=stretch, anchor="center" if col == "time" else "w")
        self.rec_tree.tag_configure("odd", background="#F3F6F9")
        rsb = ttk.Scrollbar(right, orient="vertical", command=self.rec_tree.yview)
        self.rec_tree.configure(yscrollcommand=rsb.set)
        rsb.pack(side="right", fill="y")
        self.rec_tree.pack(side="left", fill="both", expand=True)
        self.rec_tree.bind("<Double-1>", self._open_history_item)

        bottom = ttk.Frame(tab)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Button(bottom, text="이 날 보고서 다시 열기 (메일용)", command=self._reopen_history_report).pack(side="left")
        ttk.Button(bottom, text="새로고침", command=self._refresh_history).pack(side="left", padx=6)
        ttk.Button(bottom, text="기존 보고 메일 불러오기 (HTML)", command=self._import_mails).pack(side="left", padx=(12, 0))
        ttk.Button(bottom, text="선택한 기사 기록 취소", command=self._remove_history_items).pack(side="right")
        self.history_days: dict[str, list[tuple[str, dict]]] = {}
        self._refresh_history()

    def _refresh_history(self, select_day: str | None = None):
        keep = (select_day,) if select_day else self.day_tree.selection()
        self.history_days = history.by_date(history.load())
        self.day_tree.delete(*self.day_tree.get_children())
        for day, items in self.history_days.items():
            d = dt.date.fromisoformat(day)
            self.day_tree.insert("", "end", iid=day, values=(f"{day} ({'월화수목금토일'[d.weekday()]})", len(items)))
        if keep and self.day_tree.exists(keep[0]):
            self.day_tree.selection_set(keep[0])
        elif self.history_days:
            self.day_tree.selection_set(next(iter(self.history_days)))
        self._show_history_day()

    def _history_day(self) -> str | None:
        sel = self.day_tree.selection()
        return sel[0] if sel else None

    def _show_history_day(self):
        self.rec_tree.delete(*self.rec_tree.get_children())
        day = self._history_day()
        for i, (link, rec) in enumerate(self.history_days.get(day, [])):
            self.rec_tree.insert("", "end", iid=link, values=(rec["time"], rec["source"], rec["title"] or link),
                                 tags=("odd",) if i % 2 else ())

    def _history_record(self, link: str) -> dict | None:
        return next((r for l, r in self.history_days.get(self._history_day(), []) if l == link), None)

    def _open_history_item(self, event):
        link = self.rec_tree.identify_row(event.y)
        rec = self._history_record(link) if link else None
        if rec is None:
            return
        self._open_article(Article(rec["title"], rec["url"] or link, "", rec["source"],
                                   dt.datetime.now(KST), ""))

    def _reopen_history_report(self):
        day = self._history_day()
        if not day or not self.history_days.get(day):
            messagebox.showinfo("보고 기록", "왼쪽에서 날짜를 고르세요.")
            return
        arts = []
        for link, rec in self.history_days[day]:
            when = dt.datetime.fromisoformat(f"{day} {rec['time'] or '09:00'}").replace(tzinfo=KST)
            arts.append(Article(rec["title"] or link, rec["url"] or link, "", rec["source"], when, ""))

        def work():
            links = google_news.resolve_links([a.link for a in arts])
            items = [dataclasses.replace(a, link=links.get(a.link, a.link)) for a in arts]
            self.after(0, done, items)

        def done(items):
            subject = report.mail_subject(self.cfg.get("mail_subject", report.DEFAULT_SUBJECT),
                                          dt.date.fromisoformat(day))
            path = report.save_report("", subject=subject, simple_html=report.build_simple_html(items))
            webbrowser.open("file:///" + path.replace("\\", "/"))
            self._set_status(f"{day} 보고서 다시 열기: {len(items)}건")

        self._set_status("기사 원문 주소 확인 중…")
        threading.Thread(target=work, daemon=True).start()

    def _import_mails(self):
        """그룹웨어에서 내려받은 지난 보고 메일(HTML) 여러 개 → 미리보기 → 보고 기록에 넣기."""
        paths = filedialog.askopenfilenames(
            parent=self, title="지난 보고 메일 파일 고르기 (여러 개 가능)",
            filetypes=[("메일 HTML", "*.html *.htm *.mht *.mhtml *.eml"), ("모든 파일", "*.*")])
        if not paths:
            return
        reports = [mail_import.parse_file(p) for p in paths]
        reports.sort(key=lambda r: (r.day or dt.date.max, r.path))

        win = tk.Toplevel(self)
        win.title("기존 보고 메일 불러오기 — 확인")
        win.transient(self)
        win.grab_set()
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="파일마다 찾은 보고일과 기사 수입니다. 보고일이 틀리거나 비었으면 그 줄을 더블클릭해 고치세요.\n"
                            "이미 기록에 있는 기사는 건너뜁니다.", foreground="#444").pack(anchor="w")
        tree = ttk.Treeview(frm, columns=("file", "day", "time", "n", "note"), show="headings", height=12)
        for col, head, width in (("file", "파일", 300), ("day", "보고일", 100), ("time", "시각", 60),
                                 ("n", "기사", 50), ("note", "날짜 찾은 곳 / 문제", 160)):
            tree.heading(col, text=head)
            tree.column(col, width=width, anchor="w" if col == "file" else "center")
        tree.pack(fill="both", expand=True, pady=8)

        def show():
            tree.delete(*tree.get_children())
            for i, r in enumerate(reports):
                tree.insert("", "end", iid=str(i), values=(
                    os.path.basename(r.path), r.day.isoformat() if r.day else "(직접 입력)", r.time,
                    len(r.items), r.note))

        def edit_day(event):
            iid = tree.identify_row(event.y)
            if not iid:
                return
            r = reports[int(iid)]
            text = simpledialog.askstring("보고일 고치기", f"{os.path.basename(r.path)}\n보고일 (예: 2026-10-15)",
                                          initialvalue=r.day.isoformat() if r.day else "", parent=win)
            if text:
                try:
                    r.day = dt.date.fromisoformat(text.strip())
                    r.note = "직접 입력"
                except ValueError:
                    messagebox.showwarning("보고일", "2026-10-15 형식으로 적어 주세요.", parent=win)
            show()

        def do_import():
            added = skipped = files = 0
            for r in reports:
                if r.day and r.items:
                    a, s = history.import_day(r.day.isoformat(), r.time, r.items)
                    added, skipped, files = added + a, skipped + s, files + 1
            win.destroy()
            last = max((r.day for r in reports if r.day and r.items), default=None)
            self._refresh_history(select_day=last.isoformat() if last else None)
            left = len(reports) - files
            self._set_status(f"지난 보고 메일 {files}개에서 {added}건 불러옴"
                             + (f" · 이미 있던 {skipped}건 건너뜀" if skipped else "")
                             + (f" · 날짜·기사를 못 찾은 파일 {left}개 제외" if left else ""))

        tree.bind("<Double-1>", edit_day)
        show()
        btns = ttk.Frame(frm)
        btns.pack(anchor="e")
        ttk.Button(btns, text="불러오기", command=do_import).pack(side="left", padx=4)
        ttk.Button(btns, text="취소", command=win.destroy).pack(side="left")

    def _remove_history_items(self):
        links = list(self.rec_tree.selection())
        if not links:
            messagebox.showinfo("기록 취소", "오른쪽 표에서 취소할 기사를 고르세요 (Ctrl·Shift 로 여러 개).")
            return
        if not messagebox.askyesno("기록 취소", f"선택한 {len(links)}건의 보고 기록을 지울까요?\n"
                                   "지우면 다음 조회에 다시 나옵니다."):
            return
        n = history.remove(links)
        self._refresh_history()
        self._set_status(f"보고 기록 {n}건 취소")

    # ------------------------------------------------------------ 설정 ↔ 화면
    def _load_config_into_ui(self):
        self._set_auto_period()
        self.kw_a_text.insert("1.0", "\n".join(self.cfg.get("keywords_a", [])))
        self.kw_b_text.insert("1.0", "\n".join(self.cfg.get("keywords_b", [])))
        self.ex_text.insert("1.0", "\n".join(self.cfg.get("exclude_words", [])))
        self.exclude_sent_var.set(bool(self.cfg.get("exclude_sent", True)))
        self.merge_similar_var.set(bool(self.cfg.get("merge_similar", True)))
        self.exclude_events_var.set(bool(self.cfg.get("exclude_events", True)))
        self.source_var.set(self._source())
        self.feeds_var.set(bool(self.cfg.get("use_feeds", True)))
        for key, v in self.setting_vars.items():
            v.set(str(self.cfg.get(key, "")))
        self.event_text.insert("1.0", "\n".join(self.cfg.get("event_words", [])))
        self.holiday_text.insert("1.0", "\n".join(self.cfg.get("holidays", [])))
        tab = self.cfg.get("last_tab", "basic")
        self.nb.select(TABS.index(tab) if tab in TABS else 0)

    def _save_ui_into_config(self):
        self.cfg["keywords_a"] = self._lines(self.kw_a_text)
        self.cfg["keywords_b"] = self._lines(self.kw_b_text)
        self.cfg["keywords"] = config.all_keywords(self.cfg)
        self.cfg["exclude_words"] = self._lines(self.ex_text)
        self.cfg["exclude_sent"] = self.exclude_sent_var.get()
        self.cfg["merge_similar"] = self.merge_similar_var.get()
        self.cfg["exclude_events"] = self.exclude_events_var.get()
        config.save(self.cfg)

    def _save_settings(self):
        self.cfg["source"] = self.source_var.get()
        self.cfg["use_feeds"] = self.feeds_var.get()
        for key, v in self.setting_vars.items():
            self.cfg[key] = v.get().strip()
        for key, default in (("best_count", 5), ("b_max_per_keyword", 50)):
            try:
                self.cfg[key] = max(0, int(self.cfg[key]))
            except ValueError:
                self.cfg[key] = default
            self.setting_vars[key].set(str(self.cfg[key]))
        self.cfg["event_words"] = self._lines(self.event_text)
        self.cfg["holidays"] = self._lines(self.holiday_text)
        config.save(self.cfg)
        self._set_auto_period()
        self._set_status("설정 저장됨")

    def _on_tab_changed(self, _event=None):
        idx = self.nb.index(self.nb.select())
        self.cfg["last_tab"] = TABS[idx]
        try:
            config.save(self.cfg)
        except OSError:
            pass

    @staticmethod
    def _lines(widget: tk.Text) -> list[str]:
        seen, out = set(), []
        for line in widget.get("1.0", "end").splitlines():
            s = line.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def _set_status(self, text: str):
        self.status_var.set(text)

    # --------------------------------------------------------------- 기간
    def _holidays(self) -> set[dt.date]:
        return calendar_kr.parse_holidays(self.cfg.get("holidays", []))

    def _auto_period(self) -> tuple[dt.datetime, dt.date]:
        now = dt.datetime.now(KST)
        return calendar_kr.auto_start(now, self._holidays()), now.date()

    def _set_auto_period(self):
        start, end = self._auto_period()
        self.start_var.set(start.strftime("%Y-%m-%d %H:%M"))
        self.end_var.set(end.isoformat())
        self.basic_period_var.set(f"자동 기간 = 직전 영업일 9시부터 ({calendar_kr.describe(start)} ~ 지금)")

    def _set_period(self, days_back: int):
        today = dt.date.today()
        self.start_var.set((today - dt.timedelta(days=days_back)).isoformat() + " 00:00")
        self.end_var.set(today.isoformat())

    # --------------------------------------------------------------- 조회
    def _source(self) -> str:
        return self.cfg.get("source") if self.cfg.get("source") in SOURCE_LABELS else "google"

    def _keyword_rank(self, kw: str) -> int:
        """키워드 칸에 적힌 순서(A 다음 B). 목록에 없는 것은 맨 뒤."""
        order = self.cfg.get("keywords", [])
        return order.index(kw) if kw in order else len(order)

    def _search(self, mode: str):
        if self.searching:
            return
        try:
            start = parse_start(self.start_var.get())
            end = parse_date(self.end_var.get())
        except ValueError:
            messagebox.showwarning("기간 확인", "기간은 2026-10-15 09:00 ~ 2026-10-16 형식으로 입력하세요.")
            return
        if start.date() > end:
            messagebox.showwarning("기간 확인", "시작이 끝보다 늦습니다.")
            return

        self._save_ui_into_config()
        if not self.cfg["keywords"]:
            messagebox.showwarning("키워드 확인", "[프로] 탭에서 검색 키워드를 한 개 이상 입력하세요.")
            return
        if self._source() == "naver" and (not self.cfg.get("client_id") or not self.cfg.get("client_secret")):
            messagebox.showwarning("설정 필요", "네이버 Client ID / Secret 을 [설정] 탭에서 입력하세요.\n"
                                   "키가 없으면 '구글 뉴스 (키 불필요)'를 고르세요.")
            self.nb.select(TABS.index("settings"))
            return

        # 키워드 → 등급. A·B 양쪽에 같은 키워드가 있으면 A.
        grades = {k: "A" for k in self.cfg["keywords_a"]}
        for k in self.cfg["keywords_b"]:
            grades.setdefault(k, "B")

        self.searching = True
        self.search_btn.state(["disabled"])
        self._clear_results()
        self.period = (start, end)
        threading.Thread(target=self._search_worker, args=(grades, start, end), daemon=True).start()

    def _search_worker(self, grades: dict[str, str], start: dt.datetime, end: dt.date):
        source = self._source()
        label = SOURCE_LABELS[source]
        found: list[Article] = []
        feed_failed: list[str] = []
        try:
            b_max = int(self.cfg.get("b_max_per_keyword", 50) or 0)
            for i, kw in enumerate(grades, 1):
                self.after(0, self._set_status, f"{label} 조회 중… ({i}/{len(grades)}) {kw}")
                is_a = grades[kw] == "A"
                if source == "naver":
                    arts = naver_api.search_news(kw, self.cfg["client_id"], self.cfg["client_secret"],
                                                 start.date(), end)
                else:
                    # A 는 빠짐없이(기간 나눠 다시 묻기), B 는 한 번만
                    arts = google_news.search_news(kw, start.date(), end, split=is_a)
                if not is_a and b_max > 0:
                    arts = arts[:b_max]
                for a in arts:
                    a.grade = grades[kw]
                found.extend(arts)
            if self.cfg.get("use_feeds", True) and self.cfg.get("extra_feeds"):
                self.after(0, self._set_status, "전문지 RSS 조회 중…")
                arts, feed_failed = feeds.search_feeds(self.cfg["extra_feeds"], grades, start.date(), end)
                found.extend(arts)
        except NaverApiError as e:
            self.after(0, self._search_failed, str(e))
            return
        except Exception as e:  # 예상 못한 오류도 화면에 보여 준다
            self.after(0, self._search_failed, f"오류: {e!r}")
            return

        # 시작 '시각'(예: 전 영업일 09:00) 이전 기사는 뺀다 — 검색은 날짜 단위라서
        found = [a for a in found if a.published >= start]
        raw_count = len(found)
        # B 키워드로 찾았어도 제목·요약에 A 키워드(주택관리공단 등)가 있으면 A 로 올린다
        a_keywords = [k for k, g in grades.items() if g == "A"]
        for a in found:
            if a.grade != "A" and any(feeds.keyword_matches(k, f"{a.title} {a.description}") for k in a_keywords):
                a.grade = "A"
        # 제외어는 B 에만 적용한다(A 는 '무조건 포함').
        found = [a for a in found if a.grade == "A"] + dedup.apply_exclude(
            [a for a in found if a.grade != "A"], self.cfg.get("exclude_words", []))
        events_skipped = 0
        if self.cfg.get("exclude_events", True):
            # 단순 행사 기사는 A 등급이라도 뺀다
            before = len(found)
            found = dedup.apply_exclude(found, self.cfg.get("event_words", []))
            events_skipped = before - len(found)
        found = dedup.dedupe(found, self.cfg.get("merge_similar", True),
                             float(self.cfg.get("similar_threshold", 0.85)), self.cfg.get("keywords", []))
        sent_skipped = 0
        if self.cfg.get("exclude_sent", True):
            sent = history.load()
            before = len(found)
            titles = history.sent_titles(sent, dedup.normalize)
            found = [a for a in found if not history.is_sent(a.all_links, sent)
                     and dedup.normalize(a.title) not in titles]
            sent_skipped = before - len(found)
        self.after(0, self._search_done, found, raw_count, sent_skipped, feed_failed, events_skipped)

    def _search_failed(self, msg: str):
        self.searching = False
        self.search_btn.state(["!disabled"])
        self._set_status("조회 실패")
        messagebox.showerror("조회 실패", msg)

    def _rescore(self):
        """추천 점수를 다시 매기고 추천 5건(★)을 고른다."""
        now = dt.datetime.now(KST)
        n_kw = len(self.cfg.get("keywords", []))
        arts = list(self.arts.values())
        for a in arts:
            main = min((self._keyword_rank(k) for k in a.keywords), default=n_kw)
            a.score = ranking.score(a, main, n_kw, now)
        best = ranking.pick_best(arts, self._keyword_rank, int(self.cfg.get("best_count", 5) or 5))
        best_ids = {id(a) for a in best}
        for a in arts:
            a.best = id(a) in best_ids
        return best

    def _iid_of(self, art: Article) -> str:
        return next(i for i, a in self.arts.items() if a is art)

    def _search_done(self, found: list[Article], raw_count: int, sent_skipped: int, feed_failed: list[str],
                     events_skipped: int = 0):
        self.searching = False
        self.search_btn.state(["!disabled"])
        for art in found:
            art.keywords.sort(key=self._keyword_rank)
            self._new_iid(art)
        best = self._rescore()
        best_ids = [self._iid_of(a) for a in best]
        ordered = sorted(self.arts, key=lambda i: (not self.arts[i].best, -self.arts[i].score))
        for iid in ordered:
            self.basic.add(iid, checked=iid in best_ids)   # 베이직: 추천만 선택
            self.pro.add(iid, checked=True)                # 프로: 후보 전체 선택
        self.basic.restyle()
        self.pro.sort_by("grade", reverse=False)  # 기본: A 가 위 → 키워드 우선순위 → 최신순
        self._refresh_pick_box()
        self.cfg["last_search_at"] = dt.datetime.now(KST).isoformat(timespec="minutes")
        config.save(self.cfg)

        n_a = sum(1 for a in found if a.grade == "A")
        merged = sum(len(a.others) for a in found)
        src = SOURCE_LABELS[self._source()] + ("+전문지" if self.cfg.get("use_feeds", True) else "")
        msg = (f"[{src}] 수집 {raw_count}건"
               + (f" → 행사 {events_skipped}건 제외" if events_skipped else "")
               + (f" → 같은 사안 {merged}건 묶음" if merged else "")
               + (f" → 기보고 {sent_skipped}건 제외" if sent_skipped else "")
               + f" → 표시 {len(found)}건 (A {n_a} · B {len(found) - n_a}) · ★추천 {len(best)}건 선택됨")
        if feed_failed:
            msg += f" · 전문지 조회 실패: {', '.join(feed_failed)}"
        self._set_status(msg)

    def _new_iid(self, art: Article) -> str:
        self.next_id += 1
        iid = f"a{self.next_id}"
        self.arts[iid] = art
        return iid

    def _clear_results(self):
        self.basic.clear()
        self.pro.clear()
        self.arts.clear()
        self.request_map.clear()
        self.pick_targets.clear()
        self.pick_box.configure(values=[])
        self.pick_var.set("")

    # ------------------------------------------------------------ 선택 도구
    def _select_best(self, table: ResultTable):
        ids = [i for i, a in self.arts.items() if a.best or a.grade == "직접"]
        table.set_only(ids)
        table.sort_by("best", reverse=False)
        self._set_status(f"★추천 {len(ids)}건만 선택")

    def _refresh_pick_box(self):
        """키워드별 선택 목록: 등급 A·B, 그리고 결과에 나온 키워드(건수 포함)."""
        arts = list(self.arts.values())
        self.pick_targets.clear()
        for g in ("A", "B"):
            n = sum(1 for a in arts if a.grade == g)
            if n:
                self.pick_targets[f"[등급 {g}] 전체 ({n}건)"] = ("grade", g)
        counts: dict[str, int] = {}
        for a in arts:
            for k in a.keywords:
                counts[k] = counts.get(k, 0) + 1
        for k in sorted(counts, key=self._keyword_rank):
            self.pick_targets[f"{k} ({counts[k]}건)"] = ("kw", k)
        values = list(self.pick_targets)
        self.pick_box.configure(values=values)
        self.pick_var.set(values[0] if values else "")

    def _pick_matches(self) -> list[str] | None:
        target = self.pick_targets.get(self.pick_var.get())
        if not target:
            messagebox.showinfo("키워드별 선택", "먼저 조회한 뒤 목록에서 키워드를 고르세요.")
            return None
        kind, value = target
        return [iid for iid, a in self.arts.items()
                if (a.grade == value if kind == "grade" else value in a.keywords)]

    def _pick(self, on: bool):
        iids = self._pick_matches()
        if iids is None:
            return
        for iid in iids:
            self.pro.toggle(iid, on)
        self._set_status(f"'{self.pick_var.get()}' {len(iids)}건 {'선택' if on else '해제'}")

    def _pick_only(self):
        iids = self._pick_matches()
        if iids is None:
            return
        self.pro.set_only(iids)
        self._set_status(f"'{self.pick_var.get()}' {len(iids)}건만 선택")

    def _open_article(self, art: Article):
        url = art.link or art.naver_link
        if google_news.is_google_link(url):
            # 원문 주소 찾기는 인터넷을 거치므로 화면이 멈추지 않게 따로 돌린다
            self._set_status("기사 원문 주소 확인 중…")
            threading.Thread(target=lambda: self.after(
                0, self._open_url, google_news.resolve_link(url)), daemon=True).start()
        else:
            webbrowser.open(url)

    def _open_url(self, url: str):
        self._set_status("기사 열기" + (" (원문 주소를 못 찾아 구글 경유)" if google_news.is_google_link(url) else ""))
        webbrowser.open(url)

    # ---------------------------------------------------- 기사 링크로 추가
    def _open_add_link(self):
        win = tk.Toplevel(self)
        win.title("기사 링크로 추가")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=14)
        frm.pack()
        ttk.Label(frm, text="구글 조회에 없지만 꼭 넣어야 할 기사의 주소를 붙여 넣고 [불러오기]를 누르세요.\n"
                            "제목·매체를 못 불러오면 직접 적으면 됩니다.", foreground="#444").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        vars_ = {k: tk.StringVar() for k in ("url", "title", "source", "date")}
        vars_["date"].set(dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"))
        rows = [("기사 주소", "url", 60), ("제목", "title", 60), ("매체", "source", 24), ("날짜", "date", 18)]
        for r, (label, key, width) in enumerate(rows, 1):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=3)
            e = ttk.Entry(frm, textvariable=vars_[key], width=width)
            e.grid(row=r, column=1, sticky="w", pady=3, padx=(8, 0))
            if key == "url":
                e.focus_set()
        info = tk.StringVar()

        def fill(page):
            if page is None:
                info.set("불러오지 못했습니다. 제목·매체를 직접 적어 주세요.")
                return
            vars_["url"].set(page.url)
            vars_["title"].set(page.title)
            vars_["source"].set(page.source)
            if page.published:
                vars_["date"].set(page.published.strftime("%Y-%m-%d %H:%M"))
            info.set("불러왔습니다. 확인 후 [추가]를 누르세요.")

        def load():
            url = vars_["url"].get().strip()
            if not url.startswith("http"):
                info.set("http 로 시작하는 기사 주소를 붙여 넣으세요.")
                return
            info.set("불러오는 중…")

            def work():
                try:
                    page = article_fetch.fetch(url)
                except Exception:
                    page = None
                self.after(0, fill, page)
            threading.Thread(target=work, daemon=True).start()

        def add():
            url, title = vars_["url"].get().strip(), vars_["title"].get().strip()
            if not url.startswith("http") or not title:
                info.set("주소와 제목은 꼭 있어야 합니다.")
                return
            try:
                when = parse_start(vars_["date"].get())
            except ValueError:
                when = dt.datetime.now(KST)
            win.destroy()
            self._add_manual(Article(title=title, link=url, naver_link="",
                                     source=vars_["source"].get().strip() or article_fetch.source_name(url),
                                     published=when, description="", keywords=["직접 추가"], grade="직접"))

        ttk.Button(frm, text="불러오기", command=load).grid(row=1, column=2, padx=(6, 0))
        ttk.Label(frm, textvariable=info, foreground="#2E7D8C").grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="추가", command=add).pack(side="left", padx=4)
        ttk.Button(btns, text="취소", command=win.destroy).pack(side="left")

    def _add_manual(self, art: Article):
        """직접 추가한 기사: 두 탭 모두 맨 위에, 선택된 채로. 이미 있는 기사면 그 줄을 선택해 올린다."""
        iid = next((i for i, a in self.arts.items() if url_key(a) == url_key(art)), None)
        if iid is None:
            iid = self._new_iid(art)
            self._rescore()
            self.basic.add(iid, checked=True, top=True)
            self.pro.add(iid, checked=True, top=True)
        else:
            self.arts[iid].grade = "직접"
            self._rescore()
            self.basic.toggle(iid, True)
            self.pro.toggle(iid, True)
        for t in (self.basic, self.pro):
            t.refresh()
            t.move_to_top([iid])
        self._set_status(f"직접 추가: {art.title[:40]} — 두 탭 모두 맨 위에 선택됨")

    # ------------------------------------------------------- AI 선별 중계
    def _copy_request(self):
        iids = self.pro.checked_iids()
        if not iids:
            messagebox.showinfo("AI 선별 요청문", "후보 기사가 없습니다. 먼저 조회하세요.")
            return
        text = selection.build_request([self.arts[i] for i in iids])
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()  # 클립보드 내용을 확정
        # 붙여넣기 때 번호로 기사를 찾으려고, 복사한 순간의 번호↔줄을 기억해 둔다(그 뒤 정렬해도 안전)
        self.request_map = {n: iid for n, iid in enumerate(iids, 1)}
        self._set_status(f"선별 요청문 {len(iids)}건 복사됨 → Claude 프로젝트 채팅에 붙여 넣으세요")

    def _open_paste(self):
        if not self.request_map:
            messagebox.showinfo("선정 결과 붙여넣기", "먼저 '① AI 선별 요청문 복사'를 누르고 Claude 에게 보내세요.\n"
                                "번호는 그때 복사한 목록 기준입니다.")
            return
        win = tk.Toplevel(self)
        win.title("선정 결과 붙여넣기")
        win.transient(self)
        win.grab_set()
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Claude 답변의 '#선정' 아래 줄들을 붙여 넣으세요 (답변 전체를 붙여도 됩니다).\n"
                            "형식: 번호|분류|한 줄 인사이트   예) 12|리스크|공단 관리 단지 승강기 사고 → 전 단지 점검 검토",
                  foreground="#444").pack(anchor="w")
        box = tk.Text(frm, width=90, height=14, font=FONT)
        box.pack(fill="both", expand=True, pady=8)
        box.focus_set()

        def apply():
            picked, ignored = selection.parse_selection(box.get("1.0", "end"), len(self.request_map))
            if not picked:
                messagebox.showwarning("선정 결과", "읽을 수 있는 줄이 없습니다.\n형식: 번호|분류|한 줄 인사이트",
                                       parent=win)
                return
            win.destroy()
            self._apply_selection(picked, ignored)

        btns = ttk.Frame(frm)
        btns.pack(anchor="e")
        ttk.Button(btns, text="적용", command=apply).pack(side="left", padx=4)
        ttk.Button(btns, text="취소", command=win.destroy).pack(side="left")

    def _apply_selection(self, picked: list[tuple[int, str, str]], ignored: int):
        """프로 표: 모두 ☐ → 선정된 번호만 ☑, 분류·인사이트 저장, 선정 순서대로 맨 위로."""
        for art in self.arts.values():
            art.category = art.insight = ""
        chosen = []
        for no, cat, insight in picked:
            iid = self.request_map[no]
            self.arts[iid].category, self.arts[iid].insight = cat, insight
            chosen.append(iid)
        self.pro.set_only(chosen)
        self.pro.refresh()
        self.basic.refresh()
        self.pro.move_to_top(chosen)
        self._set_status(f"선정 {len(picked)}건 적용 → ③ HTML 보고서 열기"
                         + (f" · 무시된 줄 {ignored}개" if ignored else ""))

    # ---------------------------------------------------------- 보고서
    def _open_report(self, table: ResultTable, keep_order: bool = False):
        selected = table.selected()
        if not selected:
            messagebox.showinfo("보고서", "포함할 기사가 없습니다. 먼저 조회하고 ☑ 를 확인하세요.")
            return
        threading.Thread(target=self._report_worker, args=(selected, keep_order), daemon=True).start()

    def _report_worker(self, selected: list[Article], keep_order: bool):
        # 구글 경유 주소는 보고서에 넣기 전에 언론사 원문 주소로 바꾼다(실패하면 구글 주소 유지).
        # 보고 완료 기록은 조회 때와 같은 주소(구글 주소)로 해야 다음 조회에서 걸러지므로 사본만 바꾼다.
        def progress(i, n):
            self.after(0, self._set_status, f"기사 원문 주소 확인 중… ({i}/{n})")
        links = google_news.resolve_links([a.link for a in selected], progress)
        report_items = [dataclasses.replace(a, link=links.get(a.link, a.link)) for a in selected]
        failed = sum(1 for a in report_items if google_news.is_google_link(a.link))
        self.after(0, self._report_done, report_items, failed, keep_order)

    def _report_done(self, report_items: list[Article], failed: int, keep_order: bool):
        start, end = self.period or (parse_start(self.start_var.get()), parse_date(self.end_var.get()))
        body = report.build_html(report_items, self.cfg["keywords"], start.date(), end,
                                 self.cfg.get("report_title", "언론보도 모니터링"))
        mail_items = report_items if keep_order else report.ordered_for_mail(report_items, self.cfg["keywords"])
        simple = report.build_simple_html(mail_items)
        subject = report.mail_subject(self.cfg.get("mail_subject", report.DEFAULT_SUBJECT), dt.date.today())
        path = report.save_report(body, subject=subject, simple_html=simple)
        webbrowser.open("file:///" + path.replace("\\", "/"))
        self._set_status(f"보고서 저장: {path}" + (f" (원문 주소 못 찾은 {failed}건은 구글 경유)" if failed else ""))

    def _mark_sent(self, table: ResultTable):
        selected = table.selected()
        if not selected:
            messagebox.showinfo("기록", "기록할 기사가 없습니다.")
            return
        if not messagebox.askyesno("보고 완료", f"선택된 {len(selected)}건을 보고 완료로 기록할까요?\n"
                                   "다음 조회부터 '이미 보고한 기사 제외'로 걸러집니다."):
            return
        entries = []
        for a in selected:
            main = url_key(a)
            entries.append({"link": main, "title": a.title, "source": a.source, "main": main,
                            "url": google_news.cached_link(main)})
            for src, title, link in a.others:  # 같은 사안으로 묶인 기사도 함께(다음 조회에서 걸러지게)
                entries.append({"link": link, "title": title, "source": src, "main": main})
        now = dt.datetime.now(KST)
        n = history.mark_sent(entries, when=now)
        self._refresh_history(select_day=now.date().isoformat())
        self._set_status(f"보고 완료 기록: {n}건 추가 → [보고 기록] 탭에서 날짜별로 볼 수 있습니다")

    # -------------------------------------------------------- 업데이트
    def _check_update_silently(self):
        threading.Thread(target=self._update_worker, args=(False,), daemon=True).start()

    def _check_update(self):
        self._set_status("업데이트 확인 중…")
        threading.Thread(target=self._update_worker, args=(True,), daemon=True).start()

    def _update_worker(self, verbose: bool):
        try:
            info = updater.check_latest()
        except Exception as e:  # 어떤 오류든 '확인 중…'에 멈춰 있지 않게 이유를 보여 준다
            info = str(e) or type(e).__name__
        self.after(0, self._update_result, info, verbose)

    def _update_result(self, info, verbose: bool):
        if isinstance(info, str):
            if verbose:
                self._set_status(f"업데이트 확인 실패: {info}")
            return
        if not updater.is_newer(info.version):
            if verbose:
                self._set_status(f"최신 버전입니다 (v{__version__})")
            return

        notes = ("\n\n변경 내용:\n" + info.notes[:600]) if info.notes else ""
        if updater.is_frozen() and info.asset_url:
            if messagebox.askyesno("업데이트", f"새 버전 {info.version} 이 있습니다. 지금 업데이트할까요?\n"
                                   f"(내려받은 뒤 앱이 자동으로 다시 시작됩니다){notes}"):
                self._apply_update(info)
        else:
            if messagebox.askyesno("업데이트", f"새 버전 {info.version} 이 있습니다. 다운로드 페이지를 열까요?{notes}"):
                webbrowser.open(info.page_url)

    def _apply_update(self, info):
        win = tk.Toplevel(self)
        win.title("업데이트 중")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text="새 버전을 내려받는 중입니다…", padding=14).pack()
        bar = ttk.Progressbar(win, length=320, mode="determinate", maximum=100)
        bar.pack(padx=14, pady=(0, 14))

        def progress(ratio: float):
            self.after(0, bar.configure, {"value": int(ratio * 100)})

        def worker():
            try:
                updater.apply_update(info.asset_url, progress)
            except Exception as e:
                self.after(0, lambda: (win.destroy(), messagebox.showerror("업데이트 실패", str(e))))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
