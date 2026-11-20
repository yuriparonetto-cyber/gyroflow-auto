"""
Gyroflow Auto — kit visual (painel escuro, cards arredondados, botões, barra de progresso).
Só tkinter, sem nada para instalar. Usado pelo painel e pela janela de evento novo.
"""
import sys
import tkinter as tk
import tkinter.font as tkfont

IS_MAC = sys.platform == "darwin"

# ---- cores -------------------------------------------------------------------
BG = "#0A0E14"       # fundo
SURF = "#121823"     # card
SURF2 = "#1A2230"    # campo / botão secundário
LINE = "#263247"     # borda
TEXT = "#EAF0FA"
MUTED = "#8B98AE"
DIM = "#5C6880"
ACC1 = "#8B5CF6"     # violeta
ACC2 = "#22D3EE"     # ciano
OK = "#34D399"
WARN = "#FBBF24"
ERR = "#F87171"
BLUE = "#60A5FA"


def mix(c1, c2, t):
    """Mistura duas cores #rrggbb (t=0 → c1, t=1 → c2)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


# ---- fontes ------------------------------------------------------------------
_F = {}


def font(size=13, weight="normal", mono=False):
    key = (size, weight, mono)
    if key not in _F:
        base = tkfont.nametofont("TkFixedFont" if mono else "TkDefaultFont").actual()["family"]
        if not IS_MAC and not mono:
            base = "Segoe UI"
        _F[key] = tkfont.Font(family=base, size=size, weight=weight)
    return _F[key]


# ---- formas ------------------------------------------------------------------
def rrect(c, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def hgrad(c, x1, y1, x2, y2, c1, c2, tag=None):
    w = max(1, int(x2 - x1))
    for i in range(w):
        c.create_line(x1 + i, y1, x1 + i, y2, fill=mix(c1, c2, i / w), tags=tag)


class Card(tk.Canvas):
    """Card arredondado; coloque widgets em card.body."""

    def __init__(self, parent, pad=18, radius=18, fill=SURF, outline=LINE, bg=BG, stretch=False, **kw):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, **kw)
        self.pad, self.radius, self.fill, self.outline, self.stretch = pad, radius, fill, outline, stretch
        self.body = tk.Frame(self, bg=fill)
        self._win = self.create_window(pad, pad, window=self.body, anchor="nw")
        self.bind("<Configure>", self._draw)
        self.body.bind("<Configure>", self._fit)

    def _fit(self, _=None):
        if self.stretch:
            return
        h = self.body.winfo_reqheight() + 2 * self.pad
        if self.winfo_reqheight() != h:
            self.configure(height=h)

    def _draw(self, e=None):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("bg")
        rrect(self, 1, 1, w - 2, h - 2, self.radius, fill=self.fill, outline=self.outline, width=1, tags="bg")
        self.tag_lower("bg")
        self.itemconfigure(self._win, width=max(10, w - 2 * self.pad))
        if self.stretch:
            self.itemconfigure(self._win, height=max(10, h - 2 * self.pad))


class Button(tk.Canvas):
    """Botão arredondado. kind: primary | ghost | danger."""

    def __init__(self, parent, text, command=None, kind="ghost", size=13, height=40, padx=18, bg=SURF, width=None):
        f = font(size, "bold" if kind == "primary" else "normal")
        w = width or f.measure(text) + 2 * padx
        super().__init__(parent, width=w, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.command, self.kind, self.f = text, command, kind, f
        self.hover = False
        self.pressed = False
        self.enabled = True
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False, pressed=False))
        self.bind("<ButtonPress-1>", lambda e: self._set(pressed=True))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Configure>", lambda e: self._draw())

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self._draw()

    def _click(self, e):
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        self._set(pressed=False)
        if inside and self.enabled and self.command:
            self.command()

    def set_text(self, text):
        self.text = text
        self._draw()

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            w, h = int(self.cget("width")), int(self.cget("height"))
        self.delete("all")
        if self.kind == "primary":
            c1, c2 = (ACC1, mix(ACC1, ACC2, 0.85))
            if self.hover:
                c1, c2 = mix(c1, "#ffffff", 0.12), mix(c2, "#ffffff", 0.12)
            if self.pressed:
                c1, c2 = mix(c1, "#000000", 0.15), mix(c2, "#000000", 0.15)
            # gradiente com cantos arredondados: faixas + tampas redondas
            r = h / 2
            hgrad(self, r, 0, w - r, h, c1, c2)
            self.create_oval(0, 0, 2 * r, h, fill=c1, outline=c1)
            self.create_oval(w - 2 * r - 1, 0, w - 1, h, fill=c2, outline=c2)
            fg = "#ffffff"
        else:
            base = SURF2 if self.kind == "ghost" else mix(SURF2, ERR, 0.12)
            fill = mix(base, "#ffffff", 0.06) if self.hover else base
            if self.pressed:
                fill = mix(base, "#000000", 0.2)
            line = mix(LINE, ERR, 0.5) if self.kind == "danger" else (mix(LINE, ACC1, 0.5) if self.hover else LINE)
            rrect(self, 1, 1, w - 2, h - 2, h / 2, fill=fill, outline=line, width=1)
            fg = ERR if self.kind == "danger" else TEXT
        if not self.enabled:
            fg = DIM
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=self.f)


class Segmented(tk.Canvas):
    """Seletor tipo iOS: 30 | 60 | 80."""

    def __init__(self, parent, options, value, command=None, bg=SURF, seg_w=66, height=38, suffix="%"):
        super().__init__(parent, width=seg_w * len(options) + 8, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.options, self.value, self.command = options, value, command
        self.seg_w, self.h, self.suffix = seg_w, height, suffix
        self.hover = None
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda e: self._hov(None))
        self.draw()

    def _idx(self, x):
        return max(0, min(len(self.options) - 1, int((x - 4) // self.seg_w)))

    def _move(self, e):
        self._hov(self._idx(e.x))

    def _hov(self, i):
        if i != self.hover:
            self.hover = i
            self.draw()

    def _click(self, e):
        v = self.options[self._idx(e.x)]
        if v != self.value:
            self.value = v
            self.draw()
            if self.command:
                self.command(v)

    def set(self, v):
        if v != self.value:
            self.value = v
            self.draw()

    def draw(self):
        self.delete("all")
        W = self.seg_w * len(self.options) + 8
        rrect(self, 1, 1, W - 2, self.h - 2, self.h / 2, fill=SURF2, outline=LINE)
        for i, o in enumerate(self.options):
            x1 = 4 + i * self.seg_w
            sel = o == self.value
            if sel:
                r = (self.h - 8) / 2
                c1, c2 = ACC1, mix(ACC1, ACC2, 0.7)
                hgrad(self, x1 + r, 4, x1 + self.seg_w - r, self.h - 4, c1, c2)
                self.create_oval(x1, 4, x1 + 2 * r, self.h - 4, fill=c1, outline=c1)
                self.create_oval(x1 + self.seg_w - 2 * r - 1, 4, x1 + self.seg_w - 1, self.h - 4, fill=c2, outline=c2)
            elif self.hover == i:
                rrect(self, x1, 4, x1 + self.seg_w, self.h - 4, (self.h - 8) / 2, fill=mix(SURF2, "#ffffff", 0.06), outline="")
            self.create_text(x1 + self.seg_w / 2, self.h / 2, text=(o.capitalize() if isinstance(o, str) else f"{o}{self.suffix}"),
                             fill="#ffffff" if sel else MUTED, font=font(13, "bold" if sel else "normal"))


class Progress(tk.Canvas):
    """Barra de progresso com gradiente; pct=None → animação de 'trabalhando'."""

    def __init__(self, parent, bg=SURF, height=10):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.pct, self.h, self.phase = 0.0, height, 0.0
        self.bind("<Configure>", lambda e: self.draw())

    def set(self, pct):
        self.pct = pct
        self.draw()

    def tick(self):
        if self.pct is None:
            self.phase = (self.phase + 0.02) % 1.4
            self.draw()

    def draw(self):
        w, h = self.winfo_width(), self.h
        if w < 10:
            return
        self.delete("all")
        r = h / 2
        rrect(self, 0, 0, w - 1, h - 1, r, fill=SURF2, outline="")
        if self.pct is None:
            seg = w * 0.3
            x = (self.phase - 0.3) * w
            a, b = max(0, x), min(w, x + seg)
            if b - a > h:
                hgrad(self, a + r, 0, b - r, h, ACC1, ACC2)
                self.create_oval(a, 0, a + h, h - 1, fill=ACC1, outline=ACC1)
                self.create_oval(b - h, 0, b - 1, h - 1, fill=ACC2, outline=ACC2)
            return
        fw = max(h, w * max(0.0, min(100.0, self.pct)) / 100.0)
        end = mix(ACC1, ACC2, fw / w)
        hgrad(self, r, 0, fw - r, h, ACC1, end)
        self.create_oval(0, 0, h, h - 1, fill=ACC1, outline=ACC1)
        self.create_oval(fw - h, 0, fw - 1, h - 1, fill=end, outline=end)


class Pill(tk.Canvas):
    """Selo de estado com bolinha pulsando."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, height=34, width=200, bg=bg, highlightthickness=0, bd=0)
        self.text, self.color, self.t, self.pulse = "", MUTED, 0.0, False

    def set(self, text, color, pulse=False):
        if (text, color, pulse) != (self.text, self.color, self.pulse):
            self.text, self.color, self.pulse = text, color, pulse
            self.draw()

    def tick(self):
        if self.pulse:
            self.t = (self.t + 0.08) % 2
            self.draw()

    def draw(self):
        f = font(12, "bold")
        w = f.measure(self.text) + 48
        self.configure(width=w)
        self.delete("all")
        rrect(self, 1, 1, w - 2, 32, 16, fill=mix(BG, self.color, 0.16), outline=mix(BG, self.color, 0.45))
        k = abs(1 - self.t) if self.pulse else 1
        halo = mix(mix(BG, self.color, 0.16), self.color, 0.35 * k)
        self.create_oval(10, 9, 26, 25, fill=halo, outline="")
        self.create_oval(14, 13, 22, 21, fill=self.color, outline="")
        self.create_text(34, 17, text=self.text, anchor="w", fill=self.color, font=f)


