"""보고 기록·업데이트 중계함 — 구글 Apps Script 웹 앱 대본.

부서 공용 구글 계정 하나에 이 대본을 올려 두면, 각 PC 는 앱만 있으면(구글 드라이브 설치·로그인 없이)
1) 보고 기록을 주고받고(history_share.sync_relay) 2) 새 버전을 확인·내려받는다(updater.py, v1.3.0~).
- 보고 기록: 그 계정 구글 드라이브 'KOHOM뉴스룸_보고기록' 폴더에 PC 마다 파일 하나(보고기록_PC이름.json).
- 업데이트: 같은 계정 드라이브 'KOHOM뉴스룸_업데이트' 폴더에 관리자가 NewsMonitor_v1.3.1.exe 처럼 올려 두면
  버전 숫자가 가장 큰 파일을 새 버전으로 알려 준다. 같은 폴더의 '변경내용.txt'는 업데이트 안내창에 보인다.

- [설정] → [중계함 대본 복사]를 누르면 앱이 암호를 넣어(없으면 새로 만들어) 대본을 복사한다. 암호는 소스에 없다.
- 요청은 모두 POST {"key": 암호, "action": …}
  sync   {"pc", "data"} → 이 PC 파일 저장, 다른 PC 파일들 {"files": [{"name", "data"}]}
  latest              → {"version", "name", "size", "sha256", "notes", "chunks"} (올린 파일이 없으면 version "")
  chunk  {"name", "index"} → {"data": base64 조각} — 4MB 씩(구글 응답 크기 한도 안)
- 대본을 바꾸면 RELAY_VERSION 을 올린다. 옛 대본에 없는 요청은 'bad_action' → 앱이 "대본을 다시 배포" 안내.
"""

RELAY_VERSION = 2
CHUNK = 4 * 1024 * 1024

SCRIPT = r"""// KOHOM 뉴스룸 — 보고 기록·업데이트 중계함 (구글 Apps Script 웹 앱)
// KOHOM 뉴스룸 앱 [설정] → [중계함 대본 복사]로 만든 대본입니다. 암호는 앱이 넣었습니다.
// 처음 배포: [배포] → [새 배포] → 유형 '웹 앱' → 실행 계정 '나' · 액세스 권한 '모든 사용자' → [배포]
// 고쳐서 다시 올릴 때: [배포] → [배포 관리] → 연필 → 버전 '새 버전' → [배포] (주소가 그대로 유지됨)
// 보고 기록: 이 계정 드라이브 'KOHOM뉴스룸_보고기록' 폴더(PC마다 파일 하나, 지우지 마세요)
// 업데이트: 이 계정 드라이브 'KOHOM뉴스룸_업데이트' 폴더에 NewsMonitor_v1.3.1.exe 처럼 올리면 각 PC 앱이 받아 갑니다
const PASSCODE = '__PASSCODE__';
const RELAY_VERSION = __VERSION__;
const FOLDER = 'KOHOM뉴스룸_보고기록';
const UPDATE_FOLDER = 'KOHOM뉴스룸_업데이트';
const PREFIX = '보고기록_';
const CHUNK = __CHUNK__;
const EXE_RE = /^NewsMonitor_v(\d+)\.(\d+)\.(\d+)\.exe$/i;

function doGet() {
  return ContentService.createTextOutput('KOHOM 뉴스룸 중계함이 켜져 있습니다 (v' + RELAY_VERSION + ').');
}

function doPost(e) {
  let req;
  try {
    req = JSON.parse(e.postData.contents);
  } catch (err) {
    return out_({ ok: false, error: 'bad_request' });
  }
  if (!PASSCODE || req.key !== PASSCODE) return out_({ ok: false, error: 'bad_key' });
  if (req.action === 'ping') return out_({ ok: true, version: RELAY_VERSION });
  if (req.action === 'latest') return out_(latest_());
  if (req.action === 'chunk') return out_(chunk_(String(req.name || ''), Number(req.index || 0)));
  if (req.action !== 'sync') return out_({ ok: false, error: 'bad_action' });
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return out_({ ok: false, error: 'busy' });
  try {
    const folder = folder_(FOLDER);
    const pc = String(req.pc || '').replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 60);
    if (!pc) return out_({ ok: false, error: 'no_pc' });
    const name = PREFIX + pc + '.json';
    const body = JSON.stringify(req.data);
    const mine = folder.getFilesByName(name);
    if (mine.hasNext()) mine.next().setContent(body);
    else folder.createFile(name, body, 'application/json');
    const files = [];
    const all = folder.getFiles();
    while (all.hasNext()) {
      const f = all.next();
      const n = f.getName();
      if (n.indexOf(PREFIX) !== 0 || n === name) continue;
      files.push({ name: n, data: f.getBlob().getDataAsString('UTF-8') });
    }
    return out_({ ok: true, version: RELAY_VERSION, files: files });
  } finally {
    lock.releaseLock();
  }
}

// 업데이트 폴더에서 버전이 가장 큰 exe
function latest_() {
  const folder = folder_(UPDATE_FOLDER);
  let best = null, bestKey = null;
  const all = folder.getFiles();
  while (all.hasNext()) {
    const f = all.next();
    const m = EXE_RE.exec(f.getName());
    if (!m) continue;
    const key = [Number(m[1]), Number(m[2]), Number(m[3])];
    if (!bestKey || cmp_(key, bestKey) > 0) { best = f; bestKey = key; }
  }
  let notes = '';
  const nt = folder.getFilesByName('변경내용.txt');
  if (nt.hasNext()) notes = nt.next().getBlob().getDataAsString('UTF-8').slice(0, 1500);
  if (!best) return { ok: true, relay: RELAY_VERSION, version: '', notes: notes };
  const size = best.getSize();
  return { ok: true, relay: RELAY_VERSION, version: bestKey.join('.'), name: best.getName(), size: size,
           sha256: sha_(best), chunks: Math.ceil(size / CHUNK), notes: notes };
}

function chunk_(name, index) {
  if (!EXE_RE.test(name)) return { ok: false, error: 'bad_name' };
  const it = folder_(UPDATE_FOLDER).getFilesByName(name);
  if (!it.hasNext()) return { ok: false, error: 'no_file' };
  const bytes = it.next().getBlob().getBytes();
  const start = index * CHUNK;
  if (index < 0 || start >= bytes.length) return { ok: false, error: 'bad_index' };
  return { ok: true, index: index, data: Utilities.base64Encode(bytes.slice(start, start + CHUNK)) };
}

// 파일 확인값(SHA-256) — 계산이 무거워 파일이 바뀌지 않으면 저장해 둔 값을 쓴다
function sha_(file) {
  const props = PropertiesService.getScriptProperties();
  const key = 'sha_' + file.getId() + '_' + file.getLastUpdated().getTime();
  let v = props.getProperty(key);
  if (!v) {
    const d = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, file.getBlob().getBytes());
    v = d.map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
    props.setProperty(key, v);
  }
  return v;
}

function cmp_(a, b) {
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
}

function folder_(name) {
  const it = DriveApp.getFoldersByName(name);
  return it.hasNext() ? it.next() : DriveApp.createFolder(name);
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
"""


def build(passcode: str) -> str:
    """암호를 넣은 대본. 암호에는 따옴표·역슬래시가 없어야 한다(앱이 만드는 암호는 영문·숫자만)."""
    return (SCRIPT.replace("__PASSCODE__", passcode).replace("__VERSION__", str(RELAY_VERSION))
            .replace("__CHUNK__", str(CHUNK)))
