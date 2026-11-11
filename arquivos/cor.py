#!/usr/bin/env python3
"""
Cor sob demanda (Gyroflow Auto) — só roda quando você pede pelo app.
Aplica: LUT de conversão (D-Log M ou GoPro Log -> Rec709) + LUT de look a X% (padrão FUJI_CLASSICO 50%).
Os dois LUTs são "assados" num LUT único para renderizar mais rápido.
Uso: python3 cor.py <pasta_ou_arquivo> [...]
"""
import json, os, re, subprocess, sys, shutil, hashlib, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plataforma as P
import gyroflow_auto as ga  # reaproveita log/notify/config

APP_DIR = P.APP_DIR
LUT_DIR = P.LUT_DIR
FFMPEG = ga.FFMPEG
FFPROBE = ga.FFPROBE


def pick_encoder(cfg):
    """Escolhe o encoder H.265 10-bit mais rápido que funciona NESTE computador (testa de verdade)."""
    if cfg.get("encoder_cor"):
        return cfg["encoder_cor"]
    if P.IS_MAC:
        cands = [("hevc_videotoolbox", ["-profile:v", "main10", "-pix_fmt", "p010le"])]
    else:
        cands = [("hevc_nvenc", ["-profile:v", "main10", "-pix_fmt", "p010le", "-preset", "p5"]),
                 ("hevc_qsv", ["-profile:v", "main10", "-pix_fmt", "p010le"]),
                 ("hevc_amf", ["-profile:v", "main10", "-pix_fmt", "p010le"])]
    cands.append(("libx265", ["-pix_fmt", "yuv420p10le", "-preset", "fast"]))
    for name, extra in cands:
        r = subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=640x480:d=0.2",
                            "-c:v", name] + extra + ["-f", "null", "-"], capture_output=True, text=True, errors="replace")
        if r.returncode == 0:
            ga.log(f"  encoder de cor escolhido: {name}")
            cfg["encoder_cor"] = {"nome": name, "args": extra}
            try:
                c = ga.load_json(ga.CONFIG_FILE, ga.DEFAULT_CONFIG); c["encoder_cor"] = cfg["encoder_cor"]; ga.save_json(ga.CONFIG_FILE, c)
            except Exception:
                pass
            return cfg["encoder_cor"]
    raise RuntimeError("nenhum encoder H.265 10-bit funcionou neste computador")


def read_cube(path):
    size, data = None, []
    dmin, dmax = [0.0] * 3, [1.0] * 3
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        u = line.upper()
        if u.startswith("LUT_3D_SIZE"):
            size = int(line.split()[-1]); continue
        if u.startswith("DOMAIN_MIN"):
            dmin = [float(x) for x in line.split()[1:4]]; continue
        if u.startswith("DOMAIN_MAX"):
            dmax = [float(x) for x in line.split()[1:4]]; continue
        if u[0].isalpha():
            continue
        p = line.split()
        if len(p) >= 3:
            data.append((float(p[0]), float(p[1]), float(p[2])))
    assert size and len(data) == size ** 3, f"LUT inválido: {path}"
    return size, data, dmin, dmax


def sample(lut, r, g, b):
    """Interpolação tetraédrica (igual ao Resolve)."""
    n, data, dmin, dmax = lut
    m = n - 1
    def norm(v, i):
        v = (v - dmin[i]) / (dmax[i] - dmin[i]) * m
        return min(max(v, 0.0), m)
    x, y, z = norm(r, 0), norm(g, 1), norm(b, 2)
    x0, y0, z0 = min(int(x), m - 1), min(int(y), m - 1), min(int(z), m - 1)
    fx, fy, fz = x - x0, y - y0, z - z0
    def P(i, j, k):
        return data[(x0 + i) + (y0 + j) * n + (z0 + k) * n * n]
    c000, c111 = P(0, 0, 0), P(1, 1, 1)
    if fx > fy:
        if fy > fz:   a, b_, w = P(1, 0, 0), P(1, 1, 0), (fx, fy, fz)
        elif fx > fz: a, b_, w = P(1, 0, 0), P(1, 0, 1), (fx, fz, fy)
        else:         a, b_, w = P(0, 0, 1), P(1, 0, 1), (fz, fx, fy)
    else:
        if fz > fy:   a, b_, w = P(0, 0, 1), P(0, 1, 1), (fz, fy, fx)
        elif fz > fx: a, b_, w = P(0, 1, 0), P(0, 1, 1), (fy, fz, fx)
        else:         a, b_, w = P(0, 1, 0), P(1, 1, 0), (fy, fx, fz)
    w1, w2, w3 = w
    return tuple(c000[i] * (1 - w1) + a[i] * (w1 - w2) + b_[i] * (w2 - w3) + c111[i] * w3 for i in range(3))


