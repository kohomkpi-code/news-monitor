"""언론보도 모니터링 앱 — 화면(GUI).

화면은 이 파일에만 있고, 실제 일(검색·중복제거·보고서·업데이트)은
각각의 모듈이 한다. 화면과 일을 분리해 두면 나중에 화면을 바꾸거나
자동 실행 버전을 만들 때 아래 모듈들을 그대로 쓸 수 있다.

하루 흐름(v0.3.0 '5건 추리기'):
조회(A·B 등급) → ① AI 선별 요청문 복사 → Claude 채팅에 붙여넣기 → 답변의 '#선정' 아래 복사
→ ② 선정 결과 붙여넣기 → ③ HTML 보고서 열기 → 메일 붙여넣기 → ④ 보고 완료로 기록
"""

import dataclasses
import datetime as dt
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

# 회사 보안장비가 HTTPS 를 검사하면서 자체 인증서로 바꿔 끼우면, Python 은 자기 인증서 목록만
# 믿어서 접속을 거부한다(CERTIFICATE_VERIFY_FAILED). 브라우저처럼 윈도우 인증서 저장소를 믿게 한다.
# requests 를 쓰는 모듈(google_news·naver_api·updater)보다 먼저 실행해야 한다.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:  # 실패해도 기존 방식으로 동작
    pass

import config
import dedup
import feeds
import google_news
import history
import naver_api
import report
import selection
import updater
from naver_api import Article, NaverApiError
from version import APP_TITLE, __version__

FONT = ("맑은 고딕", 10)
FONT_BOLD = ("맑은 고딕", 10, "bold")
CHECK_ON, CHECK_OFF = "☑", "☐"
SOURCE_LABELS = {"google": "구글 뉴스", "naver": "네이버"}

# 결과 표의 열: (id, 머리글, 폭, 가운데 정렬, 늘어남)
COLUMNS = [
    ("chk", "포함", 46, True, False),
    ("grade", "등급", 46, True, False),
    ("category", "분류", 90, True, False),
    ("keyword", "키워드", 140, False, False),
    ("date", "날짜", 90, True, False),
    ("source", "매체", 110, False, False),
    ("title", "제목 (더블클릭: 기사 열기)", 520, False, True),
]


