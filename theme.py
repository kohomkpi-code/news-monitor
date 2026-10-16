"""화면 디자인 — 색·글꼴·버튼 모양을 한곳에 모아 둔 것 (Claude Design 시안·명세 v0.9.0 반영).

- 색: 공단 팔레트 6색 + 회색 계열 + 오류 빨강 하나 (명세 3장)
- 글꼴: Pretendard(무료, SIL OFL). exe 안에 넣어 두고 이 프로그램 안에서만 불러온다(PC 설치 없음).
  못 불러오면 맑은 고딕. 크기는 pt 기준이라 화면 배율 125%에서도 알맞게 커진다.
- 모서리는 모두 직각, 그림자·그라데이션 없음. ttk 테마는 'clam'(색을 바꿀 수 있는 테마).
- 버튼 3종: 주(네이비 채움, 한 화면에 하나) / 보조(흰 바탕·테두리) / 위험(빨간 글자)
"""

import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import icons

# ---------------------------------------------------------------- 색 (명세 3장)
NAVY, NAVY_HOVER, NAVY_PRESS, NAVY_OFF = "#1F3B5C", "#2B4D74", "#16304B", "#A5B1BE"
TEAL, AMBER, RED = "#2E7D8C", "#E8A33D", "#C93A27"
BG, PANEL, BORDER, INNER = "#F4F6F8", "#FFFFFF", "#DFE4EA", "#E8ECF0"
TEXT, TEXT2, DESC, FAINT = "#1E2833", "#3F4A57", "#5B6673", "#98A2AD"
INPUT_BORDER, INPUT_OFF, INPUT_OFF_BORDER = "#CBD3DC", "#F3F6F9", "#E1E6EB"
HEAD_BG, STRIPE, A_BG, MANUAL_BG, SELECT_BG = "#F3F6F9", "#F7F9FB", "#FBF3E4", "#E4F0F2", "#DCE6F0"
TAB_OFF, STATUS_TEXT, DOT_OK, TROUGH = "#A9BACC", "#C9D5E1", "#5FC3D3", "#34516F"
NOTE_BG, NOTE_BORDER = "#E4F0F2", "#BFDCE1"
BAR_BG, BAR_LINE = "#F3F6F9", "#E8ECF0"   # 대화상자 아래 버튼 단

FONT_FILES = ("Pretendard-Regular.otf", "Pretendard-SemiBold.otf", "Pretendard-Bold.otf")


def resource_dir(*parts) -> str:
    """exe 안(PyInstaller 임시 폴더) 또는 소스 폴더 기준 경로."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def load_private_fonts() -> None:
    """윈도우: 글꼴 파일을 이 프로그램 안에서만 쓰도록 불러온다(Tk 창을 만들기 전에 불러야 함)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        FR_PRIVATE = 0x10
        for f in FONT_FILES:
            path = resource_dir("assets", "fonts", f)
            if os.path.exists(path):
                ctypes.windll.gdi32.AddFontResourceExW(path, FR_PRIVATE, 0)
    except Exception:
        pass  # 실패하면 맑은 고딕


class Fonts:
    """용도별 글꼴(명세 2장). pt 크기 → 화면 배율에 맞춘 픽셀로 바꿔 소수점 크기(10.5pt)도 쓴다."""

    def __init__(self, root: tk.Misc):
        fams = set(tkfont.families(root))
        self.pretendard = "Pretendard" in fams
        body = "Pretendard" if self.pretendard else "맑은 고딕"
        semi = "Pretendard SemiBold" if "Pretendard SemiBold" in fams else None
        px_per_pt = root.winfo_fpixels("1p")

        def f(pt, weight="normal", fam=None):
            return tkfont.Font(root=root, family=fam or body, size=-round(pt * px_per_pt), weight=weight)

        def s(pt):  # SemiBold: 별도 패밀리가 없으면 굵게로 대신
            return f(pt, fam=semi) if semi else f(pt, "bold")

        self.family = body
        self.app = f(12, "bold")
        self.tab, self.tab_on = f(10.5), s(10.5)
        self.title = f(10.5, "bold")            # 단계 제목·패널 제목
        self.big_title = f(12, "bold")          # 보고 기록 오른쪽 머리 '10월 16일 (금) 보고'
        self.desc = f(10)                       # 설명·안내문
        self.num = f(15, "bold")                # 선택 건수 숫자
        self.num_side = s(10.5)
        self.btn = f(10.5, "bold")
        self.small = f(10)                      # 작은 버튼·입력칸
        self.small_semi = s(10)
        self.head = s(10)                       # 표 머리글
        self.row_on, self.row_off = s(10), f(10)
        self.status_word, self.status = f(10, "bold"), f(10)
        self.step_no = f(10.5, "bold")


