"""보고 기록 공유 — 여러 PC 가 같은 보고 기록을 쓰게 한다(구글 드라이브 등 공유 폴더).

- [설정] 탭 '보고 기록 공유'에 폴더를 고르면 켜진다. 구글 드라이브(데스크톱용)가 PC 에 만든 폴더
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
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
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


def sync(folder: str, pc: str) -> SyncResult:
    """공유 폴더와 이 PC 기록을 맞춘다. 폴더에 못 닿으면 이 PC 기록은 그대로 두고 이유를 돌려준다."""
    folder = folder.strip()
    if not folder:
        return SyncResult(False, "공유 폴더가 정해지지 않았습니다.")
    if not os.path.isdir(folder):
        return SyncResult(False, f"공유 폴더를 찾을 수 없습니다: {folder} (구글 드라이브가 켜져 있는지 확인)")
    mine = own_path(folder, pc)
    with history.LOCK:
        local = (history.load(), history.load_removed())
        others, pcs = [], {os.path.basename(mine)}
        for path in glob.glob(os.path.join(folder, PREFIX + "*.json")):
            got = _read_share(path)
            if got is not None:
                others.append(got)
                pcs.add(re.sub(r" \(\d+\)(?=\.json$)", "", os.path.basename(path)))  # 충돌 사본은 같은 PC 로
        recs, removed = merge([local] + others)
        before = _mains(local[0])
        after = _mains(recs)
        payload = {"format": FORMAT, "pc": pc, "saved": history.now_stamp(), "records": recs, "removed": removed}
        tmp = mine + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            os.replace(tmp, mine)
        except OSError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return SyncResult(False, f"공유 폴더에 쓰지 못했습니다: {e}")
        if recs != local[0]:
            history.save(recs)
        if removed != local[1]:
            history.save_removed(removed)
    return SyncResult(True, pcs=len(pcs), received=len(after - before), cancelled=len(before - after),
                      total=len(after), at=dt.datetime.now().strftime("%m-%d %H:%M"))


def describe(r: SyncResult) -> str:
    if not r.ok:
        return r.message + " — 이 PC 기록만 씁니다."
    bits = [f"공유 폴더와 맞춤 · PC {r.pcs}대 · 기록 {r.total}건"]
    if r.received:
        bits.append(f"새로 받은 기록 {r.received}건")
    if r.cancelled:
        bits.append(f"다른 PC 에서 취소한 {r.cancelled}건 반영")
    return " · ".join(bits)
