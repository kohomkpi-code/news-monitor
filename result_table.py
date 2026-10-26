"""결과 표 — 선택(체크 아이콘), 머리글 클릭 정렬, 줄 색칠.

베이직 탭과 프로 탭이 각자 하나씩 쓴다. 두 표는 같은 기사(Article)를 보지만
선택은 따로 가진다: 베이직은 추천 5건만, 프로는 후보 전체를 선택한 채로 시작한다.
줄 id(iid)는 두 표에서 같아서, 한 기사를 두 표에서 같은 id 로 찾을 수 있다.

모양(디자인 명세 3·6장):
- 첫 칸(#0)에 아이콘 하나: 체크 상자 + ★(추천). 칸마다 색을 못 바꾸는 tkinter 제약을 그림으로 피한다.
- 줄 바탕: 공단(A) 연앰버 · 직접 추가 연틸 · 나머지 줄무늬. 글자: 포함 줄 SemiBold, 빠진 줄 흐린 회색.
- 순번: 조회 때 매긴 고정 번호(정렬해도 그대로) — AI 선별 요청문의 번호와 같다.
- 순서 바꾸기: 줄을 마우스로 끌어 놓기(체크 칸 말고 제목 등 나머지 칸을 잡고), 줄을 누른 뒤 ▲▼(Ctrl+↑↓),
  [선택 항목 맨 위로]. 보고서는 표에 보이는 순서(체크한 것만)대로 실린다.
"""

import tkinter as tk
from tkinter import ttk

import icons
import theme
from naver_api import Article
from report import CATEGORY_ORDER

GRADE_ORDER = {"직접": 0, "A": 1, "A?": 2, "S": 3, "B": 4, "전문지": 5}

# 열 id → (머리글, 폭, 가운데 정렬, 늘어남)  — 명세 5장 열 폭
COLUMN_DEFS = {
    "no": ("순번", 50, True, False),
    "grade": ("등급", 64, True, False),
    "score": ("점수", 52, True, False),
    "category": ("분류", 84, True, False),
    "keyword": ("키워드", 150, False, False),
    "date": ("날짜", 96, False, False),
    "source": ("매체", 170, False, False),
    "title": ("제목 · 더블클릭하면 기사가 열립니다", 480, False, True),
}
SELECT_HEAD = "선택"


