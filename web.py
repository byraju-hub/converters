#!/usr/bin/env python
"""vod2md 웹 화면: 링크 붙여넣기 / 파일 드래그 앤 드롭 -> 일괄 변환 -> .md 미리보기·다운로드
실행: python web.py  → http://127.0.0.1:8765
"""
import io
import shutil
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from queue import Queue

from flask import Flask, jsonify, request, send_file, Response

import vod2md

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


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html; charset=utf-8")


PAGE = r"""<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>영상 → Markdown</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--mut:#6b6a66;--line:#e2e0da;--acc:#2f5d50}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,"Malgun Gothic",sans-serif}
main{max-width:820px;margin:0 auto;padding:32px 20px 80px}h1{font-size:22px;margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}
textarea{width:100%;height:84px;border:1px solid var(--line);border-radius:8px;padding:10px;font:inherit;resize:vertical}
#drop{border:2px dashed var(--line);border-radius:10px;padding:26px;text-align:center;color:var(--mut);cursor:pointer;margin-top:12px}
#drop.on{border-color:var(--acc);background:#eef4f1;color:var(--acc)}
.row{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-top:14px}
select,input[type=text]{border:1px solid var(--line);border-radius:6px;padding:6px 8px;font:inherit}
button{background:var(--acc);color:#fff;border:0;border-radius:8px;padding:9px 18px;font:inherit;cursor:pointer}
button.sec{background:#fff;color:var(--ink);border:1px solid var(--line);padding:5px 10px;font-size:13px}
button:disabled{opacity:.5}
.job{display:flex;gap:10px;align-items:center;padding:10px 0;border-top:1px solid var(--line)}
.job:first-child{border-top:0}.job .t{flex:1;min-width:0}.job .t b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.job small{color:var(--mut)}.st{font-size:12px;padding:2px 8px;border-radius:99px;background:#eee}
.st.done{background:#dcefe6;color:#1c5a42}.st.error{background:#f6dcdc;color:#8a2323}.st.running{background:#fdf0cf;color:#7a5a00}
pre{white-space:pre-wrap;background:#fafaf8;border:1px solid var(--line);border-radius:8px;padding:14px;max-height:420px;overflow:auto;margin:8px 0 0}
</style>
<main>
<h1>영상 → Markdown</h1>
<div class="card">
  <textarea id="urls" placeholder="유튜브 링크를 한 줄에 하나씩 붙여넣기"></textarea>
  <div id="drop">여기에 영상/오디오 파일을 끌어다 놓거나 클릭해서 선택<br><small id="picked"></small></div>
  <input id="file" type="file" multiple accept="video/*,audio/*" hidden>
  <div class="row">
    <label>모델 <select id="model"><option>tiny</option><option>base</option><option selected>small</option><option>medium</option><option>large-v3</option></select></label>
    <label>언어 <select id="lang"><option value="">자동</option><option value="ko">한국어</option><option value="en">English</option></select></label>
    <label><input type="checkbox" id="whisper"> 자막 무시, 음성인식</label>
    <label><input type="checkbox" id="summ"> Claude 요약·소제목</label>
  </div>
  <div class="row"><button id="go">변환 시작</button><button class="sec" id="zip">완료된 것 전체 ZIP</button></div>
</div>
<div class="card" id="jobs" hidden></div>
</main>
<script>
const $=id=>document.getElementById(id);let files=[];
const drop=$('drop'),fi=$('file');
function setFiles(l){files=[...files,...l];$('picked').textContent=files.map(f=>f.name).join(', ')}
drop.onclick=()=>fi.click();fi.onchange=()=>setFiles(fi.files);
['dragenter','dragover'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add('on')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('on')}));
drop.addEventListener('drop',x=>setFiles(x.dataTransfer.files));
$('go').onclick=async()=>{
  if(!$('urls').value.trim()&&!files.length)return;
  const fd=new FormData();fd.append('urls',$('urls').value);fd.append('model',$('model').value);fd.append('lang',$('lang').value);
  fd.append('whisper',$('whisper').checked?'1':'');fd.append('summarize',$('summ').checked?'1':'');
  files.forEach(f=>fd.append('files',f));
  $('go').disabled=true;$('go').textContent='업로드 중…';
  await fetch('/api/submit',{method:'POST',body:fd});
  $('urls').value='';files=[];$('picked').textContent='';fi.value='';
  $('go').disabled=false;$('go').textContent='변환 시작';poll();
};
$('zip').onclick=()=>location.href='/api/zip';
const label={queued:'대기',running:'변환 중',done:'완료',error:'실패'};
let open=null;
async function show(id){
  if(open===id){open=null;$('prev')?.remove();return}
  open=id;$('prev')?.remove();
  const t=await (await fetch('/api/md/'+id)).text();
  const p=document.createElement('pre');p.id='prev';p.textContent=t;$('jobs').appendChild(p);
}
async function poll(){
  const js=await (await fetch('/api/jobs')).json();
  const box=$('jobs');box.hidden=!js.length;
  const prev=$('prev');
  box.innerHTML=js.map(j=>`<div class="job"><div class="t"><b>${esc(j.title||j.label)}</b><small>${esc(j.log||'')}</small></div>
    <span class="st ${j.status}">${label[j.status]}</span>
    ${j.status=='done'?`<button class="sec" onclick="show('${j.id}')">미리보기</button><button class="sec" onclick="location.href='/api/download/${j.id}'">.md</button>`:''}</div>`).join('');
  if(prev&&open)box.appendChild(prev);
  if(js.some(j=>j.status=='queued'||j.status=='running'))setTimeout(poll,1500);
}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
poll();
</script></html>"""

if __name__ == "__main__":
    print("http://127.0.0.1:8765  (결과 파일은 vod-md\\output 에도 저장됩니다)")
    app.run(host="127.0.0.1", port=8765, threaded=True)
