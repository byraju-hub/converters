#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""PDF -> Markdown 변환기 (제목·목록·표 구조를 살립니다)

글자가 들어 있는 쪽은 텍스트를 그대로 뽑고, 글자 없이 이미지뿐인(스캔한) 쪽은
한국어 글자 인식(OCR, RapidOCR)으로 읽습니다. 한 문서에 두 종류가 섞여 있어도 됩니다.

사용법:
  python pdf2md.py 문서.pdf [문서2.pdf ...] [-d 결과폴더] [--no-page-marks] [--no-ocr]
"""
import argparse
import re
import sys
from pathlib import Path

from vod2md import log, unique_path

MIN_CHARS_PER_PAGE = 20     # 이보다 적게 뽑히는 쪽은 글자가 없는 쪽으로 본다
OCR_DPI = 250               # 스캔 쪽을 이 해상도로 그려서 읽는다
OCR_MIN_SCORE = 0.4         # 인식 확신도가 이보다 낮은 조각은 버린다

_ocr = None


def get_ocr(cb=None):
    """글자 인식 엔진 (처음 한 번만 불러온다. 한국어 모델 약 13MB 는 자동으로 내려받는다)."""
    global _ocr
    if _ocr is None:
        try:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        except ImportError:
            raise ValueError("글자 인식 도구가 설치되지 않았어요. 'pip install -r requirements.txt'를 실행해 주세요.")
        log("[ocr] 한국어 글자 인식 모델을 불러오는 중… (처음 한 번은 내려받아요)", cb)
        _ocr = RapidOCR(params={"Rec.lang_type": LangRec.KOREAN, "Rec.ocr_version": OCRVersion.PPOCRV5,
                                "Rec.model_type": ModelType.MOBILE, "Global.log_level": "error"})
    return _ocr


def ocr_page(page, cb=None):
    """스캔한 쪽 하나를 글자로 읽어 문단 단위 텍스트로 돌려준다."""
    engine = get_ocr(cb)
    png = page.get_pixmap(dpi=OCR_DPI, alpha=False).tobytes("png")
    res = engine(png)
    if res.txts is None or len(res.txts) == 0:
        return ""
    boxes = [] if res.boxes is None else res.boxes
    items = []
    for box, txt, score in zip(boxes, res.txts, res.scores):
        if score < OCR_MIN_SCORE or not txt.strip():
            continue
        ys, xs = [p[1] for p in box], [p[0] for p in box]
        items.append({"top": min(ys), "bot": max(ys), "left": min(xs), "right": max(xs), "text": txt.strip()})
    if not items:
        return ""

    # 1) 같은 높이에 있는 조각을 한 줄로 묶는다
    items.sort(key=lambda t: (t["top"] + t["bot"]) / 2)
    lines = []
    for it in items:
        mid = (it["top"] + it["bot"]) / 2
        if lines and lines[-1]["top"] <= mid <= lines[-1]["bot"]:
            ln = lines[-1]
            ln["parts"].append(it)
            ln["top"], ln["bot"] = min(ln["top"], it["top"]), max(ln["bot"], it["bot"])
        else:
            lines.append({"top": it["top"], "bot": it["bot"], "parts": [it]})
    for ln in lines:
        ln["parts"].sort(key=lambda t: t["left"])
        ln["text"] = " ".join(p["text"] for p in ln["parts"])
        ln["right"] = max(p["right"] for p in ln["parts"])

    # 2) 줄을 문단으로 묶는다: 간격이 크거나, 앞 줄이 짧게 끝났거나, 문장·목록이 끝나면 새 문단
    heights = sorted(ln["bot"] - ln["top"] for ln in lines)
    med = heights[len(heights) // 2] or 1
    page_right = max(ln["right"] for ln in lines)
    list_start = re.compile(r"^\s*([-•·ㆍ※*]|\d+[.)]|[①-⑩]|[가-하][.)])\s*")
    ends_sentence = re.compile(r"[.?!。]['\")]?\s*$")
    def is_heading(ln):     # 다른 줄보다 눈에 띄게 크고 짧은 한 줄 = 제목
        return (ln["bot"] - ln["top"]) >= 1.25 * med and len(ln["text"]) <= 40

    paras, cur = [], []
    for k, ln in enumerate(lines):
        head = is_heading(ln)
        if cur:
            prev = lines[k - 1]
            new_para = (head or is_heading(prev)
                        or ln["top"] - prev["bot"] > 0.5 * med
                        or prev["right"] < 0.82 * page_right
                        or bool(ends_sentence.search(prev["text"]))
                        or bool(list_start.match(ln["text"])))
            if new_para:
                paras.append(" ".join(cur))
                cur = []
        cur.append(("## " + ln["text"]) if head else ln["text"])
    if cur:
        paras.append(" ".join(cur))
    text = "\n\n".join(paras)
    # 글자 인식이 문장 끝 마침표 뒤의 공백을 빼먹는 일이 잦다: "습니다.제자들은" -> "습니다. 제자들은"
    return re.sub(r"(?<=[.?!])(?=[가-힣])", " ", text)


def plain_len(md):
    return len(re.sub(r"[\s#*|\-_>`]", "", md))


def convert_pdf(path, local_name=None, page_marks=True, ocr=True, cb=None):
    """PDF 한 건 -> (제목, markdown)"""
    import pymupdf
    import pymupdf4llm

    pymupdf4llm.use_layout(False)       # 표·줄바꿈이 더 정확하고 가벼운 엔진
    doc = pymupdf.open(str(path))
    ocr_pages, skipped_scans = [], 0
    try:                                # 파일을 꼭 닫는다 (Windows 에서는 열려 있으면 지울 수 없다)
        if doc.needs_pass:
            raise ValueError("암호가 걸린 PDF예요. 암호를 해제한 뒤 다시 올려 주세요.")
        n = len(doc)
        if n == 0:
            raise ValueError("페이지가 없는 PDF예요.")

        pages, last = [], -10
        for i in range(n):
            md = pymupdf4llm.to_markdown(doc, pages=[i], show_progress=False).strip()
            if plain_len(md) < MIN_CHARS_PER_PAGE and doc[i].get_images():    # 이미지뿐인 쪽 = 스캔
                if ocr:
                    log(f"[pdf] {int(i / n * 100)}% ({i + 1}/{n}쪽 · 글자 인식 중)", cb)
                    md = ocr_page(doc[i], cb)
                    ocr_pages.append(i + 1)
                else:
                    skipped_scans += 1
            pages.append(md)
            pct = int((i + 1) / n * 100)
            if pct >= last + 5 or i == n - 1:
                last = pct
                log(f"[pdf] {pct}% ({i + 1}/{n}쪽)", cb)
    finally:
        doc.close()

    if sum(plain_len(p) for p in pages) < MIN_CHARS_PER_PAGE * n:
        if skipped_scans:
            raise ValueError("글자가 없는 스캔 PDF예요. '스캔 PDF 글자 인식(OCR)' 옵션을 켜고 다시 시도해 주세요.")
        raise ValueError("글자를 찾지 못했어요. 비어 있거나 글자를 읽을 수 없는 PDF예요.")

    # PDF 내부 제목 정보는 "Microsoft Word - 문서1" 같은 값이 많아 파일 이름을 제목으로 쓴다
    title = Path(local_name).stem if local_name else Path(path).stem

    method = "PDF 텍스트 추출 (pymupdf4llm)"
    if ocr_pages:
        shown = ", ".join(map(str, ocr_pages[:8])) + (" …" if len(ocr_pages) > 8 else "")
        method += f" + 글자 인식 OCR {len(ocr_pages)}쪽 (RapidOCR 한국어: {shown}쪽)"
    lines = [f"# {title}", "", f"- 원본 파일: {local_name or Path(path).name}", f"- 페이지: {n}쪽",
             f"- 변환 방식: {method}"]
    if ocr_pages:
        lines.append("- 참고: 글자 인식 결과에는 오타가 있을 수 있어요. 중요한 부분은 원본과 대조해 주세요.")
    lines.append("")
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
    ap.add_argument("--no-ocr", action="store_true", help="스캔한 쪽의 글자 인식(OCR)을 하지 않음")
    a = ap.parse_args()

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for n, src in enumerate(a.pdfs, 1):
        log(f"\n=== [{n}/{len(a.pdfs)}] {src}")
        try:
            title, md = convert_pdf(src, page_marks=not a.no_page_marks, ocr=not a.no_ocr)
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
