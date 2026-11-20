"""
Gyroflow Auto — Painel (Mac e Windows).
Painel aberto = ligado. Liga o motor (gyroflow_auto.py) por baixo e mostra tudo ao vivo.
Mac: fechar a janela só esconde (fica no Dock); ⌘Q ou "Desligar" desliga.
Windows: fechar a janela desliga.
"""
import json, os, re, subprocess, sys, time
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import plataforma as P
import visual as V
from visual import BG, SURF, SURF2, LINE, TEXT, MUTED, DIM, ACC1, ACC2, OK, WARN, ERR, BLUE

VERSAO = "2.0"
PY = sys.executable
if PY.lower().endswith("pythonw.exe"):
    PY = PY[:-11] + "python.exe"  # motor e cor rodam sem janela, mas com saída
CONFIG = P.APP_DIR / "config.json"
REGISTRY = P.APP_DIR / "estabilizados.json"
ERR_LOG = P.LOG_FILE.with_suffix(".err")
SEM_MOTOR = bool(os.environ.get("GFA_NO_ENGINE"))  # só para testes do visual
motor = None
pergunta_atual = {"id": None}


# ---------------------------------------------------------------- dados
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
    tmp = CONFIG.with_name(f"config.painel.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CONFIG)


def status():
    try:
        st = json.loads((P.APP_DIR / "status.json").read_text(encoding="utf-8"))
    except Exception:
        st = {"estado": "iniciando"}
    if st.get("estado") not in ("erro",) and not motor_vivo():
        st["estado"] = "desligado"
    return st


def motor_vivo():
    try:
        return P.pid_alive((P.APP_DIR / "gyroflow_auto.pid").read_text().strip())
    except Exception:
        return False


def total_estabilizados():
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        return len({v.get("saida") for v in reg.values() if isinstance(v, dict)})
    except Exception:
        return 0


def ligar_motor():
    global motor
    if SEM_MOTOR or motor_vivo():
        return
    if motor is not None and motor.poll() is None:
        return
    motor = subprocess.Popen([PY, "-u", str(AQUI / "gyroflow_auto.py")], cwd=str(AQUI),
                             stdout=subprocess.DEVNULL, stderr=open(ERR_LOG, "a"),
                             **({} if P.IS_WIN else {"start_new_session": True}))


def matar_motor():
    try:
        pid = int((P.APP_DIR / "gyroflow_auto.pid").read_text().strip())
    except Exception:
        pid = None
    if motor is not None and motor.poll() is None:
        P.kill_tree(motor)
    elif pid and P.pid_alive(pid):
        if P.IS_WIN:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.kill(pid, 15)
            except Exception:
                pass
    if not P.IS_WIN:
        subprocess.run(["pkill", "-f", "MacOS/gyroflow .*GyroflowAuto_cache"], capture_output=True)
    P.write_status("desligado")


def tempo(s):
    s = int(max(0, s or 0))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60:02d} s"
    return f"{s // 3600} h {s % 3600 // 60:02d} min"


