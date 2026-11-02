"""보고 기록 공유 검증 — 두 PC(담당자·대리자)가 같은 보고 기록을 쓰는지.

1부(공유 폴더): 임시 폴더에 PC 두 대의 기록 파일과 공유 폴더를 만들어, 기록·취소·다시 기록·충돌 사본·폴더 없음을 확인한다.
2부(중계함): 실제 중계함 대본(relay_script.py, Apps Script)을 node 로 돌리고 구글 드라이브만 가짜로 바꿔,
  앱 → 중계함 → 앱 왕복을 확인한다. node 가 없으면 2부는 건너뛴다.
사용: python tests/check_history.py   (저장소 맨 위 폴더에서). 하나라도 실패하면 끝 코드 1 → 빌드 중단.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import datetime as dt
import json
import shutil
import subprocess
import tempfile

import requests

import history
import history_share as hs
import relay_script

root = tempfile.mkdtemp()
share = os.path.join(root, "공유 드라이브")
os.makedirs(share)
PCS = {}
for name in ("담당자PC", "대리자PC"):
    d = os.path.join(root, name)
    os.makedirs(d)
    PCS[name] = d

tick = [0]
base = dt.datetime(2026, 10, 30, 9, 0, 0)


def fake_stamp(when=None):  # 실제로는 초 단위 시각 — 시험에서는 부를 때마다 1초씩 늘린다
    tick[0] += 1
    return (base + dt.timedelta(seconds=tick[0])).strftime("%Y-%m-%dT%H:%M:%S")


history.now_stamp = fake_stamp


def on(pc):
    """이 PC 의 기록 파일로 바꾼다(한 프로그램 안에서 두 PC 를 흉내)."""
    history.HISTORY_PATH = os.path.join(PCS[pc], "sent_history.json")
    history.REMOVED_PATH = os.path.join(PCS[pc], "sent_history_removed.json")


def sync(pc):
    on(pc)
    return hs.sync(share, pc)


def entry(n):
    return {"link": f"https://news/{n}", "title": f"기사 {n}", "source": "연합뉴스", "main": f"https://news/{n}"}


results: list[bool] = []


def check(name, ok):
    results.append(bool(ok))
    print(f"{len(results)} {'통과' if ok else '실패'} | {name}")


# 담당자 PC: 공유를 켜기 전부터 있던 기록(예전 형태, stamp 없음) 2건 + 3년 넘은 기록 1건
on("담당자PC")
old = (dt.date.today() - dt.timedelta(days=history.KEEP_DAYS + 5)).isoformat()
with open(history.HISTORY_PATH, "w", encoding="utf-8") as f:
    json.dump({"https://news/1": {"date": "2026-10-28", "time": "09:30", "title": "기사 1", "source": "뉴스1",
                                  "url": "", "main": "https://news/1"},
               "https://news/2": "2026-10-29",
               "https://news/old": {"date": old, "time": "09:00", "title": "옛 기사", "source": "",
                                    "url": "", "main": "https://news/old"}}, f, ensure_ascii=False)

r = sync("담당자PC")
mine = hs.own_path(share, "담당자PC")
check("처음 맞추면 지금까지 기록이 공유 폴더에 올라감(보고기록_담당자PC.json)",
      r.ok and os.path.exists(mine) and set(json.load(open(mine, encoding="utf-8"))["records"]) == {
          "https://news/1", "https://news/2"})
check("3년 지난 기록은 올리지 않음", "https://news/old" not in history.load())

r = sync("대리자PC")
check("대리자 PC 를 켜면 담당자 기록 2건을 받아 옴", r.ok and r.received == 2 and r.pcs == 2
      and set(history.load()) == {"https://news/1", "https://news/2"})

on("대리자PC")
history.mark_sent([entry(3), {"link": "https://news/3b", "title": "같은 사안", "source": "뉴시스",
                              "main": "https://news/3"}])
sync("대리자PC")
r = sync("담당자PC")
check("대리자가 보고한 기사(묶인 기사 포함)가 담당자 PC 로 들어옴",
      r.received == 1 and {"https://news/3", "https://news/3b"} <= set(history.load()))

on("담당자PC")
history.remove(["https://news/3"])
sync("담당자PC")
r = sync("대리자PC")
check("담당자가 기록 취소하면 대리자 PC 에서도 빠짐(묶인 기사까지)",
      r.cancelled == 1 and not ({"https://news/3", "https://news/3b"} & set(history.load())))

on("대리자PC")
history.mark_sent([entry(3)])
sync("대리자PC")
sync("담당자PC")
check("취소한 기사를 나중에 다시 기록하면 다시 들어감", "https://news/3" in history.load())

# 구글 드라이브 충돌 사본: 같은 PC 파일이 두 개로 갈라진 경우
data = json.load(open(mine, encoding="utf-8"))
data["records"]["https://news/9"] = {"date": "2026-10-30", "time": "10:00", "title": "사본에만 있는 기사",
                                     "source": "", "url": "", "main": "https://news/9", "stamp": "2026-10-30T10:00:00"}
with open(os.path.join(share, "보고기록_담당자PC (1).json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)
r = sync("대리자PC")
check("충돌 사본에만 있는 기록도 합쳐지고 PC 는 2대로 셈", "https://news/9" in history.load() and r.pcs == 2)

with open(os.path.join(share, "보고기록_망가진PC.json"), "w", encoding="utf-8") as f:
    f.write("{망가진 파일")
r = sync("담당자PC")
check("깨진 파일이 있어도 나머지로 맞춤", r.ok and "https://news/9" in history.load())

before = history.load()
r = hs.sync(os.path.join(root, "없는 폴더"), "담당자PC")
check("공유 폴더가 없으면(드라이브 꺼짐) 실패 안내, 이 PC 기록은 그대로",
      not r.ok and "찾을 수 없습니다" in hs.describe(r) and history.load() == before)

check("PC 이름의 특수문자는 파일 이름에서 _ 로", os.path.basename(hs.own_path(share, 'a/b:c d')) == "보고기록_a_b_c_d.json")


# ---------------------------------------------------------------- 2부: 중계함
NODE_MOCK = r"""
const fs = require('fs');
const STATE = process.argv[2], REQ = process.argv[3];
let files = fs.existsSync(STATE) ? JSON.parse(fs.readFileSync(STATE, 'utf8')) : null;  // null = 폴더 아직 없음
function iter(a) { let i = 0; return { hasNext: () => i < a.length, next: () => a[i++] }; }
function file(n) { return { getName: () => n, setContent: c => { files[n] = c; },
                            getBlob: () => ({ getDataAsString: () => files[n] }) }; }
