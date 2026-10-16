"""화면 확인용 스크린샷 — GitHub Actions 윈도우에서 실제 글꼴(Pretendard)로 화면을 찍는다.

인터넷 조회는 가짜 기사로 바꿔 치고(네트워크 없이), 탭·상태·대화상자를 차례로 찍어
screens/ 폴더에 PNG 로 남긴다. 워크플로가 이 폴더를 ci-screens 브랜치에 올린다.
"""

import datetime as dt
import json
import os
import sys
import tempfile
import time
import tkinter.font as tkfont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.getcwd(), "screens")
os.makedirs(OUT, exist_ok=True)
tmp = tempfile.mkdtemp()

import config  # noqa: E402
import feeds  # noqa: E402
import google_news  # noqa: E402
import history  # noqa: E402
import report  # noqa: E402
import updater  # noqa: E402
import webbrowser  # noqa: E402
from naver_api import Article  # noqa: E402

config.CONFIG_PATH = os.path.join(tmp, "config.json")
history.HISTORY_PATH = os.path.join(tmp, "sent.json")
report.REPORT_DIR = os.path.join(OUT, "reports")
updater.check_latest = lambda timeout=10: "test"
webbrowser.open = lambda u: None
K = dt.timezone(dt.timedelta(hours=9))
now = dt.datetime.now(K)


def mk(t, src, hrs):
    return Article(t, "https://news.google.com/rss/articles/" + str(abs(hash(t))), "", src,
                   now - dt.timedelta(hours=hrs), "", [])


FAKE = {
    "주택관리공단": [mk("주택관리공단, 영구임대단지 승강기 사고 일제 점검", "서울일보", 5),
                 mk("광산구 '살던집 프로젝트' 전국화 시동…주택관리공단 협력", "브릿지경제", 3),
                 mk("주택관리공단 경남지사, 산학협력 협약", "경남도민일보", 9)],
    "LH": [mk("LH 공공임대주택 화재 안전 취약·임대료 체납 급증", "뉴스1", 4),
           mk("LH 노사, 2차 교섭도 빈손…조직 분리·임금 등 논의 진전 없어", "한국경제", 6)],
    "공공기관": [mk("공공기관 경영평가 편람 개정", "뉴스핌", 2), mk("주택관리공단 등 공공기관 청렴도 발표", "뉴시스", 7)],
    "국정감사": [mk("국토위 국정감사, 공공임대 공가 지적", "아주경제", 1)],
    "임차인": [mk("임차인 보호 강화 법안", "서울신문", 9)],
}
google_news.search_news = lambda kw, s, e, split=True: [Article(**{**a.__dict__, "keywords": [kw]}) for a in FAKE.get(kw, [])]
feeds.search_feeds = lambda fs, g, s, e: ([Article("공동주택 관리비 공개 대상 확대", "https://www.aptn.co.kr/1", "", "아파트관리신문",
                                                   now - dt.timedelta(hours=8), "", ["주택관리"], "B")], [])
google_news.resolve_links = lambda urls, progress=None: {u: u for u in urls}
json.dump({"https://old/1": {"date": "2026-10-15", "time": "10:31", "title": "지난 보고 기사 하나", "source": "연합뉴스",
                             "url": "https://old/1", "main": "https://old/1"}}, open(history.HISTORY_PATH, "w"))

import app as appmod  # noqa: E402
from PIL import ImageGrab  # noqa: E402


class SyncThread:
    def __init__(self, target, args=(), daemon=None):
        self.t, self.a = target, args

    def start(self):
        self.t(*self.a)


appmod.threading.Thread = SyncThread
appmod.messagebox.askyesno = lambda *a, **k: True

a = appmod.App()
a.geometry("1180x780+0+0")
a.update()


def shot(name, w=None):
    w = w or a
    for _ in range(3):
        a.update()
        time.sleep(0.15)
    x, y = w.winfo_rootx(), w.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + w.winfo_width(), y + w.winfo_height())).save(os.path.join(OUT, f"{name}.png"))


with open(os.path.join(OUT, "fonts.txt"), "w", encoding="utf-8") as f:
    fams = sorted(x for x in tkfont.families(a) if "Pretendard" in x or "Malgun" in x or "맑은" in x)
    f.write(f"사용 글꼴: {a.F.family} / Pretendard 로드: {a.F.pretendard}\n찾은 패밀리: {fams}\n"
            f"화면 배율(1pt=px): {a.winfo_fpixels('1p'):.3f}\n")
shot("1_basic_before")
a._search("basic")
shot("2_basic_after")
a._select_tab("pro")
shot("3_pro")
a._select_tab("history")
shot("4_history")
a._select_tab("settings")
shot("5_settings")
a._select_tab("basic")
a.geometry("980x640+0+0")
shot("6_basic_980")
a.geometry("1180x780+0+0")
a._set_status("구글 뉴스 검색 중 · 키워드 5/12 '공공기관' · 지금까지 308건 수집", word="조회 중", kind="busy", progress=0.4)
shot("7_busy")
a._open_add_link()
win = [x for x in a.winfo_children() if isinstance(x, appmod.tk.Toplevel)][-1]
shot("8_dialog_add", win)
win.destroy()
print("screens:", sorted(os.listdir(OUT)))
a.destroy()
