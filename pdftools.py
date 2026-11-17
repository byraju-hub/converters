#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""이미지 <-> PDF 변환

  이미지 -> PDF : 여러 이미지를 순서대로 한 PDF 로 묶는다
  PDF -> 이미지 : PDF 의 쪽을 PNG/JPG 이미지로 저장한다
  PDF 도구함    : 합치기 · 나누기 · 쪽 뽑기/지우기 · 회전 · 용량 줄이기 (웹 화면의 "PDF 도구" 탭)

사용법:
  python pdftools.py img2pdf 사진1.jpg 사진2.png -o 결과.pdf [--size fit|a4]
  python pdftools.py pdf2img 문서.pdf -d 결과폴더 [--format png|jpg] [--dpi 150] [--pages "1-3,5"]
"""
import argparse
import io
import re
import sys
from pathlib import Path

from vod2md import log, safe_name

try:                                   # 아이폰 사진(HEIC/HEIF) 읽기
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

A4 = (595.28, 841.89)       # PDF 단위(pt)
MARGIN = 24
MAX_PAGE_PT = 14000         # PDF 한 쪽의 한계(14400pt)보다 조금 작게
MAX_PIXELS = 120_000_000    # 이보다 큰 그림은 메모리를 너무 많이 써서 막는다


def _prepare(path):
    """이미지를 PDF 에 넣을 (바이트, 가로, 세로)로 정리한다.
    JPEG 는 원본 그대로 넣어 화질 손실이 없고, 회전 정보는 반영하며, 투명 배경은 흰색으로 채운다."""
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        fmt = (im.format or "").upper()
        w, h = im.size
        if w * h > MAX_PIXELS:
            raise ValueError(f"그림이 너무 커요 ({w}×{h}). 크기를 줄여서 다시 올려 주세요.")
        orient = im.getexif().get(0x0112, 1)
        if fmt == "JPEG" and orient in (0, 1) and im.mode in ("RGB", "L"):
            return Path(path).read_bytes(), w, h

        im = ImageOps.exif_transpose(im)
        alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        if alpha:
            rgba = im.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            bg.alpha_composite(rgba)
            im = bg.convert("RGB")
        elif im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        if fmt in ("JPEG", "WEBP", "HEIF"):   # 사진류는 JPEG 로, 그 밖(PNG·BMP·GIF·TIFF)은 손실 없이 PNG 로
            im.save(buf, "JPEG", quality=95 if fmt == "JPEG" else 92)
        else:
            im.save(buf, "PNG")
        return buf.getvalue(), im.size[0], im.size[1]


def images_to_pdf(paths, out_path, size="fit", cb=None):
    """이미지 파일들 -> PDF 한 개. size: 'fit'=이미지 비율에 맞춰 여백 없이, 'a4'=A4 용지에 여백을 두고"""
    import pymupdf

    if not paths:
        raise ValueError("이미지가 없어요.")
    doc = pymupdf.open()
    try:
        n, last = len(paths), -10
        for i, p in enumerate(paths):
            try:
                data, w, h = _prepare(p)
            except ValueError:
                raise
            except Exception:
                raise ValueError(f"이미지를 읽을 수 없어요: {Path(p).name.split('_', 1)[-1]}")
            if size == "a4":
                pw, ph = A4 if h >= w else (A4[1], A4[0])
                page = doc.new_page(width=pw, height=ph)
                bw, bh = pw - 2 * MARGIN, ph - 2 * MARGIN
                k = min(bw / w, bh / h)
                iw, ih = w * k, h * k
                x0, y0 = (pw - iw) / 2, (ph - ih) / 2
                rect = pymupdf.Rect(x0, y0, x0 + iw, y0 + ih)
            else:
                pw = A4[0]
                ph = pw * h / w
                if ph > MAX_PAGE_PT:        # 아주 긴 이미지(웹 캡처 등)는 쪽 한계에 맞춰 줄인다
                    pw, ph = pw * MAX_PAGE_PT / ph, MAX_PAGE_PT
                page = doc.new_page(width=pw, height=ph)
                rect = page.rect
            page.insert_image(rect, stream=data)
            pct = int((i + 1) / n * 100)
            if pct >= last + 5 or i == n - 1:
                last = pct
                log(f"[pdf] {pct}% ({i + 1}/{n}장)", cb)
        doc.save(str(out_path), deflate=True, garbage=3)
    finally:
        doc.close()
    return Path(out_path)


def parse_pages(spec, n):
    """'1-3, 5' -> [0,1,2,4] (0부터). 비우면 전체."""
    spec = (spec or "").strip()
    if not spec:
        return list(range(n))
    idx = []
    for part in re.split(r"[,\s]+", spec):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:\s*[-~]\s*(\d+))?", part)
        if not m:
            raise ValueError("쪽 범위 형식이 올바르지 않아요. 예: 1-3, 5")
        a = int(m.group(1))
        b = int(m.group(2) or a)
        if a < 1 or b < a:
            raise ValueError("쪽 범위 형식이 올바르지 않아요. 예: 1-3, 5")
        if b > n:
            raise ValueError(f"이 PDF는 {n}쪽까지만 있어요.")
        idx.extend(range(a - 1, b))
    seen, out = set(), []
    for i in idx:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def pdf_to_images(pdf_path, out_dir, fmt="png", dpi=150, pages="", stem=None, cb=None):
    """PDF 의 쪽들을 out_dir 에 이미지로 저장하고 파일 경로 목록을 돌려준다."""
    import pymupdf

    fmt = "jpg" if fmt.lower() in ("jpg", "jpeg") else "png"
    dpi = max(50, min(600, int(dpi)))
    out_dir = Path(out_dir)
    doc = pymupdf.open(str(pdf_path))
    files = []
    try:
        if doc.needs_pass:
            raise ValueError("암호가 걸린 PDF예요. 암호를 해제한 뒤 다시 올려 주세요.")
        idx = parse_pages(pages, len(doc))
        if not idx:
            raise ValueError("변환할 쪽이 없어요.")
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = safe_name(stem or Path(pdf_path).stem)
        width = max(3, len(str(len(doc))))
        n, last = len(idx), -10
        for k, i in enumerate(idx):
            r = doc[i].rect
            if (r.width * dpi / 72) * (r.height * dpi / 72) > MAX_PIXELS:
                raise ValueError(f"{i + 1}쪽이 너무 커서 이 해상도로는 변환할 수 없어요. 해상도를 낮춰 주세요.")
            pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
            data = pix.tobytes("jpeg", jpg_quality=92) if fmt == "jpg" else pix.tobytes("png")
            p = out_dir / f"{stem}_{i + 1:0{width}d}.{fmt}"
            p.write_bytes(data)
            files.append(p)
            pct = int((k + 1) / n * 100)
            if pct >= last + 5 or k == n - 1:
                last = pct
                log(f"[pdf] {pct}% ({k + 1}/{n}쪽)", cb)
    finally:
        doc.close()
    return files


# ====================================================================== PDF 도구함
def _open_pdf(path):
    import pymupdf
    doc = pymupdf.open(str(path))
    if doc.needs_pass:
        doc.close()
        raise ValueError("암호가 걸린 PDF예요. 암호를 해제한 뒤 다시 올려 주세요.")
    if len(doc) == 0:
        doc.close()
        raise ValueError("쪽이 없는 PDF예요.")
    return doc


def _save(doc, out_path, **kw):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path), garbage=3, deflate=True, **kw)
    return out_path


def parse_groups(spec, n):
    """'1-3, 5, 7-9' -> [[0,1,2],[4],[6,7,8]] (쉼표마다 한 묶음, 0부터)."""
    groups = []
    for part in re.split(r"[,\s]+", (spec or "").strip()):
        if part:
            groups.append(parse_pages(part, n))
    if not groups:
        raise ValueError("나눌 쪽 범위를 적어 주세요. 예: 1-3, 4-6")
    return groups


def merge_pdfs(paths, out_path, cb=None):
    """여러 PDF 를 주어진 순서대로 한 PDF 로 이어붙인다."""
    import pymupdf
    out = pymupdf.open()
    try:
        total = len(paths)
        for k, p in enumerate(paths):
            src = _open_pdf(p)
            try:
                out.insert_pdf(src)
            finally:
                src.close()
            log(f"[pdf] 합치는 중 ({k + 1}/{total})", cb)
        pages = len(out)
        _save(out, out_path)
    finally:
        out.close()
    return Path(out_path), pages


def split_pdf(pdf_path, out_dir, mode="each", every=1, spec="", stem=None, cb=None):
    """PDF 를 여러 파일로 나눠 out_dir 에 저장한다. mode: each(쪽마다) / every(N쪽씩) / ranges(범위마다)."""
    import pymupdf
    src = _open_pdf(pdf_path)
    files = []
    try:
        n = len(src)
        if mode == "every":
            every = max(1, int(every))
            groups = [list(range(i, min(i + every, n))) for i in range(0, n, every)]
        elif mode == "ranges":
            groups = parse_groups(spec, n)
        else:
            groups = [[i] for i in range(n)]
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = safe_name(stem or Path(pdf_path).stem)
        width = max(3, len(str(n)))
        for k, g in enumerate(groups):
            label = f"{g[0] + 1:0{width}d}" if len(g) == 1 else f"{g[0] + 1:0{width}d}-{g[-1] + 1:0{width}d}"
            part = pymupdf.open()
            try:
                for i in g:
                    part.insert_pdf(src, from_page=i, to_page=i)
                files.append(_save(part, out_dir / f"{stem}_{label}.pdf"))
            finally:
                part.close()
            log(f"[pdf] 나누는 중 ({k + 1}/{len(groups)})", cb)
    finally:
        src.close()
    return files


def select_pages(pdf_path, out_path, spec, mode="extract", cb=None):
    """쪽 뽑기(extract: 적은 쪽만 남김) 또는 지우기(delete: 적은 쪽을 뺌). 돌려주는 값: (경로, 남은 쪽수)."""
    doc = _open_pdf(pdf_path)
    try:
        n = len(doc)
        idx = parse_pages(spec, n)
        if not (spec or "").strip():
            raise ValueError("쪽 범위를 적어 주세요. 예: 1-3, 5")
        keep = idx if mode == "extract" else [i for i in range(n) if i not in set(idx)]
        if not keep:
            raise ValueError("모든 쪽을 지울 수는 없어요.")
        doc.select(keep)
        _save(doc, out_path)
    finally:
        doc.close()
    return Path(out_path), len(keep)


def rotate_pdf(pdf_path, out_path, angle, pages="", cb=None):
    """쪽을 시계 방향으로 angle(90·180·270)도 돌린다. pages 가 비면 전체."""
    if angle not in (90, 180, 270):
        raise ValueError("회전 각도는 90, 180, 270 중에서 골라 주세요.")
    doc = _open_pdf(pdf_path)
    try:
        idx = parse_pages(pages, len(doc))
        for i in idx:
            doc[i].set_rotation((doc[i].rotation + angle) % 360)
        _save(doc, out_path)
    finally:
        doc.close()
    return Path(out_path), len(idx)


COMPRESS_LEVELS = {                      # 그림 해상도·화질을 이 값까지 낮춘다
    "normal": dict(dpi_threshold=170, dpi_target=130, quality=78),
    "strong": dict(dpi_threshold=120, dpi_target=96, quality=55),
}


def compress_pdf(pdf_path, out_path, level="normal", cb=None):
    """PDF 용량을 줄인다(큰 그림의 해상도·화질을 낮추고 중복을 정리). 돌려주는 값: (경로, 원래 바이트, 결과 바이트)."""
    import shutil
    doc = _open_pdf(pdf_path)
    before = Path(pdf_path).stat().st_size
    try:
        log("[pdf] 그림을 줄이는 중…", cb)
        try:
            doc.rewrite_images(**COMPRESS_LEVELS.get(level, COMPRESS_LEVELS["normal"]))
        except Exception as e:                       # 그림 줄이기가 안 되는 PDF 도 구조 정리만으로 저장한다
            log(f"[pdf] 그림은 그대로 두고 정리만 해요 ({e})", cb)
        _save(doc, out_path, clean=True)
    finally:
        doc.close()
    after = Path(out_path).stat().st_size
    if after >= before:                              # 더 커지면 원본을 그대로 돌려준다
        shutil.copyfile(pdf_path, out_path)
        after = before
    return Path(out_path), before, after


def main():
    ap = argparse.ArgumentParser(description="이미지 <-> PDF")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("img2pdf", help="이미지 -> PDF")
    a.add_argument("images", nargs="+")
    a.add_argument("-o", "--out", default="이미지.pdf")
    a.add_argument("--size", choices=["fit", "a4"], default="fit", help="fit=이미지에 맞춤(기본) / a4=A4 용지")
    b = sub.add_parser("pdf2img", help="PDF -> 이미지")
    b.add_argument("pdf")
    b.add_argument("-d", "--outdir", default=".")
    b.add_argument("--format", choices=["png", "jpg"], default="png")
    b.add_argument("--dpi", type=int, default=150)
    b.add_argument("--pages", default="", help='쪽 범위 예: "1-3,5" (비우면 전체)')
    args = ap.parse_args()
    try:
        if args.cmd == "img2pdf":
            out = images_to_pdf(args.images, args.out, args.size)
            print(f"완료: {out.resolve()}")
        else:
            files = pdf_to_images(args.pdf, args.outdir, args.format, args.dpi, args.pages)
            print(f"완료: {len(files)}장 -> {Path(args.outdir).resolve()}")
    except Exception as e:
        log(f"실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
