#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""유튜브(및 yt-dlp 가 지원하는 주소) 영상에서 소리만 뽑아 오디오 파일로 저장합니다.

  m4a : 유튜브가 주는 소리를 그대로 저장 (다시 압축하지 않아 가장 빠르고 음질 손실 없음)
  mp3 : 어디서나 재생되는 MP3 로 바꿔 저장 (PyAV 에 들어 있는 인코더를 써서 ffmpeg 설치가 필요 없음)

사용법:
  python audiodl.py https://youtu.be/xxxx [--fmt m4a|mp3] [--kbps 192] [-d 결과폴더]
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import yt_dlp

from vod2md import log, safe_name, unique_path

FORMATS = ("m4a", "mp3")
BITRATES = (128, 192, 320)


def _progress_hook(cb):
    state = {"last": -1}

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                pct = int(d.get("downloaded_bytes", 0) * 100 / total)
                if pct != state["last"]:
                    state["last"] = pct
                    log(f"[오디오] 내려받는 중 {pct}%", cb)
    return hook


def transcode(src, dst, fmt, kbps=192, title=None, cb=None):
    """src 소리를 PyAV 로 읽어 mp3(libmp3lame) 또는 m4a(aac) 로 다시 저장한다."""
    import av
    codec = {"mp3": "libmp3lame", "m4a": "aac"}[fmt]
    with av.open(str(src)) as inp:
        in_stream = next((s for s in inp.streams if s.type == "audio"), None)
        if in_stream is None:
            raise ValueError("소리가 들어 있지 않은 파일이에요.")
        total = float(inp.duration or 0) / av.time_base if inp.duration else 0
        container_fmt = "mp3" if fmt == "mp3" else "ipod"       # ipod = m4a 용 MP4 컨테이너
        with av.open(str(dst), "w", format=container_fmt) as out:
            rate = in_stream.codec_context.sample_rate or 44100
            if fmt == "mp3" and rate not in (32000, 44100, 48000):
                rate = 44100                                   # MP3 가 받는 표준 샘플 속도
            out_stream = out.add_stream(codec, rate=rate)
            out_stream.bit_rate = kbps * 1000
            out_stream.layout = "stereo" if (in_stream.codec_context.channels or 2) > 1 else "mono"
            if title:
                out.metadata["title"] = title
            resampler = av.AudioResampler(format=out_stream.codec_context.format.name,
                                          layout=out_stream.layout.name, rate=rate)
            last = -1
            for frame in inp.decode(in_stream):
                for f in resampler.resample(frame):
                    for pkt in out_stream.encode(f):
                        out.mux(pkt)
                if total and frame.time is not None:
                    pct = min(99, int(frame.time * 100 / total))
                    if pct != last and pct % 5 == 0:
                        last = pct
                        log(f"[오디오] {fmt.upper()} 로 바꾸는 중 {pct}%", cb)
            for f in resampler.resample(None) or []:
                for pkt in out_stream.encode(f):
                    out.mux(pkt)
            for pkt in out_stream.encode(None):
                out.mux(pkt)


def download_audio(url, out_dir, fmt="m4a", kbps=192, cb=None):
    """링크의 소리를 out_dir 에 저장하고 (제목, 저장 경로)를 돌려준다."""
    if fmt not in FORMATS:
        raise ValueError("오디오 형식은 m4a 또는 mp3 만 돼요.")
    kbps = kbps if kbps in BITRATES else 192
    tmp = Path(tempfile.mkdtemp(prefix="audiodl_"))
    try:
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": str(tmp / "src.%(ext)s"),
                "progress_hooks": [_progress_hook(cb)]}
        log("[오디오] 영상 정보를 확인하는 중…", cb)
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
        title = info.get("title") or "audio"
        src = next(tmp.glob("src.*"), None)
        if src is None:
            raise ValueError("소리를 내려받지 못했어요.")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = unique_path(out_dir, safe_name(title), "." + fmt)
        if fmt == "m4a" and src.suffix.lower() == ".m4a":
            shutil.move(str(src), str(dest))                  # 이미 m4a: 그대로 저장
        else:
            log(f"[오디오] {fmt.upper()} 로 바꾸는 중…", cb)
            work = tmp / ("out." + fmt)
            transcode(src, work, fmt, kbps, title, cb)
            shutil.move(str(work), str(dest))
        return title, dest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="유튜브 영상 → 오디오 파일")
    ap.add_argument("url")
    ap.add_argument("--fmt", choices=FORMATS, default="m4a")
    ap.add_argument("--kbps", type=int, default=192, choices=BITRATES)
    ap.add_argument("-d", "--dir", default="output")
    a = ap.parse_args()
    try:
        title, path = download_audio(a.url, a.dir, a.fmt, a.kbps)
    except Exception as e:
        print(f"실패: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
