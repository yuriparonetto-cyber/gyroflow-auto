"""
Gyroflow Auto — Painel (Windows).
Janela aberta = ligado. Fechar a janela = desligar.
Liga o motor (gyroflow_auto.py) por baixo e mostra o que está acontecendo.
"""
import json, os, subprocess, sys, threading, time
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import plataforma as P

PY = sys.executable
if PY.lower().endswith("pythonw.exe"):
    PY_CONSOLE = PY[:-11] + "python.exe"
else:
    PY_CONSOLE = PY
CONFIG = P.APP_DIR / "config.json"
motor = None


def cfg_get(k, d=None):
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get(k, d)
    except Exception:
        return d


def cfg_set(k, v):
    try:
        c = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        c = {}
    c[k] = v
    CONFIG.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")


def status():
    try:
        return json.loads((P.APP_DIR / "status.json").read_text(encoding="utf-8"))
    except Exception:
        return {"estado": "iniciando"}


def ligar_motor():
    global motor
    if motor is None or motor.poll() is not None:
        motor = subprocess.Popen([PY_CONSOLE, str(AQUI / "gyroflow_auto.py")], cwd=str(AQUI),
                                 stdout=subprocess.DEVNULL, stderr=open(P.APP_DIR / "erros.txt", "a"))


def desligar():
    st = status()
    if st.get("estado") == "renderizando":
        if not messagebox.askyesno("Gyroflow Auto",
                                   f"Tem um vídeo sendo estabilizado agora:\n{st.get('detalhe', '')}\n\n"
                                   "Se desligar, esse render é perdido (recomeça quando ligar de novo "
                                   "com o cartão plugado).\n\nDesligar mesmo assim?"):
            return
    if motor and motor.poll() is None:
        P.kill_tree(motor)
    P.write_status("desligado")
    root.destroy()


def aplicar_cor():
    pasta = filedialog.askdirectory(title="Escolha a pasta do evento (vídeos *_stabilized.mp4)",
                                    initialdir=cfg_get("pasta_destino", str(P.desktop_dir())))
    if pasta:
        subprocess.Popen([PY_CONSOLE, str(AQUI / "cor.py"), pasta], cwd=str(AQUI),
                         stdout=subprocess.DEVNULL, stderr=open(P.APP_DIR / "erros.txt", "a"))
        messagebox.showinfo("Gyroflow Auto", "Aplicando cor em segundo plano.\nAcompanhe aqui no painel.")


def trocar_suavidade():
    novo = 50 if int(cfg_get("suavidade_pct", 30)) == 30 else 30
    cfg_set("suavidade_pct", novo)
    atualizar()


def abrir(p):
    try:
        os.startfile(str(p))
    except Exception:
        subprocess.Popen(["open", str(p)])


root = tk.Tk()
root.title("Gyroflow Auto — by Paroneto")
root.geometry("640x430")
root.minsize(520, 360)
try:
    root.iconbitmap(str(AQUI / "icone.ico"))
except Exception:
    pass
topo = tk.Frame(root, padx=14, pady=10)
topo.pack(fill="x")
lbl_estado = tk.Label(topo, text="● Ligando…", font=("Segoe UI", 14, "bold"), fg="#e08a00")
lbl_estado.pack(anchor="w")
lbl_info = tk.Label(topo, text="", fg="#555", justify="left")
lbl_info.pack(anchor="w")
txt = tk.Text(root, height=12, font=("Consolas", 9), bg="#111", fg="#ddd", relief="flat", padx=8, pady=6)
txt.pack(fill="both", expand=True, padx=14)
bot = tk.Frame(root, padx=14, pady=10)
bot.pack(fill="x")
btn_suav = tk.Button(bot, text="Suavidade: 30%", command=trocar_suavidade, width=16)
btn_suav.pack(side="left")
tk.Button(bot, text="Aplicar COR numa pasta…", command=aplicar_cor).pack(side="left", padx=6)
tk.Button(bot, text="Abrir Área de Trabalho", command=lambda: abrir(cfg_get("pasta_destino", P.desktop_dir()))).pack(side="left")
tk.Button(bot, text="Desligar", command=desligar, fg="#b00").pack(side="right")
tk.Label(root, text="Janela aberta = ligado (pode minimizar). Fechar = desligar.", fg="#888").pack(pady=(0, 8))
root.protocol("WM_DELETE_WINDOW", desligar)


def atualizar():
    st = status()
    e = st.get("estado")
    if e == "renderizando":
        lbl_estado.config(text="● ESTABILIZANDO", fg="#0a7cd8")
        lbl_info.config(text=st.get("detalhe", ""))
    elif e == "erro":
        lbl_estado.config(text="● ERRO", fg="#c00")
        lbl_info.config(text=st.get("detalhe", ""))
    elif e == "ligado":
        lbl_estado.config(text="● LIGADO — esperando cartão", fg="#1a9c3a")
        lbl_info.config(text="Plugue o cartão da GoPro ou da O4 Pro.")
    btn_suav.config(text=f"Suavidade: {cfg_get('suavidade_pct', 30)}%")
    try:
        linhas = P.LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-14:]
        txt.config(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", "\n".join(l[11:] for l in linhas))
        txt.see("end")
        txt.config(state="disabled")
    except Exception:
        pass


def loop():
    if motor is not None and motor.poll() is not None and status().get("estado") != "erro":
        ligar_motor()  # se o motor cair, religa sozinho
    atualizar()
    root.after(2000, loop)


P.APP_DIR.mkdir(parents=True, exist_ok=True)
ligar_motor()
root.after(1500, loop)
root.mainloop()