def parse_date(text: str) -> dt.date:
    return dt.datetime.strptime(text.strip(), "%Y-%m-%d").date()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} v{__version__}")
        self.geometry("1180x760")
        self.minsize(960, 620)
        self.option_add("*Font", FONT)

        self.cfg = config.load()
        self.art_by_iid: dict[str, Article] = {}  # 표의 줄 id → 기사 (정렬해도 짝이 유지됨)
        self.checked: dict[str, bool] = {}        # 표의 줄 id → 선택 여부
        self.request_map: dict[int, str] = {}     # 'AI 선별 요청문'의 번호 → 표의 줄 id
        self.sort_state: tuple[str, bool] | None = None  # (열, 역순 여부)
        self.pick_targets: dict[str, tuple[str, str]] = {}  # 키워드별 선택 목록 문구 → ("grade"/"kw", 값)
        self.searching = False

        self._build_ui()
        self._load_config_into_ui()
        self.after(1500, self._check_update_silently)

    # ------------------------------------------------------------------ UI
    @staticmethod
    def _text_box(parent, title: str) -> tk.Text:
        frame = ttk.LabelFrame(parent, text=f" {title} ")
        frame.pack(side="left", fill="both", expand=True, padx=4)
        text = tk.Text(frame, height=5, width=20, font=FONT)
        sb = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=4)
        text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        return text

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # 기간
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="기간").pack(side="left")
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.start_var, width=12).pack(side="left", padx=(6, 2))
        ttk.Label(top, text="~").pack(side="left")
        ttk.Entry(top, textvariable=self.end_var, width=12).pack(side="left", padx=(2, 10))
        for label, days in (("오늘", 0), ("어제~오늘", 1), ("최근 3일", 2), ("최근 7일", 6)):
            ttk.Button(top, text=label, width=9,
                       command=lambda d=days: self._set_period(d)).pack(side="left", padx=2)

        ttk.Label(top, text=f"v{__version__}", foreground="#888").pack(side="right")
        ttk.Button(top, text="업데이트 확인", command=self._check_update).pack(side="right", padx=4)
        ttk.Button(top, text="설정", command=self._open_settings).pack(side="right", padx=4)

        # 키워드 A / B / 제외어
        mid = ttk.Frame(self)
        mid.pack(fill="x", padx=4, pady=4)
        self.kw_a_text = self._text_box(mid, "A 기관 직접 (무조건 포함) · 한 줄에 하나")
        self.kw_b_text = self._text_box(mid, "B 정책·환경 (후보) · 한 줄에 하나")
        self.ex_text = self._text_box(mid, "제외어 (제목에 있으면 제외, A는 예외) · 한 줄에 하나")

        # 옵션 + 조회
        opt = ttk.Frame(self)
        opt.pack(fill="x", **pad)
        self.exclude_sent_var = tk.BooleanVar()
        self.merge_similar_var = tk.BooleanVar()
        ttk.Checkbutton(opt, text="이미 보고한 기사 제외", variable=self.exclude_sent_var).pack(side="left")
        ttk.Checkbutton(opt, text="같은 사안 기사 묶기 (매체만 다른 기사)", variable=self.merge_similar_var).pack(side="left", padx=12)
        self.exclude_events_var = tk.BooleanVar()
        ttk.Checkbutton(opt, text="단순 행사 기사 제외 (축제·나눔 등, 단어는 [설정])",
                        variable=self.exclude_events_var).pack(side="left")
        self.search_btn = ttk.Button(opt, text="  조  회  ", command=self._search)
        self.search_btn.pack(side="right")

        # 선택 도구: 전체 / 키워드별
        sel = ttk.Frame(self)
        sel.pack(fill="x", **pad)
        ttk.Label(sel, text="선택").pack(side="left")
        ttk.Button(sel, text="전체 선택", command=lambda: self._set_all(True)).pack(side="left", padx=(6, 2))
        ttk.Button(sel, text="전체 해제", command=lambda: self._set_all(False)).pack(side="left")
        ttk.Separator(sel, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(sel, text="키워드별").pack(side="left")
        self.pick_var = tk.StringVar()
        self.pick_box = ttk.Combobox(sel, textvariable=self.pick_var, state="readonly", width=26)
        self.pick_box.pack(side="left", padx=6)
        ttk.Button(sel, text="☑ 선택", command=lambda: self._pick(True)).pack(side="left", padx=2)
        ttk.Button(sel, text="☐ 해제", command=lambda: self._pick(False)).pack(side="left", padx=2)
        ttk.Button(sel, text="이것만 선택", command=self._pick_only).pack(side="left", padx=2)
        ttk.Label(sel, text="표 머리글 클릭 → 모아서 정렬", foreground="#888").pack(side="right")

        # 결과 표
        table = ttk.Frame(self)
        table.pack(side="top", fill="both", expand=True, padx=8, pady=4)
        self.tree = ttk.Treeview(table, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for col, head, width, center, stretch in COLUMNS:
            if col == "chk":
                cmd = self._toggle_all_from_header
            else:
                cmd = lambda c=col: self._sort_by(c)
            self.tree.heading(col, text=head, command=cmd)
            self.tree.column(col, width=width, anchor="center" if center else "w", stretch=stretch)
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=26, font=FONT)
        style.configure("Treeview.Heading", font=FONT_BOLD)
        self.tree.tag_configure("odd", background="#F3F6F9")
        self.tree.tag_configure("gradeA", background="#FBF3E4")
        self.tree.tag_configure("off", foreground="#AAAAAA")

        sb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double)

        # 하단: 하루 흐름 순서대로 번호를 붙인 버튼 + 상태
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", **pad)
        ttk.Button(bottom, text="① AI 선별 요청문 복사", command=self._copy_request).pack(side="left")
        ttk.Button(bottom, text="② 선정 결과 붙여넣기", command=self._open_paste).pack(side="left", padx=6)
        ttk.Button(bottom, text="③ HTML 보고서 열기 (메일용)", command=self._open_report).pack(side="left")
        ttk.Button(bottom, text="④ 보고 완료로 기록", command=self._mark_sent).pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="준비됨")
        ttk.Label(bottom, textvariable=self.status_var, foreground="#1F3B5C").pack(side="right")

    def _load_config_into_ui(self):
        self._set_period(int(self.cfg.get("days_back", 2)))
        self.kw_a_text.insert("1.0", "\n".join(self.cfg.get("keywords_a", [])))
        self.kw_b_text.insert("1.0", "\n".join(self.cfg.get("keywords_b", [])))
        self.ex_text.insert("1.0", "\n".join(self.cfg.get("exclude_words", [])))
        self.exclude_sent_var.set(bool(self.cfg.get("exclude_sent", True)))
        self.merge_similar_var.set(bool(self.cfg.get("merge_similar", True)))
        self.exclude_events_var.set(bool(self.cfg.get("exclude_events", True)))

    def _save_ui_into_config(self):
        self.cfg["keywords_a"] = self._lines(self.kw_a_text)
        self.cfg["keywords_b"] = self._lines(self.kw_b_text)
        self.cfg["keywords"] = config.all_keywords(self.cfg)
        self.cfg["exclude_words"] = self._lines(self.ex_text)
        self.cfg["exclude_sent"] = self.exclude_sent_var.get()
        self.cfg["merge_similar"] = self.merge_similar_var.get()
        self.cfg["exclude_events"] = self.exclude_events_var.get()
        config.save(self.cfg)

    @staticmethod
    def _lines(widget: tk.Text) -> list[str]:
        seen, out = set(), []
        for line in widget.get("1.0", "end").splitlines():
            s = line.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def _set_period(self, days_back: int):
        today = dt.date.today()
        self.start_var.set((today - dt.timedelta(days=days_back)).isoformat())
        self.end_var.set(today.isoformat())

    def _set_status(self, text: str):
        self.status_var.set(text)

    # --------------------------------------------------------------- 조회
    def _source(self) -> str:
        return self.cfg.get("source") if self.cfg.get("source") in SOURCE_LABELS else "google"

    def _search(self):
        if self.searching:
            return
        try:
            start = parse_date(self.start_var.get())
            end = parse_date(self.end_var.get())
        except ValueError:
            messagebox.showwarning("기간 확인", "날짜는 2026-10-14 형식으로 입력하세요.")
            return
        if start > end:
            start, end = end, start
            self.start_var.set(start.isoformat())
            self.end_var.set(end.isoformat())

        self._save_ui_into_config()
        if not self.cfg["keywords"]:
            messagebox.showwarning("키워드 확인", "검색 키워드를 한 개 이상 입력하세요.")
            return
        if self._source() == "naver" and (not self.cfg.get("client_id") or not self.cfg.get("client_secret")):
            messagebox.showwarning("설정 필요", "네이버 Client ID / Secret 을 먼저 [설정]에서 입력하세요.\n"
                                   "키가 없으면 [설정]에서 '구글 뉴스 (키 불필요)'를 고르세요.")
            self._open_settings()
            return

        # 키워드 → 등급. A·B 양쪽에 같은 키워드가 있으면 A.
        grades = {k: "A" for k in self.cfg["keywords_a"]}
        for k in self.cfg["keywords_b"]:
            grades.setdefault(k, "B")

        self.searching = True
        self.search_btn.state(["disabled"])
        self._clear_tree()
        threading.Thread(target=self._search_worker, args=(grades, start, end), daemon=True).start()

    def _search_worker(self, grades: dict[str, str], start: dt.date, end: dt.date):
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
                    arts = naver_api.search_news(kw, self.cfg["client_id"], self.cfg["client_secret"], start, end)
                else:
                    # A 는 빠짐없이(기간 나눠 다시 묻기), B 는 한 번만
                    arts = google_news.search_news(kw, start, end, split=is_a)
                if not is_a and b_max > 0:
                    arts = arts[:b_max]
                for a in arts:
                    a.grade = grades[kw]
                found.extend(arts)
            if self.cfg.get("use_feeds", True) and self.cfg.get("extra_feeds"):
                self.after(0, self._set_status, "전문지 RSS 조회 중…")
                arts, feed_failed = feeds.search_feeds(self.cfg["extra_feeds"], grades, start, end)
                found.extend(arts)
        except NaverApiError as e:
            self.after(0, self._search_failed, str(e))
            return
        except Exception as e:  # 예상 못한 오류도 화면에 보여 준다
            self.after(0, self._search_failed, f"오류: {e!r}")
            return

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
            found = [a for a in found if not history.is_sent(a.all_links, sent)]
            sent_skipped = before - len(found)
        self.after(0, self._search_done, found, raw_count, sent_skipped, feed_failed, events_skipped)

    def _search_failed(self, msg: str):
        self.searching = False
        self.search_btn.state(["!disabled"])
        self._set_status("조회 실패")
        messagebox.showerror("조회 실패", msg)

    def _search_done(self, found: list[Article], raw_count: int, sent_skipped: int, feed_failed: list[str],
                     events_skipped: int = 0):
        self.searching = False
        self.search_btn.state(["!disabled"])
        for art in found:
            art.keywords.sort(key=self._keyword_rank)
            iid = self.tree.insert("", "end", values=(
                CHECK_ON, art.grade, art.category, ", ".join(art.keywords),
                art.date_str, art.source_label, art.title))
            self.art_by_iid[iid] = art
            self.checked[iid] = True
        self._sort_by("grade", reverse=False)  # 기본: A 가 위 → 키워드 우선순위 → 최신순
        self._refresh_pick_box()

        n_a = sum(1 for a in found if a.grade == "A")
        src = SOURCE_LABELS[self._source()] + ("+전문지" if self.cfg.get("use_feeds", True) else "")
        merged = sum(len(a.others) for a in found)
        msg = (f"[{src}] 수집 {raw_count}건"
               + (f" → 행사 {events_skipped}건 제외" if events_skipped else "")
               + (f" → 같은 사안 {merged}건 묶음" if merged else "")
               + f" → 정리 후 {len(found) + sent_skipped}건"
               + (f" → 기보고 {sent_skipped}건 제외" if sent_skipped else "")
               + f" → 표시 {len(found)}건 (A {n_a} · B {len(found) - n_a})")
        if feed_failed:
            msg += f" · 전문지 조회 실패: {', '.join(feed_failed)}"
        self._set_status(msg)

    def _clear_tree(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.checked.clear()
        self.art_by_iid.clear()
        self.request_map.clear()
        self.pick_targets.clear()
        self.pick_box.configure(values=[])
        self.pick_var.set("")

    # ------------------------------------------------------------ 표 조작
    def _keyword_rank(self, kw: str) -> int:
        """키워드 칸에 적힌 순서(A 다음 B). 목록에 없는 것은 맨 뒤."""
        order = self.cfg.get("keywords", [])
        return order.index(kw) if kw in order else len(order)

    def _restyle(self):
        """줄무늬·A 배경·꺼진 줄 회색을 현재 순서대로 다시 칠한다."""
        for i, iid in enumerate(self.tree.get_children()):
            art = self.art_by_iid[iid]
            tags = ["gradeA"] if art.grade == "A" else (["odd"] if i % 2 else [])
            if not self.checked.get(iid, True):
                tags.append("off")
            self.tree.item(iid, tags=tags)
            self.tree.set(iid, "chk", CHECK_ON if self.checked.get(iid, True) else CHECK_OFF)

    def _sort_key(self, col: str):
        if col == "grade":
            # 등급 → 그 안에서는 키워드 우선순위(키워드 칸에 적힌 순서)
            return lambda a: (a.grade or "Z", min((self._keyword_rank(k) for k in a.keywords), default=10 ** 6))
        if col == "category":
            order = report.CATEGORY_ORDER
            return lambda a: (order.index(a.category) if a.category in order
                              else len(order) if a.category else len(order) + 1)
        if col == "keyword":
            return lambda a: min((self._keyword_rank(k) for k in a.keywords), default=10 ** 6)
        if col == "date":
            return lambda a: a.published
        if col == "source":
            return lambda a: a.source
        return lambda a: a.title

    def _sort_by(self, col: str, reverse: bool | None = None):
        """머리글 클릭: 같은 값끼리 모아서 정렬(그 안에서는 최신순). 다시 누르면 반대로."""
        if reverse is None:
            if self.sort_state and self.sort_state[0] == col:
                reverse = not self.sort_state[1]
            else:
                reverse = col == "date"  # 날짜는 처음 누르면 최신순
        iids = list(self.tree.get_children())
        iids.sort(key=lambda i: self.art_by_iid[i].published, reverse=True)
        key = self._sort_key(col)
        iids.sort(key=lambda i: key(self.art_by_iid[i]), reverse=reverse)
        for pos, iid in enumerate(iids):
            self.tree.move(iid, "", pos)
        self.sort_state = (col, reverse)
        self._update_headings()
        self._restyle()

    def _update_headings(self):
        for col, head, *_ in COLUMNS:
            if col == "chk":
                continue
            mark = ""
            if self.sort_state and self.sort_state[0] == col:
                mark = " ▼" if self.sort_state[1] else " ▲"
            self.tree.heading(col, text=head + mark)

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self._toggle(iid, not self.checked.get(iid, True))

    def _toggle(self, iid: str, on: bool):
        self.checked[iid] = on
        self.tree.set(iid, "chk", CHECK_ON if on else CHECK_OFF)
        tags = [t for t in self.tree.item(iid, "tags") if t != "off"]
        if not on:
            tags.append("off")
        self.tree.item(iid, tags=tags)

    def _set_all(self, on: bool):
        for iid in self.tree.get_children():
            self._toggle(iid, on)
        self._set_status(f"전체 {'선택' if on else '해제'}: {len(self.checked)}건")

    def _toggle_all_from_header(self):
        """'포함' 머리글 클릭: 모두 켜져 있으면 모두 끄고, 아니면 모두 켠다."""
        if self.checked:
            self._set_all(not all(self.checked.values()))

    def _refresh_pick_box(self):
        """키워드별 선택 목록: 등급 A·B, 그리고 결과에 나온 키워드(건수 포함)."""
        arts = list(self.art_by_iid.values())
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
        return [iid for iid, a in self.art_by_iid.items()
                if (a.grade == value if kind == "grade" else value in a.keywords)]

    def _pick(self, on: bool):
        iids = self._pick_matches()
        if iids is None:
            return
        for iid in iids:
            self._toggle(iid, on)
        self._set_status(f"'{self.pick_var.get()}' {len(iids)}건 {'선택' if on else '해제'}")

    def _pick_only(self):
        iids = self._pick_matches()
        if iids is None:
            return
        keep = set(iids)
        for iid in self.tree.get_children():
            self._toggle(iid, iid in keep)
        self._set_status(f"'{self.pick_var.get()}' {len(iids)}건만 선택")

    def _on_tree_double(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self.art_by_iid:
            return
        art = self.art_by_iid[iid]
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

    def _checked_iids(self) -> list[str]:
        return [iid for iid in self.tree.get_children() if self.checked.get(iid, True)]

    def _selected_articles(self) -> list[Article]:
        return [self.art_by_iid[iid] for iid in self._checked_iids()]

    # ------------------------------------------------------- AI 선별 중계
    def _copy_request(self):
        iids = self._checked_iids()
        if not iids:
            messagebox.showinfo("AI 선별 요청문", "후보 기사가 없습니다. 먼저 조회하세요.")
            return
        text = selection.build_request([self.art_by_iid[i] for i in iids])
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
        """모두 ☐ → 선정된 번호만 ☑, 분류·인사이트 저장, 선정 순서대로 맨 위로."""
        for iid, art in self.art_by_iid.items():
            art.category = art.insight = ""
            self.checked[iid] = False
            self.tree.set(iid, "category", "")
        for pos, (no, cat, insight) in enumerate(picked):
            iid = self.request_map[no]
            art = self.art_by_iid[iid]
            art.category, art.insight = cat, insight
            self.checked[iid] = True
            self.tree.set(iid, "category", cat)
            self.tree.move(iid, "", pos)
        self.sort_state = None
        self._update_headings()
        self._restyle()
        self.tree.yview_moveto(0)
        self._set_status(f"선정 {len(picked)}건 적용 → ③ HTML 보고서 열기"
                         + (f" · 무시된 줄 {ignored}개" if ignored else ""))

    # ---------------------------------------------------------- 보고서
    def _open_report(self):
        selected = self._selected_articles()
        if not selected:
            messagebox.showinfo("보고서", "포함할 기사가 없습니다. 먼저 조회하세요.")
            return
        threading.Thread(target=self._report_worker, args=(selected,), daemon=True).start()

    def _report_worker(self, selected: list[Article]):
        # 구글 경유 주소는 보고서에 넣기 전에 언론사 원문 주소로 바꾼다(실패하면 구글 주소 유지).
        # 보고 완료 기록은 조회 때와 같은 주소(구글 주소)로 해야 다음 조회에서 걸러지므로 사본만 바꾼다.
        def progress(i, n):
            self.after(0, self._set_status, f"기사 원문 주소 확인 중… ({i}/{n})")
        links = google_news.resolve_links([a.link for a in selected], progress)
        report_items = [dataclasses.replace(a, link=links.get(a.link, a.link)) for a in selected]
        failed = sum(1 for a in report_items if google_news.is_google_link(a.link))
        self.after(0, self._report_done, report_items, failed)

    def _report_done(self, report_items: list[Article], failed: int):
        start = parse_date(self.start_var.get())
        end = parse_date(self.end_var.get())
        body = report.build_html(report_items, self.cfg["keywords"], start, end,
                                 self.cfg.get("report_title", "언론보도 모니터링"))
        simple = report.build_simple_html(report.ordered_for_mail(report_items, self.cfg["keywords"]))
        subject = report.mail_subject(self.cfg.get("mail_subject", report.DEFAULT_SUBJECT), dt.date.today())
        path = report.save_report(body, subject=subject, simple_html=simple)
        webbrowser.open("file:///" + path.replace("\\", "/"))
        self._set_status(f"보고서 저장: {path}" + (f" (원문 주소 못 찾은 {failed}건은 구글 경유)" if failed else ""))

    def _mark_sent(self):
        selected = self._selected_articles()
        if not selected:
            messagebox.showinfo("기록", "기록할 기사가 없습니다.")
            return
        if not messagebox.askyesno("보고 완료", f"선택된 {len(selected)}건을 보고 완료로 기록할까요?\n"
                                   "다음 조회부터 '이미 보고한 기사 제외'로 걸러집니다."):
            return
        n = history.mark_sent([link for a in selected for link in a.all_links])
        self._set_status(f"보고 완료 기록: {n}건 추가")

    # ------------------------------------------------------------ 설정
    def _open_settings(self):
        win = tk.Toplevel(self)
        win.title("설정")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)

        frm = ttk.Frame(win, padding=14)
        frm.pack()

        # 맨 위: 기사 출처 선택
        source_var = tk.StringVar(value=self._source())
        src_frm = ttk.Frame(frm)
        src_frm.grid(row=0, column=1, sticky="w", pady=4, padx=(10, 0))
        ttk.Label(frm, text="기사 출처").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Radiobutton(src_frm, text="구글 뉴스 (키 불필요)", value="google",
                        variable=source_var).pack(side="left")
        ttk.Radiobutton(src_frm, text="네이버 (키 필요)", value="naver",
                        variable=source_var).pack(side="left", padx=(14, 0))
        feeds_var = tk.BooleanVar(value=bool(self.cfg.get("use_feeds", True)))
        names = ", ".join(f.get("name", "") for f in self.cfg.get("extra_feeds", []))
        ttk.Checkbutton(frm, text=f"전문지 RSS 함께 조회 ({names})", variable=feeds_var).grid(
            row=1, column=1, sticky="w", pady=4, padx=(10, 0))

        fields = [
            ("네이버 Client ID", "client_id", False),
            ("네이버 Client Secret", "client_secret", True),
            ("메일 제목 ({날짜}→261015)", "mail_subject", False),
            ("B 키워드당 최대 건수", "b_max_per_keyword", False),
            ("보고서 제목", "report_title", False),
        ]
        vars_: dict[str, tk.StringVar] = {}
        for r, (label, key, secret) in enumerate(fields, 2):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=4)
            v = tk.StringVar(value=self.cfg.get(key, ""))
            vars_[key] = v
            ttk.Entry(frm, textvariable=v, width=44, show="*" if secret else "").grid(row=r, column=1, pady=4, padx=(10, 0))

        ttk.Label(frm, text="네이버 Client ID/Secret 은 '네이버'를 고를 때만 필요합니다.\n"
                            "이 값은 이 PC 의 config.json 에만 저장됩니다.",
                  foreground="#666").grid(row=len(fields) + 2, column=0, columnspan=2, sticky="w", pady=(8, 4))

        r = len(fields) + 3
        ttk.Label(frm, text="단순 행사 단어").grid(row=r, column=0, sticky="nw", pady=4)
        ev_frm = ttk.Frame(frm)
        ev_frm.grid(row=r, column=1, sticky="w", pady=4, padx=(10, 0))
        ev_text = tk.Text(ev_frm, width=44, height=6, font=FONT)
        ev_sb = ttk.Scrollbar(ev_frm, orient="vertical", command=ev_text.yview)
        ev_text.configure(yscrollcommand=ev_sb.set)
        ev_text.pack(side="left")
        ev_sb.pack(side="left", fill="y")
        ev_text.insert("1.0", "\n".join(self.cfg.get("event_words", [])))
        ttk.Label(frm, text="한 줄에 하나. 제목에 이 단어가 있으면 A 등급이라도 뺍니다\n"
                            "(메인 화면 '단순 행사 기사 제외'가 켜져 있을 때).",
                  foreground="#666").grid(row=r + 1, column=1, sticky="w", padx=(10, 0))

        def ok():
            self.cfg["source"] = source_var.get()
            self.cfg["use_feeds"] = feeds_var.get()
            self.cfg["event_words"] = self._lines(ev_text)
            for key, v in vars_.items():
                self.cfg[key] = v.get().strip()
            try:
                self.cfg["b_max_per_keyword"] = max(0, int(self.cfg["b_max_per_keyword"]))
            except ValueError:
                self.cfg["b_max_per_keyword"] = 50
            config.save(self.cfg)
            win.destroy()
            self._set_status("설정 저장됨")

        btns = ttk.Frame(frm)
        btns.grid(row=r + 2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="저장", command=ok).pack(side="left", padx=4)
        ttk.Button(btns, text="취소", command=win.destroy).pack(side="left")

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
