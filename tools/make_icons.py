# 표 첫 칸 아이콘 4종(40×16): 체크+★, 체크, 빈칸+★, 빈칸 → base64 PNG
import base64, io, math
from PIL import Image, ImageDraw
SS = 4
NAVY, AMBER, EMPTY_BORDER = (31, 59, 92, 255), (232, 163, 61, 255), (174, 184, 195, 255)
def star(d, cx, cy, r):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=AMBER)
def make(checked, starred):
    im = Image.new("RGBA", (40 * SS, 16 * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x0, y0, s = 1 * SS, 1 * SS, 14 * SS
    if checked:
        d.rectangle([x0, y0, x0 + s, y0 + s], fill=NAVY)
        d.line([(x0 + 3.2 * SS, y0 + 7.4 * SS), (x0 + 6 * SS, y0 + 10.2 * SS), (x0 + 11 * SS, y0 + 4.2 * SS)],
               fill=(255, 255, 255, 255), width=int(1.9 * SS), joint="curve")
    else:
        d.rectangle([x0, y0, x0 + s, y0 + s], fill=(255, 255, 255, 255), outline=EMPTY_BORDER, width=SS)
    if starred:
        star(d, 28 * SS, 8.3 * SS, 7 * SS)
    im = im.resize((40, 16), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG"); return base64.b64encode(buf.getvalue()).decode()
out = ['"""표 첫 칸(선택) 아이콘 — 40×16 PNG 4종을 글자로 넣어 둔 것(파일 없이 tk.PhotoImage 로 바로 씀).', '',
       '체크 상자(네이비 #1F3B5C)와 ★(앰버 #E8A33D). 디자인 명세 6장 "체크 + ★ 칸".',
       '다시 만들 때: tools/make_icons.py', '"""', '']
for name, c, st in (("ON_STAR", 1, 1), ("ON", 1, 0), ("OFF_STAR", 0, 1), ("OFF", 0, 0)):
    out.append(f'{name} = "{make(c, st)}"')
open("icons.py", "w").write("\n".join(out) + "\n")


# 체크박스·라디오(22×16: 왼쪽 16px 그림 + 오른쪽 6px 여백) — ttk 체크·라디오 표시 대신 씀
def make_small(kind, on):
    im = Image.new("RGBA", (22 * SS, 16 * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x0, y0, s = 1 * SS, 1 * SS, 14 * SS
    if kind == "check":
        if on:
            d.rectangle([x0, y0, x0 + s, y0 + s], fill=NAVY)
            d.line([(x0 + 3.2 * SS, y0 + 7.4 * SS), (x0 + 6 * SS, y0 + 10.2 * SS), (x0 + 11 * SS, y0 + 4.2 * SS)],
                   fill=(255, 255, 255, 255), width=int(1.9 * SS), joint="curve")
        else:
            d.rectangle([x0, y0, x0 + s, y0 + s], fill=(255, 255, 255, 255), outline=EMPTY_BORDER, width=SS)
    else:
        d.ellipse([x0, y0, x0 + s, y0 + s], fill=(255, 255, 255, 255), outline=NAVY if on else EMPTY_BORDER,
                  width=int(1.4 * SS))
        if on:
            d.ellipse([x0 + 4 * SS, y0 + 4 * SS, x0 + s - 4 * SS, y0 + s - 4 * SS], fill=NAVY)
    im = im.resize((22, 16), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG"); return base64.b64encode(buf.getvalue()).decode()


extra = []
for name, kind, on in (("CHECK_ON", "check", 1), ("CHECK_OFF", "check", 0), ("RADIO_ON", "radio", 1), ("RADIO_OFF", "radio", 0)):
    extra.append(f'{name} = "{make_small(kind, on)}"')
open("icons.py", "a").write("\n".join(extra) + "\n")