class ResultTable:
    def __init__(self, parent, columns: list[str], arts: dict[str, Article],
                 keyword_rank, on_open, on_status, fonts: theme.Fonts, on_change=None, widths=None):
        self.columns = columns
        self.arts = arts                  # 두 표가 함께 쓰는 {줄 id: 기사}
        self.keyword_rank = keyword_rank  # 키워드 → 우선순위(0 이 최우선)
        self.on_open = on_open            # 더블클릭 시 기사 열기
        self.on_status = on_status        # 상태 표시줄에 글 쓰기
        self.on_change = on_change or (lambda: None)  # 선택이 바뀌면(건수 표시 갱신)
        self.checked: dict[str, bool] = {}
        self.sort_state: tuple[str, bool] | None = None
        self.images = {k: tk.PhotoImage(data=getattr(icons, k)) for k in ("ON_STAR", "ON", "OFF_STAR", "OFF")}

        self.frame = tk.Frame(parent, bg=theme.PANEL)
        self.tree = ttk.Treeview(self.frame, columns=columns, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text=SELECT_HEAD, anchor="w", command=self.toggle_all_from_header)
        self.tree.column("#0", width=68, minwidth=68, stretch=False, anchor="w")
        widths = widths or {}
        for col in columns:
            head, width, center, stretch = COLUMN_DEFS[col]
            self.tree.heading(col, text=head, anchor="center" if center else "w",
                              command=lambda c=col: self.sort_by(c))
            self.tree.column(col, width=widths.get(col, width), anchor="center" if center else "w", stretch=stretch)
        self.tree.tag_configure("odd", background=theme.STRIPE)
        self.tree.tag_configure("gradeA", background=theme.A_BG)
        self.tree.tag_configure("manual", background=theme.MANUAL_BG)
        self.tree.tag_configure("on", foreground=theme.TEXT, font=fonts.row_on)
        self.tree.tag_configure("off", foreground=theme.FAINT, font=fonts.row_off)
        sb = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Double-1>", self._on_double)
        # 끌어 놓기: 누른 채 6px 넘게 움직이면 시작(그보다 작으면 보통 클릭·더블클릭)
        self._drag: list | None = None  # [줄 id, 누른 y, 움직였는지]
        self.tree.bind("<ButtonPress-1>", self._drag_start, add="+")
        self.tree.bind("<B1-Motion>", self._drag_move, add="+")
        self.tree.bind("<ButtonRelease-1>", self._drag_end, add="+")
        self.tree.bind("<Control-Up>", lambda e: (self.move_selected(-1), "break")[1])
        self.tree.bind("<Control-Down>", lambda e: (self.move_selected(1), "break")[1])

    # ------------------------------------------------------------ 내용
    def _image(self, iid: str):
        a = self.arts[iid]
        star = a.best and a.grade != "직접"
        key = ("ON" if self.checked.get(iid) else "OFF") + ("_STAR" if star else "")
        return self.images[key]

    def _values(self, iid: str) -> tuple:
        a = self.arts[iid]
        cell = {
            "no": a.no or "",
            "grade": a.grade,
            "score": a.score,
            "category": a.shown_category,
            "keyword": ", ".join(a.keywords),
            "date": a.published.strftime("%m.%d %H:%M"),
            "source": a.source_label,
            "title": a.title,
        }
        return tuple(cell[c] for c in self.columns)

    def clear(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.checked.clear()
        self.sort_state = None
        self._update_headings()
        self.on_change()

    def add(self, iid: str, checked: bool, top: bool = False):
        self.checked[iid] = checked
        self.tree.insert("", 0 if top else "end", iid=iid, image=self._image(iid), values=self._values(iid))

    def has(self, iid: str) -> bool:
        return self.tree.exists(iid)

    def refresh(self, iid: str | None = None):
        for i in ([iid] if iid else self.tree.get_children()):
            self.tree.item(i, values=self._values(i), image=self._image(i))
        self.restyle()

    def order(self) -> list[str]:
        return list(self.tree.get_children())

    def checked_iids(self) -> list[str]:
        return [i for i in self.order() if self.checked.get(i)]

    def selected(self) -> list[Article]:
        return [self.arts[i] for i in self.checked_iids()]

    def count(self) -> tuple[int, int]:
        return len(self.checked_iids()), len(self.checked)

    # ------------------------------------------------------------ 선택
    def toggle(self, iid: str, on: bool, notify: bool = True):
        self.checked[iid] = on
        self.tree.item(iid, image=self._image(iid))
        self._style_row(iid, self.tree.index(iid))
        if notify:
            self.on_change()

    def set_all(self, on: bool):
        for iid in self.order():
            self.toggle(iid, on, notify=False)
        self.on_change()
        self.on_status(f"전체 {'선택' if on else '해제'}: {len(self.checked)}건")

    def set_only(self, iids):
        keep = set(iids)
        for iid in self.order():
            self.toggle(iid, iid in keep, notify=False)
        self.on_change()

    def toggle_all_from_header(self):
        """'선택' 머리글 클릭: 모두 켜져 있으면 모두 끄고, 아니면 모두 켠다."""
        if self.checked:
            self.set_all(not all(self.checked.values()))

    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "tree":  # 첫 칸(#0)만
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self.toggle(iid, not self.checked.get(iid, False))

    def _on_double(self, event):
        if self.tree.identify_region(event.x, event.y) == "tree":
            return  # 체크 칸 두 번 누름은 열기가 아님
        iid = self.tree.identify_row(event.y)
        if iid and iid in self.arts:
            self.on_open(self.arts[iid])

    # ------------------------------------------------------------ 정렬·색
    def _style_row(self, iid: str, index: int):
        a = self.arts[iid]
        if a.grade == "직접":
            tags = ["manual"]
        elif a.grade == "A":
            tags = ["gradeA"]
        else:
            tags = ["odd"] if index % 2 else []
        tags.append("on" if self.checked.get(iid) else "off")
        self.tree.item(iid, tags=tags)

    def restyle(self):
        """줄무늬·A 바탕·직접 추가 바탕·포함/빠짐 글자를 현재 순서대로 다시 칠한다."""
        for i, iid in enumerate(self.order()):
            self._style_row(iid, i)

    def _main_rank(self, a: Article) -> int:
        return min((self.keyword_rank(k) for k in a.keywords), default=10 ** 6)

    def _sort_key(self, col: str):
        if col == "grade":
            # 등급(직접→A→S→B) → 그 안에서는 점수 높은 순
            return lambda a: (GRADE_ORDER.get(a.grade, 9), -a.score)
        if col == "best":
            return lambda a: (0 if a.grade == "직접" else 1 if a.best else 2, -a.score)
        if col == "no":
            return lambda a: a.no
        if col == "score":
            return lambda a: a.score
        if col == "category":
            return lambda a: (CATEGORY_ORDER.index(a.shown_category) if a.shown_category in CATEGORY_ORDER
                              else len(CATEGORY_ORDER) if a.shown_category else len(CATEGORY_ORDER) + 1, -a.score)
        if col == "keyword":
            return self._main_rank
        if col == "date":
            return lambda a: a.published
        if col == "source":
            return lambda a: a.source
        return lambda a: a.title

    def sort_by(self, col: str, reverse: bool | None = None):
        """머리글 클릭: 같은 값끼리 모아서 정렬(그 안에서는 최신순). 다시 누르면 반대로."""
        if reverse is None:
            if self.sort_state and self.sort_state[0] == col:
                reverse = not self.sort_state[1]
            else:
                reverse = col in ("date", "score")  # 날짜·점수는 처음 누르면 큰 것부터(순번은 작은 것부터)
        iids = self.order()
        iids.sort(key=lambda i: self.arts[i].published, reverse=True)
        key = self._sort_key(col)
        iids.sort(key=lambda i: key(self.arts[i]), reverse=reverse)
        for pos, iid in enumerate(iids):
            self.tree.move(iid, "", pos)
        self.sort_state = (col, reverse)
        self._update_headings()
        self.restyle()

    def move_to_top(self, iids: list[str]):
        for pos, iid in enumerate(iids):
            self.tree.move(iid, "", pos)
        self.sort_state = None
        self._update_headings()
        self.restyle()
        self.tree.yview_moveto(0)

    def checked_to_top(self) -> int:
        """선택(☑)한 줄을 지금 순서 그대로 맨 위로 모은다. 모은 건수."""
        ids = self.checked_iids()
        self.move_to_top(ids)
        return len(ids)

    def move_selected(self, delta: int) -> bool:
        """누른 줄(파란 줄)을 한 칸 위(-1)·아래(+1)로. 움직였으면 True."""
        sel = self.tree.selection()
        if not sel:
            self.on_status("순서를 바꿀 줄을 먼저 누르세요(제목 칸을 한 번 클릭).")
            return False
        iid = sel[0]
        pos = self.tree.index(iid) + delta
        if not 0 <= pos < len(self.tree.get_children()):
            return False
        self.tree.move(iid, "", pos)
        self.tree.see(iid)
        self.sort_state = None  # 사람이 정한 순서 — 정렬 표시 끔
        self._update_headings()
        self.restyle()
        return True

    # ------------------------------------------------------------ 끌어 놓기
    def _drag_start(self, event):
        iid = self.tree.identify_row(event.y)
        # 체크 칸(#0)은 선택·해제, 머리글은 정렬이라 끌기를 시작하지 않는다
        ok = iid and self.tree.identify_region(event.x, event.y) == "cell"
        self._drag = [iid, event.y, False] if ok else None

    def _drag_move(self, event):
        if not self._drag:
            return
        iid, y0, moved = self._drag
        if not moved:
            if abs(event.y - y0) < 6:
                return
            self._drag[2] = True
            self.tree.selection_set(iid)
            self.tree.configure(cursor="sb_v_double_arrow")
        h = self.tree.winfo_height()
        if event.y < 24:  # 표 위·아래 끝으로 끌면 저절로 넘어간다
            self.tree.yview_scroll(-1, "units")
        elif event.y > h - 12:
            self.tree.yview_scroll(1, "units")
        target = self.tree.identify_row(max(26, min(event.y, h - 4)))
        if target and target != iid:
            self.tree.move(iid, "", self.tree.index(target))
            self.tree.see(iid)

    def _drag_end(self, _event=None):
        drag, self._drag = self._drag, None
        if not drag or not drag[2]:
            return
        self.tree.configure(cursor="")
        self.sort_state = None  # 사람이 정한 순서 — 정렬 표시 끔
        self._update_headings()
        self.restyle()
        self.on_status(f"순서를 옮겼습니다({self.tree.index(drag[0]) + 1}번째 줄) — 이 순서대로 보고서에 실립니다.")

    def _update_headings(self):
        for col in self.columns:
            mark = ""
            if self.sort_state and self.sort_state[0] == col:
                mark = " ▼" if self.sort_state[1] else " ▲"
            self.tree.heading(col, text=COLUMN_DEFS[col][0] + mark)
