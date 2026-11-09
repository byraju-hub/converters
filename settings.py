# Copyright (C) 2026 byraju
# SPDX-License-Identifier: AGPL-3.0-or-later
# 이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서(AGPL) 3판 또는 그 이후 판의
# 조건에 따라 배포·수정할 수 있습니다. 자세한 내용은 LICENSE 파일을 보세요.
"""사용자 설정 (결과 파일을 저장할 폴더). 설치 폴더의 settings.json 에 저장하며 git 에는 올라가지 않는다."""
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "output"
SETTINGS_FILE = HERE / "settings.json"


def load():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(data):
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def check_dir(raw):
    """사용자가 적은 경로를 확인해서 쓸 수 있는 폴더(Path)로 돌려준다. 없으면 만든다."""
    text = str(raw or "").strip().strip('"')
    if not text:
        raise ValueError("폴더 경로를 적어 주세요.")
    p = Path(os.path.expandvars(os.path.expanduser(text)))
    if not p.is_absolute():
        raise ValueError("전체 경로로 적어 주세요. 예: D:\\변환결과")
    try:
        if p.exists() and not p.is_dir():
            raise ValueError("이 경로는 폴더가 아니라 파일이에요.")
        p.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=p):          # 실제로 쓸 수 있는지 시험
            pass
    except ValueError:
        raise
    except PermissionError:
        raise ValueError("이 폴더에 파일을 쓸 수 없어요. 다른 폴더를 고르거나 권한을 확인해 주세요.")
    except OSError as e:
        raise ValueError(f"이 폴더를 쓸 수 없어요: {e.strerror or e}")
    return p.resolve()


def initial_output_dir():
    """시작할 때 쓸 저장 폴더와, 저장해 둔 폴더를 못 쓸 때의 안내(없으면 None)."""
    saved = load().get("output_dir")
    if saved:
        try:
            return check_dir(saved), None
        except ValueError as e:
            DEFAULT_OUT.mkdir(exist_ok=True)
            return DEFAULT_OUT, f"저장해 둔 폴더({saved})를 쓸 수 없어서 기본 폴더를 쓰고 있어요. ({e})"
    DEFAULT_OUT.mkdir(exist_ok=True)
    return DEFAULT_OUT, None


def set_output_dir(raw):
    p = check_dir(raw)
    data = load()
    if p == DEFAULT_OUT.resolve():
        data.pop("output_dir", None)         # 기본 폴더는 설정에서 지운다
    else:
        data["output_dir"] = str(p)
    save(data)
    return p


def reset_output_dir():
    data = load()
    data.pop("output_dir", None)
    save(data)
    DEFAULT_OUT.mkdir(exist_ok=True)
    return DEFAULT_OUT.resolve()


_PS_PICKER = r"""
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.FolderBrowserDialog
$f.Description = '결과 파일을 저장할 폴더를 고르세요'
$f.ShowNewFolderButton = $true
if ($env:VOD_INITIAL_DIR -and (Test-Path -LiteralPath $env:VOD_INITIAL_DIR)) { $f.SelectedPath = $env:VOD_INITIAL_DIR }
# 보이지 않는 소유 창을 맨 위에 두어, 선택 창이 다른 창 뒤에 숨지 않게 한다
$o = New-Object System.Windows.Forms.Form
$o.TopMost = $true; $o.ShowInTaskbar = $false; $o.Opacity = 0; $o.StartPosition = 'CenterScreen'
$o.Size = New-Object System.Drawing.Size(1, 1)
$o.Show(); $o.Activate()
if ($env:VOD_PICK_DRYRUN) { Write-Output 'DRYRUN_OK'; exit 0 }
$r = $f.ShowDialog($o)
if ($r -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }
"""


def pick_folder(initial=None, timeout=600, dryrun=False):
    """이 PC 에서 폴더 선택 창을 띄워 고른 경로를 돌려준다. 취소하면 None."""
    env = dict(os.environ, VOD_INITIAL_DIR=str(initial or ""))
    if dryrun:
        env["VOD_PICK_DRYRUN"] = "1"
    if sys.platform == "win32":
        enc = base64.b64encode(_PS_PICKER.encode("utf-16-le")).decode("ascii")
        cmd = ["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
        out = (r.stdout or "").strip()
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "폴더 선택 창을 열지 못했어요").strip()[:200])
        return out or None
    # macOS·Linux: tkinter 가 있으면 사용
    code = ("import tkinter as tk, tkinter.filedialog as fd, os\n"
            "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
            "print(fd.askdirectory(initialdir=os.environ.get('VOD_INITIAL_DIR') or None) or '')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, errors="replace", timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError("이 PC에서는 폴더 선택 창을 쓸 수 없어요. 경로를 직접 입력해 주세요.")
    return (r.stdout or "").strip() or None
