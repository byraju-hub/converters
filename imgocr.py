#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""사진·캡처 이미지 속 글자를 읽어 텍스트(Markdown)로 옮깁니다.

스캔 PDF 변환에 쓰는 한국어 글자 인식(RapidOCR)을 그대로 씁니다. 처음 한 번 모델(약 13MB)을 내려받고,
그 뒤에는 인터넷 없이 내 PC 안에서 읽습니다. 아이폰 사진의 회전 정보와 HEIC 도 처리합니다.

사용법:
  python imgocr.py 주보.jpg [캡처.png ...] [--separate] [-d 결과폴더]
"""
import argparse
import io
import sys
from pathlib import Path

from vod2md import log, unique_path
import pdf2md

try:                                   # 아이폰 사진(HEIC/HEIF) 읽기
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

MAX_EDGE = 3200            # 이보다 큰 그림은 이 길이로 줄여서 읽는다 (속도·메모리)
MIN_EDGE = 900             # 이보다 작은 그림은 키워서 읽는다 (작은 글씨 인식률)
MAX_PIXELS = 120_000_000
SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif")


def image_to_png(path):
    """그림을 글자 인식에 알맞게(방향 바로잡기·크기 조정) PNG 바이트로 만든다."""
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        w, h = im.size
        if w * h > MAX_PIXELS:
            raise ValueError(f"그림이 너무 커요 ({w}×{h}). 크기를 줄여서 다시 올려 주세요.")
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            bg.alpha_composite(rgba)
            im = bg.convert("RGB")
        elif im.mode != "RGB":
            im = im.convert("RGB")
        long_edge = max(im.size)
        if long_edge > MAX_EDGE or long_edge < MIN_EDGE:
            k = (MAX_EDGE if long_edge > MAX_EDGE else MIN_EDGE) / long_edge
            im = im.resize((max(1, round(im.size[0] * k)), max(1, round(im.size[1] * k))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()


def images_to_md(items, title=None, cb=None):
    """items: [(파일 경로, 표시 이름)]. 그림마다 글자를 읽어 (제목, markdown) 한 건으로 합친다."""
    if not items:
        raise ValueError("이미지가 없어요.")
    n = len(items)
    texts, empty = [], []
    for k, (path, name) in enumerate(items):
        log(f"[ocr] {int(k / n * 100)}% ({k + 1}/{n}장 · 글자 읽는 중)", cb)
        try:
            text = pdf2md.ocr_png(image_to_png(path), cb)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"{name}: 이미지를 읽지 못했어요 ({e})")
        texts.append(text)
        if pdf2md.plain_len(text) < 2:
            empty.append(name)
    if len(empty) == n:
        raise ValueError("글자를 찾지 못했어요. 글자가 또렷하게 보이는 사진인지, 방향이 맞는지 확인해 주세요.")
    log(f"[ocr] 100% ({n}/{n}장)", cb)

    title = title or (Path(items[0][1]).stem + (f" 외 {n - 1}장" if n > 1 else ""))
    lines = [f"# {title}", "", f"- 원본 파일: " + (items[0][1] if n == 1 else f"이미지 {n}장"),
             "- 변환 방식: 글자 인식 OCR (RapidOCR 한국어)",
             "- 참고: 글자 인식 결과에는 오타가 있을 수 있어요. 중요한 부분은 원본과 대조해 주세요."]
    if empty:
        lines.append(f"- 글자를 찾지 못한 이미지: {', '.join(empty[:5])}{' …' if len(empty) > 5 else ''}")
    lines.append("")
    for (path, name), text in zip(items, texts):
        if n > 1:
            lines += ["---", "", f"*{name}*", ""]
        lines += [text or "(글자를 찾지 못했어요)", ""]
    return title, pdf2md.tidy("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="이미지 속 글자 -> Markdown")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--separate", action="store_true", help="이미지마다 따로 파일로 저장 (기본은 한 파일로 합침)")
    ap.add_argument("-d", "--dir", default="output")
    a = ap.parse_args()
    groups = [[(p, Path(p).name)] for p in a.images] if a.separate else [[(p, Path(p).name) for p in a.images]]
    for g in groups:
        try:
            title, md = images_to_md(g)
        except ValueError as e:
            print(f"실패: {e}", file=sys.stderr)
            continue
        out = unique_path(Path(a.dir), title)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"저장: {out}")


if __name__ == "__main__":
    main()
