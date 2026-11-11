"""
Gyroflow Auto — by Paroneto
Camada de plataforma: tudo que muda entre Mac e Windows fica aqui.
"""
import os, re, shutil, subprocess, sys, json
from pathlib import Path

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
HOME = Path.home()

# ---------------------------------------------------------------- pastas
if IS_WIN:
    APP_DIR = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData/Local")) / "GyroflowAuto"
    LOG_FILE = APP_DIR / "GyroflowAuto.log"
    CACHE_ROOT = APP_DIR / "cache"
    GYRO_DATA = Path(os.environ.get("APPDATA", HOME / "AppData/Roaming")) / "Gyroflow"
    EXE = ".exe"
else:
    APP_DIR = HOME / "Library/Application Support/GyroflowAuto"
    LOG_FILE = HOME / "Library/Logs/GyroflowAuto.log"
    # O Gyroflow da App Store é sandbox: esta é a única pasta fora do container
    # que ele pode ler/escrever (funciona também com o Gyroflow do GitHub).
    CACHE_ROOT = HOME / "Library/Application Support/Gyroflow/GyroflowAuto_cache"
    GYRO_DATA = HOME / "Library/Application Support/Gyroflow"
    EXE = ""

BIN_DIR = APP_DIR / "bin"
LUT_DIR = APP_DIR / "luts"

# no Windows, nenhum subprocesso abre janela preta de console
if IS_WIN:
    _NOWIN = 0x08000000  # CREATE_NO_WINDOW
    _orig_popen_init = subprocess.Popen.__init__

    def _popen_init(self, *a, **k):
        k.setdefault("creationflags", _NOWIN)
        _orig_popen_init(self, *a, **k)

    subprocess.Popen.__init__ = _popen_init


def tool(name):
    """ffmpeg / ffprobe / mp4_merge: primeiro o que veio no pacote, depois o sistema."""
    p = BIN_DIR / (name + EXE)
    if p.exists():
        return str(p)
    w = shutil.which(name)
    if w:
        return w
    for d in ("/opt/homebrew/bin", "/usr/local/bin"):
        if Path(d, name).exists():
            return str(Path(d, name))
    return name


def desktop_dir():
    if IS_WIN:
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
            if buf.value:
                return Path(buf.value)
        except Exception:
            pass
    return HOME / "Desktop"


def gyroflow_candidates():
    if IS_MAC:
        return [Path("/Applications/Gyroflow.app/Contents/MacOS/gyroflow"),
                HOME / "Applications/Gyroflow.app/Contents/MacOS/gyroflow"]
    if IS_WIN:
        pf = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
              str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs")]
        c = []
        for base in pf:
            c += [Path(base, "Gyroflow", "Gyroflow.exe"), Path(base, "Gyroflow", "gyroflow.exe")]
            try:
                c += sorted(Path(base).glob("Gyroflow*/[Gg]yroflow.exe"))
            except Exception:
                pass
        c.append(Path(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "gyroflow.exe"))
        return c
    return []


def find_gyroflow(cfg):
    p = cfg.get("gyroflow_path")
    if p and Path(p).exists():
        return p
    for c in gyroflow_candidates():
        if c.exists():
            return str(c)
    w = shutil.which("gyroflow")
    return w


def gyro_default_preset():
    for p in (GYRO_DATA / "lens_profiles" / "default.gyroflow",):
        if p.exists():
            return p
    return None


def output_folder_url(folder: Path):
    if IS_WIN:
        return "file:///" + str(folder).replace("\\", "/").rstrip("/") + "/"
    return "file://" + str(folder) + "/"


# ---------------------------------------------------------------- cartões
_MAC_IGNORE = {"Macintosh HD", "Recovery", "Preboot", "VM", "Data"}


