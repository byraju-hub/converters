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

import pdf2md
import pdftools
import vod2md

PORT = int(os.environ.get("VOD_PORT", "8765"))
app = Flask(__name__)
OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)
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
                 meta=f"{len(j['names'])}장 · {human(path.stat().st_size)}", log="완료")
    elif kind == "pdf2img":
        folder = vod2md.unique_path(OUT, Path(j["name"]).stem + " 이미지", "")
        files = pdftools.pdf_to_images(j["source"], folder, j.get("fmt", "png"), j.get("dpi", 150),
                                       j.get("pages", ""), stem=Path(j["name"]).stem, cb=cb)
        total = sum(f.stat().st_size for f in files)
        j.update(status="done", title=folder.name, file=folder.name + ".zip", dir=str(folder), ext="zip",
                 meta=f"{len(files)}장 · {j.get('fmt', 'png').upper()} {j.get('dpi', 150)}dpi · {human(total)}", log="완료")
    elif kind == "pdf":
        title, md = pdf2md.convert_pdf(j["source"], local_name=j.get("name"),
                                       page_marks=j.get("page_marks", True), ocr=j.get("ocr", True), cb=cb)
        save_md(j, title, md)
    else:
        title, md = vod2md.convert(j["source"], j["model"], j["lang"], j["whisper"],
                                   j["summarize"], cb=cb, local_name=j.get("name"))
        save_md(j, title, md)


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


@app.post("/api/retry/<jid>")
def retry(jid):
    local_only()
    j = jobs.get(jid)
    if not j or j["status"] != "error" or not j.get("source", "").lower().startswith(("http://", "https://")):
        abort(404)      # 올린 파일은 변환 후 지워지므로 링크만 다시 시도할 수 있다
    opts = {k: j[k] for k in ("model", "lang", "whisper", "summarize")}
    del jobs[jid]
    return jsonify(id=enqueue(opts, source=j["source"], label=j["label"]))


HIDDEN = {"md", "fpath", "dir", "tmp", "tmps", "names"}


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
        return send_file(j["fpath"], as_attachment=not inline, download_name=j["file"], mimetype="application/pdf")
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


@app.get("/api/info")
def info():
    return jsonify(outdir=str(OUT))


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
    print(f"http://127.0.0.1:{PORT}  (결과 파일은 vod-md\\output 에도 저장됩니다)")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
