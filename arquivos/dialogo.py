"""
Gyroflow Auto — janela "EVENTO NOVO" (usada no Windows).
Uso: dialogo.py <nome_padrao> <descricao>
Imprime o nome escolhido, ou __IGNORAR__. Se ninguém responder em 90 s, usa o padrão.
"""
import sys
import tkinter as tk

padrao = sys.argv[1] if len(sys.argv) > 1 else "Evento"
desc = sys.argv[2] if len(sys.argv) > 2 else ""
resultado = {"v": padrao}
restante = [90]

root = tk.Tk()
root.title("Gyroflow Auto — Evento novo")
root.attributes("-topmost", True)
root.resizable(False, False)
f = tk.Frame(root, padx=18, pady=14)
f.pack()
tk.Label(f, text="Cartão detectado:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
tk.Label(f, text=desc, wraplength=420, justify="left").pack(anchor="w", pady=(0, 10))
tk.Label(f, text="EVENTO NOVO — nome da pasta na Área de Trabalho:").pack(anchor="w")
e = tk.Entry(f, width=48, font=("Segoe UI", 11))
e.insert(0, padrao)
e.pack(fill="x", pady=4)
e.select_range(0, "end")
e.focus_set()
lbl = tk.Label(f, fg="#666")
lbl.pack(anchor="w")


def ok(*_):
    resultado["v"] = e.get().strip() or padrao
    root.destroy()


def ignorar():
    resultado["v"] = "__IGNORAR__"
    root.destroy()


def tick():
    restante[0] -= 1
    if restante[0] <= 0:
        ok()
        return
    lbl.config(text=f"Se ninguém responder, usa o nome acima em {restante[0]} s")
    root.after(1000, tick)


def digitou(*_):
    restante[0] = 10 ** 9  # parou o relógio: a pessoa está digitando
    lbl.config(text="")


e.bind("<Key>", digitou)
e.bind("<Return>", ok)
b = tk.Frame(f)
b.pack(fill="x", pady=(10, 0))
tk.Button(b, text="Ignorar este cartão", command=ignorar).pack(side="left")
tk.Button(b, text="Estabilizar", command=ok, default="active", width=14).pack(side="right")
root.protocol("WM_DELETE_WINDOW", ignorar)
root.after(1000, tick)
lbl.config(text="Se ninguém responder, usa o nome acima em 90 s")
root.update_idletasks()
w, h = root.winfo_width(), root.winfo_height()
root.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")
root.mainloop()
sys.stdout.write(resultado["v"])