const folderObj = { getFilesByName: n => iter(n in files ? [file(n)] : []),
                    createFile: (n, c) => { files[n] = c; return file(n); },
                    getFiles: () => iter(Object.keys(files).map(file)) };
const DriveApp = { getFoldersByName: () => iter(files ? [folderObj] : []), createFolder: () => { files = {}; return folderObj; } };
const LockService = { getScriptLock: () => ({ tryLock: () => true, releaseLock: () => {} }) };
const ContentService = { MimeType: { JSON: 'json' }, createTextOutput: t => ({ t, setMimeType() { return this; } }) };
"""
KEY = "a1b2c3d4e5f6a7b8c9d0"
URL = "https://script.google.com/macros/s/TEST/exec"
relay_dir = os.path.join(root, "relay")
os.makedirs(relay_dir, exist_ok=True)
js = os.path.join(relay_dir, "relay.js")
state = os.path.join(relay_dir, "drive.json")


class Resp:
    def __init__(self, text, code=200):
        self.text, self.status_code = text, code

    def json(self):
        return json.loads(self.text)


def fake_post(url, json=None, timeout=None):  # requests.post 대신: 중계함 대본을 node 로 실행
    req = os.path.join(relay_dir, "req.json")
    with open(req, "w", encoding="utf-8") as f:
        f.write(__import__("json").dumps(json, ensure_ascii=False))
    out = subprocess.run(["node", js, state, req], capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        raise RuntimeError(out.stderr)
    return Resp(out.stdout)


script = relay_script.build(KEY)
check("중계함 대본에 암호·버전이 들어감", KEY in script and "__PASSCODE__" not in script and "__VERSION__" not in script)
check("연결 코드 '주소#암호' 읽기", hs.parse_code(f" {URL}#{KEY} ") == (URL, KEY) and hs.parse_code("http://x#k") is None)
check("script.google.com 이 아닌 주소는 거절", not hs.sync_relay("https://example.com/x", KEY, "PC").ok)

if shutil.which("node") is None:
    print("node 가 없어 중계함 왕복 시험은 건너뜁니다")
else:
    with open(js, "w", encoding="utf-8") as f:
        f.write(NODE_MOCK + script + """
const res = doPost({ postData: { contents: fs.readFileSync(REQ, 'utf8') } });
fs.writeFileSync(STATE, JSON.stringify(files || {}));
process.stdout.write(res.t);
""")
    hs.requests.post = fake_post
    for name in ("담당자R", "대리자R"):
        d = os.path.join(root, name)
        os.makedirs(d)
        PCS[name] = d
    on("담당자R")
    history.mark_sent([entry(11), entry(12)])
    r = hs.sync_relay(URL, KEY, "담당자R")
    drive = json.load(open(state, encoding="utf-8"))
    check("중계함: 담당자 기록이 부서 계정 드라이브 폴더에 올라감(보고기록_담당자R.json)",
          r.ok and r.pcs == 1 and set(json.loads(drive["보고기록_담당자R.json"])["records"]) == {
              "https://news/11", "https://news/12"})
    on("대리자R")
    r = hs.sync_relay(URL, KEY, "대리자R")
    check("중계함: 대리자 PC 는 앱만으로 담당자 기록 2건을 받아 옴", r.ok and r.received == 2 and r.pcs == 2
          and set(history.load()) == {"https://news/11", "https://news/12"})
    history.remove(["https://news/12"])
    hs.sync_relay(URL, KEY, "대리자R")
    on("담당자R")
    r = hs.sync_relay(URL, KEY, "담당자R")
    check("중계함: 대리자가 취소한 기록이 담당자 PC 에서도 빠짐", r.cancelled == 1 and set(history.load()) == {"https://news/11"})
    before = history.load()
    r = hs.sync_relay(URL, "틀린암호", "담당자R")
    check("중계함: 암호가 틀리면 거절, 이 PC 기록은 그대로", not r.ok and "암호" in r.message and history.load() == before)
    hs.requests.post = lambda *a, **k: Resp("<html>로그인 필요</html>")
    r = hs.sync_relay(URL, KEY, "담당자R")
    check("중계함: 답이 JSON 이 아니면('모든 사용자' 배포 아님 등) 안내", not r.ok and "모든 사용자" in r.message)

    def down(*a, **k):
        raise requests.ConnectionError("x")
    hs.requests.post = down
    r = hs.sync_relay(URL, KEY, "담당자R")
    check("중계함: 인터넷이 끊기면 안내하고 이 PC 기록은 그대로", not r.ok and "연결하지 못했습니다" in hs.describe(r)
          and history.load() == before)

shutil.rmtree(root, ignore_errors=True)
print("\nALL", "PASS" if all(results) else "FAIL", f"{sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
