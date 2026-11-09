#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""사진 변환: 형식 바꾸기(HEIC → JPG 등)와 긴 변 기준 일괄 리사이즈

  - 긴 변이 지정한 길이(px)가 되도록 비율을 지켜 줄입니다. 이보다 작은 사진은 키우지 않습니다.
  - 사진 방향(EXIF)은 바르게 돌려서 저장합니다.
  - 위치·촬영 기기 같은 사진 정보(EXIF)는 기본으로 지우고, 색 프로필(ICC)은 유지해 색이 틀어지지 않게 합니다.

사용법:
  python imgconv.py 사진1.heic 사진2.jpg [-d 결과폴더] [--format jpg|png|webp|keep] [--long 1600] [--quality 85] [--keep-exif]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps

from vod2md import log, safe_name

try:                                   # 아이폰 사진(HEIC/HEIF) 읽기
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

MAX_PIXELS = 120_000_000               # 이보다 큰 그림은 메모리를 너무 많이 써서 막는다
EXT = {"jpg": ".jpg", "png": ".png", "webp": ".webp"}
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif")


def _target_format(src_format, want):
    """want 가 'keep' 이면 원래 형식을 따르되, JPG·PNG·WEBP 가 아닌 것(HEIC·BMP·TIFF·GIF)은 JPG 로."""
    if want in EXT:
        return want
    return {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get((src_format or "").upper(), "jpg")


def _unique(dir_, stem, ext):
    p = dir_ / (stem + ext)
    i = 2
    while p.exists():
        p = dir_ / f"{stem} ({i}){ext}"
        i += 1
    return p


def convert_one(src, out_dir, name, want="jpg", long_edge=0, quality=85, strip_exif=True):
    """사진 한 장을 변환해 out_dir 에 저장한다. 결과 정보를 dict 로 돌려준다."""
    out_dir = Path(out_dir)
    with Image.open(src) as im:
        src_format = im.format
        w0, h0 = im.size
        if w0 * h0 > MAX_PIXELS:
            raise ValueError(f"그림이 너무 커요 ({w0}×{h0}). 크기를 줄여서 다시 올려 주세요.")
        im.load()
        icc = im.info.get("icc_profile")
        im = ImageOps.exif_transpose(im)               # 방향 정보를 반영해 바르게 돌린다 (HEIC 는 라이브러리가 이미 반영)
        fmt = _target_format(src_format, want)

        if long_edge and long_edge > 0:
            scale = long_edge / max(im.size)
            if scale < 1:                               # 작은 사진은 키우지 않는다
                new = (max(1, round(im.size[0] * scale)), max(1, round(im.size[1] * scale)))
                im = im.resize(new, Image.LANCZOS, reducing_gap=3.0)

        params = {}
        if icc:
            params["icc_profile"] = icc
        if not strip_exif and fmt in ("jpg", "webp"):
            try:
                ex = im.getexif()
                if len(ex):
                    params["exif"] = ex
            except Exception:
                pass

        if fmt == "jpg":
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):   # 투명한 곳은 흰색으로
                rgba = im.convert("RGBA")
                bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                bg.alpha_composite(rgba)
                im = bg.convert("RGB")
            elif im.mode != "RGB":
                im = im.convert("RGB")
            params.update(quality=int(quality), optimize=True, progressive=True)
            save_fmt = "JPEG"
        elif fmt == "webp":
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            params.update(quality=int(quality), method=4)
            save_fmt = "WEBP"
        else:
            if im.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            params.update(optimize=True)
            save_fmt = "PNG"

        dst = _unique(out_dir, safe_name(Path(name).stem), EXT[fmt])
        out_dir.mkdir(parents=True, exist_ok=True)
        im.save(dst, save_fmt, **params)
        return dict(path=dst, size=im.size, fmt=fmt, src_bytes=Path(src).stat().st_size, out_bytes=dst.stat().st_size)


def convert_images(items, out_dir, want="jpg", long_edge=0, quality=85, strip_exif=True, cb=None):
    """items: [(파일 경로, 원래 이름)]. (성공 목록, 실패 목록[(이름, 이유)]) 를 돌려준다."""
    ok, bad = [], []
    n, last = len(items), -10
    for i, (src, name) in enumerate(items):
        try:
            ok.append(convert_one(src, out_dir, name, want, long_edge, quality, strip_exif))
        except Exception as e:
            bad.append((name, str(e) if isinstance(e, ValueError) else "읽을 수 없는 사진이에요"))
        pct = int((i + 1) / n * 100)
        if pct >= last + 5 or i == n - 1:
            last = pct
            log(f"[사진] {pct}% ({i + 1}/{n}장)", cb)
    return ok, bad


def main():
    ap = argparse.ArgumentParser(description="사진 형식 변환과 긴 변 기준 리사이즈")
    ap.add_argument("files", nargs="+")
    ap.add_argument("-d", "--outdir", default=".")
    ap.add_argument("--format", choices=["jpg", "png", "webp", "keep"], default="jpg")
    ap.add_argument("--long", type=int, default=0, help="긴 변 길이(px). 0 이면 크기를 바꾸지 않음")
    ap.add_argument("--quality", type=int, default=85, help="JPG·WEBP 품질 (30~100)")
    ap.add_argument("--keep-exif", action="store_true", help="위치 등 사진 정보를 지우지 않음")
    a = ap.parse_args()
    items = [(f, Path(f).name) for f in a.files]
    ok, bad = convert_images(items, Path(a.outdir), a.format, a.long, a.quality, not a.keep_exif)
    for r in ok:
        print(f"완료: {r['path']}  {r['size'][0]}×{r['size'][1]}  {r['src_bytes'] // 1024}KB -> {r['out_bytes'] // 1024}KB")
    for name, why in bad:
        log(f"실패: {name}: {why}")
    print(f"\n성공 {len(ok)} / 실패 {len(bad)}")
    sys.exit(1 if bad and not ok else 0)


if __name__ == "__main__":
    main()