def label(parent, text="", size=13, color=TEXT, weight="normal", bg=SURF, mono=False, **kw):
    return tk.Label(parent, text=text, fg=color, bg=bg, font=font(size, weight, mono), anchor="w", justify="left", **kw)


def caps(parent, text, bg=SURF, color=DIM):
    """Rótulo pequeno em maiúsculas."""
    return tk.Label(parent, text=" ".join(text.upper()), fg=color, bg=bg, font=font(10, "bold"), anchor="w")


def entry(parent, value="", size=16):
    """Campo de texto com respiro interno e borda que acende ao focar. Retorna (moldura, campo)."""
    box = tk.Frame(parent, bg=SURF2, highlightthickness=2, highlightbackground=LINE, highlightcolor=LINE)
    e = tk.Entry(box, font=font(size), bg=SURF2, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0,
                 highlightthickness=0, selectbackground=mix(ACC1, BG, 0.3), selectforeground="#ffffff")
    e.pack(fill="x", padx=14, pady=10)
    e.insert(0, value)
    e.bind("<FocusIn>", lambda _: box.config(highlightbackground=ACC1, highlightcolor=ACC1), add="+")
    e.bind("<FocusOut>", lambda _: box.config(highlightbackground=LINE, highlightcolor=LINE), add="+")
    box.bind("<Button-1>", lambda _: e.focus_set())
    return box, e


