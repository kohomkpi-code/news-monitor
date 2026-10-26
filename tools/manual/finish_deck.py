"""매뉴얼 PPT 마무리 — 모든 문단에 '한글 단어 잘림 허용' 해제(어절 단위 줄바꿈), 한글 글꼴 칸을 한국어로.

PowerPoint 의 '한글 단어 잘림 허용'은 문단 속성 latinLnBrk 로 저장된다(1 = 단어 중간에서 줄바꿈).
pptxgenjs 가 이 속성을 못 쓰므로, 만든 뒤 슬라이드 XML 의 문단마다 latinLnBrk="0" 을 넣는다.
사용: python finish_deck.py <파일.pptx> [...]
"""

import re
import shutil
import sys
import tempfile
import zipfile

PPR = re.compile(r"<a:pPr(?![^>]*latinLnBrk)")
BARE_P = re.compile(r"<a:p>(?!<a:pPr)")


def fix_xml(xml: str) -> str:
    # pptxgenjs 는 한글 글꼴 칸(ea)을 중국어 문자 집합(-122)·영어로 적는다 → 한글(-127)·한국어로
    # (글꼴이 없는 PC 에서 대체 글꼴을 고를 때 중국어 글꼴로 가지 않게)
    xml = re.sub(r'(<a:ea typeface="[^"]*" pitchFamily="\d+" charset=")-122"', r'\1-127"', xml)
    xml = xml.replace(' lang="en-US"', ' lang="ko-KR" altLang="en-US"')
    xml = PPR.sub('<a:pPr latinLnBrk="0"', xml)
    return BARE_P.sub('<a:p><a:pPr latinLnBrk="0"/>', xml)


def finish(path: str) -> int:
    tmp = tempfile.mktemp(suffix=".pptx")
    n = 0
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if re.match(r"ppt/slides/slide\d+\.xml$", item.filename):
                xml = data.decode("utf-8")
                new = fix_xml(xml)
                n += new.count('latinLnBrk="0"')
                data = new.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)
    return n


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, "문단", finish(p), "개에 어절 단위 줄바꿈")
