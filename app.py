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
import json
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
import export
import feeds
import google_news
import history
import mail_import
import naver_api
import ranking
import report
import rules
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
TABS = ["basic", "pro", "history", "rules", "settings"]
TAB_NAMES = {"basic": "베이직", "pro": "프로", "history": "보고 기록", "rules": "선정 규칙", "settings": "설정"}
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
        self.last_search: dict | None = None  # 마지막 조회의 조건·빠진 기사 (결과 내려받기용)
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
        self._build_rules(self.pages["rules"])
        self._build_settings(self.pages["settings"])

    def _build_header(self):
        """네이비 머리띠: 앱 이름 + 버전, 탭 5개(선택 탭 아래 흰 막대), 업데이트 확인."""
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
            elif name == "rules":
                n = len(self.cfg.get("rules_log", []))
                self._set_status("고친 규칙은 [규칙 저장]을 눌러야 다음 조회부터 적용됩니다."
                                 + (f" 지금까지 {n}번 바꿨습니다." if n else " 지금은 기본 규칙입니다."),
                                 word="선정 규칙", kind="info")

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
                          ("단순 행사 기사 제외 (A는 감점)", self.exclude_events_var)):
            ttk.Checkbutton(head, text=text, variable=var).pack(side="left", padx=(0, 18))
        hline(cond).pack(fill="x")
        body = tk.Frame(cond, bg=PANEL)
        body.pack(fill="x", padx=16, pady=(10, 12))
        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x")
        self._period_row(row, ["자동", "오늘", "최근 3일", "최근 7일"])
        self.search_btn = ttk.Button(row, text="조회", width=10, style="Secondary.TButton",
                                     command=lambda: self._search("pro"))
        self.search_btn.pack(side="right")
        # 키워드·제외어·점수는 [선정 규칙] 탭 한곳에서 고친다(여기는 요약만)
        kw = tk.Frame(body, bg=PANEL)
        kw.pack(fill="x", pady=(10, 0))
        ttk.Label(kw, text="키워드", style="PanelTitle.TLabel").pack(side="left", padx=(0, 12))
        self.kw_summary = ttk.Label(kw, text="", style="PanelDesc.TLabel")
        self.kw_summary.pack(side="left")
        ttk.Button(kw, text="선정 규칙에서 고치기 ›", style="Link.TButton",
                   command=lambda: self._select_tab("rules")).pack(side="right")

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
        for text, cmd, style in (("④ 보고 완료로 기록", lambda: self._mark_sent(self.pro), "Secondary.TButton"),
                                 ("③ HTML 보고서 열기", lambda: self._open_report(self.pro), "Secondary.TButton"),
                                 ("② 선정 결과 붙여넣기", self._open_paste, "Secondary.TButton"),
                                 ("① AI 선별 요청문 복사", self._copy_request, "Primary.TButton")):
            ttk.Button(foot, text=text, style=style, command=cmd).pack(side="right", padx=(8, 0))
        # 결과·점수 근거를 엑셀로 — Claude 에 붙여 앱 규칙 개선에 쓴다. 창이 좁으면 안내 글이 먼저 가려진다.
        ttk.Button(foot, text="⤓ 결과 엑셀로 내려받기", style="Small.TButton", command=self._export_results).pack(side="left")
        tk.Label(foot, text="· 표 머리글을 누르면 정렬", bg=BG, fg=DESC, font=self.F.desc).pack(side="left", padx=(6, 0))

    def _update_kw_summary(self):
        r = self.cfg["rules"]
        self.kw_summary.configure(
            text=f"A 기관 {len(rules.a_keywords(r))} · S 사업어 {len(rules.s_keywords(r))} · B 환경 {len(r['kw_b'])}"
                 f" · 제외어 {len(r['exclude_words'])} · 제외 매체 {len(r['exclude_media'])}"
                 f" · 추천 {r['best_count']}건({r['min_score']}점 이상)")

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

        scroll = theme.ScrollPanel(page)
        scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left = scroll.inner
        self.setting_vars: dict[str, tk.StringVar] = {}

        def section(title, desc):
            box = tk.Frame(left, bg=PANEL)
            box.pack(fill="x", padx=20, pady=(10, 9))
            t = ttk.Label(box, text=title, style="PanelTitle.TLabel")
            t.pack(anchor="w")
            ttk.Label(box, text=desc, style="PanelDesc.TLabel").pack(anchor="w", pady=(1, 6))
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
        fr = tk.Frame(box, bg=PANEL)
        fr.pack(fill="x", pady=(4, 0))
        ttk.Button(fr, text="전문지 고르기 ›", style="Link.TButton", command=self._open_feeds).pack(side="right")
        ttk.Checkbutton(fr, text="전문지 RSS 함께 조회", variable=self.feeds_var).pack(side="left")
        self.feeds_summary = ttk.Label(fr, text="", style="PanelDesc.TLabel")
        self.feeds_summary.pack(side="left", padx=(10, 0))
        hline(left).pack(fill="x")

        box, self.naver_title = section("네이버 API", "기사 출처가 '네이버'일 때만 필요합니다.")
        self.naver_entries = []
        for label, key, secret in (("Client ID", "client_id", False), ("Client Secret", "client_secret", True)):
            r = tk.Frame(box, bg=PANEL)
            r.pack(fill="x", pady=2)
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
            r.pack(fill="x", pady=2)
            ttk.Label(r, text=label, style="Panel.TLabel", width=14).pack(side="left")
            v = tk.StringVar()
            self.setting_vars[key] = v
            ttk.Entry(r, textvariable=v, width=36).pack(side="left")
            if key == "mail_subject":
                self.subject_preview = ttk.Label(box, text="", style="PanelDesc.TLabel")
                self.subject_preview.pack(anchor="w", padx=(0, 0), pady=(1, 3))
                v.trace_add("write", lambda *a: self._update_subject_preview())
        hline(left).pack(fill="x")

        box, _ = section("선정 규칙", "키워드·제외어·행사 단어·점수·추천 기준은 [선정 규칙] 탭에서 보고 고칩니다.\n"
                                   "앱을 업데이트하지 않아도 다음 조회부터 바로 적용됩니다.")
        ttk.Button(box, text="선정 규칙 열기 ›", style="Link.TButton",
                   command=lambda: self._select_tab("rules")).pack(anchor="w")

        right = tk.Frame(page, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)
        self.list_counts = {}
        for i, (key, title, desc) in enumerate((
                ("holiday", "공휴일", "자동 기간 계산용 · 임시공휴일은 'YYYY-MM-DD 이름'으로 한 줄 추가"),)):
            p = panel(right)
            p.grid(row=i, column=0, sticky="nsew")
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
            self.holiday_text = text

        foot = tk.Frame(page, bg=BG)
        foot.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        tk.Label(foot, text="모든 값은 이 PC의 config.json에만 저장됩니다.", bg=BG, fg=DESC, font=self.F.desc).pack(side="left")
        ttk.Button(foot, text="설정 저장", width=14, style="PrimaryBig.TButton", command=self._save_settings).pack(side="right")

    # ================================================================== 선정 규칙
    def _build_rules(self, page):
        """선정 규칙: 키워드·거르기·점수·분류·추천을 보고 고친다. 환류(Claude 개선안 붙여넣기)·변경 이력."""
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        self.rule_lists: dict[str, tk.Text] = {}
        self.rule_counts: dict[str, ttk.Label] = {}
        self.rule_nums: dict[str, tk.StringVar] = {}
        self.rule_flags: dict[str, tk.BooleanVar] = {}
        self.rule_texts: dict[str, tk.StringVar] = {}

        note = tk.Frame(page, bg=NOTE_BG, highlightthickness=1, highlightbackground=NOTE_BORDER)
        note.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(note, text="환류: 프로 탭 [결과 엑셀로 내려받기] → [개선 요청문 복사] → Claude 에 엑셀과 함께 보내기 "
                             "→ 답변을 [Claude 답변 붙여넣기] → 바뀐 점 확인 후 적용",
                  style="Note.TLabel", wraplength=560, justify="left").pack(side="left", padx=16, pady=10)
        ttk.Button(note, text="Claude 답변 붙여넣기", style="Small.TButton",
                   command=self._paste_rules).pack(side="right", padx=(6, 12), pady=6)
        ttk.Button(note, text="개선 요청문 복사", style="Small.TButton",
                   command=self._copy_rules_request).pack(side="right", pady=6)

        scroll = theme.ScrollPanel(page)
        scroll.grid(row=1, column=0, sticky="nsew")
        inner = scroll.inner

        def section(title: str, desc: str) -> tk.Frame:
            box = tk.Frame(inner, bg=PANEL)
            box.pack(fill="x", padx=20, pady=(12, 10))
            ttk.Label(box, text=title, style="PanelTitle.TLabel").pack(anchor="w")
            ttk.Label(box, text=desc, style="PanelDesc.TLabel", wraplength=860, justify="left").pack(anchor="w", pady=(1, 8))
            body = tk.Frame(box, bg=PANEL)
            body.pack(fill="x")
            return body

        def lists(body: tk.Frame, keys: list[str], height: int = 6):
            grid = tk.Frame(body, bg=PANEL)
            grid.pack(fill="x", pady=(0, 10))
            for i, key in enumerate(keys):
                grid.grid_columnconfigure(i, weight=1, uniform="rl")
                name, desc = rules.LIST_FIELDS[key]
                col = tk.Frame(grid, bg=PANEL)
                col.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == len(keys) - 1 else 6))
                head = tk.Frame(col, bg=PANEL)
                head.pack(fill="x")
                ttk.Label(head, text=name, style="Panel.TLabel").pack(side="left")
                cnt = ttk.Label(head, text="", style="PanelFaint.TLabel")
                cnt.pack(side="right")
                ttk.Label(col, text=desc, style="PanelDesc.TLabel").pack(anchor="w", pady=(0, 4))
                wrap, text = theme.text_box(col, self.F, height=height)
                wrap.pack(fill="both", expand=True)
                text.bind("<KeyRelease>", lambda e: self._update_rule_counts())
                self.rule_lists[key] = text
                self.rule_counts[key] = cnt

        def numbers(body: tk.Frame, keys: list[str], per_row: int = 4):
            grid = tk.Frame(body, bg=PANEL)
            grid.pack(fill="x", pady=(0, 10))
            for i, key in enumerate(keys):
                name, unit = rules.NUMBER_FIELDS[key]
                cell = tk.Frame(grid, bg=PANEL)
                cell.grid(row=i // per_row, column=i % per_row, sticky="w", padx=(0, 22), pady=3)
                ttk.Label(cell, text=name, style="Panel.TLabel").pack(side="left", padx=(0, 6))
                v = tk.StringVar()
                ttk.Entry(cell, textvariable=v, width=5, justify="right").pack(side="left")
                ttk.Label(cell, text=unit, style="PanelDesc.TLabel").pack(side="left", padx=(4, 0))
                self.rule_nums[key] = v

        body = section("① 검색 키워드", "이 말들로 기사를 찾고, 제목에 실제로 들어 있는지 다시 확인합니다(구글은 검색어가 없는 "
                                      "기사도 주기 때문). 띄어 쓴 말은 같은 순서로 20자 안에 있으면 맞음 · \"따옴표\"는 그대로 · "
                                      "A OR B · -빼는말. 한 줄에 하나.")
        lists(body, ["kw_a", "kw_s", "kw_b"], height=9)
        lists(body, ["kw_a_branch", "complex_names", "exclude_words"], height=5)
        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x")
        ttk.Label(row, text=rules.TEXT_FIELDS["kw_a_branch_with"][0], style="Panel.TLabel").pack(side="left", padx=(0, 6))
        v = tk.StringVar()
        ttk.Entry(row, textvariable=v, width=12).pack(side="left", padx=(0, 22))
        self.rule_texts["kw_a_branch_with"] = v
        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x", pady=(8, 0))
        for key, text in rules.FLAG_FIELDS.items():
            fv = tk.BooleanVar()
            ttk.Checkbutton(row, text=text, variable=fv).pack(side="left", padx=(0, 18))
            self.rule_flags[key] = fv
        numbers(body, ["max_per_keyword"])
        hline(inner).pack(fill="x")

        body = section("② 거르기", "제외 매체는 매체명·주소에 들어 있으면 뺍니다. 단순 행사어가 있으면 A 기사는 감점, "
                                  "나머지는 뺍니다(프로 탭 '단순 행사 기사 제외'가 켜져 있을 때).")
        lists(body, ["event_words", "exclude_media"], height=5)
        hline(inner).pack(fill="x")

        body = section("③ 점수", "제목 기준. 리스크어는 A·S·모회사어·B·리스크 조건어가 같은 제목에 있을 때만, 정책어는 "
                                "S·모회사어·정책 조건어가 있을 때만 점수를 줍니다. 공급·개발어는 S가 없을 때, 일상 공고어는 "
                                "A가 아닐 때 감점. 감점은 음수로 적습니다.")
        numbers(body, ["w_a", "w_s", "w_s2", "w_parent", "w_b", "w_risk", "w_policy", "w_multi_each", "w_multi_max",
                       "w_specialist", "w_specialist_base", "w_local", "w_recent", "w_exclusive", "w_branch_only",
                       "w_dev", "w_routine", "w_event_a"])
        lists(body, ["parent_words", "risk_words", "risk_context_extra"], height=6)
        lists(body, ["policy_words", "policy_context", "dev_words", "routine_words"], height=5)
        lists(body, ["specialist_press", "specialist_free_press", "local_press"], height=4)
        hline(inner).pack(fill="x")

        body = section("④ 분류", "'분류 순서'에서 위부터 처음 맞는 것. 리스크(리스크어 점수) · 기관 직접(A) · 정책·제도"
                                "(정책어 점수·정책·제도어) · 모회사·부처(모회사어) · 공공기관 공통(공통어) · 업계·환경(나머지). "
                                "S 사업어만으로는 정책·제도가 아니고, A가 아닌 공고 기사는 리스크가 아니면 업계·환경. "
                                "프로 탭에서 AI 선정 결과를 붙여 넣으면 AI 분류가 우선입니다.")
        lists(body, ["category_order", "cat_policy_words", "cat_public_words"], height=6)
        hline(inner).pack(fill="x")

        body = section("⑤ 추천 (베이직 ★)", "리스크 먼저(최대 N건) → 공단(A) 최소 N건 → 점수순. 같은 분류는 N건까지"
                                          "(업계·환경은 따로), 최소 점수 미만은 추천하지 않습니다(그날은 추천이 적게 나옴). "
                                          "직접 추가한 기사는 항상 포함.")
        numbers(body, ["best_count", "min_score", "risk_first_max", "a_min", "per_category_max", "industry_max"])
        hline(inner).pack(fill="x")

        body = section("변경 이력", "규칙을 저장할 때마다 무엇이 바뀌었는지 남깁니다(최근 10개).")
        self.rules_log_label = ttk.Label(body, text="", style="Panel.TLabel", wraplength=860, justify="left")
        self.rules_log_label.pack(anchor="w")

        foot = tk.Frame(page, bg=BG)
        foot.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        for text, cmd in (("규칙 파일 불러오기", self._import_rules_file), ("규칙 파일 내보내기", self._export_rules_file),
                          ("기본값으로", self._reset_rules)):
            ttk.Button(foot, text=text, style="Small.TButton", command=cmd).pack(side="left", padx=(0, 8))
        ttk.Button(foot, text="규칙 저장", width=14, style="PrimaryBig.TButton",
                   command=lambda: self._save_rules("직접 수정")).pack(side="right")

    def _load_rules_into_ui(self, r: dict | None = None):
        r = r or self.cfg["rules"]
        for key, text in self.rule_lists.items():
            text.delete("1.0", "end")
            text.insert("1.0", "\n".join(r[key]))
        for key, v in self.rule_nums.items():
            v.set(str(r[key]))
        for key, v in self.rule_flags.items():
            v.set(bool(r[key]))
        for key, v in self.rule_texts.items():
            v.set(r[key])
        self._update_rule_counts()
        self._update_rules_log()
        self._update_kw_summary()

    def _update_rule_counts(self):
        for key, text in self.rule_lists.items():
            self.rule_counts[key].configure(text=f"{len(self._lines(text))}개")

    def _update_rules_log(self):
        log = self.cfg.get("rules_log", [])[-10:][::-1]
        lines = [f"{e['at']} · {e['how']} · " + " / ".join(e["changes"][:6])
                 + (f" 외 {len(e['changes']) - 6}건" if len(e["changes"]) > 6 else "") for e in log]
        self.rules_log_label.configure(text="\n".join(lines) or "아직 바꾼 적이 없습니다(기본 규칙 사용 중).")

    def _rules_from_ui(self) -> dict:
        """화면의 규칙. 숫자가 아닌 칸이 있으면 ValueError(칸 이름)."""
        r = dict(self.cfg["rules"])
        for key, text in self.rule_lists.items():
            r[key] = self._lines(text)
        for key, v in self.rule_nums.items():
            try:
                r[key] = int(v.get().strip())
            except ValueError:
                raise ValueError(rules.label(key)) from None
        for key, v in self.rule_flags.items():
            r[key] = v.get()
        for key, v in self.rule_texts.items():
            r[key] = v.get().strip()
        return rules.normalize(r)

    def _save_rules(self, how: str, new: dict | None = None):
        if new is None:
            try:
                new = self._rules_from_ui()
            except ValueError as e:
                messagebox.showwarning("규칙 저장", f"'{e}' 칸에는 숫자만 적어 주세요.")
                return
        changes = rules.diff(self.cfg["rules"], new)
        if not changes:
            self._load_rules_into_ui()
            self._set_status("바뀐 규칙이 없습니다.", word="선정 규칙", kind="info")
            return
        old = self.cfg["rules"]
        refetch = any(new[k] != old[k] for k in ("kw_a", "kw_a_branch", "kw_a_branch_with", "kw_s", "complex_names",
                                                 "kw_b", "exclude_words", "event_words", "exclude_media",
                                                 "exact_search", "check_summary", "check_summary_s", "max_per_keyword"))
        self.cfg["rules"] = new
        self.cfg["keywords"] = config.all_keywords(self.cfg)
        self.cfg["rules_log"] = (self.cfg.get("rules_log", []) + [rules.log_entry(changes, how, dt.datetime.now(KST))])[-100:]
        config.save(self.cfg)
        self._load_rules_into_ui()
        msg = f"규칙을 저장했습니다({how} · 바뀐 항목 {len(changes)}개)."
        if self.arts:
            self._rescore()
            for t in (self.basic, self.pro):
                t.refresh()
            msg += " 지금 결과의 점수·분류·★추천을 다시 계산했습니다."
            if refetch:
                msg += " 키워드·거르기 규칙이 바뀌었으니 다시 조회해야 반영됩니다."
        self._set_status(msg, word="선정 규칙")

    def _preview_rules(self, new: dict, how: str):
        """바뀔 점을 보여 주고 [적용]을 누르면 저장한다."""
        try:
            current = self._rules_from_ui()
        except ValueError:
            current = self.cfg["rules"]
        changes = rules.diff(current, new)
        if not changes:
            messagebox.showinfo("선정 규칙", "지금 규칙과 같습니다. 바뀔 것이 없습니다.")
            return

        def apply():
            win.destroy()
            self._save_rules(how, new)

        win, body, _ = self._dialog("바뀔 규칙 확인", f"{how} — 아래 {len(changes)}개 항목이 바뀝니다. "
                                                   "[적용]을 누르면 저장하고 변경 이력에 남깁니다.", "적용", apply)
        wrap, box = theme.text_box(body, self.F, height=14, width=84)
        wrap.pack(fill="both", expand=True)
        box.configure(wrap="word")
        box.insert("1.0", "\n".join(f"• {c}" for c in changes))
        box.configure(state="disabled")

    def _paste_rules(self):
        def go():
            try:
                new = rules.normalize(rules.from_text(box.get("1.0", "end")))
            except ValueError as e:
                info.configure(text=f"{e} Claude 답변의 JSON 부분({{ 로 시작)을 포함해 붙여 넣으세요.")
                return
            win.destroy()
            self._preview_rules(new, "Claude 개선안 적용")

        win, body, _ = self._dialog(
            "Claude 답변 붙여넣기",
            "Claude 가 돌려준 규칙(JSON)을 붙여 넣으세요. 답변 전체를 붙여 넣어도 됩니다.\n"
            "[다음]을 누르면 바뀔 항목을 먼저 보여 줍니다. 빠진 항목은 기본값으로 채웁니다.", "다음", go)
        wrap, box = theme.text_box(body, self.F, height=14, width=84)
        wrap.pack(fill="both", expand=True)
        box.focus_set()
        row, info = self._info_line(body)
        row.pack(anchor="w", pady=(10, 0))
        info.configure(text="예) {\"format\": \"kohom-newsroom-rules\", \"rules\": {\"kw_s\": [...], \"w_s\": 30, ...}}")

    def _copy_rules_request(self):
        text = selection.build_rules_request(self.cfg["rules"], __version__)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self._set_status("개선 요청문을 복사했습니다 → Claude 대화창에 붙여 넣고 결과 엑셀 파일을 첨부하세요.", word="선정 규칙")

    def _export_rules_file(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="규칙 파일 내보내기", defaultextension=".json",
            initialfile=f"KOHOM뉴스룸_선정규칙_{dt.datetime.now(KST):%Y%m%d}.json", filetypes=[("규칙 파일", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(rules.to_json(self.cfg["rules"]))
        self._set_status(f"저장된 규칙을 파일로 내보냈습니다: {os.path.basename(path)} (다른 PC에서 [규칙 파일 불러오기])",
                         word="선정 규칙")

    def _import_rules_file(self):
        path = filedialog.askopenfilename(parent=self, title="규칙 파일 불러오기",
                                          filetypes=[("규칙 파일", "*.json *.txt"), ("모든 파일", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig") as f:
                new = rules.normalize(rules.from_text(f.read()))
        except (OSError, ValueError, UnicodeDecodeError) as e:
            messagebox.showwarning("규칙 파일 불러오기", f"규칙을 읽지 못했습니다.\n{e}")
            return
        self._preview_rules(new, f"규칙 파일 불러옴({os.path.basename(path)})")

    def _reset_rules(self):
        self._preview_rules(rules.normalize(None), "기본값으로 되돌림")

    def _update_feeds_summary(self):
        fs = self.cfg.get("extra_feeds", [])
        on = [f.get("name", "") for f in fs if f.get("on", True)]
        self.feeds_summary.configure(text=(" · ".join(on) if on else "고른 매체 없음") + f"  ({len(on)}/{len(fs)}곳)")

    def _open_feeds(self):
        """전문지 고르기: 쓸 매체 체크, 추가·수정·삭제, 연결 확인. [저장]하면 바로 config.json 에."""
        feeds_ = [dict(f, on=f.get("on", True)) for f in self.cfg.get("extra_feeds", [])]
        results: dict[int, str] = {}

        def save():
            self.cfg["extra_feeds"] = [{"name": f["name"], "url": f["url"], "on": f["on"]} for f in feeds_]
            config.save(self.cfg)
            win.destroy()
            self._update_feeds_summary()
            on = sum(1 for f in feeds_ if f["on"])
            self._set_status(f"전문지 {on}곳을 함께 조회합니다(전체 {len(feeds_)}곳).", word="설정")

        win, body, _ = self._dialog(
            "전문지 고르기",
            "함께 조회할 전문지를 고릅니다. 첫 칸을 눌러 켜고 끄고, 아래 칸에서 매체를 추가·수정합니다.\n"
            "언론사 홈페이지 주소만 넣어도 됩니다(예: www.aptn.co.kr) — RSS 주소(…/rss/allArticle.xml)를 찾아 연결까지 확인하고,\n"
            "매체 칸을 비워 두면 이름도 채웁니다.",
            "저장", save)
        imgs = {k: tk.PhotoImage(master=win, data=getattr(theme.icons, k)) for k in ("CHECK_ON", "CHECK_OFF")}
        win._imgs = imgs
        tf = tk.Frame(body, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        tf.pack(fill="both", expand=True)
        tree = ttk.Treeview(tf, columns=("name", "url", "check"), show="tree headings", height=7, selectmode="browse")
        tree.heading("#0", text="사용", anchor="w")
        tree.column("#0", width=56, stretch=False)
        for col, head, width, stretch in (("name", "매체", 130, False), ("url", "RSS 주소", 330, True),
                                          ("check", "연결 확인", 190, False)):
            tree.heading(col, text=head, anchor="w")
            tree.column(col, width=width, stretch=stretch, anchor="w")
        tree.pack(fill="both", expand=True)

        form = tk.Frame(body, bg=PANEL)
        form.pack(fill="x", pady=(12, 0))
        name_v, url_v = tk.StringVar(), tk.StringVar()
        ttk.Label(form, text="매체", style="PanelTitle.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(form, textvariable=name_v, width=14).pack(side="left")
        ttk.Label(form, text="홈페이지 또는 RSS 주소", style="PanelTitle.TLabel").pack(side="left", padx=(14, 8))
        ttk.Entry(form, textvariable=url_v, width=40).pack(side="left", fill="x", expand=True)
        btns = tk.Frame(body, bg=PANEL)
        btns.pack(fill="x", pady=(8, 0))
        row, info = self._info_line(body)
        row.pack(anchor="w", pady=(10, 0))
        info.configure(text="고친 내용은 [저장]을 눌러야 반영됩니다.")

        def show(select: int | None = None):
            tree.delete(*tree.get_children())
            for i, f in enumerate(feeds_):
                tree.insert("", "end", iid=str(i), image=imgs["CHECK_ON" if f["on"] else "CHECK_OFF"],
                            values=(f["name"], f["url"], results.get(i, "")))
            if select is not None and tree.exists(str(select)):
                tree.selection_set(str(select))

        def selected() -> int | None:
            sel = tree.selection()
            return int(sel[0]) if sel else None

        def on_click(event):
            iid = tree.identify_row(event.y)
            if iid and tree.identify_region(event.x, event.y) == "tree":
                feeds_[int(iid)]["on"] = not feeds_[int(iid)]["on"]
                show(int(iid))
                return "break"

        def on_select(_e=None):
            i = selected()
            if i is not None:
                name_v.set(feeds_[i]["name"])
                url_v.set(feeds_[i]["url"])

        def resolve(then):
            """주소 칸(홈페이지 또는 RSS) → RSS 주소 찾기·연결 확인 → then(이름, RSS 주소, 결과)."""
            name, text = name_v.get().strip(), url_v.get().strip()
            if not text:
                info.configure(text="언론사 홈페이지 주소(예: www.aptn.co.kr)나 RSS 주소를 적어 주세요.")
                return
            info.configure(text="RSS 주소를 찾는 중…")

            def work():
                url, title, result = feeds.discover(text)
                self.after(0, done, url, title, result)

            def done(url, title, result):
                if url is None and not feeds.looks_like_rss(text):
                    info.configure(text=result)
                    return
                url = url or feeds.rss_candidates(text)[0]  # RSS 주소를 직접 넣었으면 연결이 안 돼도 넣는다
                name_ = name or title or feeds.urlparse(url).netloc.replace("www.", "")
                name_v.set(name_)
                url_v.set(url)
                then(name_, url, result)
            threading.Thread(target=work, daemon=True).start()

        def add():
            def then(name, url, result):
                same = next((f for f in feeds_ if f["url"].split("://")[-1] == url.split("://")[-1]), None)
                if same:
                    info.configure(text=f"이미 목록에 있는 매체입니다: {same['name']}")
                    return
                feeds_.append({"name": name, "url": url, "on": True})
                results[len(feeds_) - 1] = result
                show(len(feeds_) - 1)
                info.configure(text=f"'{name}'을(를) 추가했습니다 — {result}. [저장]을 눌러야 반영됩니다.")
            resolve(then)

        def update():
            i = selected()
            if i is None:
                info.configure(text="고칠 매체를 표에서 먼저 고르세요.")
                return

            def then(name, url, result):
                feeds_[i].update(name=name, url=url)
                results[i] = result
                show(i)
                info.configure(text=f"'{name}'을(를) 고쳤습니다 — {result}.")
            resolve(then)

        def delete():
            i = selected()
            if i is None:
                info.configure(text="지울 매체를 표에서 먼저 고르세요.")
                return
            gone = feeds_.pop(i)
            results.clear()
            show()
            info.configure(text=f"'{gone['name']}'을(를) 목록에서 뺐습니다.")

        def check():
            targets = [i for i in ([selected()] if selected() is not None else range(len(feeds_)))]
            info.configure(text="연결 확인 중…")

            def work():
                for i in targets:
                    results[i] = feeds.check_feed(feeds_[i]["name"], feeds_[i]["url"])
                self.after(0, lambda: (show(selected()), info.configure(
                    text="연결 확인을 마쳤습니다. '실패'인 매체는 RSS 주소를 고치거나 꺼 두세요.")))
            threading.Thread(target=work, daemon=True).start()

        for text, cmd in (("＋ 추가", add), ("고친 내용 적용", update), ("삭제", delete)):
            ttk.Button(btns, text=text, style="Small.TButton", command=cmd).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="연결 확인 (고른 매체, 없으면 전체)", style="Small.TButton", command=check).pack(side="right")
        tree.bind("<Button-1>", on_click)
        tree.bind("<<TreeviewSelect>>", on_select)
        show()

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
        self.list_counts["holiday"].configure(text=f"{len(self._lines(self.holiday_text))}개")

    # ================================================================== 설정 ↔ 화면
    def _load_config_into_ui(self):
        self._set_auto_period()
        self.exclude_sent_var.set(bool(self.cfg.get("exclude_sent", True)))
        self.merge_similar_var.set(bool(self.cfg.get("merge_similar", True)))
        self.exclude_events_var.set(bool(self.cfg.get("exclude_events", True)))
        self.source_var.set(self._source())
        self.feeds_var.set(bool(self.cfg.get("use_feeds", True)))
        for key, v in self.setting_vars.items():
            v.set(str(self.cfg.get(key, "")))
        self.holiday_text.insert("1.0", "\n".join(self.cfg.get("holidays", [])))
        self._on_source_change()
        self._update_list_counts()
        self._update_feeds_summary()
        self._load_rules_into_ui()
        self._update_steps()
        self._on_selection_change()
        tab = self.cfg.get("last_tab", "basic")
        self._select_tab(tab if tab in TABS else "basic")
        self._set_status("[① 조회]를 누르면 시작합니다. 기간은 직전 영업일 09:00부터 자동입니다.", word="준비", kind="info")

    def _save_ui_into_config(self):
        self.cfg["keywords"] = config.all_keywords(self.cfg)
        self.cfg["exclude_sent"] = self.exclude_sent_var.get()
        self.cfg["merge_similar"] = self.merge_similar_var.get()
        self.cfg["exclude_events"] = self.exclude_events_var.get()
        config.save(self.cfg)

    def _save_settings(self):
        self.cfg["source"] = self.source_var.get()
        self.cfg["use_feeds"] = self.feeds_var.get()
        for key, v in self.setting_vars.items():
            self.cfg[key] = v.get().strip()
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
        grades = rules.search_grades(self.cfg["rules"])  # 키워드 → 등급(A/S/B), 검색 순서
        if not grades:
            messagebox.showwarning("키워드 확인", "[선정 규칙] 탭에서 검색 키워드를 한 개 이상 입력하세요.")
            return
        if self._source() == "naver" and (not self.cfg.get("client_id") or not self.cfg.get("client_secret")):
            messagebox.showwarning("설정 필요", "네이버 Client ID / Secret 을 [설정] 탭에서 입력하세요.\n"
                                   "키가 없으면 '구글 뉴스 (키 불필요)'를 고르세요.")
            self._select_tab("settings")
            return

        self.searching = True
        for b in (self.search_btn, self.basic_search_btn):
            b.state(["disabled"])
        self._clear_results()
        self.period = (start, end)
        threading.Thread(target=self._search_worker, args=(grades, start, end), daemon=True).start()

    def _search_worker(self, grades: dict[str, str], start: dt.datetime, end: dt.date):
        source = self._source()
        label = SOURCE_LABELS[source]
        r = self.cfg["rules"]
        found: list[Article] = []
        feed_failed: list[str] = []
        try:
            per_kw = max(0, int(r["max_per_keyword"]))
            n = len(grades)
            for i, kw in enumerate(grades, 1):
                msg = f"{label} 검색 중 · 키워드 {i}/{n} '{kw}' · 지금까지 {len(found)}건 수집"
                self.after(0, lambda m=msg, p=(i - 1) / n: self._set_status(m, word="조회 중", kind="busy", progress=p))
                is_a = grades[kw] == "A"
                if source == "naver":
                    arts = naver_api.search_news(kw, self.cfg["client_id"], self.cfg["client_secret"],
                                                 start.date(), end)
                else:
                    # A 는 빠짐없이(기간 나눠 다시 묻기, 지사명 조합은 한 번), 나머지는 한 번만
                    arts = google_news.search_news(kw, start.date(), end, split=kw in r["kw_a"],
                                                   query=rules.google_query(kw, r["exact_search"]))
                if not is_a and per_kw > 0:
                    arts = arts[:per_kw]
                for a in arts:
                    a.grade = grades[kw]
                found.extend(arts)
            if self.cfg.get("use_feeds", True) and self.cfg.get("extra_feeds"):
                self.after(0, lambda: self._set_status("전문지 RSS 조회 중…", word="조회 중", kind="busy", progress=0.97))
                arts, feed_failed = feeds.search_feeds(self.cfg["extra_feeds"], grades, start.date(), end,
                                                       free=r["specialist_free_press"])
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
        # 빠진 기사와 이유 — [결과 내려받기] 파일의 '빠진 기사' 시트에 남긴다
        dropped: list[tuple[str, str, Article]] = []

        def keep(arts: list[Article], test, reason: str) -> list[Article]:
            """test(기사) 가 빼는 이유(걸린 말)를 돌려주면 뺀다."""
            out = []
            for a in arts:
                why = test(a)
                if why is None:
                    out.append(a)
                else:
                    dropped.append((reason, why, a))
            return out

        # ① 제외 매체(해외·무관 매체)
        media = r["exclude_media"]
        found = keep(found, lambda a: rules.media_hit(media, a.source, a.link), "제외 매체")

        # ② 제목 검증: 구글은 검색어가 제목에 없어도 관련 기사를 준다 → 걸린 키워드를 제목(요약)으로 다시 확인
        free = r["specialist_free_press"]

        def verify(a: Article):
            kh = ranking.keyword_hits(a, r)
            matched = kh["A"] + kh["S"] + kh["B"]
            if matched:
                a.keywords = list(dict.fromkeys(matched))
                a.grade = "A" if kh["A"] else "S" if kh["S"] else "B"
            elif kh["A?"]:  # 지사명만 — 표에는 올리되 추천은 안 함
                a.keywords, a.grade = kh["A?"], "A?"
            elif any(m and m in a.source for m in free):  # 키워드 면제 전문지(실무 기사)
                a.keywords, a.grade = ["전문지"], "전문지"
            else:
                return ", ".join(a.keywords)  # 검색에 쓴 키워드
            return None
        found = keep(found, verify, "검증 실패(제목에 키워드 없음)")

        # ③ 제외어는 A·S 를 뺀 나머지(B·전문지·A?)에만
        ex = r["exclude_words"]
        found = keep(found, lambda a: ", ".join(rules.hits(ex, a.title)) or None if a.grade not in ("A", "S") else None,
                     "제외어")

        # ④ 단순 행사: A 는 빼지 않고 감점(점수 규칙), 나머지는 뺀다
        events_skipped = 0
        if self.cfg.get("exclude_events", True):
            before = len(found)
            ev = r["event_words"]
            found = keep(found, lambda a: ", ".join(rules.hits(ev, a.title)) or None if a.grade != "A" else None,
                         "단순 행사")
            events_skipped = before - len(found)
        found = dedup.dedupe(found, self.cfg.get("merge_similar", True),
                             float(self.cfg.get("similar_threshold", 0.85)), list(grades))
        sent_skipped = 0
        if self.cfg.get("exclude_sent", True):
            sent = history.load()
            titles = history.sent_titles(sent, dedup.normalize)
            before = len(found)
            found = keep(found, lambda a: "" if (history.is_sent(a.all_links, sent)
                                                 or dedup.normalize(a.title) in titles) else None, "이미 보고한 기사")
            sent_skipped = before - len(found)
        # 조회한 그때의 조건(내려받기용). 비밀값(네이버 키)은 담지 않는다.
        cond = {k: self.cfg.get(k) for k in ("exclude_sent", "merge_similar", "exclude_events", "use_feeds",
                                             "similar_threshold")}
        cond["feeds"] = [f.get("name", "") for f in self.cfg.get("extra_feeds", []) if f.get("on", True)]
        cond["rules"] = json.loads(json.dumps(r))
        self.last_search = {"at": dt.datetime.now(KST), "start": start, "end": end, "source": label,
                            "raw_count": raw_count, "feed_failed": feed_failed, "dropped": dropped, "cfg": cond}
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
        arts = list(self.arts.values())
        for a in arts:
            ranking.evaluate(a, self.cfg["rules"], now)
        best = ranking.pick_best(arts, self.cfg["rules"])
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
        self.pro.sort_by("grade", reverse=False)  # 기본: 직접 → A → S → B, 그 안에서 점수 높은 순
        self._refresh_pick_box()
        self.cfg["last_search_at"] = dt.datetime.now(KST).isoformat(timespec="minutes")
        config.save(self.cfg)

        count = lambda g: sum(1 for a in found if a.grade == g)
        merged = sum(len(a.others) for a in found)
        reasons: dict[str, int] = {}
        for reason, _w, _a in (self.last_search or {}).get("dropped", []):
            reasons[reason] = reasons.get(reason, 0) + 1
        short = {"검증 실패(제목에 키워드 없음)": "제목 검증", "이미 보고한 기사": "기보고", "단순 행사": "행사"}
        src = SOURCE_LABELS[self._source()] + ("+전문지" if self.cfg.get("use_feeds", True) else "")
        n_best = sum(1 for a in best if a.grade != "직접")
        msg = (f"[{src}] 수집 {raw_count}건"
               + "".join(f" → {short.get(r, r)} {n}건 제외" for r, n in reasons.items())
               + (f" → 같은 사안 {merged}건 묶음" if merged else "")
               + f" → 표시 {len(found)}건 (A {count('A')} · S {count('S')} · B {count('B')}"
               + (f" · 전문지 {count('전문지')}" if count("전문지") else "")
               + (f" · 지사명만 {count('A?')}" if count("A?") else "") + ")"
               + (f" · ★추천 {n_best}건" if n_best >= self.cfg["rules"]["best_count"]
                  else f" · 오늘은 ★추천 {n_best}건 (기준 {self.cfg['rules']['min_score']}점 이상)"))
        n_risk = sum(1 for a in found if a.grade != "직접" and a.auto_category == "리스크")
        risk_best = sum(1 for a in best if a.grade != "직접" and a.auto_category == "리스크")
        if n_risk > risk_best:
            msg += f" · 리스크 {n_risk}건 중 {risk_best}건 추천 — 나머지는 표에서 확인"
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
        """키워드별 선택 목록: 등급 A·S·B, 그리고 결과에 나온 키워드(건수 포함)."""
        arts = list(self.arts.values())
        self.pick_targets.clear()
        for g in ("A", "A?", "S", "B", "전문지"):
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

    def _export_results(self):
        """프로 표의 결과 전부 + 빠진 기사 + 조회 조건을 엑셀 파일 하나로 저장한다(Claude 환류용)."""
        if not self.arts or not self.last_search:
            messagebox.showinfo("결과 내려받기", "먼저 [조회]를 눌러 결과를 만든 뒤 내려받으세요.")
            return
        ls = self.last_search
        folder = os.path.join(os.path.expanduser("~"), "Downloads")
        path = filedialog.asksaveasfilename(
            parent=self, title="조회 결과 내려받기", defaultextension=".xlsx",
            initialdir=folder if os.path.isdir(folder) else None, initialfile=export.default_name(ls["at"]),
            filetypes=[("엑셀 파일", "*.xlsx")])
        if not path:
            return
        shown = [(self.arts[i], bool(self.pro.checked.get(i)), bool(self.basic.checked.get(i)))
                 for i in self.pro.order()]
        merged = sum(len(a.others) for a, *_ in shown)
        try:
            export.save_xlsx(path, shown, ls["dropped"], self._export_conditions(shown, merged), ls["cfg"]["rules"])
        except PermissionError:
            messagebox.showerror("결과 내려받기", "파일을 저장하지 못했습니다.\n"
                                 "같은 이름의 파일이 엑셀에서 열려 있으면 닫고 다시 해 주세요.")
            return
        self._set_status(f"조회 결과 {len(shown)}건 · 빠진 기사 {len(ls['dropped']) + merged}건을 저장했습니다: "
                         f"{os.path.basename(path)}", word="내려받기 완료")
        if messagebox.askyesno("결과 내려받기", f"저장했습니다.\n{path}\n\n저장한 폴더를 열까요?"):
            folder = os.path.dirname(path)
            if hasattr(os, "startfile"):
                os.startfile(folder)
            else:
                webbrowser.open(folder)

    def _export_conditions(self, shown, merged: int) -> list[tuple[str, str]]:
        """내려받기 파일의 '조회 조건' 시트 — 조회한 그때의 값."""
        ls, c = self.last_search, self.last_search["cfg"]
        yes = lambda v: "예" if v else "아니요"
        count = lambda g: sum(1 for a, *_ in shown if a.grade == g)
        reasons: dict[str, int] = {}
        for reason, _w, _a in ls["dropped"]:
            reasons[reason] = reasons.get(reason, 0) + 1
        return [
            ("앱 버전", f"{APP_TITLE} v{__version__}"),
            ("조회 시각", f"{ls['at']:%Y-%m-%d %H:%M}"),
            ("기간", f"{ls['start']:%Y-%m-%d %H:%M} ~ {ls['end']:%Y-%m-%d}"),
            ("검색 방식", ls["source"] + (" + 전문지 RSS" if c["use_feeds"] else "")),
            ("전문지 RSS", ", ".join(c["feeds"]) if c["use_feeds"] else "사용 안 함"),
            ("전문지 조회 실패", ", ".join(ls["feed_failed"]) or "없음"),
            ("이미 보고한 기사 제외", yes(c["exclude_sent"])),
            ("같은 사안 기사 묶기", yes(c["merge_similar"]) + f" (제목 비슷함 기준 {c['similar_threshold']})"),
            ("단순 행사 기사 제외", yes(c["exclude_events"]) + " (A 기사는 빼지 않고 감점)"),
            ("규칙", "조회한 그때의 규칙 전체는 '선정 규칙' 시트"),
            ("건수 흐름", f"수집 {ls['raw_count']}건"
             + "".join(f" → {r} {n}건 제외" for r, n in reasons.items())
             + (f" → 같은 사안 {merged}건 묶음" if merged else "")
             + f" → 표시 {len(shown)}건 (A {count('A')} · S {count('S')} · B {count('B')} · 직접 {count('직접')})"),
            ("최종 선택", f"프로 {sum(1 for s in shown if s[1])}건 · 베이직 {sum(1 for s in shown if s[2])}건"),
        ]

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
            if verbose:  # [업데이트 확인]을 직접 눌렀을 때만 알린다(켤 때 자동 확인은 조용히)
                self._set_status(f"업데이트를 확인하지 못했습니다: {info}", word="업데이트", kind="error")
                messagebox.showwarning("업데이트 확인 실패", self._no_github_message(info))
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

    def _no_github_message(self, detail: str) -> str:
        return ("이 PC에서 GitHub(github.com)에 접속할 수 없어 새 버전을 확인하지 못했습니다.\n"
                "회사 보안정책으로 GitHub 접속이 막힌 PC일 수 있습니다.\n\n"
                "새 버전이 필요하면 공문으로 안내된 곳에서 최신 파일(NewsMonitor_v○○.exe)을 받아\n"
                "지금 쓰는 파일과 바꿔 주세요. 설정과 보고 기록은 그대로 남습니다.\n"
                "(외부에서는 github.com/kohomkpi-code/news-monitor/releases 에서 받을 수 있습니다.)\n\n"
                f"지금 버전: v{__version__}\n오류 내용: {detail}")

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
                msg = self._no_github_message(f"{type(e).__name__}: {e}"[:200]).replace(
                    "새 버전을 확인하지 못했습니다", "새 버전 파일을 내려받지 못했습니다")
                self.after(0, lambda: (win.destroy(), messagebox.showerror("업데이트 실패", msg)))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
