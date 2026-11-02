"""보고 기록 공유 — 여러 PC 가 같은 보고 기록을 쓰게 한다. 방식 두 가지([설정] 탭 '보고 기록 공유').

- 중계함(v1.2.0, sync_relay): 부서 공용 구글 계정에 올린 Apps Script 웹 앱(relay_script.py)과 주고받는다.
  각 PC 는 앱만 있으면 된다(구글 드라이브 설치·로그인 없음). 주소와 암호는 이 PC 설정에만 저장한다.
- 공유 폴더(v1.1.0, sync): 구글 드라이브(데스크톱용)가 PC 에 만든 폴더
  (예: G:\\내 드라이브\\KOHOM뉴스룸_보고기록)를 고르면 드라이브가 올리고 내려받기를 맡는다. 사내 공유 폴더도 된다.
- PC 마다 자기 파일 하나만 쓴다: 보고기록_<PC 이름>.json. 다른 PC 파일은 읽기만 해서, 두 PC 가 같은 파일을
  동시에 고치다 생기는 충돌이 없다.
- 맞추기(sync): 폴더의 보고기록_*.json 전부 + 이 PC 기록을 합친다. 같은 기사는 나중에 기록한 것이,
  기록과 취소가 겹치면 나중 것이 이긴다. 합친 결과를 이 PC 기록(sent_history.json)과 자기 파일에 쓴다.
  → 처음 켤 때 지금까지의 기록이 그대로 올라가고, 다른 PC 의 기록·취소는 다음 맞추기 때 들어온다.
- 담기는 것: 보고일·시각·기사 제목·매체·링크와 PC 이름. 비밀값은 없다.
- 드라이브 충돌 사본(보고기록_PC (1).json)이 생겨도 함께 합치므로 기록이 빠지지 않는다.
"""

import dataclasses
import datetime as dt
import glob
import json
import os
import re
import socket

import requests

import history

FORMAT = "kohom-newsroom-history"
PREFIX = "보고기록_"


@dataclasses.dataclass
class SyncResult:
    ok: bool
    message: str = ""
    pcs: int = 0          # 기록 파일이 있는 PC 수(이 PC 포함)
    received: int = 0     # 다른 PC 에서 새로 들어온 대표 기사 수
    cancelled: int = 0    # 다른 PC 의 취소로 빠진 대표 기사 수
    total: int = 0        # 합친 뒤 대표 기사 수
    at: str = ""          # 맞춘 시각 'MM-DD HH:MM'


def default_pc_name() -> str:
    return os.environ.get("COMPUTERNAME") or socket.gethostname() or "PC"


def safe_name(name: str) -> str:
    """파일 이름에 쓸 수 없는 글자를 _ 로."""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name.strip()) or "PC"


def own_path(folder: str, pc: str) -> str:
    return os.path.join(folder, f"{PREFIX}{safe_name(pc)}.json")


def _read_share(path: str) -> tuple[dict, dict] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _parse(f.read())
    except (OSError, UnicodeDecodeError):
        return None


