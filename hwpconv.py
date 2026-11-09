#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""한글(HWP·HWPX) 문서 변환

두 가지 방식을 씁니다.
  A. 한컴오피스가 설치된 PC: 한글 프로그램을 보이지 않게 띄워 PDF 로 저장 (원본 모양 그대로).
     이 PDF 를 기존 기능으로 이미지·Markdown 으로 다시 바꿀 수 있습니다.
  B. 한컴오피스가 없는 PC: 파일 안을 직접 읽어 Markdown(텍스트)으로 바꿉니다.
     .hwpx 는 문단·제목·목록·표를 살리고, .hwp 는 글자 위주입니다.

사용법:
  python hwpconv.py 문서.hwpx --to pdf|md|img [-d 결과폴더]
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from vod2md import log, unique_path

PDF_TIMEOUT = 180            # 한글이 이 시간 안에 끝내지 못하면 멈춘 것으로 보고 중단한다(초)


# ====================================================================== A. 한컴오피스 자동화
def hancom_available():
    """이 PC 에 한컴오피스(한글 자동화 연결)와 pywin32 가 있는가."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"HWPFrame.HwpObject"))
        import win32com.client  # noqa: F401
        return True
    except Exception:
        return False


def _hwp_pids():
    """지금 떠 있는 hwp.exe 프로세스 번호들."""
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq hwp.exe", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=15)
    except Exception:
        return set()
    return {l.split(",")[1].strip('"') for l in r.stdout.splitlines() if l.lower().startswith('"hwp.exe"')}


def _worker_save(src, out, fmt):
    """(별도 프로세스에서 실행) 한글을 보이지 않게 띄워 문서를 fmt(PDF·HWPX 등)로 저장한다."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    hwp = win32com.client.DispatchEx("HWPFrame.HwpObject")      # 항상 새 한글을 띄운다 (열려 있는 내 문서를 건드리지 않는다)
    try:
        try:
            hwp.XHwpWindows.Item(0).Visible = False
        except Exception:
            pass
        if not hwp.Open(str(src), "", "forceopen:true"):
            raise RuntimeError("OPEN_FAILED")
        if not hwp.SaveAs(str(out), fmt, ""):
            raise RuntimeError("SAVE_FAILED")
    finally:
        for call in (lambda: hwp.Clear(1), lambda: hwp.Quit()):
            try:
                call()
            except Exception:
                pass


def hwp_save_as(src, out, fmt="PDF", cb=None, timeout=PDF_TIMEOUT):
    """한컴오피스로 .hwp/.hwpx 를 fmt("PDF" 또는 "HWPX")로 저장한다. 한글이 멈추면 제때 끊는다."""
    if not hancom_available():
        raise ValueError("한컴오피스를 찾지 못했어요. 한컴오피스가 설치된 PC에서만 PDF로 바꿀 수 있어요.")
    out_final = Path(out)
    out_final.parent.mkdir(parents=True, exist_ok=True)
    out_final.unlink(missing_ok=True)
    log(f"[한글] 한컴오피스로 {fmt} 저장 중… (파일 하나에 10초 안팎)", cb)
    # 한글에게는 항상 임시 폴더에만 저장시키고, 완성된 파일을 우리가 목적지로 옮긴다.
    # 임시 폴더가 아닌 곳(예: output 폴더)에 저장하게 하면 한글이 "파일 접근을 허용할까요?" 확인 창을 띄워
    # 보이지 않는 한글 뒤에서 영원히 기다리게 된다. (한컴의 보안 설정을 바꾸지 않고 피하는 방법)
    tmpdir = Path(tempfile.mkdtemp(prefix="hwpsave_"))
    work_out = tmpdir / ("doc" + (out_final.suffix or ""))
    before = _hwp_pids()
    try:
        try:
            r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker-save", str(src), str(work_out), fmt],
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            for pid in _hwp_pids() - before:         # 내가 띄운 한글만 끈다
                subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True)
            raise ValueError("한글이 응답하지 않아 중단했어요. 한글에 확인 창(암호·보안 등)이 떠 있지 않은지 보고 다시 시도해 주세요.")
        finally:
            for pid in _hwp_pids() - before:         # 혹시 남은 것이 있으면 정리
                subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True)
        err = (r.stderr or "")
        if r.returncode != 0 or not work_out.exists() or work_out.stat().st_size == 0:
            if "OPEN_FAILED" in err:
                raise ValueError("한글이 이 파일을 열지 못했어요. 암호가 걸렸거나 손상된 문서일 수 있어요.")
            if "SAVE_FAILED" in err:
                raise ValueError("한글이 저장하지 못했어요. 문서에 저장이 막혀 있을 수 있어요.")
            raise ValueError("한글 변환에 실패했어요: " + (err.strip().splitlines() or ["알 수 없는 오류"])[-1][:160])
        shutil.move(str(work_out), str(out_final))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return out_final


