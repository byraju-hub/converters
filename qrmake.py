#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""링크·글자로 QR 코드 이미지를 만듭니다. (주보·포스터에 넣는 신청 링크, 계좌 안내 등)

  PNG : 크기(px)를 정하고, 아래에 설명 글자를 넣을 수 있음 (주보에 바로 붙여 넣기 좋음)
  SVG : 아무리 키워도 깨지지 않는 벡터 (현수막·인쇄용)
인터넷 없이 내 PC 안에서 만들고, 입력한 내용은 어디에도 보내지 않습니다.

사용법:
  python qrmake.py "https://example.com/apply" [--fmt png|svg] [--size 800] [--level m] [--caption "신청하기"] [-d 결과폴더]
"""
import argparse
import io
import re
import sys
from pathlib import Path

from vod2md import log, safe_name, unique_path

FORMATS = ("png", "svg")
LEVELS = ("l", "m", "q", "h")            # 오류 정정: 높을수록 일부가 가려져도 읽히지만 점이 촘촘해진다
BORDER = 4                               # QR 규격이 권하는 흰 여백(칸 수)
MAX_TEXT = 2000
FONTS = (r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc",
         "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")


def default_name(text):
    t = re.sub(r"^https?://(www\.)?", "", text.strip())
    return "QR " + (safe_name(t)[:30] or "코드")


def _font(px):
    from PIL import ImageFont
    for f in FONTS:
        if Path(f).is_file():
            try:
                return ImageFont.truetype(f, px)
            except OSError:
                continue
    return ImageFont.load_default()


def _add_caption(png_bytes, caption):
    """QR 그림 아래에 설명 글자를 가운데 정렬로 붙인다 (긴 글은 줄을 나눈다)."""
    from PIL import Image, ImageDraw
    qr = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w = qr.width
    px = max(18, w // 14)
    font = _font(px)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = []
    for para in caption.splitlines():
        cur = ""
        for ch in para.strip():
            if probe.textlength(cur + ch, font=font) > w * 0.9 and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    lines = [l for l in lines if l][:4]
    if not lines:
        return png_bytes
    gap = int(px * 0.35)
    h = len(lines) * (px + gap) + px // 2
    out = Image.new("RGB", (w, qr.height + h), "white")
    out.paste(qr, (0, 0))
    d = ImageDraw.Draw(out)
    y = qr.height
    for l in lines:
        d.text(((w - probe.textlength(l, font=font)) / 2, y), l, font=font, fill=(20, 20, 20))
        y += px + gap
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def make_qr(text, out_dir, name=None, fmt="png", size=800, level="m", caption="", dark="#000000", cb=None):
    """text 를 QR 코드로 만들어 out_dir 에 저장하고 경로를 돌려준다."""
    try:
        import segno
    except ImportError:
        raise ValueError("QR 코드 도구가 설치되지 않았어요. update.bat 을 실행하거나 'pip install -r requirements.txt'를 실행해 주세요.")
    text = (text or "").strip()
    if not text:
        raise ValueError("QR 코드로 만들 내용이 비어 있어요.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"내용이 너무 길어요 ({MAX_TEXT}자 이하). 긴 글은 짧은 링크로 줄여서 넣어 주세요.")
    fmt = fmt if fmt in FORMATS else "png"
    level = level if level in LEVELS else "m"
    size = max(200, min(4000, int(size)))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", dark or ""):
        dark = "#000000"
    try:
        qr = segno.make(text, error=level, micro=False, boost_error=False)
    except Exception as e:
        raise ValueError("이 내용은 QR 코드에 다 들어가지 않아요. 줄이거나 오류 정정 수준을 낮춰 주세요.") from e
    modules = qr.symbol_size(border=BORDER)[0]
    scale = max(1, size // modules)
    log(f"[QR] {modules}×{modules}칸으로 만드는 중…", cb)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = unique_path(out_dir, safe_name(name) if name else default_name(text), "." + fmt)
    if fmt == "svg":
        qr.save(str(path), kind="svg", scale=scale, border=BORDER, dark=dark, xmldecl=True)
    else:
        buf = io.BytesIO()
        qr.save(buf, kind="png", scale=scale, border=BORDER, dark=dark)
        data = buf.getvalue()
        if caption and caption.strip():
            data = _add_caption(data, caption)
        path.write_bytes(data)
    return path


def main():
    ap = argparse.ArgumentParser(description="링크·글자 -> QR 코드")
    ap.add_argument("texts", nargs="+", help="QR 코드로 만들 링크나 글 (여러 개면 하나씩 만듦)")
    ap.add_argument("--fmt", choices=FORMATS, default="png")
    ap.add_argument("--size", type=int, default=800, help="PNG 한 변 길이(px)")
    ap.add_argument("--level", choices=LEVELS, default="m", help="오류 정정 (l 7%% / m 15%% / q 25%% / h 30%%)")
    ap.add_argument("--caption", default="", help="PNG 아래에 넣을 설명 글자")
    ap.add_argument("-d", "--dir", default="output")
    a = ap.parse_args()
    for t in a.texts:
        try:
            print(f"저장: {make_qr(t, a.dir, fmt=a.fmt, size=a.size, level=a.level, caption=a.caption)}")
        except ValueError as e:
            print(f"실패: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