def _parse(text: str) -> tuple[dict, dict] | None:
    """공유 파일 내용 → (기록, 취소). 형식이 다르거나 깨졌으면 None."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return None
    recs = data.get("records") if isinstance(data.get("records"), dict) else {}
    removed = data.get("removed") if isinstance(data.get("removed"), dict) else {}
    return ({l: history._normalize(l, v) for l, v in recs.items()},
            {l: t for l, t in removed.items() if isinstance(t, str)})


def merge(sources: list[tuple[dict, dict]]) -> tuple[dict, dict]:
    """[(기록, 취소)] 여러 개 → 합친 (기록, 취소). 같은 링크는 나중 시각이 이기고, 취소가 기록보다 나중이면 뺀다."""
    recs: dict[str, dict] = {}
    removed: dict[str, str] = {}
    for r, rm in sources:
        for link, rec in r.items():
            if link not in recs or history.stamp(rec) > history.stamp(recs[link]):
                recs[link] = rec
        for link, t in rm.items():
            if t > removed.get(link, ""):
                removed[link] = t
    old = history.cutoff()
    recs = {l: r for l, r in recs.items() if r["date"] >= old and removed.get(l, "") < history.stamp(r)}
    removed = {l: t for l, t in removed.items() if t[:10] >= old and l not in recs}
    return recs, removed


def _mains(recs: dict) -> set[str]:
    return {l for l, r in recs.items() if r["main"] == l}


def _payload(pc: str, recs: dict, removed: dict) -> dict:
    return {"format": FORMAT, "pc": pc, "saved": history.now_stamp(), "records": recs, "removed": removed}


def _finish(local: tuple[dict, dict], others: list[tuple[dict, dict]], pcs: int, write_own=None) -> SyncResult:
    """합쳐서 이 PC 기록에 쓴다. write_own(합친 내용) 이 실패 문구를 돌려주면 이 PC 기록은 그대로 둔다."""
    recs, removed = merge([local] + others)
    if write_own is not None:
        err = write_own(recs, removed)
        if err:
            return SyncResult(False, err)
    before, after = _mains(local[0]), _mains(recs)
    if recs != local[0]:
        history.save(recs)
    if removed != local[1]:
        history.save_removed(removed)
    return SyncResult(True, pcs=pcs, received=len(after - before), cancelled=len(before - after),
                      total=len(after), at=dt.datetime.now().strftime("%m-%d %H:%M"))


def sync(folder: str, pc: str) -> SyncResult:
    """공유 폴더와 이 PC 기록을 맞춘다. 폴더에 못 닿으면 이 PC 기록은 그대로 두고 이유를 돌려준다."""
    folder = folder.strip()
    if not folder:
        return SyncResult(False, "공유 폴더가 정해지지 않았습니다.")
    if not os.path.isdir(folder):
        return SyncResult(False, f"공유 폴더를 찾을 수 없습니다: {folder} (구글 드라이브가 켜져 있는지 확인)")
    mine = own_path(folder, pc)

    def write_own(recs, removed):
        tmp = mine + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_payload(pc, recs, removed), f, ensure_ascii=False, indent=1)
            os.replace(tmp, mine)
        except OSError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return f"공유 폴더에 쓰지 못했습니다: {e}"
        return ""

    with history.LOCK:
        others, pcs = [], {os.path.basename(mine)}
        for path in glob.glob(os.path.join(folder, PREFIX + "*.json")):
            got = _read_share(path)
            if got is not None:
                others.append(got)
                pcs.add(_pc_of(os.path.basename(path)))
        return _finish((history.load(), history.load_removed()), others, len(pcs), write_own)


def _pc_of(name: str) -> str:
    return re.sub(r" \(\d+\)(?=\.json$)", "", name)  # 드라이브 충돌 사본은 같은 PC 로


RELAY_ERRORS = {
    "bad_key": "중계함 암호가 맞지 않습니다",
    "busy": "중계함이 바빠서 기다리다 멈췄습니다(잠시 뒤 다시)",
    "no_pc": "이 PC 이름이 비어 있습니다",
    "bad_request": "중계함에 보낸 내용이 깨졌습니다",
    "bad_action": "중계함 대본이 이 앱과 맞지 않습니다(대본을 다시 복사해 배포)",
}


def parse_code(text: str) -> tuple[str, str] | None:
    """연결 코드 '중계함 주소#암호' → (주소, 암호)."""
    text = text.strip()
    if "#" not in text:
        return None
    url, key = text.rsplit("#", 1)
    url, key = url.strip(), key.strip()
    if not url.startswith("https://") or not key:
        return None
    return url, key


def sync_relay(url: str, key: str, pc: str, timeout: int = 60) -> SyncResult:
    """중계함(Apps Script)과 맞춘다. 이 PC 기록을 올리고 다른 PC 기록을 받아 합친다.
    주고받는 동안에는 기록을 잠그지 않는다(느린 인터넷에 화면이 멈추지 않게) — 받은 뒤 그사이 바뀐 것까지 다시 읽어 합친다."""
    url, key = url.strip(), key.strip()
    if not url or not key:
        return SyncResult(False, "중계함 주소와 암호를 넣어 주세요.")
    if not url.startswith("https://script.google.com/"):
        return SyncResult(False, "중계함 주소는 https://script.google.com/ 으로 시작해야 합니다.")
    with history.LOCK:
        recs, removed = history.load(), history.load_removed()
    try:
        resp = requests.post(url, json={"key": key, "action": "sync", "pc": safe_name(pc),
                                        "data": _payload(pc, recs, removed)}, timeout=timeout)
    except requests.RequestException as e:
        return SyncResult(False, f"중계함에 연결하지 못했습니다({type(e).__name__})")
    try:
        body = resp.json()
    except ValueError:
        return SyncResult(False, f"중계함 답이 이상합니다(HTTP {resp.status_code}) — 주소가 맞는지, "
                                 "배포의 '액세스 권한'이 '모든 사용자'인지 확인")
    if not isinstance(body, dict) or not body.get("ok"):
        err = body.get("error", "") if isinstance(body, dict) else ""
        return SyncResult(False, RELAY_ERRORS.get(err, f"중계함 오류: {err or '알 수 없음'}"))
    others, pcs = [], {f"{PREFIX}{safe_name(pc)}.json"}
    for f in body.get("files", []):
        got = _parse(f.get("data", "")) if isinstance(f, dict) else None
        if got is not None:
            others.append(got)
            pcs.add(_pc_of(str(f.get("name", ""))))
    with history.LOCK:
        return _finish((history.load(), history.load_removed()), others, len(pcs))


def describe(r: SyncResult) -> str:
    if not r.ok:
        return r.message + " — 이 PC 기록만 씁니다."
    bits = [f"보고 기록 맞춤 · PC {r.pcs}대 · 기록 {r.total}건"]
    if r.received:
        bits.append(f"새로 받은 기록 {r.received}건")
    if r.cancelled:
        bits.append(f"다른 PC 에서 취소한 {r.cancelled}건 반영")
    return " · ".join(bits)