def hwp_to_pdf(src, out_pdf, cb=None, timeout=PDF_TIMEOUT):
    return hwp_save_as(src, out_pdf, "PDF", cb, timeout)


# ====================================================================== B-1. .hwpx 직접 읽기
def _loc(e):
    return e.tag.rsplit("}", 1)[-1]


def _t_text(t):
    """<hp:t> 안의 글자 (줄바꿈·탭·고정폭 공백 같은 내부 표시 포함)."""
    parts = [t.text or ""]
    for ch in t:
        n = _loc(ch)
        if n == "lineBreak":
            parts.append("\n")
        elif n == "tab":
            parts.append("\t")
        elif n in ("nbSpace", "fwSpace"):
            parts.append(" ")
        elif n == "hyphen":
            parts.append("-")
        else:
            parts.append(_t_text(ch))
        parts.append(ch.tail or "")
    return "".join(parts)


def _para_items(p):
    """문단을 (글자 | 표 | 그림) 순서대로 풀어낸다."""
    items = []
    for run in p:
        if _loc(run) != "run":
            continue
        for ch in run:
            n = _loc(ch)
            if n == "t":
                items.append(("text", _t_text(ch)))
            elif n == "tbl":
                items.append(("table", ch))
            elif n in ("pic", "ole"):
                items.append(("pic", None))
    return items


def _plain(p):
    return "".join(v for k, v in _para_items(p) if k == "text").replace("\t", " ")


def _table_md(tbl):
    """표 -> Markdown 표. 병합된 칸은 빈 칸으로 둔다."""
    cells, nrows, ncols = {}, 0, 0
    for tr in tbl:
        if _loc(tr) != "tr":
            continue
        for tc in tr:
            if _loc(tc) != "tc":
                continue
            addr, span = tc.find(".//{*}cellAddr"), tc.find(".//{*}cellSpan")
            if addr is None:
                continue
            r, c = int(addr.get("rowAddr", 0)), int(addr.get("colAddr", 0))
            rs = int(span.get("rowSpan", 1)) if span is not None else 1
            cs = int(span.get("colSpan", 1)) if span is not None else 1
            sub = tc.find("{*}subList")
            lines = []
            for p in (sub.findall("{*}p") if sub is not None else []):
                t = _plain(p).strip()
                if t:
                    lines.append(t)
            cells[(r, c)] = " ".join(lines).replace("|", "\\|")
            nrows, ncols = max(nrows, r + rs), max(ncols, c + cs)
    if not cells:
        return []
    if nrows == 1 and ncols == 1:                       # 글상자처럼 쓰인 1칸 표는 그냥 문단으로
        return [cells[(0, 0)], ""]
    rows = [[cells.get((r, c), "") for c in range(ncols)] for r in range(nrows)]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * ncols]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return out + [""]


