"""
Gyroflow Auto — janela "Evento novo" avulsa (quando o painel está fechado).
Uso: dialogo.py <nome_padrao> <descricao>
Imprime o nome escolhido, ou __IGNORAR__. Se ninguém responder em 90 s, usa o padrão.
"""
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import visual as V

padrao = sys.argv[1] if len(sys.argv) > 1 else "Evento"
desc = sys.argv[2] if len(sys.argv) > 2 else ""
resultado = {"v": padrao}

root = tk.Tk()
root.withdraw()
try:
    root.iconphoto(True, tk.PhotoImage(file=str(Path(__file__).with_name("icone.png"))))
except Exception:
    pass


def fim(v):
    resultado["v"] = v
    root.after(10, root.destroy)


V.ask_event(root, padrao, desc, 90, on_answer=fim)
root.mainloop()
sys.stdout.write(resultado["v"])
