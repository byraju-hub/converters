#!/usr/bin/env python
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
import vod2md

PORT = int(os.environ.get("VOD_PORT", "8765"))
app = Flask(__name__)
OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)
UPLOADS = Path(tempfile.mkdtemp(prefix="vod2md_up_"))

jobs = {}              # id -> dict
q = Queue()


def worker():
    while True:
        jid = q.get()
        j = jobs[jid]
        try:
            j["status"] = "running"
            def cb(msg):
                j["log"] = msg
            if j.get("kind") == "pdf":
                title, md = pdf2md.convert_pdf(j["source"], local_name=j.get("name"),
                                               page_marks=j.get("page_marks", True), cb=cb)
            else:
                title, md = vod2md.convert(j["source"], j["model"], j["lang"], j["whisper"],
                                           j["summarize"], cb=cb, local_name=j.get("name"))
            path = vod2md.unique_path(OUT, title)
            path.write_text(md, encoding="utf-8")
            j.update(status="done", title=title, file=path.name, md=md, log="완료")
        except Exception as e:
            j.update(status="error", log=re.sub(r"\x1b\[[0-9;]*m", "", str(e)).strip())
        finally:
            try:
                if j.get("tmp"):
                    Path(j["tmp"]).unlink(missing_ok=True)
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


@app.post("/api/submit-pdf")
def submit_pdf():
    ups = request.files.getlist("files")
    if not ups:
        return jsonify(error="PDF 파일을 올려 주세요"), 400
    bad = []
    for up in ups:       # 확장자와 파일 머리(%PDF-)를 둘 다 확인한다
        head = up.stream.read(5)
        up.stream.seek(0)
        if not up.filename.lower().endswith(".pdf") or head != b"%PDF-":
            bad.append(up.filename)
    if bad:
        return jsonify(error="PDF 파일이 아니에요", bad=bad), 400
    opts = dict(kind="pdf", page_marks=request.form.get("page_marks") != "0")
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
    if not j or j["status"] != "error" or not j["source"].lower().startswith(("http://", "https://")):
        abort(404)      # 올린 파일은 변환 후 지워지므로 링크만 다시 시도할 수 있다
    opts = {k: j[k] for k in ("model", "lang", "whisper", "summarize")}
    del jobs[jid]
    return jsonify(id=enqueue(opts, source=j["source"], label=j["label"]))


@app.get("/api/jobs")
def list_jobs():
    return jsonify([{k: v for k, v in dict(j, id=i).items() if k != "md"} for i, j in jobs.items()])


@app.get("/api/md/<jid>")
def get_md(jid):
    return Response(jobs[jid]["md"], mimetype="text/plain; charset=utf-8")


@app.get("/api/download/<jid>")
def download(jid):
    j = jobs[jid]
    return send_file(io.BytesIO(j["md"].encode("utf-8")), as_attachment=True,
                     download_name=j["file"], mimetype="text/markdown")


@app.get("/api/zip")
def zip_all():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for j in jobs.values():
            if j["status"] == "done":
                z.writestr(j["file"], j["md"])
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="vod-md.zip")


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
