#!/usr/bin/env python
# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""Microsoft Office(Word·PowerPoint·Excel) 문서를 PDF 로 바꿉니다.

이 PC 에 설치된 Office 를 보이지 않게 띄워 PDF 로 저장하므로 원본 모양 그대로 나옵니다.
(한글 변환과 같은 방식입니다.) 이미지는 이 PDF 를 쪽마다 그림으로 저장해 만듭니다.
Office 가 없는 PC 에서는 쓸 수 없습니다.

사용법:
  python officeconv.py 주보.docx [슬라이드.pptx 표.xlsx ...] [-d 결과폴더]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from vod2md import log, unique_path

TIMEOUT = 180                # Office 가 이 시간 안에 끝내지 못하면 멈춘 것으로 보고 중단한다(초)

# 확장자 -> (Office 프로그램, COM 이름, 프로세스 이름)
APPS = {
    "word": ("Word", "Word.Application", "WINWORD.EXE"),
    "ppt": ("PowerPoint", "PowerPoint.Application", "POWERPNT.EXE"),
    "excel": ("Excel", "Excel.Application", "EXCEL.EXE"),
}
EXT_APP = {
    ".doc": "word", ".docx": "word", ".docm": "word", ".rtf": "word", ".odt": "word",
    ".ppt": "ppt", ".pptx": "ppt", ".pptm": "ppt", ".pps": "ppt", ".ppsx": "ppt", ".odp": "ppt",
    ".xls": "excel", ".xlsx": "excel", ".xlsm": "excel", ".csv": "excel", ".ods": "excel",
}
SUFFIXES = tuple(EXT_APP)


def app_of(name):
    return EXT_APP.get(Path(name).suffix.lower())


def office_available():
    """이 PC 에 설치된 Office 프로그램 {'word': bool, 'ppt': bool, 'excel': bool} (pywin32 가 있어야 쓸 수 있다)."""
    res = {k: False for k in APPS}
    if sys.platform != "win32":
        return res
    try:
        import winreg
        import win32com.client  # noqa: F401
    except Exception:
        return res
    for key, (_label, prog, _exe) in APPS.items():
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog))
            res[key] = True
        except OSError:
            pass
    return res


def _pids(exe):
    """지금 떠 있는 해당 Office 프로세스 번호들."""
    try:
        r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=15)
    except Exception:
        return set()
    return {l.split(",")[1].strip('"') for l in r.stdout.splitlines() if l.lower().startswith(f'"{exe.lower()}"')}


def _worker(kind, src, out):
    """(별도 프로세스에서 실행) Office 를 보이지 않게 띄워 문서를 PDF 로 저장한다."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    prog = APPS[kind][1]
    app = win32com.client.DispatchEx(prog)              # 항상 새로 띄운다 (열려 있는 내 문서를 건드리지 않는다)
    doc = None
    try:
        if kind == "word":
            app.Visible = False
            app.DisplayAlerts = 0
            doc = app.Documents.Open(str(src), ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False,
                                     Visible=False, NoEncodingDialog=True)
            doc.ExportAsFixedFormat(str(out), 17)           # wdExportFormatPDF
        elif kind == "excel":
            app.Visible = False
            app.DisplayAlerts = False
            doc = app.Workbooks.Open(str(src), ReadOnly=True, UpdateLinks=0)
            doc.ExportAsFixedFormat(0, str(out))            # xlTypePDF
        else:
            doc = app.Presentations.Open(str(src), ReadOnly=True, Untitled=False, WithWindow=False)
            doc.SaveAs(str(out), 32)                        # ppSaveAsPDF
    except Exception as e:
        print("OPEN_OR_SAVE_FAILED: " + str(e), file=sys.stderr)
        raise
    finally:
        for call in (lambda: doc.Close(False) if kind != "ppt" else doc.Close(), lambda: app.Quit()):
            try:
                call()
            except Exception:
                pass


def office_to_pdf(src, out_pdf, cb=None, timeout=TIMEOUT):
    """Word·PowerPoint·Excel 파일을 PDF 로 저장한다. Office 가 멈추면 제때 끊는다."""
    kind = app_of(src)
    if not kind:
        raise ValueError("지원하지 않는 형식이에요. Word·PowerPoint·Excel 파일을 올려 주세요.")
    label, _prog, exe = APPS[kind]
    if not office_available()[kind]:
        raise ValueError(f"{label}을(를) 찾지 못했어요. 이 PC에 Microsoft {label} 프로그램이 설치돼 있어야 PDF로 바꿀 수 있어요.")
    out_final = Path(out_pdf)
    out_final.parent.mkdir(parents=True, exist_ok=True)
    out_final.unlink(missing_ok=True)
    log(f"[오피스] {label}로 PDF 저장 중… (파일 하나에 10초 안팎)", cb)
    # Office 에게는 항상 임시 폴더에만 저장시키고 완성된 파일을 우리가 목적지로 옮긴다 (한글 변환과 같은 이유).
    tmpdir = Path(tempfile.mkdtemp(prefix="officesave_"))
    work_out = tmpdir / "doc.pdf"
    before = _pids(exe)
    try:
        try:
            r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", kind, str(src), str(work_out)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env={**os.environ, "PYTHONUTF8": "1"}, timeout=timeout)
        except subprocess.TimeoutExpired:
            for pid in _pids(exe) - before:               # 내가 띄운 것만 끈다
                subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True)
            raise ValueError(f"{label} 프로그램이 응답하지 않아 중단했어요. 암호가 걸렸거나 {label} 화면에 확인 창이 떠 있지 않은지 보고 다시 시도해 주세요.")
        finally:
            for pid in _pids(exe) - before:               # 혹시 남은 것이 있으면 정리
                subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True)
        err = r.stderr or ""
        if r.returncode != 0 or not work_out.exists() or work_out.stat().st_size == 0:
            low = err.lower()
            if "password" in low or "암호" in err:
                raise ValueError("암호가 걸린 문서예요. 암호를 풀고 다시 올려 주세요.")
            if "OPEN_OR_SAVE_FAILED" in err:
                raise ValueError(f"이 파일을 {label}에서 열거나 저장하지 못했어요. 손상됐거나 암호가 걸린 문서일 수 있어요.")
            raise ValueError("오피스 변환에 실패했어요: " + (err.strip().splitlines() or ["알 수 없는 오류"])[-1][:160])
        shutil.move(str(work_out), str(out_final))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return out_final


def main():
    if len(sys.argv) >= 5 and sys.argv[1] == "--worker":            # 내부용: Office 를 띄우는 별도 프로세스
        try:
            _worker(sys.argv[2], sys.argv[3], sys.argv[4])
        except Exception:
            sys.exit(2)
        return
    ap = argparse.ArgumentParser(description="Word·PowerPoint·Excel -> PDF")
    ap.add_argument("files", nargs="+")
    ap.add_argument("-d", "--dir", default="output")
    a = ap.parse_args()
    for f in a.files:
        p = Path(f)
        out = unique_path(Path(a.dir), p.stem, ".pdf")
        try:
            office_to_pdf(p, out)
            print(f"저장: {out}")
        except ValueError as e:
            print(f"실패({p.name}): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