def ask_event(root, padrao, desc, segundos=90, on_answer=None, bring_front=None):
    """Janela 'Evento novo' no visual do painel. Chama on_answer(nome | '__IGNORAR__')."""
    top = tk.Toplevel(root, bg=BG)
    top.title("Gyroflow Auto — Evento novo")
    top.resizable(False, False)
    top.attributes("-topmost", True)
    state = {"left": segundos, "done": False}

    card = Card(top, pad=28, radius=22, width=560)
    card.pack(padx=18, pady=18)
    b = card.body
    pill = tk.Frame(b, bg=SURF)
    pill.pack(anchor="w")
    p = Pill(pill, bg=SURF)
    p.set("CARTÃO DETECTADO", ACC2, pulse=True)
    p.pack(anchor="w")
    label(b, "Evento novo", 24, TEXT, "bold").pack(anchor="w", pady=(14, 2))
    label(b, desc, 13, MUTED, wraplength=490).pack(anchor="w")
    caps(b, "Nome da pasta na área de trabalho").pack(anchor="w", pady=(20, 6))
    box, e = entry(b, padrao, 17)
    box.pack(fill="x")
    cd = label(b, "", 12, DIM)
    cd.pack(anchor="w", pady=(8, 0))
    row = tk.Frame(b, bg=SURF)
    row.pack(fill="x", pady=(22, 0))

    def answer(v):
        if state["done"]:
            return
        state["done"] = True
        top.destroy()
        if on_answer:
            on_answer(v)

    def ok(*_):
        answer(e.get().strip() or padrao)

    Button(row, "Ignorar este cartão", lambda: answer("__IGNORAR__"), "ghost").pack(side="left")
    Button(row, "Estabilizar  →", ok, "primary", padx=26).pack(side="right")
    e.bind("<Return>", ok)
    e.bind("<Escape>", lambda *_: answer("__IGNORAR__"))

    def typing(_):
        state["left"] = None
        cd.config(text="")

    e.bind("<Key>", typing, add="+")
    top.protocol("WM_DELETE_WINDOW", lambda: answer("__IGNORAR__"))

    def tick():
        if state["done"]:
            return
        p.tick()
        if state["left"] is not None:
            state["left"] -= 0.05
            if state["left"] <= 0:
                ok()
                return
            cd.config(text=f"Se ninguém responder, usa esse nome em {int(state['left']) + 1} s")
        top.after(50, tick)

    top.update_idletasks()
    w, h = top.winfo_reqwidth(), top.winfo_reqheight()
    top.geometry(f"+{(top.winfo_screenwidth() - w) // 2}+{(top.winfo_screenheight() - h) // 3}")
    top.deiconify()
    top.lift()
    if bring_front:
        bring_front()
    top.after(150, lambda: (top.focus_force(), e.focus_set(), e.select_range(0, "end")))
    tick()
    return top


