"""언론보도 모니터링 앱 — 화면(GUI).

화면은 이 파일에만 있고, 실제 일(검색·중복제거·보고서·업데이트)은
각각의 모듈이 한다. 화면과 일을 분리해 두면 나중에 화면을 바꾸거나
자동 실행 버전을 만들 때 아래 모듈들을 그대로 쓸 수 있다.
"""

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
import google_news
import history
import naver_api
import report
import updater
from naver_api import Article, NaverApiError
from version import APP_TITLE, __version__

FONT = ("맑은 고딕", 10)
FONT_BOLD = ("맑은 고딕", 10, "bold")
CHECK_ON, CHECK_OFF = "☑", "☐"
SOURCE_LABELS = {"google": "구글 뉴스", "naver": "네이버"}


def parse_date(text: str) -> dt.date:
    return dt.datetime.strptime(text.strip(), "%Y-%m-%d").date()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} v{__version__}")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.option_add("*Font", FONT)

        self.cfg = config.load()
        self.articles: list[Article] = []
        self.checked: dict[str, bool] = {}   # 트리 항목 id → 선택 여부
        self.searching = False

        self._build_ui()
        self._load_config_into_ui()
        self.after(1500, self._check_update_silently)

    # ------------------------------------------------------------------ UI
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
        for label, days in (("오늘", 0), ("어제~오늘", 1), ("최근 7일", 6)):
            ttk.Button(top, text=label, width=9,
                       command=lambda d=days: self._set_period(d)).pack(side="left", padx=2)

        ttk.Label(top, text=f"v{__version__}", foreground="#888").pack(side="right")
        ttk.Button(top, text="업데이트 확인", command=self._check_update).pack(side="right", padx=4)
        ttk.Button(top, text="설정", command=self._open_settings).pack(side="right", padx=4)

        # 키워드 / 제외어
        mid = ttk.Frame(self)
        mid.pack(fill="x", **pad)
        kw_frame = ttk.LabelFrame(mid, text=" 검색 키워드 (한 줄에 하나) ")
        kw_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.kw_text = tk.Text(kw_frame, height=5, font=FONT)
        self.kw_text.pack(fill="both", expand=True, padx=6, pady=4)

        ex_frame = ttk.LabelFrame(mid, text=" 제외어 (제목에 포함되면 제외, 한 줄에 하나) ")
        ex_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self.ex_text = tk.Text(ex_frame, height=5, font=FONT)
        self.ex_text.pack(fill="both", expand=True, padx=6, pady=4)

        # 옵션 + 조회
        opt = ttk.Frame(self)
        opt.pack(fill="x", **pad)
        self.exclude_sent_var = tk.BooleanVar()
        self.merge_similar_var = tk.BooleanVar()
        ttk.Checkbutton(opt, text="이미 보고한 기사 제외", variable=self.exclude_sent_var).pack(side="left")
        ttk.Checkbutton(opt, text="제목이 거의 같은 기사 묶기", variable=self.merge_similar_var).pack(side="left", padx=12)
        self.search_btn = ttk.Button(opt, text="  조  회  ", command=self._search)
        self.search_btn.pack(side="right")

        # 결과 표
        cols = ("chk", "keyword", "date", "source", "title")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("chk", text="포함")
        self.tree.heading("keyword", text="키워드")
        self.tree.heading("date", text="날짜")
        self.tree.heading("source", text="매체")
        self.tree.heading("title", text="제목 (더블클릭: 기사 열기)")
        self.tree.column("chk", width=46, anchor="center", stretch=False)
        self.tree.column("keyword", width=130, stretch=False)
        self.tree.column("date", width=90, anchor="center", stretch=False)
        self.tree.column("source", width=110, stretch=False)
        self.tree.column("title", width=600)
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=26, font=FONT)
        style.configure("Treeview.Heading", font=FONT_BOLD)
        self.tree.tag_configure("odd", background="#F3F6F9")
        self.tree.tag_configure("off", foreground="#AAAAAA")

        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="top", fill="both", expand=True, padx=(8, 0), pady=4)
        sb.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double)

        # 하단 버튼 + 상태
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", **pad)
        ttk.Button(bottom, text="HTML 보고서 열기 (메일에 붙여넣기용)", command=self._open_report).pack(side="left")
        ttk.Button(bottom, text="보고 완료로 기록", command=self._mark_sent).pack(side="left", padx=6)
        ttk.Button(bottom, text="전체 선택", command=lambda: self._set_all(True)).pack(side="left", padx=(12, 2))
        ttk.Button(bottom, text="전체 해제", command=lambda: self._set_all(False)).pack(side="left")
        self.status_var = tk.StringVar(value="준비됨")
        ttk.Label(bottom, textvariable=self.status_var, foreground="#1F3B5C").pack(side="right")

    def _load_config_into_ui(self):
        self._set_period(int(self.cfg.get("days_back", 1)))
        self.kw_text.insert("1.0", "\n".join(self.cfg.get("keywords", [])))
        self.ex_text.insert("1.0", "\n".join(self.cfg.get("exclude_words", [])))
        self.exclude_sent_var.set(bool(self.cfg.get("exclude_sent", True)))
        self.merge_similar_var.set(bool(self.cfg.get("merge_similar", True)))

    def _save_ui_into_config(self):
        self.cfg["keywords"] = self._lines(self.kw_text)
        self.cfg["exclude_words"] = self._lines(self.ex_text)
        self.cfg["exclude_sent"] = self.exclude_sent_var.get()
        self.cfg["merge_similar"] = self.merge_similar_var.get()
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
        keywords = self.cfg["keywords"]
        if not keywords:
            messagebox.showwarning("키워드 확인", "검색 키워드를 한 개 이상 입력하세요.")
            return
        if self._source() == "naver" and (not self.cfg.get("client_id") or not self.cfg.get("client_secret")):
            messagebox.showwarning("설정 필요", "네이버 Client ID / Secret 을 먼저 [설정]에서 입력하세요.\n"
                                   "키가 없으면 [설정]에서 '구글 뉴스 (키 불필요)'를 고르세요.")
            self._open_settings()
            return

        self.searching = True
        self.search_btn.state(["disabled"])
        self._clear_tree()
        threading.Thread(target=self._search_worker, args=(keywords, start, end), daemon=True).start()

    def _source(self) -> str:
        return self.cfg.get("source") if self.cfg.get("source") in SOURCE_LABELS else "google"

    def _search_worker(self, keywords: list[str], start: dt.date, end: dt.date):
        source = self._source()
        label = SOURCE_LABELS[source]
        found: list[Article] = []
        try:
            for i, kw in enumerate(keywords, 1):
                self.after(0, self._set_status, f"{label} 조회 중… ({i}/{len(keywords)}) {kw}")
                if source == "naver":
                    found.extend(naver_api.search_news(kw, self.cfg["client_id"], self.cfg["client_secret"], start, end))
                else:
                    found.extend(google_news.search_news(kw, start, end))
        except NaverApiError as e:
            self.after(0, self._search_failed, str(e))
            return
        except Exception as e:  # 예상 못한 오류도 화면에 보여 준다
            self.after(0, self._search_failed, f"오류: {e!r}")
            return

        raw_count = len(found)
        found = dedup.apply_exclude(found, self.cfg.get("exclude_words", []))
        found = dedup.dedupe(found, self.cfg.get("merge_similar", True),
                             float(self.cfg.get("similar_threshold", 0.85)))
        sent_skipped = 0
        if self.cfg.get("exclude_sent", True):
            sent = history.load()
            before = len(found)
            found = [a for a in found if not history.is_sent(a.link or a.naver_link, sent)]
            sent_skipped = before - len(found)
        self.after(0, self._search_done, found, raw_count, sent_skipped)

    def _search_failed(self, msg: str):
        self.searching = False
        self.search_btn.state(["!disabled"])
        self._set_status("조회 실패")
        messagebox.showerror("조회 실패", msg)

    def _search_done(self, found: list[Article], raw_count: int, sent_skipped: int):
        self.searching = False
        self.search_btn.state(["!disabled"])
        self.articles = found
        for i, art in enumerate(found):
            iid = self.tree.insert("", "end", values=(
                CHECK_ON, ", ".join(art.keywords), art.date_str, art.source, art.title),
                tags=("odd",) if i % 2 else ())
            self.checked[iid] = True
        self._set_status(
            f"[{SOURCE_LABELS[self._source()]}] 수집 {raw_count}건 → 중복·제외어 정리 후 {len(found) + sent_skipped}건"
            + (f" → 기보고 {sent_skipped}건 제외 → " if sent_skipped else " → ")
            + f"표시 {len(found)}건"
        )

    def _clear_tree(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.checked.clear()
        self.articles = []

    # ------------------------------------------------------------ 표 조작
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

    def _on_tree_double(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        idx = self.tree.index(iid)
        if 0 <= idx < len(self.articles):
            webbrowser.open(self.articles[idx].link or self.articles[idx].naver_link)

    def _selected_articles(self) -> list[Article]:
        out = []
        for iid in self.tree.get_children():
            if self.checked.get(iid, True):
                out.append(self.articles[self.tree.index(iid)])
        return out

    # ---------------------------------------------------------- 보고서
    def _open_report(self):
        selected = self._selected_articles()
        if not selected:
            messagebox.showinfo("보고서", "포함할 기사가 없습니다. 먼저 조회하세요.")
            return
        start = parse_date(self.start_var.get())
        end = parse_date(self.end_var.get())
        body = report.build_html(selected, self.cfg["keywords"], start, end,
                                 self.cfg.get("report_title", "언론보도 모니터링"))
        path = report.save_report(body)
        webbrowser.open("file:///" + path.replace("\\", "/"))
        self._set_status(f"보고서 저장: {path}")

    def _mark_sent(self):
        selected = self._selected_articles()
        if not selected:
            messagebox.showinfo("기록", "기록할 기사가 없습니다.")
            return
        if not messagebox.askyesno("보고 완료", f"선택된 {len(selected)}건을 보고 완료로 기록할까요?\n"
                                   "다음 조회부터 '이미 보고한 기사 제외'로 걸러집니다."):
            return
        n = history.mark_sent([a.link or a.naver_link for a in selected])
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

        fields = [
            ("네이버 Client ID", "client_id", False),
            ("네이버 Client Secret", "client_secret", True),
            ("보고서 제목", "report_title", False),
        ]
        vars_: dict[str, tk.StringVar] = {}
        for r, (label, key, secret) in enumerate(fields, 1):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=4)
            v = tk.StringVar(value=self.cfg.get(key, ""))
            vars_[key] = v
            ttk.Entry(frm, textvariable=v, width=44, show="*" if secret else "").grid(row=r, column=1, pady=4, padx=(10, 0))

        ttk.Label(frm, text="네이버 Client ID/Secret 은 '네이버'를 고를 때만 필요합니다.\n"
                            "이 값은 이 PC 의 config.json 에만 저장됩니다.",
                  foreground="#666").grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", pady=(8, 4))

        def ok():
            self.cfg["source"] = source_var.get()
            for key, v in vars_.items():
                self.cfg[key] = v.get().strip()
            config.save(self.cfg)
            win.destroy()
            self._set_status("설정 저장됨")

        btns = ttk.Frame(frm)
        btns.grid(row=len(fields) + 2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="저장", command=ok).pack(side="left", padx=4)
        ttk.Button(btns, text="취소", command=win.destroy).pack(side="left")

    # -------------------------------------------------------- 업데이트
    def _check_update_silently(self):
        threading.Thread(target=self._update_worker, args=(False,), daemon=True).start()

    def _check_update(self):
        self._set_status("업데이트 확인 중…")
        threading.Thread(target=self._update_worker, args=(True,), daemon=True).start()

    def _update_worker(self, verbose: bool):
        info = updater.check_latest()
        self.after(0, self._update_result, info, verbose)

    def _update_result(self, info, verbose: bool):
        if info is None:
            if verbose:
                self._set_status("업데이트 확인 실패 (네트워크 또는 Release 없음)")
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
