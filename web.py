#!/usr/bin/env python
"""vod2md 웹 화면: 링크 붙여넣기 / 파일 드래그 앤 드롭 -> 일괄 변환 -> .md 미리보기·다운로드
실행: python web.py  → http://127.0.0.1:8765
"""
import io
import os
import shutil
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from queue import Queue

from flask import Flask, abort, jsonify, request, send_file, Response

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
            title, md = vod2md.convert(j["source"], j["model"], j["lang"], j["whisper"],
                                       j["summarize"], cb=cb, local_name=j.get("name"))
            path = vod2md.unique_path(OUT, title)
            path.write_text(md, encoding="utf-8")
            j.update(status="done", title=title, file=path.name, md=md, log="완료")
        except Exception as e:
            j.update(status="error", log=str(e))
        finally:
            if j.get("tmp"):
                Path(j["tmp"]).unlink(missing_ok=True)
            q.task_done()


threading.Thread(target=worker, daemon=True).start()


@app.post("/api/submit")
def submit():
    f = request.form
    opts = dict(model=f.get("model", "small"), lang=f.get("lang") or None,
                whisper=f.get("whisper") == "1", summarize=f.get("summarize") == "1")
    ids = []

    def add(**kw):
        jid = uuid.uuid4().hex[:8]
        jobs[jid] = dict(status="queued", log="대기 중", **opts, **kw)
        q.put(jid)
        ids.append(jid)

    for line in f.get("urls", "").splitlines():
        line = line.strip()
        if line:
            add(source=line, label=line)
    for up in request.files.getlist("files"):
        dest = UPLOADS / f"{uuid.uuid4().hex}_{Path(up.filename).name}"
        up.save(dest)
        add(source=str(dest), tmp=str(dest), name=up.filename, label=up.filename)
    return jsonify(ids)


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


@app.post("/api/shutdown")
def shutdown():
    origin = request.headers.get("Origin", "")
    if origin and not origin.startswith(("http://127.0.0.1", "http://localhost")):
        abort(403)          # 다른 웹사이트가 내 서버를 끄지 못하게
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify(ok=True)


@app.get("/")
def index():
    return send_file(Path(__file__).resolve().parent / "index.html", mimetype="text/html")


if __name__ == "__main__":
    print(f"http://127.0.0.1:{PORT}  (결과 파일은 vod-md\\output 에도 저장됩니다)")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
