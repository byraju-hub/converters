#!/usr/bin/env python
"""PDF -> Markdown 변환기 (제목·목록·표 구조를 살립니다)

사용법:
  python pdf2md.py 문서.pdf [문서2.pdf ...] [-d 결과폴더] [--no-page-marks]
"""
import argparse
import re
import sys
from pathlib import Path

from vod2md import log, safe_name, unique_path

MIN_CHARS_PER_PAGE = 20     # 이보다 적으면 글자가 없는 스캔본으로 본다


def convert_pdf(path, local_name=None, page_marks=True, cb=None):
    """PDF 한 건 -> (제목, markdown)"""
    import pymupdf
    import pymupdf4llm

    pymupdf4llm.use_layout(False)       # 표·줄바꿈이 더 정확하고 가벼운 엔진
    doc = pymupdf.open(str(path))
    try:                                # 파일을 꼭 닫는다 (Windows 에서는 열려 있으면 지울 수 없다)
        if doc.needs_pass:
            raise ValueError("암호가 걸린 PDF예요. 암호를 해제한 뒤 다시 올려 주세요.")
        n = len(doc)
        if n == 0:
            raise ValueError("페이지가 없는 PDF예요.")

        pages, last = [], -10
        for i in range(n):
            md = pymupdf4llm.to_markdown(doc, pages=[i], show_progress=False)
            pages.append(md.strip())
            pct = int((i + 1) / n * 100)
            if pct >= last + 5 or i == n - 1:
                last = pct
                log(f"[pdf] {pct}% ({i + 1}/{n}쪽)", cb)
    finally:
        doc.close()

    total = sum(len(re.sub(r"[\s#*|\-_>`]", "", p)) for p in pages)
    if total < MIN_CHARS_PER_PAGE * n:
        raise ValueError("글자를 찾지 못했어요. 스캔한 이미지 PDF라면 글자 인식(OCR)이 필요한데, 아직 지원하지 않아요.")

    # PDF 내부 제목 정보는 "Microsoft Word - 문서1" 같은 값이 많아 파일 이름을 제목으로 쓴다
    title = Path(local_name).stem if local_name else Path(path).stem

    lines = [f"# {title}", "", f"- 원본 파일: {local_name or Path(path).name}", f"- 페이지: {n}쪽",
             "- 변환 방식: PDF 텍스트 추출 (pymupdf4llm)", ""]
    for i, body in enumerate(pages, 1):
        if page_marks:
            lines += ["---", "", f"*{i}쪽*", ""]
        lines += [body, ""]
    return title, tidy("\n".join(lines))



def tidy(md):
    """변환 엔진이 붙여 놓은 블록을 보기 좋게 정리한다 (제목·표 앞뒤 빈 줄, 줄바꿈 유지)."""
    md = re.sub(r"^(#{1,6})\s*\*\*(.+?)\*\*\s*$", r"\1 \2", md, flags=re.M)   # 제목 안의 굵게 표시 제거
    out, prev = [], ""
    for line in md.split("\n"):
        cur, p = line.strip(), prev.strip()
        if cur and p:
            both_table = cur.startswith("|") and p.startswith("|")
            both_list = bool(re.match(r"^\s*([-*+]|\d+[.)])\s", cur)) and bool(re.match(r"^\s*([-*+]|\d+[.)])\s", p))
            if not both_table and not both_list:
                out.append("")      # 서로 다른 블록: 사이에 빈 줄 (엔진은 줄 단위 블록을 붙여 출력한다)
        out.append(line)
        prev = line
    md = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", md).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="PDF -> Markdown")
    ap.add_argument("pdfs", nargs="+", help="PDF 파일 (여러 개 가능)")
    ap.add_argument("-d", "--outdir", default=".", help="출력 폴더 (기본: 현재 폴더)")
    ap.add_argument("--no-page-marks", action="store_true", help="쪽 구분선을 넣지 않음")
    a = ap.parse_args()

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for n, src in enumerate(a.pdfs, 1):
        log(f"\n=== [{n}/{len(a.pdfs)}] {src}")
        try:
            title, md = convert_pdf(src, page_marks=not a.no_page_marks)
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
