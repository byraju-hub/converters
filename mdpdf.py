#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""Markdown 글을 인쇄하기 좋은 PDF 로 만듭니다.

Markdown -> HTML(markdown 패키지) -> 이 PC 의 Microsoft Edge(없으면 Chrome)로 PDF 인쇄.
브라우저는 따로 설치할 필요 없이 Windows 10/11 에 들어 있는 Edge 를 씁니다.
글 속에 스크립트·바깥 주소가 있어도 실행·접속하지 못하게 막고 인쇄합니다.

사용법:
  python mdpdf.py 설교문.md [--size a4|b5] [--font 11] [--numbers] [-d 결과폴더]
"""
import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from vod2md import log, safe_name, unique_path

PRINT_TIMEOUT = 90
PAGE_SIZES = {"a4": "A4", "b5": "B5"}
FONT_PT = {"small": 10.5, "normal": 12, "large": 14}

CSS = """
@page { size: %(size)s; margin: 20mm 18mm 22mm; %(numbers)s }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
       font-size: %(pt)spt; line-height: 1.75; color: #1b1f1d; word-break: keep-all; overflow-wrap: break-word; }
h1, h2, h3, h4 { line-height: 1.35; margin: 1.5em 0 .5em; break-after: avoid; }
h1 { font-size: 1.7em; border-bottom: 2px solid #0c7d68; padding-bottom: .25em; margin-top: 0; }
h2 { font-size: 1.35em; color: #0a5f4f; }
h3 { font-size: 1.15em; }
p { margin: .7em 0; }
ul, ol { padding-left: 1.5em; }
li { margin: .25em 0; }
blockquote { margin: 1em 0; padding: .1em 1em; border-left: 4px solid #8fd3c3; background: #f1faf7; color: #34423d; }
code { font-family: "D2Coding", Consolas, "Malgun Gothic", monospace; font-size: .9em; background: #eef3f1; padding: .1em .35em; border-radius: 4px; }
pre { background: #f2f5f4; padding: .8em 1em; border-radius: 8px; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%%; margin: 1em 0; font-size: .95em; }
th, td { border: 1px solid #c9d6d1; padding: .4em .7em; text-align: left; vertical-align: top; }
th { background: #e5f3ee; }
tr { break-inside: avoid; }
hr { border: 0; border-top: 1px solid #c9d6d1; margin: 1.6em 0; }
a { color: #0a5f4f; text-decoration: none; }
img { max-width: 100%%; }
img[src^="http"] { display: none; }
"""

PAGE_NUMBERS_CSS = '@bottom-center { content: counter(page) " / " counter(pages); font-size: 9pt; color: #6b7a74; }'


def find_browser():
    """PDF 인쇄에 쓸 Edge 또는 Chrome 실행 파일 경로 (없으면 None)."""
    cands = []
    if sys.platform == "win32":
        for env in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
            base = os.environ.get(env)
            if base:
                cands += [Path(base) / "Microsoft/Edge/Application/msedge.exe",
                          Path(base) / "Google/Chrome/Application/chrome.exe"]
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            cands.append(Path(p))
    if sys.platform == "darwin":
        cands += [Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                  Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    return next((c for c in cands if c.is_file()), None)


def available():
    try:
        import markdown  # noqa: F401
    except ImportError:
        return False
    return find_browser() is not None


def title_of(md, fallback="문서"):
    """글의 첫 제목(# ...)을 이름으로 쓴다."""
    m = re.search(r"^\s{0,3}#{1,3}\s+(.+?)\s*#*\s*$", md, re.M)
    return (m.group(1).strip() if m else fallback)


def to_html(md, size="a4", font="normal", numbers=False, title="문서"):
    try:
        import markdown
    except ImportError:
        raise ValueError("Markdown 변환 도구가 설치되지 않았어요. update.bat 을 실행하거나 'pip install -r requirements.txt'를 실행해 주세요.")
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"], output_format="html5")
    css = CSS % dict(size=PAGE_SIZES.get(size, "A4"), pt=FONT_PT.get(font, 12),
                     numbers=PAGE_NUMBERS_CSS if numbers else "")
    # 글에 들어 있을 수 있는 스크립트·바깥 주소 접속을 막는다 (그림은 PC 안의 파일·data 만)
    csp = "default-src 'none'; style-src 'unsafe-inline'; img-src data: file:"
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
            f'<title>{html.escape(title)}</title><style>{css}</style></head><body>{body}</body></html>')


def md_to_pdf(md, out_path, title=None, size="a4", font="normal", numbers=False, cb=None):
    """Markdown 글자(md)를 PDF 파일(out_path)로 만든다."""
    browser = find_browser()
    if not browser:
        raise ValueError("PDF로 인쇄할 브라우저(Microsoft Edge 또는 Chrome)를 찾지 못했어요.")
    if not md.strip():
        raise ValueError("내용이 비어 있어요.")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="mdpdf_"))
    try:
        page = tmp / "doc.html"
        page.write_text(to_html(md, size, font, numbers, title or title_of(md)), encoding="utf-8")
        pdf = tmp / "doc.pdf"
        log("[PDF] 브라우저로 인쇄하는 중…", cb)
        cmd = [str(browser), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
               "--disable-extensions", f"--user-data-dir={tmp / 'profile'}", f"--print-to-pdf={pdf}",
               page.as_uri()]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=PRINT_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise ValueError("PDF 인쇄가 너무 오래 걸려 중단했어요. 브라우저가 열려 있다면 닫고 다시 시도해 주세요.")
        if not pdf.is_file() or pdf.stat().st_size == 0:
            tail = (r.stderr or b"").decode("utf-8", "ignore").strip().splitlines()
            raise ValueError("PDF를 만들지 못했어요" + (f": {tail[-1][:140]}" if tail else ""))
        out_path.unlink(missing_ok=True)
        shutil.move(str(pdf), str(out_path))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Markdown -> PDF")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--size", choices=list(PAGE_SIZES), default="a4")
    ap.add_argument("--font", choices=list(FONT_PT), default="normal")
    ap.add_argument("--numbers", action="store_true", help="쪽 번호를 넣는다")
    ap.add_argument("-d", "--dir", default="output")
    a = ap.parse_args()
    for f in a.files:
        p = Path(f)
        md = p.read_text(encoding="utf-8-sig")
        out = unique_path(Path(a.dir), p.stem, ".pdf")
        try:
            md_to_pdf(md, out, title_of(md, p.stem), a.size, a.font, a.numbers)
            print(f"저장: {out}")
        except ValueError as e:
            print(f"실패({p.name}): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