def setup_styles(root: tk.Misc, F: Fonts) -> ttk.Style:
    st = ttk.Style(root)
    st.theme_use("clam")
    root.configure(background=BG)
    # 기본 글꼴 이름들을 바꿔 둔다('*Font' 옵션은 ttk 스타일 글꼴까지 덮어써서 쓰지 않음)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name, root=root).configure(family=F.family, size=F.small.cget("size"))
        except tk.TclError:
            pass
    root.option_add("*TCombobox*Listbox.font", F.small)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT_BG)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    st.configure(".", background=BG, foreground=TEXT, font=F.small, bordercolor=INPUT_BORDER,
                 lightcolor=PANEL, darkcolor=PANEL, troughcolor=BG, focuscolor=TEAL)
    st.configure("TFrame", background=BG)
    st.configure("Panel.TFrame", background=PANEL)
    st.configure("TLabel", background=BG, foreground=TEXT)
    for name, fg, font in (("Panel.TLabel", TEXT, F.small), ("PanelTitle.TLabel", NAVY, F.title),
                           ("PanelDesc.TLabel", DESC, F.desc), ("PanelFaint.TLabel", FAINT, F.desc),
                           ("PanelNum.TLabel", NAVY, F.num), ("PanelSemi.TLabel", NAVY, F.num_side),
                           ("PanelBig.TLabel", NAVY, F.big_title), ("PanelOk.TLabel", TEAL, F.desc)):
        st.configure(name, background=PANEL, foreground=fg, font=font)
    st.configure("Desc.TLabel", background=BG, foreground=DESC, font=F.desc)
    st.configure("Note.TLabel", background=NOTE_BG, foreground=NAVY, font=F.desc)
    st.configure("Bar.TFrame", background=BAR_BG)
    st.configure("BarDesc.TLabel", background=BAR_BG, foreground=DESC, font=F.desc)

    # 버튼: 테두리·밝은 선·어두운 선을 같은 색으로 → 납작한 직각 버튼
    def button(name, bg, fg, border, font, pad, hover, press, off_bg, off_fg, off_border, press_border=None):
        st.configure(name, background=bg, foreground=fg, bordercolor=border, lightcolor=bg, darkcolor=bg,
                     focuscolor=bg, font=font, padding=pad, relief="solid", anchor="w", borderwidth=1, width=0)
        st.map(name,
               background=[("disabled", off_bg), ("pressed", press), ("active", hover)],
               lightcolor=[("disabled", off_bg), ("pressed", press), ("active", hover)],
               darkcolor=[("disabled", off_bg), ("pressed", press), ("active", hover)],
               foreground=[("disabled", off_fg)],
               bordercolor=[("disabled", off_border), ("pressed", press_border or border)])

    button("Primary.TButton", NAVY, "#FFFFFF", NAVY, F.btn, (16, 8), NAVY_HOVER, NAVY_PRESS,
           NAVY_OFF, "#FFFFFF", NAVY_OFF)
    button("PrimaryBig.TButton", NAVY, "#FFFFFF", NAVY, F.btn, (18, 11), NAVY_HOVER, NAVY_PRESS,
           NAVY_OFF, "#FFFFFF", NAVY_OFF)
    button("Secondary.TButton", PANEL, NAVY, INPUT_BORDER, F.btn, (16, 8), "#EEF2F5", "#E1E7ED",
           PANEL, "#B9C1CA", INPUT_OFF_BORDER, "#AEB8C3")
    button("SecondaryBig.TButton", PANEL, NAVY, INPUT_BORDER, F.btn, (18, 11), "#EEF2F5", "#E1E7ED",
           PANEL, "#B9C1CA", INPUT_OFF_BORDER, "#AEB8C3")
    button("Small.TButton", PANEL, NAVY, INPUT_BORDER, F.small, (12, 5), "#EEF2F5", "#E1E7ED",
           PANEL, "#B9C1CA", INPUT_OFF_BORDER, "#AEB8C3")
    button("Danger.TButton", PANEL, RED, "#E3B5AE", F.small, (12, 5), "#FBEDEA", "#F5DAD5",
           PANEL, "#B9C1CA", INPUT_OFF_BORDER, RED)
    button("Seg.TButton", PANEL, TEXT2, INPUT_BORDER, F.small, (11, 5), "#EEF2F5", "#E1E7ED",
           PANEL, "#B9C1CA", INPUT_OFF_BORDER)
    button("SegOn.TButton", NOTE_BG, NAVY, INPUT_BORDER, F.small_semi, (11, 5), "#D6E9EC", "#C8E1E5",
           NOTE_BG, "#B9C1CA", INPUT_OFF_BORDER)
    button("Link.TButton", PANEL, NAVY, PANEL, F.small_semi, (6, 3), "#EEF2F5", "#E1E7ED",
           PANEL, "#B9C1CA", PANEL)

    # 입력칸: 높이 34px, 좌우 여백 10px, 포커스 때 틸 테두리
    st.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, bordercolor=INPUT_BORDER,
                 lightcolor=PANEL, darkcolor=PANEL, padding=(10, 6), insertcolor=TEXT)
    st.map("TEntry", bordercolor=[("focus", TEAL), ("disabled", INPUT_OFF_BORDER)],
           lightcolor=[("focus", TEAL)], fieldbackground=[("disabled", INPUT_OFF)],
           foreground=[("disabled", FAINT)])
    st.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, bordercolor=INPUT_BORDER,
                 lightcolor=PANEL, darkcolor=PANEL, arrowcolor=DESC, padding=(10, 5))
    st.map("TCombobox", fieldbackground=[("readonly", PANEL)], selectbackground=[("readonly", PANEL)],
           selectforeground=[("readonly", TEXT)], bordercolor=[("focus", TEAL)], background=[("active", PANEL)])

    # 체크·라디오: 그림으로 바꿔 끼움(선택되면 네이비 칸 + 흰 체크 / 네이비 점)
    imgs = {k: tk.PhotoImage(master=root, data=getattr(icons, k))
            for k in ("CHECK_ON", "CHECK_OFF", "RADIO_ON", "RADIO_OFF")}
    root._theme_images = imgs  # 그림이 지워지지 않게 붙잡아 둔다
    if "KCheck.indicator" not in st.element_names():
        st.element_create("KCheck.indicator", "image", imgs["CHECK_OFF"], ("selected", imgs["CHECK_ON"]))
        st.element_create("KRadio.indicator", "image", imgs["RADIO_OFF"], ("selected", imgs["RADIO_ON"]))
    for name, ind in (("TCheckbutton", "KCheck.indicator"), ("TRadiobutton", "KRadio.indicator")):
        base = name[1:]
        st.layout(name, [(f"{base}.padding", {"sticky": "nswe", "children": [
            (ind, {"side": "left", "sticky": ""}),
            (f"{base}.focus", {"side": "left", "sticky": "w", "children": [(f"{base}.label", {"sticky": "nswe"})]})]})])
        st.configure(name, background=PANEL, foreground=TEXT, font=F.small, focuscolor=PANEL, padding=(0, 2))
        st.map(name, background=[("active", PANEL)], foreground=[("disabled", FAINT)])

    # 표: 줄 높이 30, 머리글 34(회색 바탕·SemiBold), 클릭 선택은 연한 파랑
    st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=30,
                 font=F.row_off, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL, borderwidth=0)
    st.map("Treeview", background=[("selected", SELECT_BG)], foreground=[("selected", TEXT)])
    st.configure("Treeview.Heading", background=HEAD_BG, foreground=DESC, font=F.head, relief="flat",
                 bordercolor=BORDER, lightcolor=HEAD_BG, darkcolor=HEAD_BG, padding=(8, 8))
    st.map("Treeview.Heading", background=[("active", "#E9EEF3")])
    # 보고 기록 왼쪽 날짜 목록: 고른 날은 네이비 바탕 흰 글자
    st.configure("Days.Treeview", rowheight=36, font=F.row_off)
    st.map("Days.Treeview", background=[("selected", NAVY)], foreground=[("selected", "#FFFFFF")])

    st.configure("Vertical.TScrollbar", background="#D5DBE2", troughcolor=PANEL, bordercolor=PANEL,
                 lightcolor="#D5DBE2", darkcolor="#D5DBE2", arrowcolor=DESC, gripcount=0)
    st.map("Vertical.TScrollbar", background=[("active", "#BFC8D2")])
    st.configure("Status.Horizontal.TProgressbar", troughcolor=TROUGH, background=AMBER, bordercolor=NAVY,
                 lightcolor=AMBER, darkcolor=AMBER, thickness=6)
    return st


