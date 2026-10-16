"""KOHOM 뉴스룸 — 화면(GUI).

화면은 이 파일과 result_table.py(결과 표)·theme.py(색·글꼴·버튼 모양)에만 있고, 실제 일
(검색·중복제거·추천·보고서·업데이트)은 각각의 모듈이 한다. 화면과 일을 분리해 두면 나중에
화면을 바꾸거나 자동 실행 버전을 만들 때 아래 모듈들을 그대로 쓸 수 있다.

탭 네 개 (위쪽 네이비 머리띠):
- 베이직: 누구나. ①조회 → ②★추천 확인 → ③보고서 열기 → ④보고 완료 기록. 지금 단계가 위에 표시되고,
          다음에 누를 버튼 하나만 네이비(주 버튼)로 칠해진다.
- 프로:   조회 조건(키워드·제외어, 접기 가능)과 결과·작업. AI 선별 중계(요청문 복사·선정 결과 붙여넣기).
- 보고 기록: 보고한 기사를 날짜별로. 그날 보고서 다시 열기, 지난 보고 메일 불러오기, 기록 취소.
- 설정:   출처, 네이버 키, 메일 제목, 추천 건수, 행사 단어, 공휴일.
조회 기간(베이직·프로 공통)은 앱을 켜면 '직전 영업일 9시 ~ 오늘'로 자동으로 채워지고, 고칠 수 있다.
두 탭은 같은 조회 결과를 보지만 선택은 따로 가진다.
디자인: Claude Design 시안·명세(2026-10-16)를 tkinter 로 옮김 — 색·여백·글꼴은 theme.py.
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
import theme
import updater
from naver_api import Article, NaverApiError
from result_table import ResultTable
from theme import (AMBER, BG, BORDER, DESC, FAINT, INPUT_BORDER, NAVY, NAVY_HOVER, NOTE_BG, NOTE_BORDER,
                   PANEL, RED, STATUS_TEXT, TAB_OFF, TEAL, TEXT, hline, panel, vline)
from version import APP_TITLE, __version__

KST = calendar_kr.KST
SOURCE_LABELS = {"google": "구글 뉴스", "naver": "네이버"}
TABS = ["basic", "pro", "history", "settings"]
TAB_NAMES = {"basic": "베이직", "pro": "프로", "history": "보고 기록", "settings": "설정"}
STEPS = [("조회", "기간 확인 후 조회"), ("추천 확인", "★추천 확인 · 선택 0건"),
         ("보고서 열기", "제목·본문 복사 → 메일 붙여넣기"), ("보고 완료로 기록", "보낸 기사는 다음 조회에서 빠짐")]
PERIOD_BUTTONS = {"자동": "auto", "오늘": 0, "최근 3일": 2, "최근 7일": 6}

theme.load_private_fonts()  # Tk 창을 만들기 전에 (윈도우에서 Pretendard 를 이 프로그램 안에서만 쓰기)


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


def weekday_ko(d: dt.date) -> str:
    return "월화수목금토일"[d.weekday()]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} v{__version__}")
        self.geometry("1180x780")
        self.minsize(980, 640)
        self.F = theme.Fonts(self)
        theme.setup_styles(self, self.F)

        self.cfg = config.load()
        self.arts: dict[str, Article] = {}        # 줄 id → 기사 (두 탭이 함께 씀)
        self.next_id = 0
        self.request_map: dict[int, str] = {}     # 'AI 선별 요청문'의 번호 → 줄 id
        self.pick_targets: dict[str, tuple[str, str]] = {}  # 키워드별 선택 목록 문구 → ("grade"/"kw", 값)
        self.period: tuple[dt.datetime, dt.date] | None = None  # 마지막 조회 기간
        self.searching = False
        self.step = 1               # 베이직 단계: 1 조회 → 2 추천 확인 → 3 보고서 → 4 기록 → 5 끝
        self.tab = "basic"

        self._build_ui()
        self._load_config_into_ui()
        self.after(1500, self._check_update_silently)

    # ================================================================== 큰 틀
    def _build_ui(self):
        self.start_var = tk.StringVar()   # 조회 기간: 베이직·프로 두 탭이 같은 칸을 함께 쓴다
        self.end_var = tk.StringVar()
        self.period_groups: list[theme.SegGroup] = []

        self._build_header()
        self._build_statusbar()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=16)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.pages: dict[str, tk.Frame] = {}
        for name in TABS:
            page = tk.Frame(body, bg=BG)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[name] = page
        self._build_basic(self.pages["basic"])
        self._build_pro(self.pages["pro"])
        self._build_history(self.pages["history"])
        self._build_settings(self.pages["settings"])

    def _build_header(self):
        """네이비 머리띠: 앱 이름 + 버전, 탭 4개(선택 탭 아래 흰 막대), 업데이트 확인."""
        bar = tk.Frame(self, bg=NAVY, height=48)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        tk.Label(bar, text=APP_TITLE, bg=NAVY, fg="#FFFFFF", font=self.F.app).pack(side="left", padx=(20, 6))
        tk.Label(bar, text=f"v{__version__}", bg=NAVY, fg=TAB_OFF, font=self.F.desc).pack(side="left", padx=(0, 22))
        self.tab_widgets: dict[str, tuple[tk.Frame, tk.Label, tk.Frame]] = {}
        for name in TABS:
            box = tk.Frame(bg=NAVY, master=bar)
            box.pack(side="left", fill="y")
            lab = tk.Label(box, text=TAB_NAMES[name], bg=NAVY, fg=TAB_OFF, font=self.F.tab, padx=16, cursor="hand2")
            lab.pack(side="top", fill="both", expand=True)
            under = tk.Frame(box, bg=NAVY, height=3)
            under.pack(side="bottom", fill="x")
            for w in (box, lab):
                w.bind("<Button-1>", lambda e, n=name: self._select_tab(n))
                w.bind("<Enter>", lambda e, n=name: self._hover_tab(n, True))
                w.bind("<Leave>", lambda e, n=name: self._hover_tab(n, False))
            self.tab_widgets[name] = (box, lab, under)
        upd_wrap = tk.Frame(bar, bg="#4C6A8C")
        upd_wrap.pack(side="right", padx=20)
        tk.Button(upd_wrap, text="업데이트 확인", command=self._check_update, bg=NAVY, fg="#E6ECF2",
                  activebackground=NAVY_HOVER, activeforeground="#FFFFFF", relief="flat", bd=0,
                  font=self.F.small, padx=12, pady=4, cursor="hand2").pack(padx=1, pady=1)

    def _hover_tab(self, name: str, on: bool):
        if name == self.tab:
            return
        box, lab, under = self.tab_widgets[name]
        bg = NAVY_HOVER if on else NAVY
        for w in (box, lab, under):
            w.configure(bg=bg)
        lab.configure(fg="#FFFFFF" if on else TAB_OFF)

    def _select_tab(self, name: str):
        self.tab = name
        for n, (box, lab, under) in self.tab_widgets.items():
            on = n == name
            for w in (box, lab):
                w.configure(bg=NAVY)
            lab.configure(fg="#FFFFFF" if on else TAB_OFF, font=self.F.tab_on if on else self.F.tab)
            under.configure(bg="#FFFFFF" if on else NAVY)
        self.pages[name].tkraise()
        self.cfg["last_tab"] = name
        try:
            config.save(self.cfg)
        except OSError:
            pass
        if not self.searching:
            if name == "history":
                days = len(self.history_days)
                total = sum(len(v) for v in self.history_days.values())
                self._set_status(f"보고일 {days}일 · 총 {total}건 · {history.KEEP_DAYS // 365}년이 지난 기록은 자동으로 지워집니다.",
                                 word="보고 기록", kind="info")
            elif name == "settings":
                self._set_status("바꾼 값은 [설정 저장]을 눌러야 적용됩니다.", word="설정", kind="info")

    def _build_statusbar(self):
        """네이비 상태 띠: 점 · 상태어 · (진행 막대) · 문장. 오류면 띠 전체가 빨강."""
        self.status_bar = tk.Frame(self, bg=NAVY)
        self.status_bar.pack(fill="x", side="bottom")
        inner = tk.Frame(self.status_bar, bg=NAVY)
        inner.pack(fill="x", padx=20, pady=(6, 7))
        self.status_dot = tk.Frame(inner, bg=theme.DOT_OK, width=8, height=8)
        self.status_dot.pack(side="left", padx=(0, 8))
        self.status_word = tk.Label(inner, text="준비", bg=NAVY, fg="#FFFFFF", font=self.F.status_word)
        self.status_word.pack(side="left", padx=(0, 10))
        self.status_prog = ttk.Progressbar(inner, style="Status.Horizontal.TProgressbar", length=140,
                                           mode="determinate", maximum=100)
        self.status_msg = tk.Label(inner, text="[① 조회]를 누르면 시작합니다.", bg=NAVY, fg=STATUS_TEXT,
                                   font=self.F.status, anchor="w", justify="left")
        self.status_msg.pack(side="left", fill="x", expand=True)
        self.status_parts = (self.status_bar, inner, self.status_word, self.status_msg)
        self.status_bar.bind("<Configure>", lambda e: self.status_msg.configure(wraplength=max(200, e.width - 240)))
        self.status_var = tk.StringVar()  # 시험·예전 코드용(마지막 문장)

    def _set_status(self, text: str, word: str | None = None, kind: str | None = None,
                    progress: float | None = None):
        """kind: ok(완료) / busy(진행 중, 앰버) / error(빨강 띠) / info(안내)."""
        if kind is None:
            kind = ("error" if ("실패" in text or "오류" in text) else
                    "busy" if text.rstrip().endswith(("…", "...")) or "중…" in text else "ok")
        word = word or {"ok": "완료", "busy": "진행 중", "error": "오류", "info": "안내"}[kind]
        bg = RED if kind == "error" else NAVY
        for w in self.status_parts:
            w.configure(bg=bg)
        self.status_word.configure(text=word)
        self.status_msg.configure(text=text, fg="#FFFFFF" if kind == "error" else STATUS_TEXT)
        self.status_dot.configure(bg="#FFFFFF" if kind == "error" else AMBER if kind == "busy" else theme.DOT_OK)
        if progress is not None and kind == "busy":
            self.status_prog.configure(value=progress * 100)
            if not self.status_prog.winfo_manager():
                self.status_prog.pack(side="left", padx=(0, 12), before=self.status_msg)
        elif self.status_prog.winfo_manager():
            self.status_prog.pack_forget()
        self.status_var.set(text)

    # ================================================================== 베이직
    def _build_basic(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        # 단계 표시 (4칸)
        steps = panel(page)
        steps.grid(row=0, column=0, sticky="ew")
        self.step_cells = []
        for i, (title, desc) in enumerate(STEPS):
            steps.grid_columnconfigure(i * 2, weight=1, uniform="step")
            if i:
                vline(steps).grid(row=0, column=i * 2 - 1, sticky="ns")
            cell = tk.Frame(steps, bg=PANEL)
            cell.grid(row=0, column=i * 2, sticky="nsew")
            row = tk.Frame(cell, bg=PANEL)
            row.pack(fill="x", padx=16, pady=(11, 9))
            box = tk.Frame(row, width=26, height=26, bg=PANEL, highlightthickness=1, highlightbackground=INPUT_BORDER)
            box.pack(side="left", anchor="n", pady=2)
            box.pack_propagate(False)
            num = tk.Label(box, text=str(i + 1), bg=PANEL, fg=FAINT, font=self.F.step_no)
            num.pack(fill="both", expand=True)
            texts = tk.Frame(row, bg=PANEL)
            texts.pack(side="left", padx=(12, 0), fill="x")
            t = tk.Label(texts, text=title, bg=PANEL, fg=NAVY, font=self.F.title, anchor="w")
            t.pack(anchor="w")
            d = tk.Label(texts, text=desc, bg=PANEL, fg=DESC, font=self.F.desc, anchor="w")
            d.pack(anchor="w")
            under = tk.Frame(cell, bg=PANEL, height=3)
            under.pack(side="bottom", fill="x")
            self.step_cells.append((box, num, t, d, under))

        # 조회 기간
        per = panel(page)
        per.grid(row=1, column=0, sticky="ew", pady=12)
        row = tk.Frame(per, bg=PANEL)
        row.pack(fill="x", padx=16, pady=12)
        self._period_row(row, ["자동", "오늘", "최근 3일"])
        ttk.Label(row, text="자동 = 직전 영업일 09:00 ~ 지금", style="PanelDesc.TLabel").pack(side="left", padx=(14, 0))
        self.basic_search_btn = ttk.Button(row, text="① 조회", width=12, style="Primary.TButton",
                                           command=lambda: self._search("basic"))
        self.basic_search_btn.pack(side="right")

        # 결과
        res = panel(page)
        res.grid(row=2, column=0, sticky="nsew")
        head = tk.Frame(res, bg=PANEL)
        head.pack(fill="x", padx=16, pady=10)
        self.basic_count = self._count_labels(head, "후보")
        vline(head).pack(side="left", fill="y", padx=14, pady=2)
        tk.Label(head, text="★", bg=PANEL, fg=AMBER, font=self.F.small).pack(side="left")
        ttk.Label(head, text="추천", style="PanelDesc.TLabel").pack(side="left", padx=(4, 14))
        theme.swatch(head, theme.A_BG, AMBER).pack(side="left")
        ttk.Label(head, text="공단(A)", style="PanelDesc.TLabel").pack(side="left", padx=(5, 14))
        theme.swatch(head, theme.MANUAL_BG, TEAL).pack(side="left")
        ttk.Label(head, text="직접 추가", style="PanelDesc.TLabel").pack(side="left", padx=(5, 0))
        ttk.Button(head, text="＋ 기사 링크로 추가", style="Small.TButton", command=self._open_add_link).pack(side="right")
        ttk.Button(head, text="↻ 추천으로 되돌리기", style="Small.TButton",
                   command=lambda: self._select_best(self.basic)).pack(side="right", padx=8)
        hline(res, BORDER).pack(fill="x")
        self.basic = ResultTable(res, ["date", "source", "title"], self.arts, self._keyword_rank,
                                 self._open_article, self._set_status, self.F, on_change=self._on_selection_change)
        self.basic.frame.pack(fill="both", expand=True)

        # 아래: 안내 + ③ ④
        foot = tk.Frame(page, bg=BG)
        foot.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.basic_foot = tk.Label(foot, text="조회하면 ★추천 기사가 미리 선택됩니다.", bg=BG, fg=DESC, font=self.F.desc)
        self.basic_foot.pack(side="left")
        self.basic_mark_btn = ttk.Button(foot, text="④ 보고 완료로 기록", width=18, style="SecondaryBig.TButton",
                                         command=lambda: self._mark_sent(self.basic))
        self.basic_mark_btn.pack(side="right")
        self.basic_report_btn = ttk.Button(foot, text="③ HTML 보고서 열기 (메일용)", width=24, style="SecondaryBig.TButton",
                                           command=lambda: self._open_report(self.basic, keep_order=True))
        self.basic_report_btn.pack(side="right", padx=(0, 8))

    def _period_row(self, row, buttons: list[str]):
        """'조회 기간 [시작] ~ [끝] [자동|오늘|…]' — 베이직·프로가 같은 칸(start_var/end_var)을 쓴다."""
        ttk.Label(row, text="조회 기간", style="PanelTitle.TLabel").pack(side="left", padx=(0, 14))
        e1 = ttk.Entry(row, textvariable=self.start_var, width=17)
        e1.pack(side="left")
        ttk.Label(row, text="~", style="PanelDesc.TLabel").pack(side="left", padx=8)
        e2 = ttk.Entry(row, textvariable=self.end_var, width=12)
        e2.pack(side="left")
        for e in (e1, e2):
            e.bind("<KeyRelease>", lambda ev: self._mark_period(None))
        items = []
        for label in buttons:
            mode = PERIOD_BUTTONS[label]
            items.append((label, self._set_auto_period if mode == "auto" else (lambda d=mode: self._set_period(d))))
        group = theme.SegGroup(row, items)
        group.pack(side="left", padx=(16, 0))
        self.period_groups.append(group)

    def _mark_period(self, label: str | None):
        for g in self.period_groups:
            g.set_on(label if label in g.buttons else None)

    def _count_labels(self, parent, noun: str) -> tuple[ttk.Label, ttk.Label]:
        """'선택 5 건 / 후보 423건'."""
        ttk.Label(parent, text="선택", style="PanelSemi.TLabel").pack(side="left")
        num = ttk.Label(parent, text="0", style="PanelNum.TLabel")
        num.pack(side="left", padx=(6, 2))
        ttk.Label(parent, text="건", style="PanelSemi.TLabel").pack(side="left")
        total = ttk.Label(parent, text=f" / {noun} 0건", style="PanelDesc.TLabel")
        total.pack(side="left", padx=(4, 0), pady=(3, 0))
        self._count_noun = noun
        return num, total

    def _on_selection_change(self):
        for table, (num, total), noun in ((self.basic, self.basic_count, "후보 "),
                                          (getattr(self, "pro", None), getattr(self, "pro_count", (None, None)), "")):
            if table is None or num is None:
                continue
            n, all_ = table.count()
            num.configure(text=str(n))
            total.configure(text=f" / {noun}{all_}건")
        n_basic = self.basic.count()[0]
        self.basic_foot.configure(text=f"선택한 {n_basic}건이 보고서에 들어갑니다." if self.arts
                                  else "조회하면 ★추천 기사가 미리 선택됩니다.")
        self._update_steps()

    def _update_steps(self):
        """단계 칸 색과 문구, 그리고 '다음에 누를 버튼' 하나만 주 버튼(네이비)으로."""
        start = self.period[0] if self.period else None
        descs = [f"{calendar_kr.describe(start)} ~ 지금" if start and self.step > 1 else STEPS[0][1],
                 f"★추천 확인 · 선택 {self.basic.count()[0]}건" if self.arts else STEPS[1][1].replace("0건", "후"),
                 STEPS[2][1], STEPS[3][1] if self.step < 5 else "기록 완료 · 보고 기록 탭에서 확인"]
        for i, (box, num, t, d, under) in enumerate(self.step_cells, 1):
            done, now = i < self.step, i == self.step
            if done:
                bg, fg, txt, border = TEAL, "#FFFFFF", "✓", TEAL
            elif now:
                bg, fg, txt, border = NAVY, "#FFFFFF", str(i), NAVY
            else:
                bg, fg, txt, border = PANEL, FAINT, str(i), INPUT_BORDER
            box.configure(bg=bg, highlightbackground=border)
            num.configure(bg=bg, fg=fg, text=txt)
            t.configure(fg=NAVY if (done or now) else DESC)
            d.configure(fg=DESC if (done or now) else FAINT, text=descs[i - 1])
            under.configure(bg=NAVY if now else PANEL)
        self.basic_search_btn.configure(style="Primary.TButton" if self.step == 1 else "Secondary.TButton")
        self.basic_report_btn.configure(style="PrimaryBig.TButton" if self.step in (2, 3) else "SecondaryBig.TButton")
        self.basic_mark_btn.configure(style="PrimaryBig.TButton" if self.step == 4 else "SecondaryBig.TButton")

    def _set_step(self, step: int):
        self.step = step
        self._update_steps()

    # ================================================================== 프로
    def _build_pro(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        cond = panel(page)
        cond.grid(row=0, column=0, sticky="ew")
        head = tk.Frame(cond, bg=PANEL)
        head.pack(fill="x", padx=16, pady=10)
        ttk.Label(head, text="조회 조건", style="PanelTitle.TLabel").pack(side="left", padx=(0, 20))
        self.exclude_sent_var = tk.BooleanVar()
        self.merge_similar_var = tk.BooleanVar()
        self.exclude_events_var = tk.BooleanVar()
        for text, var in (("이미 보고한 기사 제외", self.exclude_sent_var), ("같은 사안 기사 묶기", self.merge_similar_var),
                          ("단순 행사 기사 제외 (단어는 [설정])", self.exclude_events_var)):
            ttk.Checkbutton(head, text=text, variable=var).pack(side="left", padx=(0, 18))
        self.fold_btn = ttk.Button(head, text="키워드 접기 ▲", style="Link.TButton", command=self._toggle_keywords)
        self.fold_btn.pack(side="right")
        hline(cond).pack(fill="x")
        body = tk.Frame(cond, bg=PANEL)
        body.pack(fill="x", padx=16, pady=(10, 12))
        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x")
        self._period_row(row, ["자동", "오늘", "최근 3일", "최근 7일"])
        self.kw_summary = ttk.Label(row, text="", style="PanelDesc.TLabel")
        self.search_btn = ttk.Button(row, text="조회", width=10, style="Secondary.TButton",
                                     command=lambda: self._search("pro"))
        self.search_btn.pack(side="right")
        self.kw_area = tk.Frame(body, bg=PANEL)
        self.kw_area.pack(fill="x", pady=(12, 0))
        boxes = []
        for i, (title, desc) in enumerate((("A 기관 직접", "무조건 포함 · 한 줄에 하나"),
                                           ("B 정책·환경", "위가 우선 · 한 줄에 하나"),
                                           ("제외어", "제목에 있으면 제외 (A는 예외)"))):
            self.kw_area.grid_columnconfigure(i, weight=1, uniform="kw")
            col = tk.Frame(self.kw_area, bg=PANEL)
            col.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 2 else 6))
            lab = tk.Frame(col, bg=PANEL)
            lab.pack(fill="x", pady=(0, 6))
            ttk.Label(lab, text=title, style="PanelTitle.TLabel").pack(side="left")
            ttk.Label(lab, text=desc, style="PanelDesc.TLabel").pack(side="left", padx=(8, 0))
            wrap, text = theme.text_box(col, self.F, height=4)
            wrap.pack(fill="both", expand=True)
            text.bind("<KeyRelease>", lambda e: self._update_kw_summary())
            boxes.append(text)
        self.kw_a_text, self.kw_b_text, self.ex_text = boxes

        res = panel(page)
        res.grid(row=1, column=0, sticky="nsew", pady=12)
        tools = tk.Frame(res, bg=PANEL)
        tools.pack(fill="x", padx=16, pady=10)
        theme.SegGroup(tools, [("전체 선택", lambda: self.pro.set_all(True)),
                               ("전체 해제", lambda: self.pro.set_all(False)),
                               ("★추천만", lambda: self._select_best(self.pro))]).pack(side="left")
        vline(tools).pack(side="left", fill="y", padx=14, pady=2)
        ttk.Label(tools, text="키워드별", style="PanelTitle.TLabel").pack(side="left", padx=(0, 10))
        self.pick_var = tk.StringVar()
        self.pick_box = ttk.Combobox(tools, textvariable=self.pick_var, state="readonly", width=22, font=self.F.small)
        self.pick_box.pack(side="left")
        theme.SegGroup(tools, [("선택", lambda: self._pick(True)), ("해제", lambda: self._pick(False)),
                               ("이것만", self._pick_only)]).pack(side="left", padx=(10, 0))
        ttk.Button(tools, text="＋ 기사 링크로 추가", style="Small.TButton", command=self._open_add_link).pack(side="right")
        cnt = tk.Frame(tools, bg=PANEL)
        cnt.pack(side="right", padx=(0, 14))
        self.pro_count = self._count_labels(cnt, "")
        hline(res, BORDER).pack(fill="x")
        self.pro = ResultTable(res, ["grade", "score", "category", "keyword", "date", "source", "title"],
                               self.arts, self._keyword_rank, self._open_article, self._set_status, self.F,
                               on_change=self._on_selection_change, widths={"source": 140})
        self.pro.frame.pack(fill="both", expand=True)

        foot = tk.Frame(page, bg=BG)
        foot.grid(row=2, column=0, sticky="ew")
        tk.Label(foot, text="표 머리글을 누르면 그 열로 정렬됩니다.", bg=BG, fg=DESC, font=self.F.desc).pack(side="left")
        for text, cmd, style in (("④ 보고 완료로 기록", lambda: self._mark_sent(self.pro), "Secondary.TButton"),
                                 ("③ HTML 보고서 열기", lambda: self._open_report(self.pro), "Secondary.TButton"),
                                 ("② 선정 결과 붙여넣기", self._open_paste, "Secondary.TButton"),
                                 ("① AI 선별 요청문 복사", self._copy_request, "Primary.TButton")):
            ttk.Button(foot, text=text, style=style, command=cmd).pack(side="right", padx=(8, 0))

    def _toggle_keywords(self, collapsed: bool | None = None):
        if collapsed is None:
            collapsed = self.kw_area.winfo_ismapped()
        if collapsed:
            self.kw_area.pack_forget()
            self.kw_summary.pack(side="left", padx=(16, 0))
            self.fold_btn.configure(text="키워드 펼치기 ▼")
        else:
            self.kw_summary.pack_forget()
            self.kw_area.pack(fill="x", pady=(12, 0))
            self.fold_btn.configure(text="키워드 접기 ▲")
        self._update_kw_summary()
        self.cfg["keywords_collapsed"] = collapsed
        try:
            config.save(self.cfg)
        except OSError:
            pass

    def _update_kw_summary(self):
        self.kw_summary.configure(text=f"A {len(self._lines(self.kw_a_text))}개 · B {len(self._lines(self.kw_b_text))}개"
                                       f" · 제외어 {len(self._lines(self.ex_text))}개")

    # ================================================================== 보고 기록
    def _build_history(self, page):
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(1, weight=1)

        note = tk.Frame(page, bg=NOTE_BG, highlightthickness=1, highlightbackground=NOTE_BORDER)
        note.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Label(note, text=f"'④ 보고 완료로 기록'한 기사와 불러온 지난 보고 메일을 날짜별로 봅니다. "
                             f"기록은 {history.KEEP_DAYS // 365}년 보관되며, 기록을 취소한 기사는 다음 조회에 다시 나옵니다.",
                  style="Note.TLabel").pack(side="left", padx=16, pady=10)
        ttk.Button(note, text="＋ 지난 보고 메일 불러오기 (HTML)", style="Small.TButton",
                   command=self._import_mails).pack(side="right", padx=12, pady=6)

        left = panel(page)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        left.configure(width=260)
        left.grid_propagate(False)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.day_tree = ttk.Treeview(left, columns=("day", "n"), show="headings", selectmode="browse",
                                     style="Days.Treeview")
        self.day_tree.heading("day", text="보고일", anchor="w")
        self.day_tree.heading("n", text="건수", anchor="e")
        self.day_tree.column("day", width=170, anchor="w", stretch=True)
        self.day_tree.column("n", width=60, anchor="e", stretch=False)
        self.day_tree.tag_configure("all", font=self.F.row_off)
        self.day_tree.grid(row=0, column=0, sticky="nsew")
        dsb = ttk.Scrollbar(left, orient="vertical", command=self.day_tree.yview)
        self.day_tree.configure(yscrollcommand=dsb.set)
        dsb.grid(row=0, column=1, sticky="ns")
        self.day_tree.bind("<<TreeviewSelect>>", lambda e: self._show_history_day())
        hline(left).grid(row=1, column=0, columnspan=2, sticky="ew")
        lf = tk.Frame(left, bg=PANEL)
        lf.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(lf, text="↻ 새로고침", style="Small.TButton", command=self._refresh_history).pack(side="left", padx=16, pady=10)

        right = panel(page)
        right.grid(row=1, column=1, sticky="nsew")
        rh = tk.Frame(right, bg=PANEL)
        rh.pack(fill="x", padx=16, pady=10)
        self.day_title = ttk.Label(rh, text="보고 기록", style="PanelBig.TLabel")
        self.day_title.pack(side="left")
        self.day_sub = ttk.Label(rh, text="", style="PanelDesc.TLabel")
        self.day_sub.pack(side="left", padx=(10, 0), pady=(3, 0))
        ttk.Button(rh, text="이 날 보고서 다시 열기 (메일용)", style="Primary.TButton",
                   command=self._reopen_history_report).pack(side="right")
        hline(right, BORDER).pack(fill="x")
        rf = tk.Frame(right, bg=PANEL)
        rf.pack(side="bottom", fill="x")
        hline(rf).pack(fill="x")
        rfi = tk.Frame(rf, bg=PANEL)
        rfi.pack(fill="x", padx=16, pady=10)
        ttk.Label(rfi, text="기록을 취소할 기사를 표에서 먼저 고르세요 (Ctrl·Shift 로 여러 개).",
                  style="PanelDesc.TLabel").pack(side="left")
        self.remove_btn = ttk.Button(rfi, text="선택한 기사 기록 취소", style="Danger.TButton",
                                     command=self._remove_history_items)
        self.remove_btn.pack(side="right")
        self.remove_btn.state(["disabled"])
        tablef = tk.Frame(right, bg=PANEL)
        tablef.pack(fill="both", expand=True)
        self.rec_tree = ttk.Treeview(tablef, columns=("time", "source", "title"), show="headings", selectmode="extended")
        for col, head, width, stretch in (("time", "기록 시각", 96, False), ("source", "매체", 170, False),
                                          ("title", "제목 · 더블클릭하면 기사가 열립니다", 520, True)):
            self.rec_tree.heading(col, text=head, anchor="w")
            self.rec_tree.column(col, width=width, stretch=stretch, anchor="w")
        self.rec_tree.tag_configure("odd", background=theme.STRIPE)
        rsb = ttk.Scrollbar(tablef, orient="vertical", command=self.rec_tree.yview)
        self.rec_tree.configure(yscrollcommand=rsb.set)
        rsb.pack(side="right", fill="y")
        self.rec_tree.pack(side="left", fill="both", expand=True)
        self.rec_tree.bind("<Double-1>", self._open_history_item)
        self.rec_tree.bind("<<TreeviewSelect>>", lambda e: self.remove_btn.state(
            ["!disabled"] if self.rec_tree.selection() else ["disabled"]))
        self.history_days: dict[str, list[tuple[str, dict]]] = {}
        self._refresh_history()

    def _refresh_history(self, select_day: str | None = None):
        keep = (select_day,) if select_day else self.day_tree.selection()
        self.history_days = history.by_date(history.load())
        self.day_tree.delete(*self.day_tree.get_children())
        for day, items in self.history_days.items():
            d = dt.date.fromisoformat(day)
            self.day_tree.insert("", "end", iid=day, values=(f"{day} ({weekday_ko(d)})", f"{len(items)}건"))
        if keep and self.day_tree.exists(keep[0]):
            self.day_tree.selection_set(keep[0])
            self.day_tree.see(keep[0])
        elif self.history_days:
            self.day_tree.selection_set(next(iter(self.history_days)))
        self._show_history_day()

    def _history_day(self) -> str | None:
        sel = self.day_tree.selection()
        return sel[0] if sel else None

    def _show_history_day(self):
        self.rec_tree.delete(*self.rec_tree.get_children())
        self.remove_btn.state(["disabled"])
        day = self._history_day()
        items = self.history_days.get(day, [])
        if day:
            d = dt.date.fromisoformat(day)
            self.day_title.configure(text=f"{d.month}월 {d.day}일 ({weekday_ko(d)}) 보고")
            times = sorted(r["time"] for _, r in items if r["time"])
            self.day_sub.configure(text=f"{len(items)}건" + (f" · {times[-1]} 기록" if times else ""))
        else:
            self.day_title.configure(text="보고 기록이 없습니다")
            self.day_sub.configure(text="④ 보고 완료로 기록하거나 지난 보고 메일을 불러오세요")
        for i, (link, rec) in enumerate(items):
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
            d = dt.date.fromisoformat(day)
            subject = report.mail_subject(self.cfg.get("mail_subject", report.DEFAULT_SUBJECT), d)
            path = report.save_report("", subject=subject, simple_html=report.build_simple_html(items),
                                      day=d, count=len(items))
            webbrowser.open("file:///" + path.replace("\\", "/"))
            self._set_status(f"{day} 보고서를 다시 열었습니다: {len(items)}건", word="보고서")

        self._set_status("기사 원문 주소 확인 중…", word="보고서")
        threading.Thread(target=work, daemon=True).start()

    def _remove_history_items(self):
        links = list(self.rec_tree.selection())
        if not links:
            return
        if not messagebox.askyesno("기록 취소", f"선택한 {len(links)}건의 보고 기록을 지울까요?\n"
                                   "지우면 다음 조회에 다시 나옵니다."):
            return
        n = history.remove(links)
        self._refresh_history()
        self._set_status(f"보고 기록 {n}건을 취소했습니다.", word="보고 기록")

    # ================================================================== 설정
    def _build_settings(self, page):
        page.grid_columnconfigure(0, weight=3, uniform="set")
        page.grid_columnconfigure(1, weight=2, uniform="set")
        page.grid_rowconfigure(0, weight=1)

        left = panel(page)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.setting_vars: dict[str, tk.StringVar] = {}

        def section(title, desc):
            box = tk.Frame(left, bg=PANEL)
            box.pack(fill="x", padx=20, pady=(14, 12))
            t = ttk.Label(box, text=title, style="PanelTitle.TLabel")
            t.pack(anchor="w")
            ttk.Label(box, text=desc, style="PanelDesc.TLabel").pack(anchor="w", pady=(2, 8))
            return box, t

        box, _ = section("기사 출처", "어디에서 기사를 모을지 고릅니다.")
        self.source_var = tk.StringVar()
        r = tk.Frame(box, bg=PANEL)
        r.pack(anchor="w")
        ttk.Radiobutton(r, text="구글 뉴스 (키 필요 없음)", value="google", variable=self.source_var,
                        command=self._on_source_change).pack(side="left", padx=(0, 24))
        ttk.Radiobutton(r, text="네이버 (API 키 필요)", value="naver", variable=self.source_var,
                        command=self._on_source_change).pack(side="left")
        self.feeds_var = tk.BooleanVar()
        names = " · ".join(f.get("name", "") for f in self.cfg.get("extra_feeds", []))
        ttk.Checkbutton(box, text=f"전문지 RSS 함께 조회   {names}", variable=self.feeds_var).pack(anchor="w", pady=(8, 0))
        hline(left).pack(fill="x")

        box, self.naver_title = section("네이버 API", "기사 출처가 '네이버'일 때만 필요합니다.")
        self.naver_entries = []
        for label, key, secret in (("Client ID", "client_id", False), ("Client Secret", "client_secret", True)):
            r = tk.Frame(box, bg=PANEL)
            r.pack(fill="x", pady=3)
            ttk.Label(r, text=label, style="PanelDesc.TLabel", width=14).pack(side="left")
            v = tk.StringVar()
            self.setting_vars[key] = v
            e = ttk.Entry(r, textvariable=v, width=36, show="*" if secret else "")
            e.pack(side="left")
            self.naver_entries.append(e)
        hline(left).pack(fill="x")

        box, _ = section("보고서", "메일 제목과 보고서 맨 위 제목입니다.")
        for label, key in (("메일 제목", "mail_subject"), ("보고서 제목", "report_title")):
            r = tk.Frame(box, bg=PANEL)
            r.pack(fill="x", pady=3)
            ttk.Label(r, text=label, style="Panel.TLabel", width=14).pack(side="left")
            v = tk.StringVar()
            self.setting_vars[key] = v
            ttk.Entry(r, textvariable=v, width=36).pack(side="left")
            if key == "mail_subject":
                self.subject_preview = ttk.Label(box, text="", style="PanelDesc.TLabel")
                self.subject_preview.pack(anchor="w", padx=(0, 0), pady=(2, 6))
                v.trace_add("write", lambda *a: self._update_subject_preview())
        hline(left).pack(fill="x")

        box, _ = section("추천", "베이직 탭에서 미리 고를 건수와 B 키워드 하나당 받을 최대 건수입니다.")
        r = tk.Frame(box, bg=PANEL)
        r.pack(anchor="w")
        for i, (label, key) in enumerate((("추천 건수 (베이직)", "best_count"), ("B 키워드당 최대", "b_max_per_keyword"))):
            ttk.Label(r, text=label, style="Panel.TLabel").pack(side="left", padx=(0 if i == 0 else 28, 8))
            v = tk.StringVar()
            self.setting_vars[key] = v
            ttk.Entry(r, textvariable=v, width=6).pack(side="left")
            ttk.Label(r, text="건", style="PanelDesc.TLabel").pack(side="left", padx=(6, 0))

        right = tk.Frame(page, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        self.list_counts = {}
        for i, (key, title, desc) in enumerate((
                ("event", "단순 행사 단어", "제목에 있으면 A 등급이라도 제외합니다 · 한 줄에 하나"),
                ("holiday", "공휴일", "자동 기간 계산용 · 임시공휴일은 'YYYY-MM-DD 이름'으로 한 줄 추가"))):
            p = panel(right)
            p.grid(row=i, column=0, sticky="nsew", pady=(0, 12) if i == 0 else 0)
            h = tk.Frame(p, bg=PANEL)
            h.pack(fill="x", padx=20, pady=(14, 2))
            ttk.Label(h, text=title, style="PanelTitle.TLabel").pack(side="left")
            cnt = ttk.Label(h, text="", style="PanelDesc.TLabel")
            cnt.pack(side="right")
            self.list_counts[key] = cnt
            ttk.Label(p, text=desc, style="PanelDesc.TLabel", wraplength=380).pack(anchor="w", padx=20, pady=(0, 8))
            wrap, text = theme.text_box(p, self.F, height=6)
            wrap.pack(fill="both", expand=True, padx=20, pady=(0, 16))
            text.bind("<KeyRelease>", lambda e: self._update_list_counts())
            if key == "event":
                self.event_text = text
            else:
                self.holiday_text = text

        foot = tk.Frame(page, bg=BG)
        foot.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        tk.Label(foot, text="모든 값은 이 PC의 config.json에만 저장됩니다.", bg=BG, fg=DESC, font=self.F.desc).pack(side="left")
        ttk.Button(foot, text="설정 저장", width=14, style="PrimaryBig.TButton", command=self._save_settings).pack(side="right")

    def _on_source_change(self):
        naver = self.source_var.get() == "naver"
        for e in self.naver_entries:
            e.state(["!disabled"] if naver else ["disabled"])
        self.naver_title.configure(style="PanelTitle.TLabel" if naver else "PanelFaint.TLabel")

    def _update_subject_preview(self):
        today = dt.date.today()
        result = report.mail_subject(self.setting_vars["mail_subject"].get(), today)
        self.subject_preview.configure(text=f"{{날짜}} → {today:%y%m%d} · 결과: {result}")

    def _update_list_counts(self):
        self.list_counts["event"].configure(text=f"{len(self._lines(self.event_text))}개")
        self.list_counts["holiday"].configure(text=f"{len(self._lines(self.holiday_text))}개")

    # ================================================================== 설정 ↔ 화면
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
        self._on_source_change()
        self._update_list_counts()
        self._toggle_keywords(bool(self.cfg.get("keywords_collapsed", False)))
        self._update_steps()
        self._on_selection_change()
        tab = self.cfg.get("last_tab", "basic")
        self._select_tab(tab if tab in TABS else "basic")
        self._set_status("[① 조회]를 누르면 시작합니다. 기간은 직전 영업일 09:00부터 자동입니다.", word="준비", kind="info")

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
        self._set_status("설정을 저장했습니다.", word="설정")

    @staticmethod
    def _lines(widget: tk.Text) -> list[str]:
        seen, out = set(), []
        for line in widget.get("1.0", "end").splitlines():
            s = line.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    # ================================================================== 대화상자 틀
    def _dialog(self, title: str, intro: str, primary: str, on_primary, secondary: str = "취소"):
        """흰 본문 + 아래 회색 버튼 단(오른쪽에 [주 버튼][취소]). (창, 본문 프레임, 주 버튼)."""
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=PANEL)
        win.transient(self)
        win.grab_set()
        bar = ttk.Frame(win, style="Bar.TFrame")
        bar.pack(side="bottom", fill="x")
        hline(bar, theme.BAR_LINE).pack(fill="x")
        inner = ttk.Frame(bar, style="Bar.TFrame")
        inner.pack(fill="x", padx=20, pady=12)
        ttk.Button(inner, text=secondary, style="Secondary.TButton", width=10, command=win.destroy).pack(side="right")
        pbtn = ttk.Button(inner, text=primary, style="Primary.TButton", width=10, command=on_primary)
        pbtn.pack(side="right", padx=(0, 8))
        body = tk.Frame(win, bg=PANEL)
        body.pack(fill="both", expand=True, padx=20, pady=(18, 14))
        ttk.Label(body, text=intro, style="PanelDesc.TLabel", justify="left").pack(anchor="w", pady=(0, 12))
        win.bind("<Escape>", lambda e: win.destroy())
        return win, body, pbtn

    def _info_line(self, parent) -> tuple[tk.Frame, ttk.Label]:
        row = tk.Frame(parent, bg=PANEL)
        sq = tk.Frame(row, bg=TEAL, width=8, height=8)
        sq.pack(side="left", padx=(0, 8))
        lab = ttk.Label(row, text="", style="PanelOk.TLabel")
        lab.pack(side="left")
        return row, lab

    # ================================================================== 기사 링크로 추가
    def _open_add_link(self):
        vars_ = {k: tk.StringVar() for k in ("url", "title", "source", "date")}
        vars_["date"].set(dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"))

        def add():
            url, title = vars_["url"].get().strip(), vars_["title"].get().strip()
            if not url.startswith("http") or not title:
                info.configure(text="주소와 제목은 꼭 있어야 합니다.")
                return
            try:
                when = parse_start(vars_["date"].get())
            except ValueError:
                when = dt.datetime.now(KST)
            win.destroy()
            self._add_manual(Article(title=title, link=url, naver_link="",
                                     source=vars_["source"].get().strip() or article_fetch.source_name(url),
                                     published=when, description="", keywords=["직접 추가"], grade="직접"))

        win, body, _ = self._dialog(
            "기사 링크로 추가",
            "구글 뉴스에 없는 기사를 직접 추가합니다. 기사 주소를 넣고 [불러오기]를 누르면 제목·매체·날짜가 채워집니다.\n"
            "잘못 채워진 칸은 고친 뒤 [추가]를 누르세요.", "추가", add)
        win.resizable(False, False)
        grid = tk.Frame(body, bg=PANEL)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)

        def label(text, r, c=0):
            ttk.Label(grid, text=text, style="PanelTitle.TLabel").grid(row=r, column=c, sticky="w", pady=5, padx=(0, 16))

        label("기사 주소", 0)
        url_e = ttk.Entry(grid, textvariable=vars_["url"], width=56)
        url_e.grid(row=0, column=1, columnspan=3, sticky="ew", pady=5)
        url_e.focus_set()
        load_btn = ttk.Button(grid, text="불러오기", style="Secondary.TButton")
        load_btn.grid(row=0, column=4, padx=(10, 0))
        label("제목", 1)
        ttk.Entry(grid, textvariable=vars_["title"], width=56).grid(row=1, column=1, columnspan=4, sticky="ew", pady=5)
        label("매체", 2)
        ttk.Entry(grid, textvariable=vars_["source"], width=22).grid(row=2, column=1, sticky="w", pady=5)
        label("날짜", 2, 2)
        ttk.Entry(grid, textvariable=vars_["date"], width=18).grid(row=2, column=3, columnspan=2, sticky="w", pady=5)
        row, info = self._info_line(body)
        row.pack(anchor="w", pady=(10, 0))
        info.configure(text="기사 주소를 붙여 넣고 [불러오기]를 누르세요.")

        def fill(page):
            if page is None:
                info.configure(text="불러오지 못했습니다. 제목·매체를 직접 적어 주세요.")
                return
            vars_["url"].set(page.url)
            vars_["title"].set(page.title)
            vars_["source"].set(page.source)
            if page.published:
                vars_["date"].set(page.published.strftime("%Y-%m-%d %H:%M"))
            info.configure(text="불러왔습니다. 내용을 확인하고 [추가]를 누르세요.")

        def load():
            url = vars_["url"].get().strip()
            if not url.startswith("http"):
                info.configure(text="http 로 시작하는 기사 주소를 붙여 넣으세요.")
                return
            info.configure(text="불러오는 중…")

            def work():
                try:
                    page = article_fetch.fetch(url)
                except Exception:
                    page = None
                self.after(0, fill, page)
            threading.Thread(target=work, daemon=True).start()

        load_btn.configure(command=load)
        url_e.bind("<Return>", lambda e: load())

    # ================================================================== 기간
    def _holidays(self) -> set[dt.date]:
        return calendar_kr.parse_holidays(self.cfg.get("holidays", []))

    def _auto_period(self) -> tuple[dt.datetime, dt.date]:
        now = dt.datetime.now(KST)
        return calendar_kr.auto_start(now, self._holidays()), now.date()

    def _set_auto_period(self):
        start, end = self._auto_period()
        self.start_var.set(start.strftime("%Y-%m-%d %H:%M"))
        self.end_var.set(end.isoformat())
        self._mark_period("자동")

    def _set_period(self, days_back: int):
        today = dt.date.today()
        self.start_var.set((today - dt.timedelta(days=days_back)).isoformat() + " 00:00")
        self.end_var.set(today.isoformat())
        self._mark_period({0: "오늘", 2: "최근 3일", 6: "최근 7일"}.get(days_back))

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
            self._select_tab("settings")
            return

        # 키워드 → 등급. A·B 양쪽에 같은 키워드가 있으면 A.
        grades = {k: "A" for k in self.cfg["keywords_a"]}
        for k in self.cfg["keywords_b"]:
            grades.setdefault(k, "B")

        self.searching = True
        for b in (self.search_btn, self.basic_search_btn):
            b.state(["disabled"])
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
            n = len(grades)
            for i, kw in enumerate(grades, 1):
                msg = f"{label} 검색 중 · 키워드 {i}/{n} '{kw}' · 지금까지 {len(found)}건 수집"
                self.after(0, lambda m=msg, p=(i - 1) / n: self._set_status(m, word="조회 중", kind="busy", progress=p))
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
                self.after(0, lambda: self._set_status("전문지 RSS 조회 중…", word="조회 중", kind="busy", progress=0.97))
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
        for b in (self.search_btn, self.basic_search_btn):
            b.state(["!disabled"])
        self._set_status(msg.splitlines()[0], word="조회 실패", kind="error")
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
        for b in (self.search_btn, self.basic_search_btn):
            b.state(["!disabled"])
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
        self._set_step(2)
        self._on_selection_change()
        self._set_status(msg, word="조회 완료", kind="ok")

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

    # ================================================================== 직접 추가 반영·AI 선별 중계
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

        def apply():
            picked, ignored = selection.parse_selection(box.get("1.0", "end"), len(self.request_map))
            if not picked:
                info.configure(text="읽을 수 있는 줄이 없습니다. 형식: 번호|분류|한 줄 인사이트")
                return
            win.destroy()
            self._apply_selection(picked, ignored)

        # 형식은 판단 기준서(프로젝트 지침) 4장의 '#선정' 줄 그대로 — 시안의 '3, 7, 12' 형식은 쓰지 않는다
        win, body, _ = self._dialog(
            "선정 결과 붙여넣기",
            "Claude 답변의 '#선정' 아래 줄들을 붙여 넣고 [적용]을 누르세요. 답변 전체를 붙여 넣어도 됩니다.\n"
            "형식 예) 12|리스크|공단 관리 단지 승강기 사고 → 전 단지 점검 검토", "적용", apply)
        wrap, box = theme.text_box(body, self.F, height=10, width=84)
        wrap.pack(fill="both", expand=True)
        box.configure(wrap="word")
        box.focus_set()
        row, info = self._info_line(body)
        row.pack(anchor="w", pady=(10, 0))
        info.configure(text="붙여 넣으면 찾은 기사 수가 여기에 나옵니다.")

        def check(_e=None):
            picked, ignored = selection.parse_selection(box.get("1.0", "end"), len(self.request_map))
            if picked:
                info.configure(text=f"기사 {len(picked)}건을 찾았습니다. [적용]을 누르면 이 {len(picked)}건만 선택됩니다."
                               + (f" (무시된 줄 {ignored}개)" if ignored else ""))
            else:
                info.configure(text="아직 읽을 수 있는 줄이 없습니다. 형식: 번호|분류|한 줄 인사이트")
        box.bind("<KeyRelease>", check)
        box.bind("<<Paste>>", lambda e: self.after(50, check))

    def _import_mails(self):
        """그룹웨어에서 내려받은 지난 보고 메일(HTML) 여러 개 → 미리보기 → 보고 기록에 넣기."""
        paths = filedialog.askopenfilenames(
            parent=self, title="지난 보고 메일 파일 고르기 (여러 개 가능)",
            filetypes=[("메일 HTML", "*.html *.htm *.mht *.mhtml *.eml"), ("모든 파일", "*.*")])
        if not paths:
            return
        reports = [mail_import.parse_file(p) for p in paths]
        reports.sort(key=lambda r: (r.day or dt.date.max, r.path))

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
                             + (f" · 날짜·기사를 못 찾은 파일 {left}개 제외" if left else ""), word="불러오기 완료")

        win, body, _ = self._dialog(
            "지난 보고 메일 불러오기",
            "파일마다 찾은 보고일과 기사 수입니다. 보고일이 틀리거나 비었으면 그 줄을 더블클릭해 고치세요.\n"
            "이미 기록에 있는 기사는 건너뜁니다.", "불러오기", do_import)
        tf = tk.Frame(body, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        tf.pack(fill="both", expand=True)
        tree = ttk.Treeview(tf, columns=("file", "day", "time", "n", "note"), show="headings", height=10)
        for col, head, width in (("file", "파일", 300), ("day", "보고일", 110), ("time", "시각", 64),
                                 ("n", "기사", 56), ("note", "날짜 찾은 곳 / 문제", 170)):
            tree.heading(col, text=head, anchor="w")
            tree.column(col, width=width, anchor="w")
        tree.pack(fill="both", expand=True)

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

        tree.bind("<Double-1>", edit_day)
        show()

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
            self.after(0, lambda: self._set_status(f"기사 원문 주소 확인 중… ({i}/{n})", word="보고서",
                                                   kind="busy", progress=i / n))
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
        path = report.save_report(body, subject=subject, simple_html=simple, day=dt.date.today(),
                                  count=len(report_items))
        webbrowser.open("file:///" + path.replace("\\", "/"))
        if self.step < 4:
            self._set_step(4)
        self._set_status("브라우저에서 [제목 복사]·[본문 복사] → 그룹웨어 편지쓰기에 붙여넣기 → 보낸 뒤 [④ 보고 완료로 기록]"
                         + (f" (원문 주소 못 찾은 {failed}건은 구글 경유)" if failed else ""), word="보고서 열림")

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
        if table is self.basic:
            self._set_step(5)
        self._set_status(f"{n}건을 기록했습니다. 다음 조회부터 빠지고, [보고 기록] 탭에서 날짜별로 볼 수 있습니다.",
                         word="기록 완료")

    # -------------------------------------------------------- 업데이트
    def _check_update_silently(self):
        threading.Thread(target=self._update_worker, args=(False,), daemon=True).start()

    def _check_update(self):
        self._set_status("업데이트 확인 중…", word="업데이트")
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
        win.configure(bg=PANEL)
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text="새 버전을 내려받는 중입니다…", style="PanelTitle.TLabel").pack(padx=20, pady=(18, 10))
        bar = ttk.Progressbar(win, length=320, mode="determinate", maximum=100)
        bar.pack(padx=20, pady=(0, 20))

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
