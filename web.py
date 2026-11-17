#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""vod2md 웹 화면: 링크 붙여넣기 / 파일 드래그 앤 드롭 -> 일괄 변환 -> .md 미리보기·다운로드
실행: python web.py  → http://127.0.0.1:8765
"""
import io
import os
import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from queue import Queue

from flask import Flask, abort, jsonify, request, send_file, Response

import audiodl
import hwpconv
import imgconv
import imgocr
import mdpdf
import mimetypes
import officeconv
import pdf2md
import pdftools
import qrmake
import settings
import vod2md

PORT = int(os.environ.get("VOD_PORT", "8765"))
app = Flask(__name__)
OUT, OUT_WARN = settings.initial_output_dir()      # 저장 폴더 (사용자가 바꿀 수 있고 settings.json 에 기억된다)
UPLOADS = Path(tempfile.mkdtemp(prefix="vod2md_up_"))

jobs = {}              # id -> dict
q = Queue()


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


def run_job(j, cb):
    """작업 한 건을 실행하고 j 에 결과를 기록한다."""
    kind = j.get("kind")
    if kind == "img2pdf":
        stem = vod2md.safe_name(j["pdfname"]) if j.get("pdfname") else None
        if not stem:
            first = Path(j["names"][0]).stem
            stem = first + (f" 외 {len(j['names']) - 1}장" if len(j["names"]) > 1 else "")
        path = vod2md.unique_path(OUT, stem, ".pdf")
        pdftools.images_to_pdf(j["tmps"], path, j.get("size", "fit"), cb=cb)
        j.update(status="done", title=path.stem, file=path.name, fpath=str(path), ext="pdf",
                 meta=human(path.stat().st_size), log="완료")
    elif kind == "hwp":
        stem = Path(j["name"]).stem
        t = j.get("target", "md")
        if t == "pdf":
            path = vod2md.unique_path(OUT, stem, ".pdf")
            hwpconv.hwp_to_pdf(j["source"], path, cb)
            j.update(status="done", title=path.stem, file=path.name, fpath=str(path), ext="pdf",
                     meta=human(path.stat().st_size), log="완료")
        elif t == "img":
            with tempfile.TemporaryDirectory(prefix="hwp2img_") as tmp:
                pdf = hwpconv.hwp_to_pdf(j["source"], Path(tmp) / "doc.pdf", cb)
                folder = vod2md.unique_path(OUT, stem + " 이미지", "")
                files = pdftools.pdf_to_images(pdf, folder, j.get("fmt", "png"), j.get("dpi", 150), "", stem=stem, cb=cb)
            total = sum(f.stat().st_size for f in files)
            j.update(status="done", title=folder.name, file=folder.name + ".zip", dir=str(folder), ext="zip",
                     meta=f"{len(files)}장 · {j.get('fmt', 'png').upper()} {j.get('dpi', 150)}dpi · {human(total)}", log="완료")
        else:
            title, md = hwpconv.convert_hwp_md(j["source"], j["name"], cb)
            save_md(j, title, md)
    elif kind == "imgconv":
        items = list(zip(j["tmps"], j["names"]))
        n = len(items)
        out_dir = OUT if n == 1 else vod2md.unique_path(OUT, f"{Path(items[0][1]).stem} 외 {n - 1}장 변환", "")
        ok, bad = imgconv.convert_images(items, out_dir, j["fmt"], j["long"], j["quality"], j["strip"], cb)
        if not ok:
            raise ValueError("변환하지 못했어요: " + "; ".join(f"{a} ({b})" for a, b in bad[:3]))
        src_total = sum(r["src_bytes"] for r in ok)
        dst_total = sum(r["out_bytes"] for r in ok)
        fmts = "/".join(sorted({r["fmt"].upper() for r in ok}))
        size_txt = f"긴 변 {j['long']}px" if j["long"] else "원래 크기"
        meta = f"{fmts} · {size_txt} · {human(dst_total)} (원본 {human(src_total)})"
        if bad:
            meta += f" · 실패 {len(bad)}장: " + ", ".join(a for a, _ in bad[:3])
        if n == 1:
            p = ok[0]["path"]
            j.update(status="done", title=p.name, file=p.name, fpath=str(p), ext=p.suffix.lstrip("."), meta=meta, log="완료")
        else:
            j.update(status="done", title=out_dir.name, file=out_dir.name + ".zip", dir=str(out_dir), ext="zip", meta=meta, log="완료")
    elif kind == "pdf2img":
        folder = vod2md.unique_path(OUT, Path(j["name"]).stem + " 이미지", "")
        files = pdftools.pdf_to_images(j["source"], folder, j.get("fmt", "png"), j.get("dpi", 150),
                                       j.get("pages", ""), stem=Path(j["name"]).stem, cb=cb)
        total = sum(f.stat().st_size for f in files)
        j.update(status="done", title=folder.name, file=folder.name + ".zip", dir=str(folder), ext="zip",
                 meta=f"{len(files)}장 · {j.get('fmt', 'png').upper()} {j.get('dpi', 150)}dpi · {human(total)}", log="완료")
    elif kind == "audio":
        title, path = audiodl.download_audio(j["source"], OUT, j["fmt"], j["kbps"], cb)
        j.update(status="done", title=title, file=path.name, fpath=str(path), ext=j["fmt"],
                 meta=f"{j['fmt'].upper()}" + (f" {j['kbps']}kbps" if j["fmt"] == "mp3" else "") + f" · {human(path.stat().st_size)}",
                 log="완료")
    elif kind == "ocr":
        items = list(zip(j["tmps"], j["names"]))
        title, md = imgocr.images_to_md(items, cb=cb)
        save_md(j, title, md)
    elif kind == "md2pdf":
        stem = j["stem"]
        path = vod2md.unique_path(OUT, stem, ".pdf")
        mdpdf.md_to_pdf(j["md_text"], path, title=mdpdf.title_of(j["md_text"], stem), size=j["size"],
                        font=j["font"], numbers=j["numbers"], cb=cb)
        j.update(status="done", title=path.stem, file=path.name, fpath=str(path), ext="pdf",
                 meta=f"{pdf_pages(path)}쪽 · {human(path.stat().st_size)}", log="완료")
    elif kind == "office":
        stem = Path(j["name"]).stem
        if j.get("target") == "img":
            with tempfile.TemporaryDirectory(prefix="office2img_") as tmp:
                pdf = officeconv.office_to_pdf(j["source"], Path(tmp) / "doc.pdf", cb)
                folder = vod2md.unique_path(OUT, stem + " 이미지", "")
                files = pdftools.pdf_to_images(pdf, folder, j.get("fmt", "png"), j.get("dpi", 150), "", stem=stem, cb=cb)
            total = sum(f.stat().st_size for f in files)
            j.update(status="done", title=folder.name, file=folder.name + ".zip", dir=str(folder), ext="zip",
                     meta=f"{len(files)}장 · {j.get('fmt', 'png').upper()} {j.get('dpi', 150)}dpi · {human(total)}", log="완료")
        else:
            path = vod2md.unique_path(OUT, stem, ".pdf")
            officeconv.office_to_pdf(j["source"], path, cb)
            j.update(status="done", title=path.stem, file=path.name, fpath=str(path), ext="pdf",
                     meta=f"{pdf_pages(path)}쪽 · {human(path.stat().st_size)}", log="완료")
    elif kind == "qr":
        path = qrmake.make_qr(j["text"], OUT, name=j.get("qname") or None, fmt=j["fmt"], size=j["size"],
                              level=j["level"], caption=j.get("caption", ""), cb=cb)
        j.update(status="done", title=path.stem, file=path.name, fpath=str(path), ext=path.suffix.lstrip("."),
                 meta=f"{path.suffix.lstrip('.').upper()} · {human(path.stat().st_size)}", log="완료")
    elif kind == "pdftool":
        run_pdftool(j, cb)
    elif kind == "pdf":
        title, md = pdf2md.convert_pdf(j["source"], local_name=j.get("name"),
                                       page_marks=j.get("page_marks", True), ocr=j.get("ocr", True), cb=cb)
        save_md(j, title, md)
    else:
        title, md = vod2md.convert(j["source"], j["model"], j["lang"], j["whisper"],
                                   j["summarize"], cb=cb, local_name=j.get("name"))
        save_md(j, title, md)


def pdf_pages(path):
    try:
        import pymupdf
        with pymupdf.open(str(path)) as d:
            return len(d)
    except Exception:
        return "?"


def run_pdftool(j, cb):
    """PDF 도구함: 합치기·나누기·쪽 뽑기/지우기·회전·용량 줄이기"""
    op = j["op"]
    if op == "merge":
        stem = vod2md.safe_name(j["pdfname"]) if j.get("pdfname") else None
        if not stem:
            first = Path(j["names"][0]).stem
            stem = first + (f" 외 {len(j['names']) - 1}개 합침" if len(j["names"]) > 1 else " (합침)")
        path = vod2md.unique_path(OUT, stem, ".pdf")
        _, pages = pdftools.merge_pdfs(j["tmps"], path, cb=cb)
        j.update(status="done", title=path.stem, file=path.name, fpath=str(path), ext="pdf",
                 meta=f"{len(j['tmps'])}개 → {pages}쪽 · {human(path.stat().st_size)}", log="완료")
        return
    stem = Path(j["name"]).stem
    if op == "split":
        folder = vod2md.unique_path(OUT, stem + " 나눔", "")
        files = pdftools.split_pdf(j["source"], folder, j["mode"], j.get("every", 1), j.get("spec", ""), stem=stem, cb=cb)
        total = sum(f.stat().st_size for f in files)
        j.update(status="done", title=folder.name, file=folder.name + ".zip", dir=str(folder), ext="zip",
                 meta=f"{len(files)}개 파일 · {human(total)}", log="완료")
        return
    if op == "pick":
        tag = "(일부 쪽)" if j["mode"] == "extract" else "(쪽 지움)"
        path = vod2md.unique_path(OUT, f"{stem} {tag}", ".pdf")
        _, kept = pdftools.select_pages(j["source"], path, j["spec"], j["mode"], cb)
        meta = f"{kept}쪽 · {human(path.stat().st_size)}"
    elif op == "rotate":
        path = vod2md.unique_path(OUT, f"{stem} (회전)", ".pdf")
        _, count = pdftools.rotate_pdf(j["source"], path, j["angle"], j.get("spec", ""), cb)
        meta = f"{count}쪽을 {j['angle']}° 돌림 · {human(path.stat().st_size)}"
    elif op == "compress":
        path = vod2md.unique_path(OUT, f"{stem} (용량 줄임)", ".pdf")
        _, before, after = pdftools.compress_pdf(j["source"], path, j["level"], cb)
        if after >= before:
            meta = f"{human(before)} · 이미 충분히 작아서 그대로 뒀어요"
        else:
            meta = f"{human(before)} → {human(after)} ({round((1 - after / before) * 100)}% 줄임)"
    else:
        raise ValueError("알 수 없는 PDF 도구예요.")
    j.update(status="done", title=path.stem, file=path.name, fpath=str(path), ext="pdf", meta=meta, log="완료")


def save_md(j, title, md):
    path = vod2md.unique_path(OUT, title)
    path.write_text(md, encoding="utf-8")
    j.update(status="done", title=title, file=path.name, md=md, ext="md", log="완료")


def worker():
    while True:
        jid = q.get()
        j = jobs[jid]
        try:
            j["status"] = "running"

            def cb(msg):
                j["log"] = msg
            run_job(j, cb)
        except Exception as e:
            j.update(status="error", log=re.sub(r"\x1b\[[0-9;]*m", "", str(e)).strip())
        finally:
            for t in ([j["tmp"]] if j.get("tmp") else []) + list(j.get("tmps", [])):
                try:
                    Path(t).unlink(missing_ok=True)
                except OSError:
                    pass        # 임시 파일을 못 지워도 다음 작업은 계속 처리한다
            q.task_done()


threading.Thread(target=worker, daemon=True).start()


def enqueue(opts, **kw):
    jid = uuid.uuid4().hex[:8]
    jobs[jid] = dict(status="queued", log="대기 중", **opts, **kw)
    q.put(jid)
    return jid


@app.post("/api/submit")
def submit():
    f = request.form
    opts = dict(model=f.get("model", "small"), lang=f.get("lang") or None,
                whisper=f.get("whisper") == "1", summarize=f.get("summarize") == "1")
    lines = [l.strip() for l in f.get("urls", "").splitlines() if l.strip()]
    bad = [l for l in lines if not l.lower().startswith(("http://", "https://"))]
    if bad:    # 하나라도 이상하면 아무것도 시작하지 않고 어떤 줄이 문제인지 알려준다
        return jsonify(error="링크는 http:// 또는 https:// 로 시작해야 해요", bad=bad), 400
    ids = [enqueue(opts, source=l, label=l) for l in lines]
    for up in request.files.getlist("files"):
        dest = UPLOADS / f"{uuid.uuid4().hex}_{Path(up.filename).name}"
        up.save(dest)
        ids.append(enqueue(opts, source=str(dest), tmp=str(dest), name=up.filename, label=up.filename))
    return jsonify(ids)


def not_pdfs(ups):
    """확장자와 파일 머리(%PDF-)를 둘 다 확인해서 PDF 가 아닌 파일 이름을 돌려준다."""
    bad = []
    for up in ups:
        head = up.stream.read(5)
        up.stream.seek(0)
        if not up.filename.lower().endswith(".pdf") or head != b"%PDF-":
            bad.append(up.filename)
    return bad


def save_upload(up):
    dest = UPLOADS / f"{uuid.uuid4().hex}_{Path(up.filename).name}"
    up.save(dest)
    return dest


@app.post("/api/submit-img2pdf")
def submit_img2pdf():
    from PIL import Image
    ups = request.files.getlist("files")
    if not ups:
        return jsonify(error="이미지를 올려 주세요"), 400
    bad = []
    for up in ups:
        try:
            Image.open(up.stream).verify()
        except Exception:
            bad.append(up.filename)
        finally:
            up.stream.seek(0)
    if bad:
        return jsonify(error="이미지로 읽을 수 없는 파일이 있어요", bad=bad), 400
    size = request.form.get("size") if request.form.get("size") in ("fit", "a4") else "fit"
    paths = [str(save_upload(up)) for up in ups]       # 올린 순서가 쪽 순서
    jid = enqueue(dict(kind="img2pdf", size=size, pdfname=request.form.get("name", "").strip()),
                  source="", tmps=paths, names=[up.filename for up in ups], label=f"이미지 {len(ups)}장")
    return jsonify([jid])


@app.post("/api/submit-imgconv")
def submit_imgconv():
    from PIL import Image
    ups = request.files.getlist("files")
    if not ups:
        return jsonify(error="사진을 올려 주세요"), 400
    bad = []
    for up in ups:
        try:
            Image.open(up.stream).verify()
        except Exception:
            bad.append(up.filename)
        finally:
            up.stream.seek(0)
    if bad:
        return jsonify(error="사진으로 읽을 수 없는 파일이 있어요", bad=bad), 400
    f = request.form
    fmt = f.get("fmt") if f.get("fmt") in ("jpg", "png", "webp", "keep") else "jpg"
    try:
        long_edge = int(f.get("long", "0"))
    except ValueError:
        long_edge = 0
    long_edge = 0 if long_edge <= 0 else max(100, min(20000, long_edge))
    try:
        quality = max(30, min(100, int(f.get("quality", "85"))))
    except ValueError:
        quality = 85
    paths = [str(save_upload(up)) for up in ups]
    jid = enqueue(dict(kind="imgconv", fmt=fmt, long=long_edge, quality=quality, strip=f.get("strip") != "0"),
                  source="", tmps=paths, names=[up.filename for up in ups], label=f"사진 {len(ups)}장")
    return jsonify([jid])


@app.post("/api/submit-pdf2img")
def submit_pdf2img():
    ups = request.files.getlist("files")
    if not ups:
        return jsonify(error="PDF 파일을 올려 주세요"), 400
    bad = not_pdfs(ups)
    if bad:
        return jsonify(error="PDF 파일이 아니에요", bad=bad), 400
    f = request.form
    try:
        dpi = max(50, min(600, int(f.get("dpi", "150"))))
    except ValueError:
        dpi = 150
    try:                    # 쪽 범위 형식이 틀렸으면 시작하기 전에 알려 준다
        pdftools.parse_pages(f.get("pages", ""), 10 ** 6)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    opts = dict(kind="pdf2img", fmt="jpg" if f.get("fmt") == "jpg" else "png", dpi=dpi,
                pages=f.get("pages", "").strip())
    ids = []
    for up in ups:
        dest = save_upload(up)
        ids.append(enqueue(opts, source=str(dest), tmp=str(dest), name=up.filename, label=up.filename))
    return jsonify(ids)


@app.post("/api/submit-pdf")
def submit_pdf():
    ups = request.files.getlist("files")
    if not ups:
        return jsonify(error="PDF 파일을 올려 주세요"), 400
    bad = not_pdfs(ups)
    if bad:
        return jsonify(error="PDF 파일이 아니에요", bad=bad), 400
    opts = dict(kind="pdf", page_marks=request.form.get("page_marks") != "0",
                ocr=request.form.get("ocr") != "0")
    ids = []
    for up in ups:
        dest = UPLOADS / f"{uuid.uuid4().hex}_{Path(up.filename).name}"
        up.save(dest)
        ids.append(enqueue(opts, source=str(dest), tmp=str(dest), name=up.filename, label=up.filename))
    return jsonify(ids)


@app.get("/api/capabilities")
def capabilities():
    """이 PC에서 가능한 것 (화면이 선택지를 맞추는 데 쓴다)"""
    return jsonify(hancom=hwpconv.hancom_available(), office=officeconv.office_available(), mdpdf=mdpdf.available())


@app.post("/api/submit-hwp")
def submit_hwp():
    ups = request.files.getlist("files")
    if not ups:
        return jsonify(error="한글 문서(.hwp, .hwpx)를 올려 주세요"), 400
    bad = []
    for up in ups:          # 확장자와 파일 머리를 모두 확인한다
        head = up.stream.read(8)
        up.stream.seek(0)
        name = up.filename.lower()
        ok = (name.endswith(".hwpx") and head[:4] == b"PK\x03\x04") or \
             (name.endswith(".hwp") and head == bytes.fromhex("D0CF11E0A1B11AE1"))
        if not ok:
            bad.append(up.filename)
    if bad:
        return jsonify(error="한글 문서가 아니에요", bad=bad), 400
    f = request.form
    target = f.get("target") if f.get("target") in ("pdf", "md", "img") else "md"
    if target != "md" and not hwpconv.hancom_available():
        return jsonify(error="PDF·이미지로 바꾸려면 한컴오피스가 필요해요. 이 PC에서는 Markdown만 가능해요"), 400
    try:
        dpi = max(50, min(600, int(f.get("dpi", "150"))))
    except ValueError:
        dpi = 150
    opts = dict(kind="hwp", target=target, fmt="jpg" if f.get("fmt") == "jpg" else "png", dpi=dpi)
    ids = []
    for up in ups:
        dest = save_upload(up)
        ids.append(enqueue(opts, source=str(dest), tmp=str(dest), name=up.filename, label=up.filename))
    return jsonify(ids)


@app.post("/api/submit-audio")
def submit_audio():
    f = request.form
    lines = [l.strip() for l in f.get("urls", "").splitlines() if l.strip()]
    if not lines:
        return jsonify(error="유튜브 링크를 붙여넣어 주세요"), 400
    bad = [l for l in lines if not l.lower().startswith(("http://", "https://"))]
    if bad:
        return jsonify(error="링크는 http:// 또는 https:// 로 시작해야 해요", bad=bad), 400
    fmt = f.get("fmt") if f.get("fmt") in audiodl.FORMATS else "m4a"
    try:
        kbps = int(f.get("kbps", "192"))
    except ValueError:
        kbps = 192
    opts = dict(kind="audio", fmt=fmt, kbps=kbps if kbps in audiodl.BITRATES else 192)
    return jsonify([enqueue(opts, source=l, label=l) for l in lines])


@app.post("/api/submit-ocr")
def submit_ocr():
    from PIL import Image
    ups = request.files.getlist("files")
    if not ups:
        return jsonify(error="사진이나 캡처 이미지를 올려 주세요"), 400
    bad = []
    for up in ups:
        try:
            Image.open(up.stream).verify()
        except Exception:
            bad.append(up.filename)
        finally:
            up.stream.seek(0)
    if bad:
        return jsonify(error="이미지로 읽을 수 없는 파일이 있어요", bad=bad), 400
    paths = [str(save_upload(up)) for up in ups]
    names = [up.filename for up in ups]
    if request.form.get("merge") == "1" or len(ups) == 1:        # 여러 장을 한 문서로
        return jsonify([enqueue(dict(kind="ocr"), source="", tmps=paths, names=names,
                                label=names[0] if len(names) == 1 else f"이미지 {len(names)}장")])
    return jsonify([enqueue(dict(kind="ocr"), source="", tmps=[pa], names=[nm], label=nm)
                    for pa, nm in zip(paths, names)])


def read_text_upload(up):
    raw = up.stream.read()
    up.stream.seek(0)
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("글자 인코딩을 읽을 수 없어요")


@app.post("/api/submit-md2pdf")
def submit_md2pdf():
    if not mdpdf.available():
        return jsonify(error="PDF로 인쇄할 브라우저(Microsoft Edge 또는 Chrome)를 찾지 못했어요"), 400
    f = request.form
    size = f.get("size") if f.get("size") in mdpdf.PAGE_SIZES else "a4"
    font = f.get("font") if f.get("font") in mdpdf.FONT_PT else "normal"
    opts = dict(kind="md2pdf", size=size, font=font, numbers=f.get("numbers") == "1")
    docs, bad = [], []
    for up in request.files.getlist("files"):
        if not up.filename.lower().endswith((".md", ".markdown", ".txt")):
            bad.append(up.filename)
            continue
        try:
            text = read_text_upload(up)
        except ValueError:
            bad.append(up.filename)
            continue
        docs.append((Path(up.filename).stem, up.filename, text))
    if bad:
        return jsonify(error="Markdown(.md)나 텍스트(.txt) 파일이 아니거나 읽을 수 없어요", bad=bad), 400
    pasted = f.get("text", "")
    if pasted.strip():
        docs.append((mdpdf.title_of(pasted, "붙여넣은 글"), "붙여넣은 글", pasted))
    if not docs:
        return jsonify(error="Markdown 파일을 올리거나 글을 붙여넣어 주세요"), 400
    if any(len(t) > 3_000_000 for _, _, t in docs):
        return jsonify(error="글이 너무 길어요 (300만 자 이하)"), 400
    ids = [enqueue(opts, source="", stem=stem, md_text=text, name=label, label=label) for stem, label, text in docs]
    return jsonify(ids)


def office_file_ok(up):
    """확장자와 파일 머리(OOXML=PK, 옛 형식=OLE)를 확인한다."""
    name = up.filename.lower()
    ext = Path(name).suffix
    if ext not in officeconv.SUFFIXES:
        return False
    head = up.stream.read(8)
    up.stream.seek(0)
    if ext in (".csv",):
        return True
    if ext == ".rtf":
        return head[:5] == b"{\\rtf"
    if ext in (".doc", ".ppt", ".pps", ".xls"):
        return head == bytes.fromhex("D0CF11E0A1B11AE1")
    return head[:4] == b"PK\x03\x04"              # docx·pptx·xlsx·odt·odp·ods 등 (ZIP 기반)


@app.post("/api/submit-office")
def submit_office():
    ups = request.files.getlist("files")
    if not ups:
        return jsonify(error="Word·PowerPoint·Excel 파일을 올려 주세요"), 400
    bad = [up.filename for up in ups if not office_file_ok(up)]
    if bad:
        return jsonify(error="지원하지 않는 파일이에요 (Word·PowerPoint·Excel만)", bad=bad), 400
    have = officeconv.office_available()
    missing = sorted({officeconv.APPS[officeconv.app_of(up.filename)][0] for up in ups if not have[officeconv.app_of(up.filename)]})
    if missing:
        return jsonify(error="이 PC에서 " + ", ".join(missing) + "을(를) 찾지 못했어요. Microsoft Office가 있어야 변환할 수 있어요"), 400
    f = request.form
    try:
        dpi = max(50, min(600, int(f.get("dpi", "150"))))
    except ValueError:
        dpi = 150
    opts = dict(kind="office", target="img" if f.get("target") == "img" else "pdf",
                fmt="jpg" if f.get("fmt") == "jpg" else "png", dpi=dpi)
    ids = []
    for up in ups:
        dest = save_upload(up)
        ids.append(enqueue(opts, source=str(dest), tmp=str(dest), name=up.filename, label=up.filename))
    return jsonify(ids)


@app.post("/api/submit-pdftool")
def submit_pdftool():
    ups = request.files.getlist("files")
    if not ups:
        return jsonify(error="PDF 파일을 올려 주세요"), 400
    bad = not_pdfs(ups)
    if bad:
        return jsonify(error="PDF 파일이 아니에요", bad=bad), 400
    f = request.form
    op = f.get("op")
    spec = f.get("spec", "").strip()
    try:
        if op == "merge":
            if len(ups) < 2:
                return jsonify(error="합치려면 PDF를 두 개 이상 올려 주세요"), 400
            paths = [str(save_upload(up)) for up in ups]       # 올린 순서가 이어붙이는 순서
            return jsonify([enqueue(dict(kind="pdftool", op="merge", pdfname=f.get("name", "").strip()),
                                    source="", tmps=paths, names=[up.filename for up in ups], label=f"PDF {len(ups)}개")])
        if op == "split":
            mode = f.get("mode") if f.get("mode") in ("each", "every", "ranges") else "each"
            every = max(1, min(1000, int(f.get("every", "1") or 1)))
            if mode == "ranges":
                pdftools.parse_groups(spec, 10 ** 6)
            opts = dict(kind="pdftool", op="split", mode=mode, every=every, spec=spec)
        elif op == "pick":
            if not spec:
                return jsonify(error="쪽 범위를 적어 주세요. 예: 1-3, 5"), 400
            pdftools.parse_pages(spec, 10 ** 6)
            opts = dict(kind="pdftool", op="pick", mode="delete" if f.get("mode") == "delete" else "extract", spec=spec)
        elif op == "rotate":
            angle = int(f.get("angle", "90"))
            if angle not in (90, 180, 270):
                return jsonify(error="회전 각도는 90, 180, 270 중에서 골라 주세요"), 400
            pdftools.parse_pages(spec, 10 ** 6)
            opts = dict(kind="pdftool", op="rotate", angle=angle, spec=spec)
        elif op == "compress":
            opts = dict(kind="pdftool", op="compress", level="strong" if f.get("level") == "strong" else "normal")
        else:
            return jsonify(error="알 수 없는 PDF 도구예요"), 400
    except ValueError as e:
        return jsonify(error=str(e)), 400
    ids = []
    for up in ups:
        dest = save_upload(up)
        ids.append(enqueue(opts, source=str(dest), tmp=str(dest), name=up.filename, label=up.filename))
    return jsonify(ids)


@app.post("/api/submit-qr")
def submit_qr():
    f = request.form
    lines = [l.strip() for l in f.get("text", "").splitlines() if l.strip()]
    if not lines:
        return jsonify(error="QR 코드로 만들 링크나 글을 적어 주세요"), 400
    if len(lines) > 200:
        return jsonify(error="한 번에 200개까지만 만들 수 있어요"), 400
    fmt = f.get("fmt") if f.get("fmt") in qrmake.FORMATS else "png"
    level = f.get("level") if f.get("level") in qrmake.LEVELS else "m"
    try:
        size = max(200, min(4000, int(f.get("size", "800"))))
    except ValueError:
        size = 800
    caption = f.get("caption", "").strip()[:120] if fmt == "png" else ""
    name = f.get("name", "").strip()[:80] if len(lines) == 1 else ""
    opts = dict(kind="qr", fmt=fmt, level=level, size=size, caption=caption, qname=name)
    return jsonify([enqueue(opts, source="", text=l, label=l[:60]) for l in lines])


@app.post("/api/retry/<jid>")
def retry(jid):
    local_only()
    j = jobs.get(jid)
    if not j or j["status"] != "error" or not j.get("source", "").lower().startswith(("http://", "https://")):
        abort(404)      # 올린 파일은 변환 후 지워지므로 링크만 다시 시도할 수 있다
    if j.get("kind") == "audio":
        opts = {k: j[k] for k in ("kind", "fmt", "kbps")}
    else:
        opts = {k: j[k] for k in ("model", "lang", "whisper", "summarize")}
    del jobs[jid]
    return jsonify(id=enqueue(opts, source=j["source"], label=j["label"]))


HIDDEN = {"md", "fpath", "dir", "tmp", "tmps", "names", "md_text", "stem", "text", "caption", "qname"}


@app.get("/api/jobs")
def list_jobs():
    out = []
    for i, j in jobs.items():
        d = {k: v for k, v in j.items() if k not in HIDDEN}
        d.update(id=i, has_md="md" in j)
        out.append(d)
    return jsonify(out)


@app.get("/api/md/<jid>")
def get_md(jid):
    j = jobs.get(jid)
    if not j or "md" not in j:
        abort(404)
    return Response(j["md"], mimetype="text/plain; charset=utf-8")


def zip_folder_bytes(folder):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:       # 이미지는 이미 압축돼 있어 묶기만 한다
        for f in sorted(Path(folder).iterdir()):
            if f.is_file():
                z.write(f, f.name)
    buf.seek(0)
    return buf


@app.get("/api/download/<jid>")
def download(jid):
    j = jobs.get(jid)
    if not j or j["status"] != "done":
        abort(404)
    if "md" in j:
        return send_file(io.BytesIO(j["md"].encode("utf-8")), as_attachment=True,
                         download_name=j["file"], mimetype="text/markdown")
    if j.get("fpath"):
        if not Path(j["fpath"]).is_file():
            abort(404)          # output 폴더에서 지운 파일
        inline = request.args.get("inline") == "1"          # PDF 는 새 탭에서 바로 열어 볼 수 있다
        return send_file(j["fpath"], as_attachment=not inline, download_name=j["file"],
                         mimetype=mimetypes.guess_type(j["file"])[0] or "application/octet-stream")
    if j.get("dir"):
        if not Path(j["dir"]).is_dir():
            abort(404)
        return send_file(zip_folder_bytes(j["dir"]), as_attachment=True, download_name=j["file"],
                         mimetype="application/zip")
    abort(404)


@app.get("/api/zip")
def zip_all():
    buf = io.BytesIO()
    used = set()

    def unique(name):
        base, k = name, 2
        while name in used:
            stem, dot, ext = base.rpartition(".")
            name = f"{stem} ({k}){dot}{ext}" if dot else f"{base} ({k})"
            k += 1
        used.add(name)
        return name

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for j in jobs.values():
            if j["status"] != "done":
                continue
            if "md" in j:
                z.writestr(unique(j["file"]), j["md"])
            elif j.get("fpath") and Path(j["fpath"]).is_file():
                z.write(j["fpath"], unique(j["file"]))
            elif j.get("dir") and Path(j["dir"]).is_dir():
                for f in sorted(Path(j["dir"]).iterdir()):
                    if f.is_file():
                        z.write(f, unique(f"{Path(j['dir']).name}/{f.name}"))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="to-md.zip")


@app.post("/api/clear")
def clear():
    for jid in [i for i, j in jobs.items() if j["status"] in ("done", "error")]:
        del jobs[jid]
    return jsonify(ok=True)


def local_only():
    """다른 웹사이트가 내 서버를 조작하지 못하게 출처를 확인한다."""
    origin = request.headers.get("Origin", "")
    if origin and not origin.startswith(("http://127.0.0.1", "http://localhost")):
        abort(403)


def out_info():
    return dict(outdir=str(OUT), default=str(settings.DEFAULT_OUT.resolve()),
                is_default=(OUT.resolve() == settings.DEFAULT_OUT.resolve()), warning=OUT_WARN)


@app.get("/api/info")
def info():
    return jsonify(out_info())


@app.post("/api/output-dir")
def set_output_dir():
    """결과 파일을 저장할 폴더를 바꾼다 (앞으로 하는 변환부터 적용). 이미 끝난 결과물은 그대로 둔다."""
    global OUT, OUT_WARN
    local_only()
    body = request.get_json(silent=True) or {}
    try:
        OUT = settings.set_output_dir(body.get("path"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    OUT_WARN = None
    return jsonify(out_info())


@app.post("/api/output-dir/reset")
def reset_output_dir():
    global OUT, OUT_WARN
    local_only()
    OUT = settings.reset_output_dir()
    OUT_WARN = None
    return jsonify(out_info())


_pick_lock = threading.Lock()


@app.post("/api/pick-folder")
def pick_folder():
    """이 PC 에서 폴더 선택 창을 띄운다. (서버가 내 PC 에서 돌기 때문에 가능하다)"""
    local_only()
    if not _pick_lock.acquire(blocking=False):
        return jsonify(error="이미 폴더 선택 창이 열려 있어요."), 409
    try:
        path = settings.pick_folder(initial=OUT)
    except Exception as e:
        return jsonify(error=str(e) or "폴더 선택 창을 열지 못했어요. 경로를 직접 입력해 주세요."), 500
    finally:
        _pick_lock.release()
    return jsonify(cancelled=True) if not path else jsonify(path=path)


@app.post("/api/open-folder")
def open_folder():
    local_only()
    if hasattr(os, "startfile"):
        os.startfile(OUT)                       # Windows 탐색기
    else:
        import subprocess, sys
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(OUT)])
    return jsonify(ok=True, outdir=str(OUT))


@app.post("/api/shutdown")
def shutdown():
    local_only()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify(ok=True)


@app.get("/")
def index():
    return send_file(Path(__file__).resolve().parent / "index.html", mimetype="text/html")


if __name__ == "__main__":
    print(f"http://127.0.0.1:{PORT}  (결과 파일은 converters\\output 에도 저장됩니다)")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