def mounted_volumes():
    """{chave: Path} dos volumes montados (Mac: /Volumes/*, Windows: D:\\ ... Z:\\)."""
    vols = {}
    if IS_WIN:
        import string, ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i, letter in enumerate(string.ascii_uppercase):
            if mask & (1 << i) and letter not in ("A", "B", "C"):
                vols[letter] = Path(f"{letter}:\\")
    else:
        try:
            for p in Path("/Volumes").iterdir():
                if p.is_dir() and p.name not in _MAC_IGNORE:
                    vols[p.name] = p
        except Exception:
            pass
    return vols


def volume_label(vol: Path):
    if IS_WIN:
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(261)
            ctypes.windll.kernel32.GetVolumeInformationW(str(vol), buf, 261, None, None, None, None, 0)
            return f"{buf.value or 'Cartão'} ({str(vol)[:2]})"
        except Exception:
            return str(vol)
    return vol.name


# ---------------------------------------------------------------- avisos e janelas
def _esc_as(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def notify(title, msg, sound=None):
    try:
        if IS_MAC:
            s = f'display notification "{_esc_as(msg)}" with title "Gyroflow Auto" subtitle "{_esc_as(title)}"'
            if sound:
                s += f' sound name "{sound}"'
            subprocess.run(["osascript", "-e", s], capture_output=True, timeout=10)
        elif IS_WIN:
            t = (title or "").replace("'", "''")
            m = (msg or "").replace("'", "''")
            ps = ("Add-Type -AssemblyName System.Windows.Forms;Add-Type -AssemblyName System.Drawing;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Information;"
                  f"$n.Visible=$true;$n.ShowBalloonTip(6000,'Gyroflow Auto — {t}','{m}','Info');Start-Sleep 7;$n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps])
    except Exception:
        pass


def ask_event_name(default, card_desc):
    """Janela de EVENTO NOVO. Se ninguém responder em 90 s, usa o nome padrão. None = ignorar."""
    if IS_MAC:
        script = (
            f'display dialog "Cartão detectado: {_esc_as(card_desc)}\\n\\nEVENTO NOVO — nome da pasta na Área de Trabalho:\\n'
            f'(se não responder em 90 s, usa o nome abaixo)" default answer "{_esc_as(default)}" with title "Gyroflow Auto" '
            f'buttons {{"Ignorar este cartão", "Estabilizar"}} default button "Estabilizar" giving up after 90'
        )
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if r.returncode != 0:
            return None
        out = r.stdout.strip()
        m = re.search(r"button returned:([^,]*)", out)
        if m and m.group(1) == "Ignorar este cartão":
            return None
        m = re.search(r"text returned:(.*?)(, gave up:.*)?$", out)
        name = (m.group(1) if m else default).strip()
    else:
        py = sys.executable
        if IS_WIN and py.lower().endswith("python.exe") and Path(py[:-10] + "pythonw.exe").exists():
            py = py[:-10] + "pythonw.exe"
        r = subprocess.run([py, str(Path(__file__).with_name("dialogo.py")), default, card_desc],
                           capture_output=True, text=True, encoding="utf-8")
        out = (r.stdout or "").strip()
        if not out or out == "__IGNORAR__":
            return None
        name = out
    name = re.sub(r'[/:\\*?"<>|]', "-", name).strip()
    return name or default or None


def set_file_dates(path: Path, birth: float, mtime: float):
    os.utime(path, (mtime, mtime))
    if IS_MAC:
        from datetime import datetime
        try:
            subprocess.run(["SetFile", "-d", datetime.fromtimestamp(birth).strftime("%m/%d/%Y %H:%M:%S"), str(path)],
                           capture_output=True)
        except Exception:
            pass


def kill_tree(proc):
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        proc.kill()


def popen_group_kwargs():
    return {} if IS_WIN else {"start_new_session": True}


class SingleInstance:
    """Trava exclusiva do sistema: impossível rodar dois motores."""

    def __init__(self, path: Path):
        self.fh = open(path, "a+")
        try:
            if IS_WIN:
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.ok = True
        except OSError:
            self.ok = False


def write_status(estado, detalhe=""):
    try:
        (APP_DIR / "status.json").write_text(json.dumps({"estado": estado, "detalhe": detalhe, "pid": os.getpid()},
                                                         ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