def baked_lut(conv_path, look_path, mix, size=65):
    key = hashlib.md5(f"{conv_path}|{os.path.getmtime(conv_path)}|{look_path}|"
                      f"{look_path and os.path.getmtime(look_path)}|{mix}|{size}".encode()).hexdigest()[:10]
    out = LUT_DIR / f"assado_{Path(conv_path).stem}_{key}.cube"
    if out.exists():
        return out
    ga.log(f"  assando LUT: {Path(conv_path).name} + {Path(look_path).name if look_path else '-'} {int(mix*100)}%")
    conv = read_cube(conv_path)
    look = read_cube(look_path) if look_path and mix > 0 else None
    m = size - 1
    lines = [f'TITLE "Gyroflow Auto {Path(conv_path).stem} + look {int(mix*100)}%"', f"LUT_3D_SIZE {size}"]
    for bi in range(size):
        for gi in range(size):
            for ri in range(size):
                c = sample(conv, ri / m, gi / m, bi / m)
                if look:
                    l = sample(look, *[min(max(v, 0.0), 1.0) for v in c])
                    c = tuple(c[i] * (1 - mix) + l[i] * mix for i in range(3))
                lines.append(f"{c[0]:.6f} {c[1]:.6f} {c[2]:.6f}")
    tmp = out.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    return out


def conv_for(name, cfg):
    if re.match(r"^DJI_", name, re.I):
        return LUT_DIR / cfg["lut_o4"]
    if re.match(r"^G[XHLP]", name, re.I) or name.upper().startswith("GOPR"):
        return LUT_DIR / cfg["lut_gopro"]
    return None


def apply_color(src: Path, cfg):
    out = src.with_name(src.stem + cfg["sufixo_cor"] + ".mp4")
    if out.exists():
        ga.log(f"  cor já existe: {out.name}")
        return None
    conv = conv_for(src.name, cfg)
    if not conv:
        ga.log(f"  pulei {src.name}: câmera desconhecida")
        return None
    look = LUT_DIR / cfg["lut_look"] if cfg.get("lut_look") else None
    lut = baked_lut(conv, look, cfg["look_pct"] / 100.0)
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=color_range,bit_rate:format=bit_rate,duration", "-of", "json", str(src)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(r.stdout)
    st = d["streams"][0]
    rng = "pc" if st.get("color_range") == "pc" else "tv"
    mbps = int(min(max(int(st.get("bit_rate") or d["format"].get("bit_rate") or 1e8) / 1e6, 40), 200))
    dur = float(d["format"].get("duration") or 0)
    lutname = lut.name  # rodamos dentro de LUT_DIR para não ter espaço no caminho do filtro
    g = (f"[0:v]scale=in_range={rng}:in_color_matrix=bt709:out_range=pc,format=gbrp16le,"
         f"lut3d=file={lutname}:interp=tetrahedral,"
         f"scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=p010le[v]")
    tmp = src.with_name(src.stem + cfg["sufixo_cor"] + ".part.mp4")
    enc = pick_encoder(cfg)
    hw = ["-hwaccel", "videotoolbox"] if P.IS_MAC else ["-hwaccel", "auto"]
    rate = ["-b:v", f"{mbps}M"] if enc["nome"] != "libx265" else ["-crf", "16"]
    cmd = [FFMPEG, "-v", "error", "-y"] + hw + ["-i", str(src), "-filter_complex", g,
           "-map", "[v]", "-map", "0:a?", "-c:a", "copy", "-map_metadata", "0",
           "-c:v", enc["nome"]] + [a for a in enc["args"] if a not in ("-pix_fmt", "p010le", "yuv420p10le")] + rate + ["-tag:v", "hvc1",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
           "-movflags", "+faststart+use_metadata_tags", "-metadata", f"comment=LUT {conv.stem} + {cfg.get('lut_look')} {cfg['look_pct']}%",
           str(tmp)]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(LUT_DIR), capture_output=True, text=True, errors="replace")
    if p.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(p.stderr[-300:])
    os.replace(tmp, out)
    s = src.stat()
    P.set_file_dates(out, getattr(s, "st_birthtime", s.st_mtime), s.st_mtime)
    ga.log(f"  cor ok: {out.name} em {time.time() - t0:.0f}s ({dur:.0f}s de vídeo)")
    return out


def main(args):
    cfg = ga.load_json(ga.CONFIG_FILE, ga.DEFAULT_CONFIG)
    files = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.name.endswith(cfg["sufixo"] + ".mp4"))
        elif p.is_file():
            files.append(p)
    if not files:
        ga.notify("Cor", "Nenhum vídeo estabilizado encontrado nessa pasta.")
        return
    ga.log(f"=== Cor sob demanda: {len(files)} vídeo(s) — look {cfg.get('lut_look')} {cfg['look_pct']}% ===")
    ga.notify("Aplicando cor", f"{len(files)} vídeo(s) — {cfg['look_pct']}% de look")
    ok = err = 0
    for f in files:
        try:
            if apply_color(f, cfg):
                ok += 1
        except Exception as e:
            err += 1
            ga.log(f"ERRO cor {f.name}: {e}")
    if err:
        ga.notify("Cor terminou com erro", f"{ok} ok, {err} falharam — veja o log", sound="Basso")
    else:
        ga.notify("Cor pronta", f"{ok} vídeo(s) com cor", sound="Glass")


if __name__ == "__main__":
    main(sys.argv[1:])
