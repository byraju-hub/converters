#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""영상(유튜브 링크 / 로컬 파일) -> Markdown 변환기

사용법:
  python vod2md.py URL_또는_파일 [URL_또는_파일 ...]     # 여러 개 한꺼번에 가능
  python vod2md.py --list 목록.txt                       # 한 줄에 하나씩 적힌 목록 파일
  python vod2md.py URL --whisper                         # 자막 무시하고 음성인식 강제
  python vod2md.py FILE -m medium -l ko -d 결과폴더      # 모델/언어/출력 폴더
  python vod2md.py URL --summarize                       # Claude 요약 + 소제목 (ANTHROPIC_API_KEY 필요)
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import yt_dlp

HERE = Path(__file__).resolve().parent
PARA_GAP = 2.0        # 이 초 이상 쉬면 새 문단
PARA_MAX = 60.0       # 문단 최대 길이(초)
URL_RE = re.compile(r"^https?://", re.I)
SUMMARY_MODEL = "claude-sonnet-5-5"


def log(msg, cb=None):
    print(msg, file=sys.stderr, flush=True)
    if cb:
        cb(msg)


def ts(sec: float) -> str:
    t = int(sec)
    return str(timedelta(seconds=t)) if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", s).strip()[:100] or "video"


def load_api_key():
    """환경변수 또는 프로젝트 폴더의 .env 에서 ANTHROPIC_API_KEY 를 찾는다."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env = HERE / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*ANTHROPIC_API_KEY\s*=\s*(.+)", line)
            if m:
                return m.group(1).strip().strip("\"'")
    return None


# ---------- 유튜브 자막 ----------
def captions_from_info(info, langs):
    import urllib.request

    for pool, kind in ((info.get("subtitles") or {}, "수동자막"),
                       (info.get("automatic_captions") or {}, "자동자막")):
        for lang in langs:
            for k in [k for k in pool if k == lang or k.startswith(lang + "-")]:
                for f in pool[k]:
                    if f.get("ext") == "json3":
                        with urllib.request.urlopen(f["url"]) as r:
                            data = json.load(r)
                        segs = []
                        for ev in data.get("events", []):
                            text = "".join(s.get("utf8", "") for s in ev.get("segs", []) if s.get("utf8"))
                            text = text.replace("\n", " ").strip()
                            if text:
                                start = ev["tStartMs"] / 1000
                                segs.append((start, start + ev.get("dDurationMs", 0) / 1000, text))
                        if segs:
                            return segs, f"유튜브 {kind} ({k})"
    return None, None


# ---------- 음성인식 ----------
_models = {}


def transcribe(path: Path, model_name: str, lang, cb=None):
    from faster_whisper import WhisperModel

    if model_name not in _models:
        log(f"[whisper] 모델 로드: {model_name} (CPU) — 처음엔 다운로드가 있습니다", cb)
        _models[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    gen, info = _models[model_name].transcribe(str(path), language=lang, vad_filter=True, beam_size=5)
    total = info.duration or 1
    segs, last_pct = [], -10
    for s in gen:
        segs.append((s.start, s.end, s.text.strip()))
        pct = int(s.end / total * 100)
        if pct >= last_pct + 5:
            last_pct = pct
            log(f"[whisper] {pct}%", cb)
    return segs, f"Whisper {model_name} (언어: {info.language})", info.duration


# ---------- Claude 요약/소제목 ----------
def summarize(title, paras, cb=None):
    """paras: [(start_sec, text)] -> {'summary', 'points', 'sections':[{'start','heading'}]}"""
    key = load_api_key()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY 가 없습니다 (환경변수 또는 vod-md\\.env 파일)")
    import anthropic

    log("[claude] 요약/소제목 생성 중...", cb)
    body = "\n".join(f"[{int(s)}] {t}" for s, t in paras)[:400_000]
    prompt = (
        f"아래는 영상 '{title}' 의 스크립트입니다. 각 줄 앞의 [숫자]는 시작 시각(초)입니다.\n"
        "스크립트 언어와 같은 언어로, 다음 JSON 만 출력하세요(코드펜스 금지):\n"
        '{"summary": "3~5문장 요약", "points": ["핵심 포인트", ...(3~8개)], '
        '"sections": [{"start": 초(스크립트에 있는 값), "heading": "소제목"}, ...]}\n'
        "sections 는 내용 흐름이 바뀌는 지점마다 하나씩, 시간순으로 만드세요. "
        "내용을 지어내지 말고 스크립트에 있는 것만 사용하세요.\n\n" + body
    )
    msg = anthropic.Anthropic(api_key=key).messages.create(
        model=SUMMARY_MODEL, max_tokens=4000, messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


# ---------- Markdown ----------
def to_paragraphs(segs):
    paras, cur, p_start, last_end = [], [], None, None
    for start, end, text in segs:
        if cur and (start - last_end >= PARA_GAP or start - p_start >= PARA_MAX):
            paras.append((p_start, " ".join(cur)))
            cur = []
        if not cur:
            p_start = start
        cur.append(text)
        last_end = end
    if cur:
        paras.append((p_start, " ".join(cur)))
    return paras


def build_md(title, source, method, duration, segs, link_base=None, ai=None):
    paras = to_paragraphs(segs)
    lines = [f"# {title}", "", f"- 출처: {source}"]
    if duration:
        lines.append(f"- 길이: {ts(duration)}")
    lines.append(f"- 변환 방식: {method}" + (" + Claude 요약" if ai else ""))
    if ai:
        lines += ["", "## 요약", "", ai.get("summary", ""), "", "### 핵심 포인트", ""]
        lines += [f"- {p}" for p in ai.get("points", [])]
    lines += ["", "## 스크립트", ""]

    headings = sorted(ai.get("sections", []), key=lambda x: x["start"]) if ai else []
    hi = 0
    for start, text in paras:
        # 이 문단 시작 이전(포함)에 걸린 소제목 중 마지막 것을 이 문단 앞에 삽입
        pending = None
        while hi < len(headings) and headings[hi]["start"] <= start + 1:
            pending = headings[hi]["heading"]
            hi += 1
        if pending:
            lines += [f"### {pending}", ""]
        stamp = f"[{ts(start)}]({link_base}&t={int(start)}s)" if link_base else f"`{ts(start)}`"
        lines += [f"{stamp} {text}", ""]
    return "\n".join(lines)


# ---------- 한 건 변환 ----------
def convert(source, model="small", lang=None, force_whisper=False, do_summary=False,
            cb=None, local_name=None):
    """source: URL 또는 파일경로. 반환: (제목, markdown)"""
    langs = [lang] if lang else ["ko", "en"]
    link = None
    if URL_RE.match(source):
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(source, download=False)
        title = info.get("title", "video")
        duration = info.get("duration")
        link = info.get("webpage_url") or source
        segs = method = None
        if not force_whisper:
            segs, method = captions_from_info(info, langs)
            if segs:
                log(f"[자막] {method} 사용", cb)
        if not segs:
            log("[자막 없음/무시] 오디오를 받아 음성인식합니다", cb)
            tmp = Path(tempfile.mkdtemp(prefix="vod2md_"))
            try:
                o = dict(opts, format="bestaudio[ext=m4a]/bestaudio", outtmpl=str(tmp / "audio.%(ext)s"))
                with yt_dlp.YoutubeDL(o) as y:
                    y.download([source])
                segs, method, dur = transcribe(next(tmp.glob("audio.*")), model, lang, cb)
                duration = duration or dur
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        src_label = source
    else:
        p = Path(source)
        if not p.is_file():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")
        title = Path(local_name).stem if local_name else p.stem
        segs, method, duration = transcribe(p, model, lang, cb)
        src_label = local_name or str(p.resolve())

    ai = None
    if do_summary and segs:
        try:
            ai = summarize(title, to_paragraphs(segs), cb)
        except Exception as e:  # 요약 실패해도 스크립트는 살린다
            log(f"[claude] 요약 실패(스크립트만 저장): {e}", cb)
    return title, build_md(title, src_label, method, duration, segs, link_base=link, ai=ai)


def unique_path(d: Path, name: str, ext: str = ".md") -> Path:
    """d 안에서 겹치지 않는 경로를 돌려준다. ext="" 이면 폴더 이름용."""
    p = d / (safe_name(name) + ext)
    i = 2
    while p.exists():
        p = d / f"{safe_name(name)} ({i}){ext}"
        i += 1
    return p


def main():
    ap = argparse.ArgumentParser(description="영상 -> Markdown (여러 개 가능)")
    ap.add_argument("sources", nargs="*", help="유튜브 URL 또는 로컬 파일 (여러 개 가능)")
    ap.add_argument("--list", help="한 줄에 하나씩 URL/경로가 적힌 텍스트 파일")
    ap.add_argument("-d", "--outdir", default=".", help="출력 폴더 (기본: 현재 폴더)")
    ap.add_argument("-m", "--model", default="small", help="tiny/base/small/medium/large-v3 (기본 small)")
    ap.add_argument("-l", "--lang", default=None, help="언어 코드 (ko, en ...). 기본: 자동")
    ap.add_argument("--whisper", action="store_true", help="유튜브 자막 대신 음성인식 강제")
    ap.add_argument("--summarize", action="store_true", help="Claude 로 요약 + 소제목 추가")
    a = ap.parse_args()

    items = list(a.sources)
    if a.list:
        items += [l.strip() for l in Path(a.list).read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")]
    if not items:
        ap.error("변환할 URL/파일이 없습니다")

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for n, src in enumerate(items, 1):
        log(f"\n=== [{n}/{len(items)}] {src}")
        try:
            title, md = convert(src, a.model, a.lang, a.whisper, a.summarize)
            out = unique_path(outdir, title)
            out.write_text(md, encoding="utf-8")
            print(f"완료: {out.resolve()}")
            ok += 1
        except Exception as e:
            log(f"실패: {e}")
            fail += 1
    print(f"\n성공 {ok} / 실패 {fail}")
    sys.exit(1 if fail and not ok else 0)


if __name__ == "__main__":
    main()
