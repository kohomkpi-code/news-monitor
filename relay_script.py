"""보고 기록 중계함 — 구글 Apps Script 웹 앱 대본.

부서 공용 구글 계정 하나에 이 대본을 올려 두면, 각 PC 는 앱만 있으면(구글 드라이브 설치·로그인 없이)
보고 기록을 주고받는다(history_share.sync_relay). 기록은 그 계정의 구글 드라이브 'KOHOM뉴스룸_보고기록' 폴더에
PC 마다 파일 하나(보고기록_PC이름.json)로 쌓인다 — 드라이브 폴더 방식과 같은 파일 형태.

- [설정] → [중계함 대본 복사]를 누르면 앱이 암호를 새로 만들어 대본에 넣고 복사한다. 암호는 저장소에 없다.
- 요청: POST {"key": 암호, "action": "sync", "pc": PC 이름, "data": 이 PC 기록}
  → 이 PC 파일을 저장하고, 다른 PC 파일들을 돌려준다 {"ok": true, "files": [{"name", "data"}]}.
- 대본을 바꾸면 RELAY_VERSION 을 올린다(중계함이 오래된 버전이면 앱이 알려 줌).
"""

RELAY_VERSION = 1

SCRIPT = r"""// KOHOM 뉴스룸 — 보고 기록 중계함 (구글 Apps Script 웹 앱)
// KOHOM 뉴스룸 앱 [설정] → [중계함 대본 복사]로 만든 대본입니다. 암호는 앱이 만들어 넣었습니다.
// 배포: [배포] → [새 배포] → 유형 '웹 앱' → 실행 계정 '나' · 액세스 권한 '모든 사용자' → [배포]
// 기록은 이 계정 구글 드라이브의 'KOHOM뉴스룸_보고기록' 폴더에 PC마다 파일 하나로 쌓입니다. 파일은 지우지 마세요.
const PASSCODE = '__PASSCODE__';
const RELAY_VERSION = __VERSION__;
const FOLDER = 'KOHOM뉴스룸_보고기록';
const PREFIX = '보고기록_';

function doGet() {
  return ContentService.createTextOutput('KOHOM 뉴스룸 보고 기록 중계함이 켜져 있습니다 (v' + RELAY_VERSION + ').');
}

function doPost(e) {
  let req;
  try {
    req = JSON.parse(e.postData.contents);
  } catch (err) {
    return out_({ ok: false, error: 'bad_request' });
  }
  if (!PASSCODE || req.key !== PASSCODE) return out_({ ok: false, error: 'bad_key' });
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return out_({ ok: false, error: 'busy' });
  try {
    const folder = folder_();
    if (req.action === 'ping') return out_({ ok: true, version: RELAY_VERSION });
    if (req.action !== 'sync') return out_({ ok: false, error: 'bad_action' });
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

function folder_() {
  const it = DriveApp.getFoldersByName(FOLDER);
  return it.hasNext() ? it.next() : DriveApp.createFolder(FOLDER);
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
"""


def build(passcode: str) -> str:
    """암호를 넣은 대본. 암호에는 따옴표·역슬래시가 없어야 한다(앱이 만드는 암호는 영문·숫자만)."""
    return SCRIPT.replace("__PASSCODE__", passcode).replace("__VERSION__", str(RELAY_VERSION))