class Slider(tk.Canvas):
    """Controle deslizante 0–100 com trilho em gradiente (estilo Quik)."""

    def __init__(self, parent, value=50, command=None, bg=SURF, width=300, height=28):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.value, self.command, self.h, self.enabled = int(value), command, height, True
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<Configure>", lambda e: self.draw())

    def _drag(self, e):
        if not self.enabled:
            return
        w = self.winfo_width()
        v = int(round(max(0, min(1, (e.x - 12) / max(1, w - 24))) * 100))
        if v != self.value:
            self.value = v
            self.draw()
            if self.command:
                self.command(v)

    def set(self, v):
        self.value = int(v)
        self.draw()

    def set_enabled(self, on):
        self.enabled = on
        self.configure(cursor="hand2" if on else "arrow")
        self.draw()

    def draw(self):
        w, h = self.winfo_width(), self.h
        if w < 30:
            w = int(self.cget("width"))
        self.delete("all")
        y1, y2 = h / 2 - 3, h / 2 + 3
        rrect(self, 12, y1, w - 12, y2, 3, fill=SURF2, outline="")
        x = 12 + (w - 24) * self.value / 100
        c2 = mix(ACC1, ACC2, self.value / 100)
        if self.enabled and x > 15:
            hgrad(self, 12, y1, x, y2, ACC1, c2)
        elif x > 15:
            self.create_rectangle(12, y1, x, y2, fill=DIM, outline="")
        r = 10
        self.create_oval(x - r, h / 2 - r + 1, x + r, h / 2 + r + 1, fill=mix(BG, "#000000", 0.5), outline="")
        self.create_oval(x - r, h / 2 - r, x + r, h / 2 + r, fill="#ffffff" if self.enabled else MUTED, outline="")


class Toggle(tk.Canvas):
    """Chave liga/desliga (estilo iOS)."""

    def __init__(self, parent, value=False, command=None, bg=SURF):
        super().__init__(parent, width=48, height=28, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.value, self.command = bool(value), command
        self.bind("<Button-1>", self._click)
        self.draw()

    def _click(self, e):
        self.value = not self.value
        self.draw()
        if self.command:
            self.command(self.value)

    def set(self, v):
        self.value = bool(v)
        self.draw()

    def draw(self):
        self.delete("all")
        if self.value:
            hgrad(self, 13, 2, 35, 26, ACC1, mix(ACC1, ACC2, 0.8))
            self.create_oval(1, 2, 25, 26, fill=ACC1, outline=ACC1)
            self.create_oval(23, 2, 47, 26, fill=mix(ACC1, ACC2, 0.8), outline=mix(ACC1, ACC2, 0.8))
            self.create_oval(25, 4, 45, 24, fill="#ffffff", outline="")
        else:
            rrect(self, 1, 2, 47, 26, 12, fill=SURF2, outline=LINE)
            self.create_oval(4, 5, 22, 23, fill=MUTED, outline="")