# ---------------------------------------------------------------- 자주 쓰는 모양
def panel(parent, **grid_or_pack) -> tk.Frame:
    """흰 패널(1px 회색 테두리, 직각)."""
    return tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)


def hline(parent, color=INNER) -> tk.Frame:
    return tk.Frame(parent, bg=color, height=1)


def vline(parent, color=INNER) -> tk.Frame:
    return tk.Frame(parent, bg=color, width=1)


def text_box(parent, F: Fonts, height=5, width=20) -> tuple[tk.Frame, tk.Text]:
    """여러 줄 글상자(입력칸과 같은 테두리) + 세로 스크롤."""
    wrap = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=INPUT_BORDER, highlightcolor=TEAL)
    text = tk.Text(wrap, height=height, width=width, font=F.small, relief="flat", bd=0, padx=10, pady=6,
                   fg=TEXT, bg=PANEL, insertbackground=TEXT, highlightthickness=0, wrap="none")
    sb = ttk.Scrollbar(wrap, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    text.bind("<FocusIn>", lambda e: wrap.configure(highlightbackground=TEAL))
    text.bind("<FocusOut>", lambda e: wrap.configure(highlightbackground=INPUT_BORDER))
    return wrap, text


class SegGroup(tk.Frame):
    """붙어 있는 버튼 묶음(바깥 테두리 하나). on=True 인 버튼은 연틸 바탕."""

    def __init__(self, parent, items: list[tuple[str, callable]], bg=PANEL):
        super().__init__(parent, bg=bg)
        self.buttons: dict[str, ttk.Button] = {}
        for i, (label, cmd) in enumerate(items):
            b = ttk.Button(self, text=label, style="Seg.TButton", command=cmd, takefocus=False)
            b.pack(side="left")
            self.buttons[label] = b

    def set_on(self, label: str | None):
        for name, b in self.buttons.items():
            b.configure(style="SegOn.TButton" if name == label else "Seg.TButton")


def swatch(parent, fill, border, bg=PANEL, size=10) -> tk.Frame:
    """범례용 작은 네모."""
    outer = tk.Frame(parent, bg=border, width=size, height=size)
    outer.pack_propagate(False)
    tk.Frame(outer, bg=fill).pack(fill="both", expand=True, padx=1, pady=1)
    return outer


class ScrollPanel(tk.Frame):
    """흰 패널 + 내용이 넘칠 때만 세로 스크롤(작은 창 980×640 에서도 아래 항목이 잘리지 않게).
    내용은 self.inner 에 넣는다."""

    def __init__(self, parent):
        super().__init__(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)
        self.canvas = tk.Canvas(self, bg=PANEL, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=PANEL)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self._refresh())
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(self._win, width=e.width), self._refresh()))
        self.bind_all("<MouseWheel>", self._wheel, add="+")

    def _refresh(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        need = self.inner.winfo_reqheight() > self.canvas.winfo_height() > 1
        if need and not self.sb.winfo_manager():
            self.sb.pack(side="right", fill="y", before=self.canvas)
        elif not need and self.sb.winfo_manager():
            self.sb.pack_forget()
            self.canvas.yview_moveto(0)

    def _wheel(self, event):
        w = self.winfo_containing(event.x_root, event.y_root)
        while w is not None and w is not self:
            w = w.master
        if w is self and self.sb.winfo_manager():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