def hwpx_to_md_native(path):
    """.hwpx 를 한컴오피스 없이 읽어 Markdown 본문으로. (본문, 안내 목록) 을 돌려준다."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ValueError("올바른 .hwpx 파일이 아니에요.")
    with z:
        names = z.namelist()
        if any(n.startswith("META-INF/") and "encrypt" in n.lower() for n in names):
            raise ValueError("암호가 걸린 문서예요. 암호를 해제한 뒤 다시 올려 주세요.")
        sections = sorted((n for n in names if re.fullmatch(r"Contents/section\d+\.xml", n)),
                          key=lambda n: int(re.search(r"(\d+)\.xml", n).group(1)))
        if not sections:
            raise ValueError("본문을 찾지 못했어요. 배포용이거나 손상된 문서일 수 있어요.")
        styles, paraprs = {}, {}
        if "Contents/header.xml" in names:
            hdr = ET.fromstring(z.read("Contents/header.xml"))
            for e in hdr.iter():
                n = _loc(e)
                if n == "style":
                    styles[e.get("id")] = e.get("name") or ""
                elif n == "paraPr":
                    h = e.find("{*}heading")
                    paraprs[e.get("id")] = (h.get("type"), int(h.get("level", 0))) if h is not None else ("NONE", 0)

        pics, lines = 0, []

        def heading_prefix(p):
            style = styles.get(p.get("styleIDRef"), "")
            m = re.match(r"개요\s*(\d+)", style)
            if m:
                return "#" * min(6, int(m.group(1)) + 1) + " "
            kind, lvl = paraprs.get(p.get("paraPrIDRef"), ("NONE", 0))
            if kind == "OUTLINE":
                return "#" * min(6, lvl + 2) + " "
            if kind == "BULLET":
                return "  " * lvl + "- "
            if kind == "NUMBER":
                return "  " * lvl + "1. "
            return ""

        for sec_name in sections:
            root = ET.fromstring(z.read(sec_name))
            for p in root:
                if _loc(p) != "p":
                    continue
                buf = []
                prefix = heading_prefix(p)

                def flush():
                    text = "".join(buf).replace("\t", " ").strip("\n")
                    buf.clear()
                    if text.strip() == "":
                        return
                    text = text.replace("\n", "  \n")
                    if not prefix:
                        text = re.sub(r"^(\d+)([.)])", r"\1\\\2", text)
                        text = re.sub(r"^([#>+\-*])", r"\\\1", text)
                    lines.append(prefix + text.strip())
                    lines.append("")

                for kind, val in _para_items(p):
                    if kind == "text":
                        buf.append(val)
                    elif kind == "table":
                        flush()
                        lines.extend(_table_md(val))
                    elif kind == "pic":
                        pics += 1
                flush()
        notes = []
        if pics:
            notes.append(f"그림 {pics}개는 Markdown에 넣지 못했어요. 그림까지 필요하면 한컴오피스가 있는 PC에서 PDF로 바꿔 주세요.")
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        if not body:
            # 본문이 비어 보이면 미리보기 텍스트라도 쓴다
            if "Preview/PrvText.txt" in names:
                body = z.read("Preview/PrvText.txt").decode("utf-8", "replace").strip()
                notes.append("본문을 읽지 못해 문서의 미리보기 텍스트를 대신 담았어요.")
        if not body:
            raise ValueError("글자를 찾지 못했어요. 비어 있거나 읽을 수 없는 문서예요.")
        return body + "\n", notes


# ====================================================================== B-2. .hwp 직접 읽기 (글자 위주)
_INLINE_CTRL = {4, 5, 6, 7, 8, 9, 19, 20}                 # 글자 8개 분량 (자신 포함)
_EXTEND_CTRL = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}


def _decode_para_text(payload):
    import array
    units = array.array("H")
    units.frombytes(payload[: len(payload) // 2 * 2])
    out, j = [], 0
    while j < len(units):
        c = units[j]
        if c < 32:
            if c in _INLINE_CTRL or c in _EXTEND_CTRL:
                if c == 9:
                    out.append(32)                       # 탭 -> 공백
                j += 8
                continue
            if c in (24, 30, 31):                        # 하이픈, 묶음 빈칸, 고정폭 빈칸
                out.append(45 if c == 24 else 32)
            j += 1
            continue
        out.append(c)
        j += 1
    return array.array("H", out).tobytes().decode("utf-16-le", "replace")


def hwp_text_native(path):
    """.hwp(바이너리)에서 글자만 뽑는다. 표·그림 서식은 살리지 못한다."""
    import struct
    import zlib
    try:
        import olefile
    except ImportError:
        raise ValueError("'olefile'이 설치되지 않았어요. 'pip install -r requirements.txt'를 실행해 주세요.")
    if not olefile.isOleFile(str(path)):
        raise ValueError("올바른 .hwp 파일이 아니에요. (아주 오래된 한글 3.0 문서는 지원하지 않아요.)")
    ole = olefile.OleFileIO(str(path))
    try:
        head = ole.openstream("FileHeader").read()
        if not head.startswith(b"HWP Document File"):
            raise ValueError("올바른 .hwp 파일이 아니에요.")
        flags = struct.unpack("<I", head[36:40])[0]
        if flags & 2:
            raise ValueError("암호가 걸린 문서예요. 암호를 해제한 뒤 다시 올려 주세요.")
        if flags & 4:
            raise ValueError("배포용(읽기 전용) 문서는 직접 읽을 수 없어요. 한컴오피스가 있는 PC에서 PDF로 바꿔 주세요.")
        compressed = bool(flags & 1)
        secs = sorted((e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText" and e[1].startswith("Section")),
                      key=lambda e: int(re.sub(r"\D", "", e[1]) or 0))
        paras = []
        for e in secs:
            data = ole.openstream(e).read()
            if compressed:
                data = zlib.decompress(data, -15)
            i = 0
            while i + 4 <= len(data):
                h = struct.unpack_from("<I", data, i)[0]
                i += 4
                tag, size = h & 0x3FF, (h >> 20) & 0xFFF
                if size == 0xFFF:
                    size = struct.unpack_from("<I", data, i)[0]
                    i += 4
                payload = data[i:i + size]
                i += size
                if tag == 67:                            # HWPTAG_PARA_TEXT
                    t = _decode_para_text(payload).strip()
                    if t:
                        paras.append(t)
        if not paras:
            raise ValueError("글자를 찾지 못했어요. 비어 있거나 읽을 수 없는 문서예요.")
        return "\n\n".join(paras) + "\n"
    finally:
        ole.close()


# ====================================================================== 합치기
def hwp_kind(path):
    """파일 머리로 종류를 알아본다: 'hwpx' | 'hwp' | None"""
    with open(path, "rb") as f:
        head = f.read(8)
    if head[:4] == b"PK\x03\x04":
        return "hwpx"
    if head == bytes.fromhex("D0CF11E0A1B11AE1"):
        return "hwp"
    return None


def convert_hwp_md(path, local_name=None, cb=None):
    """한글 문서 -> (제목, Markdown).
    .hwpx 는 직접 읽고, .hwp 는 한컴오피스가 있으면 .hwpx 로 저장한 뒤 읽는다(구조가 살아난다).
    한컴이 없거나 실패하면 .hwp 의 글자만 직접 읽는다."""
    kind = hwp_kind(path)
    if kind is None:
        raise ValueError("한글(.hwp, .hwpx) 문서가 아니에요.")
    title = Path(local_name).stem if local_name else Path(path).stem
    lines = [f"# {title}", "", f"- 원본 파일: {local_name or Path(path).name}"]
    notes = []
    if kind == "hwpx":
        log("[한글] .hwpx 를 직접 읽는 중…", cb)
        body, notes = hwpx_to_md_native(path)
        lines.append("- 변환 방식: .hwpx 직접 읽기 (문단·제목·목록·표)")
    else:
        body = None
        if hancom_available():
            try:
                with tempfile.TemporaryDirectory(prefix="hwp2md_") as tmp:
                    hwpx = hwp_save_as(path, Path(tmp) / "doc.hwpx", "HWPX", cb)
                    body, notes = hwpx_to_md_native(hwpx)
                lines.append("- 변환 방식: 한컴오피스로 .hwpx 변환 후 읽기 (문단·제목·목록·표)")
            except Exception as e:
                log(f"[한글] 한컴 변환이 안 돼 글자만 읽어요: {e}", cb)
                body = None
        if body is None:
            log("[한글] .hwp 글자를 직접 읽는 중…", cb)
            body = hwp_text_native(path)
            notes = ["표·그림·서식은 포함되지 않은 글자 위주의 결과예요. 한컴오피스가 있는 PC에서는 더 정확하게 바꿀 수 있어요."]
            lines.append("- 변환 방식: .hwp 글자만 직접 읽기")
    for n in notes:
        lines.append(f"- 참고: {n}")
    lines += ["", body.strip(), ""]
    return title, "\n".join(lines)


def main():
    if len(sys.argv) >= 5 and sys.argv[1] == "--worker-save":        # 내부용: 한글을 띄우는 별도 프로세스
        try:
            _worker_save(sys.argv[2], sys.argv[3], sys.argv[4])
        except Exception as e:
            print(str(e) or type(e).__name__, file=sys.stderr)
            sys.exit(1)
        return

    ap = argparse.ArgumentParser(description="한글(HWP·HWPX) 변환")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--to", choices=["pdf", "md", "img"], default="md")
    ap.add_argument("-d", "--outdir", default=".")
    ap.add_argument("--format", choices=["png", "jpg"], default="png")
    ap.add_argument("--dpi", type=int, default=150)
    a = ap.parse_args()
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for f in a.files:
        log(f"\n=== {f}")
        try:
            stem = Path(f).stem
            if a.to == "pdf":
                out = hwp_to_pdf(f, unique_path(outdir, stem, ".pdf"))
                print(f"완료: {out.resolve()}")
            elif a.to == "img":
                import pdftools
                with tempfile.TemporaryDirectory(prefix="hwp2img_") as tmp:
                    pdf = hwp_to_pdf(f, Path(tmp) / "doc.pdf")
                    folder = unique_path(outdir, stem + " 이미지", "")
                    files = pdftools.pdf_to_images(pdf, folder, a.format, a.dpi, stem=stem)
                print(f"완료: {len(files)}장 -> {folder.resolve()}")
            else:
                title, md = convert_hwp_md(f)
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