# ---------------------------------------------------------------- janela
root = tk.Tk()
root.withdraw()
root.title("Gyroflow Auto")
root.configure(bg=BG)
root.minsize(860, 700)
try:
    ICON = tk.PhotoImage(file=str(AQUI / "icone.png"))
    root.iconphoto(True, ICON)
    LOGO = ICON.subsample(max(1, ICON.width() // 52))
except Exception:
    ICON = LOGO = None
if P.IS_WIN:
    try:
        root.iconbitmap(str(AQUI / "icone.ico"))
    except Exception:
        pass


def trazer_pra_frente():
    root.deiconify()
    root.lift()
    if P.IS_MAC and os.environ.get("GFA_BUNDLE"):
        subprocess.Popen(["open", os.environ["GFA_BUNDLE"]])  # ativa o app (sem pedir permissão)
    root.attributes("-topmost", True)
    root.after(400, lambda: root.attributes("-topmost", False))
    root.focus_force()


def confirmar(titulo, msg, ok_txt, cancel_txt="Cancelar", perigo=False):
    res = {"v": False}
    top = tk.Toplevel(root, bg=BG)
    top.title("Gyroflow Auto")
    top.resizable(False, False)
    top.transient(root)
    c = V.Card(top, pad=26, radius=20, width=500)
    c.pack(padx=16, pady=16)
    V.label(c.body, titulo, 19, TEXT, "bold").pack(anchor="w")
    V.label(c.body, msg, 13, MUTED, wraplength=440).pack(anchor="w", pady=(8, 20))
    row = tk.Frame(c.body, bg=SURF)
    row.pack(fill="x")

    def fim(v):
        res["v"] = v
        top.destroy()

    V.Button(row, cancel_txt, lambda: fim(False), "ghost").pack(side="left")
    V.Button(row, ok_txt, lambda: fim(True), "danger" if perigo else "primary").pack(side="right")
    top.protocol("WM_DELETE_WINDOW", lambda: fim(False))
    top.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - top.winfo_reqwidth()) // 2
    y = root.winfo_rooty() + (root.winfo_height() - top.winfo_reqheight()) // 3
    top.geometry(f"+{max(0, x)}+{max(0, y)}")
    top.grab_set()
    top.focus_force()
    root.wait_window(top)
    return res["v"]


def desligar():
    st = status()
    if st.get("estado") == "renderizando":
        if not confirmar("Desligar agora?",
                         f"Tem um vídeo sendo estabilizado:\n{st.get('detalhe', '')}\n\n"
                         "Se desligar, esse render é perdido (recomeça quando ligar de novo com o cartão plugado).",
                         "Desligar mesmo assim", "Continuar rodando", perigo=True):
            return
    if not SEM_MOTOR:
        matar_motor()
    try:
        (P.APP_DIR / "painel.alive").unlink()
    except Exception:
        pass
    root.destroy()


def fechar_janela():
    if P.IS_MAC:
        root.withdraw()  # continua ligado no Dock
    else:
        desligar()


root.protocol("WM_DELETE_WINDOW", fechar_janela)
if P.IS_MAC:
    root.createcommand("tk::mac::Quit", desligar)
    root.createcommand("tk::mac::ReopenApplication", lambda: (root.deiconify(), root.lift()))
    root.bind_all("<Command-w>", lambda e: fechar_janela())

wrap = tk.Frame(root, bg=BG)
wrap.pack(fill="both", expand=True, padx=26, pady=(22, 16))

# ---- topo ----
top = tk.Frame(wrap, bg=BG)
top.pack(fill="x")
if LOGO:
    tk.Label(top, image=LOGO, bg=BG).pack(side="left", padx=(0, 14))
tit = tk.Frame(top, bg=BG)
tit.pack(side="left")
V.label(tit, "Gyroflow Auto", 22, TEXT, "bold", bg=BG).pack(anchor="w")
V.label(tit, "by Paroneto  ·  estabilização automática de cartão", 12, MUTED, bg=BG).pack(anchor="w")
btn_off = V.Button(top, "Desligar", desligar, "danger", size=12, height=34, padx=16, bg=BG)
btn_off.pack(side="right")
pill = V.Pill(top, bg=BG)
pill.pack(side="right", padx=12)

linha = tk.Canvas(wrap, height=2, bg=BG, highlightthickness=0)
linha.pack(fill="x", pady=(18, 18))
linha.bind("<Configure>", lambda e: (linha.delete("all"), V.hgrad(linha, 0, 0, e.width, 2, ACC1, ACC2)))

# ---- AGORA ----
hero = V.Card(wrap, pad=24, radius=22)
hero.pack(fill="x")
hb = hero.body
hrow = tk.Frame(hb, bg=SURF)
hrow.pack(fill="x")
V.caps(hrow, "Agora").pack(side="left")
lbl_fila = V.label(hrow, "", 11, ACC2, cursor="hand2")
lbl_fila.pack(side="right")
lbl_titulo = V.label(hb, "Ligando…", 26, TEXT, "bold")
lbl_titulo.pack(anchor="w", pady=(10, 2))
lbl_sub = V.label(hb, "", 13, MUTED)
lbl_sub.pack(anchor="w")
prog_box = tk.Frame(hb, bg=SURF)
prog = V.Progress(prog_box, height=10)
prog.pack(fill="x", pady=(18, 8))
prow = tk.Frame(prog_box, bg=SURF)
prow.pack(fill="x")
lbl_pct = V.label(prow, "", 15, TEXT, "bold")
lbl_pct.pack(side="left")
lbl_eta = V.label(prow, "", 12, MUTED)
lbl_eta.pack(side="right")

# ---- COR (só aparece enquanto está aplicando cor) ----
cor_card = V.Card(wrap, pad=20, radius=20)
cb = cor_card.body
crow = tk.Frame(cb, bg=SURF)
crow.pack(fill="x")
cor_pill = tk.Canvas(crow, width=12, height=12, bg=SURF, highlightthickness=0)
cor_pill.pack(side="left", padx=(0, 8))
cor_pill.create_oval(2, 2, 11, 11, fill=WARN, outline="")
V.caps(crow, "Aplicando cor", color=WARN).pack(side="left")
lbl_cor_n = V.label(crow, "", 11, DIM)
lbl_cor_n.pack(side="right")
lbl_cor_arq = V.label(cb, "", 15, TEXT, "bold")
lbl_cor_arq.pack(anchor="w", pady=(10, 0))
cor_prog = V.Progress(cb, height=8)
cor_prog.pack(fill="x", pady=(12, 6))
crow2 = tk.Frame(cb, bg=SURF)
crow2.pack(fill="x")
lbl_cor_pct = V.label(crow2, "", 13, TEXT, "bold")
lbl_cor_pct.pack(side="left")
lbl_cor_eta = V.label(crow2, "", 12, MUTED)
lbl_cor_eta.pack(side="right")
cor_visivel = {"v": False}


def crescer(dh):
    """Aumenta/diminui a janela para o card da cor não espremer a atividade."""
    if root.state() != "normal" or not dh:
        return 0
    w, h, y = root.winfo_width(), root.winfo_height(), root.winfo_y()
    novo = max(700, min(h + dh, root.winfo_screenheight() - y - 40))
    root.geometry(f"{w}x{novo}")
    return novo - h


def cor_info():
    try:
        d = json.loads((P.APP_DIR / "cor_status.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    return d if d.get("ativo") and P.pid_alive(d.get("pid")) else None


def atualizar_cor():
    d = cor_info()
    if not d:
        if cor_visivel["v"]:
            cor_card.pack_forget()
            cor_visivel["v"] = False
            crescer(-cor_visivel.get("extra", 0))
        return
    if not cor_visivel["v"]:
        cor_card.pack(fill="x", pady=(16, 0), before=grid)
        cor_visivel["v"] = True
        root.update_idletasks()
        cor_visivel["extra"] = crescer(cor_card.winfo_reqheight() + 16)
    pct = float(d.get("pct") or 0)
    lbl_cor_n.config(text=f"{d.get('i', 1)} de {d.get('n', 1)}  ·  {d.get('pasta', '')}")
    lbl_cor_arq.config(text=d.get("arquivo", ""))
    cor_prog.set(pct)
    lbl_cor_pct.config(text=f"{pct:.0f}%")
    eta = d.get("eta") or 0
    lbl_cor_eta.config(text=(f"faltam {tempo(eta)}" if eta else "calculando…") + f"   ·   rodando há {tempo(d.get('decorrido'))}")


# ---- cards de info ----
grid = tk.Frame(wrap, bg=BG)
grid.pack(fill="x", pady=16)
for i in range(3):
    grid.columnconfigure(i, weight=1, uniform="c")

c_ev = V.Card(grid, pad=20)
c_ev.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
cap_ev = V.caps(c_ev.body, "Último evento")
cap_ev.pack(anchor="w")
lbl_ev = V.label(c_ev.body, "—", 17, TEXT, "bold", wraplength=230)
lbl_ev.pack(anchor="w", pady=(8, 2))
ev_links = tk.Frame(c_ev.body, bg=SURF)
ev_links.pack(anchor="w", pady=(0, 10))
lnk_ev = V.label(ev_links, "Abrir pasta  →", 12, ACC2, cursor="hand2")
lnk_ev.pack(side="left")
lnk_auto = V.label(ev_links, "", 12, WARN, cursor="hand2")
lnk_auto.pack(side="left", padx=(12, 0))
ev_btns = tk.Frame(c_ev.body, bg=SURF)
ev_btns.pack(anchor="w")

c_n = V.Card(grid, pad=20)
c_n.grid(row=0, column=1, sticky="nsew", padx=8)
V.caps(c_n.body, "Estabilizados").pack(anchor="w")
lbl_n = V.label(c_n.body, "0", 30, TEXT, "bold")
lbl_n.pack(anchor="w", pady=(4, 0))
V.label(c_n.body, "vídeos no total", 12, MUTED).pack(anchor="w")

c_s = V.Card(grid, pad=20)
c_s.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
V.caps(c_s.body, "Estabilização").pack(anchor="w")
AJ_PADRAO = {"suavidade_pct": 60, "corte_vel": 50, "corte_estatico": False, "correcao_lente": 100,
             "horizonte": False, "proporcao": "original"}
PROPORCOES = ["original", "16:9", "4:3", "9:16", "1:1"]


def aj_get():
    return {k: cfg_get(k, v) for k, v in AJ_PADRAO.items()}


def aj_resumo():
    a = aj_get()
    corte = "estático" if a["corte_estatico"] else str(a["corte_vel"])
    l1 = f"Uniformidade {a['suavidade_pct']}  ·  Corte {corte}"
    l2 = f"Lente {a['correcao_lente']}  ·  Horizonte {'on' if a['horizonte'] else 'off'}  ·  " + \
         ("Original" if a["proporcao"] == "original" else a["proporcao"])
    if len(l1) > 30:
        l1 = l1.replace("Uniformidade", "Unif.")
    return l1, l2


lbl_aj1 = V.label(c_s.body, "", 13, TEXT, "bold")
lbl_aj1.pack(anchor="w", pady=(10, 0))
lbl_aj2 = V.label(c_s.body, "", 11, MUTED, wraplength=230)
lbl_aj2.pack(anchor="w", pady=(2, 8))


def abrir_ajustes():
    a = aj_get()
    top = tk.Toplevel(root, bg=BG)
    top.title("Estabilização")
    top.resizable(False, False)
    top.transient(root)
    card = V.Card(top, pad=24, radius=20, width=470)
    card.pack(padx=14, pady=14)
    b = card.body
    V.label(b, "Estabilização", 19, TEXT, "bold").pack(anchor="w")
    V.label(b, "Vale para os próximos vídeos. Para refazer um cartão: \"Refazer cartão plugado\".", 11, DIM,
            wraplength=420).pack(anchor="w", pady=(2, 14))

    def linha_toggle(txt, val):
        r = tk.Frame(b, bg=SURF)
        r.pack(fill="x", pady=6)
        V.label(r, txt, 14, TEXT).pack(side="left")
        t = V.Toggle(r, val)
        t.pack(side="right")
        return t

    def linha_slider(txt, val):
        r = tk.Frame(b, bg=SURF)
        r.pack(fill="x", pady=(10, 0))
        V.label(r, txt, 14, TEXT).pack(side="left")
        box = tk.Label(r, text=str(val), width=4, font=V.font(13, "bold"), fg=TEXT, bg=SURF2,
                       highlightthickness=1, highlightbackground=LINE)
        box.pack(side="right")
        sl = V.Slider(b, val, lambda v: box.config(text=str(v)), width=420)
        sl.pack(fill="x", pady=(4, 0))
        return sl, box

    t_hor = linha_toggle("Nivelamento de horizonte", a["horizonte"])
    s_uni, b_uni = linha_slider("Uniformidade", a["suavidade_pct"])
    s_cor, b_cor = linha_slider("Velocidade de corte", a["corte_vel"])
    t_est = linha_toggle("Corte estático", a["corte_estatico"])
    s_len, b_len = linha_slider("Correção de lente", a["correcao_lente"])

    def estatico(on):
        s_cor.set_enabled(not on)
        b_cor.config(fg=DIM if on else TEXT)

    t_est.command = estatico
    estatico(a["corte_estatico"])
    r = tk.Frame(b, bg=SURF)
    r.pack(fill="x", pady=(16, 0))
    V.label(r, "Proporção de imagem", 14, TEXT).pack(anchor="w")
    seg_p = V.Segmented(b, PROPORCOES, a["proporcao"] if a["proporcao"] in PROPORCOES else "original", seg_w=80, suffix="")
    seg_p.pack(anchor="w", pady=(8, 0))
    V.label(b, "Original = sem corte (8:7 da GoPro, 4:3 da O4). As outras cortam o centro.", 11, DIM,
            wraplength=420).pack(anchor="w", pady=(6, 0))

    bot = tk.Frame(b, bg=SURF)
    bot.pack(fill="x", pady=(22, 0))

    def redefinir():
        t_hor.set(AJ_PADRAO["horizonte"])
        s_uni.set(AJ_PADRAO["suavidade_pct"]); b_uni.config(text=str(AJ_PADRAO["suavidade_pct"]))
        s_cor.set(AJ_PADRAO["corte_vel"]); b_cor.config(text=str(AJ_PADRAO["corte_vel"]))
        t_est.set(AJ_PADRAO["corte_estatico"]); estatico(AJ_PADRAO["corte_estatico"])
        s_len.set(AJ_PADRAO["correcao_lente"]); b_len.config(text=str(AJ_PADRAO["correcao_lente"]))
        seg_p.set("original")

    def aplicar():
        novo = {"horizonte": t_hor.value, "suavidade_pct": s_uni.value, "corte_vel": s_cor.value,
                "corte_estatico": t_est.value, "correcao_lente": s_len.value, "proporcao": seg_p.value}
        for k, v in novo.items():
            cfg_set(k, v)
        top.destroy()
        atualizar()
        toast("Ajustes salvos — valem para os próximos vídeos")

    V.Button(bot, "Redefinir", redefinir, "ghost").pack(side="left")
    V.Button(bot, "Aplicar", aplicar, "primary", padx=30).pack(side="right")
    top.protocol("WM_DELETE_WINDOW", top.destroy)
    top.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - top.winfo_reqwidth()) // 2
    y = root.winfo_rooty() + 60
    top.geometry(f"+{max(0, x)}+{max(0, y)}")
    top.grab_set()
    top.focus_force()


V.Button(c_s.body, "Ajustar…", abrir_ajustes, "ghost", size=12, height=32, padx=16).pack(anchor="w")

# ---- ações ----
acts = tk.Frame(wrap, bg=BG)
acts.pack(fill="x")


def refazer():
    l1, l2 = aj_resumo()
    if confirmar("Refazer o cartão plugado?",
                 f"Refaz os vídeos do cartão plugado que foram feitos com outros ajustes, usando os atuais:\n"
                 f"{l1}\n{l2}\n\nOs novos saem ao lado dos antigos (ex.: *_stabilized_60.mp4).", "Refazer"):
        (P.APP_DIR / "refazer.flag").write_text("1")
        toast("Refazendo o cartão com os ajustes atuais…")


def refazer_pasta():
    pasta = filedialog.askdirectory(parent=root, title="Pasta com os brutos (ex.: <Evento>/BRUTOS)",
                                    initialdir=str(cfg_get("pasta_destino", P.desktop_dir())))
    if not pasta:
        return
    l1, l2 = aj_resumo()
    if confirmar("Refazer a partir desta pasta?",
                 f"{Path(pasta).name}\n\nEstabiliza os brutos desta pasta que ainda não estão com os ajustes atuais:\n"
                 f"{l1}\n{l2}", "Refazer"):
        (P.APP_DIR / "refazer.flag").write_text(json.dumps({"pasta": pasta}, ensure_ascii=False), encoding="utf-8")
        toast("Refazendo a partir da pasta…")


def ler_fila():
    try:
        return json.loads((P.APP_DIR / "fila.json").read_text(encoding="utf-8")) if motor_vivo() else []
    except Exception:
        return []


def pedir_remocao(jid):
    f = P.APP_DIR / "remover.json"
    try:
        ids = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        ids = []
    if jid not in ids:
        ids.append(jid)
    tmp = P.APP_DIR / "remover.tmp"
    tmp.write_text(json.dumps(ids), encoding="utf-8")
    os.replace(tmp, f)


COR_ESTADO = {"estabilizando": BLUE, "juntando": ACC2, "copiando": ACC2, "na fila": MUTED,
              "aguardando cópia": DIM, "removendo": ERR}
janela_fila = {"top": None}


def abrir_fila():
    if janela_fila["top"] is not None and janela_fila["top"].winfo_exists():
        janela_fila["top"].lift()
        return
    top = tk.Toplevel(root, bg=BG)
    janela_fila["top"] = top
    top.title("Fila")
    top.transient(root)
    top.minsize(560, 300)
    card = V.Card(top, pad=22, radius=20, width=600, stretch=True, height=420)
    card.pack(fill="both", expand=True, padx=14, pady=14)
    b = card.body
    cab = tk.Frame(b, bg=SURF)
    cab.pack(fill="x")
    V.label(cab, "Fila", 19, TEXT, "bold").pack(side="left")
    lbl_qtd = V.label(cab, "", 12, MUTED)
    lbl_qtd.pack(side="right")
    V.label(b, "Remover tira o vídeo da fila (e para o render, se for o atual). Ele não volta ao plugar o cartão de novo.",
            11, DIM, wraplength=540).pack(anchor="w", pady=(4, 12))
    lista = tk.Frame(b, bg=SURF)
    lista.pack(fill="both", expand=True)
    estado = {"sig": None}

    def remover(item):
        if item.get("estado") == "estabilizando" and not confirmar(
                "Parar este render?", f"{item.get('nome')}\n\nEle está sendo estabilizado agora. Parar e tirar da fila?",
                "Parar e remover", "Continuar", perigo=True):
            return
        pedir_remocao(item["id"])
        toast(f"Removendo {item.get('nome')}…")

    def redesenha():
        if not top.winfo_exists():
            return
        itens = ler_fila()
        sig = json.dumps([(i["id"], i.get("estado")) for i in itens])
        if sig != estado["sig"]:
            estado["sig"] = sig
            for w in lista.winfo_children():
                w.destroy()
            lbl_qtd.config(text=f"{len(itens)} vídeo(s)" if itens else "")
            if not itens:
                V.label(lista, "Nada na fila agora.", 14, MUTED).pack(anchor="w", pady=20)
            for it in itens:
                row = tk.Frame(lista, bg=SURF2, highlightthickness=1, highlightbackground=LINE)
                row.pack(fill="x", pady=4)
                inner = tk.Frame(row, bg=SURF2)
                inner.pack(fill="x", padx=14, pady=10)
                esq = tk.Frame(inner, bg=SURF2)
                esq.pack(side="left", fill="x", expand=True)
                V.label(esq, it.get("nome", ""), 13, TEXT, "bold", bg=SURF2).pack(anchor="w")
                cor = COR_ESTADO.get(it.get("estado"), MUTED)
                sub = tk.Frame(esq, bg=SURF2)
                sub.pack(anchor="w")
                V.label(sub, "● " + (it.get("estado") or ""), 11, cor, bg=SURF2).pack(side="left")
                V.label(sub, f"   {it.get('evento', '')}  ·  {it.get('gb', '')} GB", 11, MUTED, bg=SURF2).pack(side="left")
                if it.get("estado") != "removendo":
                    V.Button(inner, "Remover", lambda i=it: remover(i), "danger", size=11, height=30, padx=14,
                             bg=SURF2).pack(side="right")
        top.after(1000, redesenha)

    redesenha()
    top.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - 640) // 2
    top.geometry(f"640x480+{max(0, x)}+{root.winfo_rooty() + 80}")


def aplicar_cor():
    pasta = filedialog.askdirectory(parent=root, title="Escolha a pasta do evento (vídeos *_stabilized.mp4)",
                                    initialdir=str(cfg_get("pasta_destino", P.desktop_dir())))
    if pasta:
        subprocess.Popen([PY, "-u", str(AQUI / "cor.py"), pasta], cwd=str(AQUI),
                         stdout=subprocess.DEVNULL, stderr=open(ERR_LOG, "a"))
        toast("Aplicando cor em segundo plano…")


def pasta_do_evento(nome):
    for e in cfg_get("eventos", []) or []:
        if e.get("nome") == nome and e.get("pasta"):
            return Path(e["pasta"])
    return Path(cfg_get("pasta_destino", str(P.desktop_dir()))) / nome


def abrir_evento():
    fixo = cfg_get("evento_fixo")
    nome = fixo.get("nome") if isinstance(fixo, dict) else cfg_get("ultimo_evento")
    if isinstance(fixo, dict) and fixo.get("pasta"):
        alvo = Path(fixo["pasta"])
    elif nome:
        alvo = pasta_do_evento(nome)
    else:
        alvo = Path(cfg_get("pasta_destino", str(P.desktop_dir())))
    P.open_path(alvo if alvo.is_dir() else alvo.parent)


def fixar_destino(nome, pasta):
    cfg_set("evento_fixo", {"nome": nome, "pasta": str(pasta)})
    Path(pasta).mkdir(parents=True, exist_ok=True)
    atualizar()
    toast(f"Próximos cartões vão para: {nome}")


def novo_evento():
    res = {"v": None}
    top = tk.Toplevel(root, bg=BG)
    top.title("Novo evento")
    top.resizable(False, False)
    top.transient(root)
    c = V.Card(top, pad=26, radius=20, width=500)
    c.pack(padx=14, pady=14)
    V.label(c.body, "Novo evento", 19, TEXT, "bold").pack(anchor="w")
    V.label(c.body, "Cria a pasta na Área de Trabalho. Os próximos cartões vão direto para ela, sem perguntar.",
            12, MUTED, wraplength=440).pack(anchor="w", pady=(4, 14))
    box, e = V.entry(c.body, "", 16)
    box.pack(fill="x")
    row = tk.Frame(c.body, bg=SURF)
    row.pack(fill="x", pady=(18, 0))

    def ok(*_):
        nome = re.sub(r'[/:\\*?"<>|]', "-", e.get()).strip()
        if nome:
            res["v"] = nome
            top.destroy()

    V.Button(row, "Cancelar", top.destroy, "ghost").pack(side="left")
    V.Button(row, "Criar evento", ok, "primary", padx=24).pack(side="right")
    e.bind("<Return>", ok)
    top.update_idletasks()
    top.geometry(f"+{root.winfo_rootx() + (root.winfo_width() - top.winfo_reqwidth()) // 2}+{root.winfo_rooty() + 120}")
    top.grab_set()
    top.after(100, e.focus_set)
    root.wait_window(top)
    if res["v"]:
        fixar_destino(res["v"], Path(cfg_get("pasta_destino", str(P.desktop_dir()))) / res["v"])


def pasta_antiga():
    pasta = filedialog.askdirectory(parent=root, title="Escolha a pasta do evento (os próximos cartões vão para ela)",
                                    initialdir=str(cfg_get("pasta_destino", P.desktop_dir())))
    if pasta:
        p = Path(pasta)
        if p.name.upper() == str(cfg_get("pasta_brutos", "BRUTOS")).upper():
            p = p.parent  # escolheu a BRUTOS: usa o evento
        fixar_destino(p.name, p)


def voltar_automatico():
    cfg_set("evento_fixo", None)
    atualizar()
    toast("Destino automático: pela data das gravações")


def ver_log():
    if P.IS_MAC:
        subprocess.Popen(["open", "-a", "Console", str(P.LOG_FILE)])
    else:
        P.open_path(P.LOG_FILE)


lnk_ev.bind("<Button-1>", lambda e: abrir_evento())
lnk_auto.bind("<Button-1>", lambda e: voltar_automatico())
V.Button(ev_btns, "Novo evento", novo_evento, "primary", size=12, height=32, padx=14).pack(side="left")
V.Button(ev_btns, "Pasta antiga…", pasta_antiga, "ghost", size=12, height=32, padx=12).pack(side="left", padx=(8, 0))
V.Button(acts, "Refazer cartão plugado", refazer, "primary", bg=BG).pack(side="left")
V.Button(acts, "Refazer de uma pasta…", refazer_pasta, "ghost", bg=BG).pack(side="left", padx=(10, 0))
V.Button(acts, "Aplicar cor…", aplicar_cor, "ghost", bg=BG).pack(side="left", padx=10)
btn_fila = V.Button(acts, "Fila", abrir_fila, "ghost", bg=BG, width=96)
btn_fila.pack(side="left")
V.Button(acts, "Log", ver_log, "ghost", bg=BG).pack(side="left", padx=(10, 0))
lbl_toast = V.label(wrap, "", 12, OK, bg=BG)
lbl_toast.pack(anchor="e", pady=(6, 0))
lbl_fila.bind("<Button-1>", lambda e: abrir_fila())


def toast(msg):
    lbl_toast.config(text="✓  " + msg)
    root.after(4500, lambda: lbl_toast.config(text="") if lbl_toast.cget("text").endswith(msg) else None)


rod = V.label(wrap, "", 11, DIM, bg=BG)
rod.pack(side="bottom", anchor="w", pady=(12, 0))

# ---- atividade ----
act = V.Card(wrap, pad=20, stretch=True, height=230)
act.pack(fill="both", expand=True, pady=(16, 0))
V.caps(act.body, "Atividade").pack(anchor="w", pady=(0, 8))
txt = tk.Text(act.body, height=9, bg=SURF, fg=MUTED, relief="flat", bd=0, highlightthickness=0,
              font=V.font(12), wrap="none", cursor="arrow", padx=0, pady=0, spacing1=3, spacing3=3)
txt.pack(fill="both", expand=True)
for tag, cor in (("ok", OK), ("erro", ERR), ("aviso", ACC1), ("info", ACC2), ("dim", DIM), ("txt", TEXT), ("hora", DIM)):
    txt.tag_configure(tag, foreground=cor)
txt.tag_configure("hora", font=V.font(11, mono=True))
txt.config(state="disabled")

rod.config(text=("Fechar a janela deixa ligado no Dock  ·  ⌘Q ou Desligar desliga" if P.IS_MAC
                 else "Fechar a janela desliga o Gyroflow Auto  ·  pode minimizar") + f"  ·  v{VERSAO}")


def classifica(msg):
    m = msg.strip()
    if m.startswith("ERRO") or "ERRO" in m[:12] or "falh" in m.lower():
        return "erro", "●", m
    if m.startswith("[notificação]"):
        return "aviso", "◆", m[len("[notificação]"):].strip()
    if m.startswith("OK ->"):
        return "ok", "✓", "Salvo: " + Path(m[5:].strip()).name
    r = re.match(r"render ok \(suavidade (\d+)%\): (\S+) em (\d+)s \((\d+)s de vídeo\)", m)
    if r:
        return "ok", "✓", f"Estabilizado em {r.group(1)}%: {r.group(2)}  ·  {tempo(int(r.group(3)))}"
    r = re.match(r"cor ok: (\S+) em (\d+)s", m)
    if r:
        return "ok", "✓", f"Cor pronta: {r.group(1)}  ·  {tempo(int(r.group(2)))}"
    r = re.match(r"copiado \[(\d+/\d+)\] (.*?) -> (.*)", m)
    if r:
        return "info", "›", f"Copiado {r.group(1)}: {r.group(2).replace(', ', ' + ')}"
    if m.startswith(("copiado", "juntando", "corte detectado", "assando", "sessão", "Cartão")):
        return "info", "›", m
    if m.startswith("===") and "iniciado" in m:
        return "dim", "•", "Motor ligado"
    if m.startswith("==="):
        return "dim", "•", m.strip("= ").replace("===", "").strip()
    return "dim", "·", m


_ultimo_log = {"sig": None}


def atualizar_log():
    try:
        with open(P.LOG_FILE, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 12000))
            linhas = f.read().decode("utf-8", "replace").splitlines()
    except Exception:
        linhas = []
    cabe = max(3, int(txt.winfo_height() / (V.font(12).metrics("linespace") + 6)))  # só as linhas que cabem inteiras
    ok = [l for l in linhas if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", l)][-cabe:]
    sig = f"{cabe}|" + "\n".join(ok)
    if sig == _ultimo_log["sig"]:
        return
    _ultimo_log["sig"] = sig
    txt.config(state="normal")
    txt.delete("1.0", "end")
    for l in ok:
        hora, msg = l[11:16], l[21:]
        tag, ic, m = classifica(msg)
        if len(m) > 96:
            m = m[:93] + "…"
        txt.insert("end", hora + "   ", "hora")
        txt.insert("end", ic + "  ", tag)
        txt.insert("end", m + ("\n" if l is not ok[-1] else ""), "txt" if tag in ("ok", "aviso", "erro") else "dim")
    txt.yview_moveto(0)
    txt.config(state="disabled")


def atualizar():
    st = status()
    e = st.get("estado")
    fila = int(st.get("fila") or 0)
    if e == "renderizando":
        pill.set("ESTABILIZANDO", BLUE, pulse=True)
        lbl_titulo.config(text="Estabilizando")
        sub = st.get("detalhe", "")
        if st.get("evento"):
            sub += f"   ·   {st['evento']}"
        lbl_sub.config(text=sub)
        pct = float(st.get("pct") or 0)
        prog_box.pack(fill="x")
        prog.set(pct)
        lbl_pct.config(text=f"{pct:.0f}%")
        eta = st.get("eta") or 0
        partes = [f"faltam {tempo(eta)}" if eta else "calculando…", f"rodando há {tempo(st.get('decorrido'))}"]
        if st.get("suavidade"):
            partes.append(f"uniformidade {st['suavidade']}")
        lbl_eta.config(text="   ·   ".join(partes))
        lbl_fila.config(text=f"{fila} na fila" if fila > 1 else "último da fila" if fila == 1 else "")
    elif e == "copiando":
        pill.set("COPIANDO", ACC2, pulse=True)
        lbl_titulo.config(text="Copiando do cartão")
        lbl_sub.config(text=f"{st.get('detalhe', '')}   ·   {st.get('evento', '')}")
        prog_box.pack(fill="x")
        if prog.pct is not None:
            prog.set(None)
        lbl_pct.config(text="")
        lbl_eta.config(text="não tire o cartão ainda")
        lbl_fila.config(text="")
    else:
        prog_box.pack_forget()
        lbl_fila.config(text="")
        if e == "erro":
            pill.set("ERRO", ERR)
            lbl_titulo.config(text="Precisa de atenção")
            lbl_sub.config(text=st.get("detalhe", "") or "Veja o log.")
        elif e == "desligado":
            pill.set("DESLIGADO", DIM)
            lbl_titulo.config(text="Desligado")
            lbl_sub.config(text="Religando o motor…" if not SEM_MOTOR else "Motor desligado.")
        elif e == "iniciando":
            pill.set("LIGANDO", WARN, pulse=True)
            lbl_titulo.config(text="Ligando…")
            lbl_sub.config(text="")
        else:
            pill.set("LIGADO", OK, pulse=True)
            lbl_titulo.config(text="Esperando cartão")
            lbl_sub.config(text="Plugue o cartão da GoPro ou da DJI O4 Pro — o resto é automático.")
    fixo = cfg_get("evento_fixo")
    if isinstance(fixo, dict) and fixo.get("nome"):
        cap_ev.config(text=" ".join("PRÓXIMOS CARTÕES →"), fg=ACC2)
        lbl_ev.config(text=fixo["nome"])
        lnk_auto.config(text="↺ Automático")
    else:
        cap_ev.config(text=" ".join("ÚLTIMO EVENTO"), fg=DIM)
        lbl_ev.config(text=cfg_get("ultimo_evento") or "—")
        lnk_auto.config(text="")
    lbl_n.config(text=str(total_estabilizados()))
    nfila = len(ler_fila())
    btn_fila.set_text(f"Fila ({nfila})" if nfila else "Fila")
    l1, l2 = aj_resumo()
    lbl_aj1.config(text=l1)
    lbl_aj2.config(text=l2)
    atualizar_cor()
    atualizar_log()


def ver_pergunta():
    q = P.APP_DIR / "pergunta.json"
    try:
        d = json.loads(q.read_text(encoding="utf-8"))
    except Exception:
        return
    if d.get("id") == pergunta_atual["id"]:
        return
    pergunta_atual["id"] = d.get("id")

    def resp(nome, qid=d.get("id")):
        tmp = P.APP_DIR / "resposta.tmp"
        tmp.write_text(json.dumps({"id": qid, "nome": nome}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, P.APP_DIR / "resposta.json")

    trazer_pra_frente()
    V.ask_event(root, d.get("padrao", "Evento"), d.get("desc", ""), int(d.get("segundos", 90)),
                on_answer=resp, bring_front=None)


def anima():
    pill.tick()
    prog.tick()
    root.after(70, anima)


def loop():
    try:
        (P.APP_DIR / "painel.alive").write_text(str(os.getpid()))
    except Exception:
        pass
    if not SEM_MOTOR and status().get("estado") != "erro":
        ligar_motor()  # se o motor cair, religa sozinho
    ver_pergunta()
    atualizar()
    root.after(1000, loop)


P.APP_DIR.mkdir(parents=True, exist_ok=True)
# pede já a permissão do macOS para a pasta de destino (Área de Trabalho), com o app na frente —
# senão o motor trava esperando essa permissão na hora de ler/salvar os vídeos
try:
    os.listdir(cfg_get("pasta_destino", str(P.desktop_dir())))
except Exception:
    pass
ligar_motor()
root.update_idletasks()
W, H = 940, min(860, root.winfo_screenheight() - 80)
root.geometry(f"{W}x{H}+{(root.winfo_screenwidth() - W) // 2}+{max(30, (root.winfo_screenheight() - H) // 3)}")
root.deiconify()
atualizar()
root.after(300, loop)
root.after(50, anima)
_demo = {"ajustes": lambda: abrir_ajustes(), "fila": lambda: abrir_fila(), "evento": lambda: novo_evento()}
if os.environ.get("GFA_DEMO") in _demo:  # só para conferir o visual
    root.after(1200, _demo[os.environ["GFA_DEMO"]])
root.mainloop()
