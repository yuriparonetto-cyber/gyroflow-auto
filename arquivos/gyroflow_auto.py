#!/usr/bin/env python3
"""
Gyroflow Auto — by Paroneto
Fica rodando em segundo plano. Quando um cartão (GoPro / DJI O4 Pro) é plugado:
  1. pergunta o nome do evento (já vem preenchido com o último)
  2. copia os brutos novos para um cache local (nunca estabiliza direto do cartão)
  3. junta os arquivos que a O4 cortou (só quando tem certeza que é corte)
  4. estabiliza com o Gyroflow (mesma resolução/fps do original, MP4 H.265 por hardware)
  5. salva em <Área de Trabalho>/<EVENTO>/ e apaga o cache
  6. registra o arquivo para nunca estabilizar de novo
Funciona no Mac e no Windows (diferenças ficam em plataforma.py).
"""
import json, os, re, shutil, signal, subprocess, sys, threading, time, traceback
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plataforma as P

HOME = P.HOME
APP_DIR = P.APP_DIR
CONFIG_FILE = APP_DIR / "config.json"
REGISTRY_FILE = APP_DIR / "estabilizados.json"
LOG_FILE = P.LOG_FILE
PID_FILE = APP_DIR / "gyroflow_auto.pid"
CACHE_ROOT = P.CACHE_ROOT
MP4_MERGE = P.tool("mp4_merge")
FFPROBE = P.tool("ffprobe")
FFMPEG = P.tool("ffmpeg")
GYROFLOW = None  # achado no main() (config "gyroflow_path" ou locais padrão)

DEFAULT_CONFIG = {
    "pasta_destino": str(P.desktop_dir()),
    "gyroflow_path": "",
    "ultimo_evento": "",
    "codec": "H.265/HEVC",          # ou "H.264/AVC"
    "renders_em_paralelo": 1,       # testado no M4 Max: 2 em paralelo fica MAIS lento
    "interpolacao": "Lanczos4",
    "audio": True,
    "sufixo": "_stabilized",
    # regra de corte da O4: 1º arquivo >= este tamanho E próximo começa até X s depois
    "o4_tamanho_corte_bytes": 3_700_000_000,
    "o4_intervalo_max_s": 3.0,
    "folga_disco_gb": 20,
    # gravações com mais de X horas de diferença = outro evento (pergunta o nome)
    "horas_novo_evento": 10,
    "eventos": [],
    "dispositivo_gpu": None,
    # suavidade do Gyroflow em %: 30 (padrão) ou 50 — muda pelo app
    "suavidade_pct": 30,
    # COR: só roda quando você pede pelo app (nunca automático)
    "lut_o4": "dlogm_rec709.cube",
    "lut_gopro": "gplog_rec709.cube",
    "lut_look": "fuji_classico.cube",
    "look_pct": 50,
    "sufixo_cor": "_COR",
}

VIDEO_RE_GOPRO = re.compile(r"^G([XHL]|OPR|P)(\d{2})?(\d{4})\.MP4$", re.I)  # GX010123 / GH010123 / GOPR0123
VIDEO_RE_DJI = re.compile(r"^DJI_(\d{14})_(\d{4})_[A-Z]\.MP4$", re.I)

log_lock = threading.Lock()


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    with log_lock:
        print(line, flush=True)
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(default, dict):
            out = dict(default)
            out.update(d)
            return out
        return d
    except Exception:
        return default.copy() if isinstance(default, dict) else default


def save_json(path, data):
    tmp = Path(f"{path}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def notify(title, msg, sound=None):
    P.notify(title, msg, sound)
    log(f"[notificação] {title}: {msg}")


def ask_event_name(default, card_desc):
    return P.ask_event_name(default, card_desc)


# ---------------------------------------------------------------- probing

def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video" and s.get("codec_name") != "mjpeg"), {})
    fmt = d.get("format", {})
    ct = fmt.get("tags", {}).get("creation_time")
    start = None
    if ct:
        try:
            start = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        except Exception:
            pass
    num, den = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    return {
        "width": int(v.get("width", 0)),
        "height": int(v.get("height", 0)),
        "fps": round(float(num) / float(den or 1), 3) if float(den or 1) else 0,
        "bitrate": int(v.get("bit_rate") or fmt.get("bit_rate") or 0),
        "duration": float(fmt.get("duration") or 0),
        "start": start,
        "has_audio": any(s.get("codec_type") == "audio" for s in d.get("streams", [])),
    }


def file_key(p: Path):
    st = p.stat()
    return f"{p.name}|{st.st_size}"


# ---------------------------------------------------------------- card scan

def scan_card(vol: Path):
    dcim = vol / "DCIM"
    if not dcim.is_dir():
        return []
    vids = []
    for sub in sorted(dcim.iterdir()):
        if not sub.is_dir():
            continue
        for f in sorted(sub.iterdir()):
            if f.name.startswith("._") or not f.is_file():
                continue
            if VIDEO_RE_DJI.match(f.name):
                vids.append(("O4", f))
            elif VIDEO_RE_GOPRO.match(f.name):
                vids.append(("GoPro", f))
    return vids


def group_files(vids, cfg):
    """Retorna lista de jobs: [{'cam':..., 'parts':[Path,...], 'info':probe}]"""
    jobs = []
    # --- DJI O4: junta só quando é corte de verdade
    dji = sorted([f for c, f in vids if c == "O4"], key=lambda p: VIDEO_RE_DJI.match(p.name).group(2))
    i = 0
    while i < len(dji):
        parts = [dji[i]]
        infos = [probe(dji[i])]
        while i + 1 < len(dji):
            cur, nxt = parts[-1], dji[i + 1]
            ci, ni = infos[-1], probe(nxt)
            big = cur.stat().st_size >= cfg["o4_tamanho_corte_bytes"]
            same = (ci["width"], ci["height"], ci["fps"]) == (ni["width"], ni["height"], ni["fps"])
            gap = None
            if ci["start"] and ni["start"]:
                gap = (ni["start"] - (ci["start"] + timedelta(seconds=ci["duration"]))).total_seconds()
            if big and same and gap is not None and -1.0 <= gap <= cfg["o4_intervalo_max_s"]:
                log(f"  corte detectado: {cur.name} -> {nxt.name} (intervalo {gap:.2f}s)")
                parts.append(nxt)
                infos.append(ni)
                i += 1
            else:
                break
        jobs.append({"cam": "O4", "parts": parts, "info": infos[0]})
        i += 1
    # --- GoPro: capítulos GX01xxxx, GX02xxxx... com o mesmo número de clipe
    gp = {}
    for c, f in vids:
        if c != "GoPro":
            continue
        m = VIDEO_RE_GOPRO.match(f.name)
        prefix, chap, clip = m.group(1).upper(), m.group(2) or "00", m.group(3)
        gp.setdefault((prefix, clip), []).append((chap, f))
    for (prefix, clip), lst in sorted(gp.items(), key=lambda kv: kv[0][1]):
        parts = [f for _, f in sorted(lst)]
        if len(parts) > 1:
            log(f"  capítulos GoPro: {', '.join(p.name for p in parts)}")
        jobs.append({"cam": "GoPro", "parts": parts, "info": probe(parts[0])})
    return jobs


# ---------------------------------------------------------------- processing

def build_preset(cfg, info, out_dir: Path, out_name: str):
    stab = {}
    try:
        pre = P.gyro_default_preset()
        if pre:
            with open(pre, encoding="utf-8") as f:
                stab = json.load(f).get("stabilization", {}) or {}
    except Exception:
        stab = {}
    pct = cfg.get("suavidade_pct")
    if pct and stab.get("smoothing_params"):
        for sp in stab["smoothing_params"]:
            if sp.get("name") == "smoothness":
                sp["value"] = float(pct) / 100.0
    mbps = info["bitrate"] / 1_000_000 if info["bitrate"] else 100
    mbps = int(min(max(round(mbps), 40), 200))
    out = {
        "codec": cfg["codec"], "codec_options": "", "bitrate": mbps, "use_gpu": True,
        "audio": bool(cfg["audio"] and info["has_audio"]), "audio_codec": "AAC",
        "interpolation": cfg["interpolacao"],
        "output_folder": P.output_folder_url(out_dir), "output_filename": out_name,
        "output_width": info["width"], "output_height": info["height"],
        "preserve_other_tracks": False, "pad_with_black": False, "export_trims_separately": False,
        "keyframe_distance": 1, "encoder_options": "",
    }
    preset = {"version": 2, "output": out}
    if stab:
        preset["stabilization"] = stab
    return json.dumps(preset), json.dumps({k: out[k] for k in ("output_folder", "output_filename", "output_width", "output_height")})


def run_gyroflow(src: Path, cfg, info, out_dir: Path, out_name: str):
    preset, params = build_preset(cfg, info, out_dir, out_name)
    cmd = [GYROFLOW, str(src), "-f", "--stdout-progress", "--preset", preset, "-p", params]
    if cfg.get("dispositivo_gpu") is not None:
        cmd += ["-b", str(cfg["dispositivo_gpu"])]
    timeout = max(900, info["duration"] * 10)
    t0 = time.time()
    P.write_status("renderizando", out_name)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                            **P.popen_group_kwargs())
    error = None
    last = ""
    for line in proc.stdout:
        last = line.strip() or last
        # O Gyroflow trava em vez de sair quando dá erro: detecta e mata
        if re.search(r"\[ERROR\] \[[0-9a-f]{8}\] Error", line) or "Unable to read the video file" in line:
            error = line.strip()
            break
        if time.time() - t0 > timeout:
            error = "timeout"
            break
    if error:
        P.kill_tree(proc)
        proc.wait()
        P.write_status("ligado")
        raise RuntimeError(f"Gyroflow falhou: {error}")
    proc.wait()
    P.write_status("ligado")
    out = out_dir / out_name
    if proc.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError(f"Gyroflow saiu com código {proc.returncode}: {last}")
    log(f"  render ok (suavidade {cfg.get('suavidade_pct')}%): {out_name} em {time.time() - t0:.0f}s ({info['duration']:.0f}s de vídeo)")
    return out


def copy_verified(src: Path, dst: Path):
    tmp = dst.with_suffix(dst.suffix + ".part")
    shutil.copy2(src, tmp)  # copia preservando datas
    if tmp.stat().st_size != src.stat().st_size:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"cópia incompleta: {src.name}")
    os.replace(tmp, dst)


class Worker:
    """Fila de render: roda N renders em paralelo, a partir do cache."""

    def __init__(self):
        self.lock = threading.Lock()
        self.sem = None
        self.active = 0
        self.done_event = threading.Event()
        self.errors = 0

    def submit(self, job, cfg, event_dir: Path, reg):
        if self.sem is None:
            self.sem = threading.Semaphore(max(1, int(cfg["renders_em_paralelo"])))
        with self.lock:
            self.active += 1
        t = threading.Thread(target=self._run, args=(job, cfg, event_dir, reg), daemon=True)
        t.start()

    def _run(self, job, cfg, event_dir, reg):
        with self.sem:
            try:
                process_cached_job(job, cfg, event_dir, reg)
            except Exception as e:
                self.errors += 1
                log(f"ERRO em {job['parts'][0].name}: {e}\n{traceback.format_exc()}")
                notify("Erro ao estabilizar", f"{job['parts'][0].name}: {e}", sound="Basso")
            finally:
                with reg_lock:
                    for k in job.get("keys", []):
                        INFLIGHT.discard(k)
                with self.lock:
                    self.active -= 1
                    if self.active == 0:
                        if self.errors:
                            notify("Terminou com erro", f"{self.errors} vídeo(s) falharam — veja o log", sound="Basso")
                        else:
                            notify("Tudo pronto", f"Estabilizados em {event_dir.name}", sound="Glass")
                        self.errors = 0


reg_lock = threading.Lock()
INFLIGHT = set()  # arquivos já na fila/cache (evita duplicar se o cartão remontar)


TRC_CODES = {"bt709": 1, "smpte170m": 6, "bt2020-10": 14, "smpte2084": 16, "arib-std-b67": 18}
PRI_CODES = {"bt709": 1, "smpte170m": 6, "bt2020": 9}
MAT_CODES = {"bt709": 1, "smpte170m": 6, "bt2020nc": 9}


def read_source_meta(path: Path):
    """Guarda as informações do bruto antes de juntar/estabilizar."""
    r = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video" and s.get("codec_name") != "mjpeg"), {})
    st = path.stat()
    return {
        "tags": d.get("format", {}).get("tags", {}),
        "pix_fmt": v.get("pix_fmt", ""),
        "range": v.get("color_range"), "trc": v.get("color_transfer"),
        "pri": v.get("color_primaries"), "mat": v.get("color_space"),
        "birth": getattr(st, "st_birthtime", st.st_mtime), "mtime": st.st_mtime,
        "name": path.name,
    }


def restore_metadata(out: Path, meta, codec):
    """Remux sem recodificar: devolve tags de cor, metadados da câmera e datas do arquivo."""
    fixed = out.with_name(out.stem + "_meta.mp4")
    cmd = [FFMPEG, "-v", "error", "-y", "-i", str(out),
           "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-map_metadata", "0", "-movflags", "+faststart+use_metadata_tags"]
    for k, v in meta["tags"].items():
        if k in ("major_brand", "minor_version", "compatible_brands", "creation_time"):
            continue
        cmd += ["-metadata", f"{k}={v}"]
    cmd += ["-metadata", f"original_filename={meta['name']}"]
    bsf = []
    if meta["trc"] in TRC_CODES:
        bsf.append(f"transfer_characteristics={TRC_CODES[meta['trc']]}")
    if meta["pri"] in PRI_CODES:
        bsf.append(f"colour_primaries={PRI_CODES[meta['pri']]}")
    if meta["mat"] in MAT_CODES:
        bsf.append(f"matrix_coefficients={MAT_CODES[meta['mat']]}")
    if meta["range"] in ("pc", "tv"):
        bsf.append(f"video_full_range_flag={1 if meta['range'] == 'pc' else 0}")
    if bsf:
        name = "hevc_metadata" if "265" in codec else "h264_metadata"
        cmd += ["-bsf:v", f"{name}={':'.join(bsf)}"]
    for flag, val in (("-color_trc", meta["trc"]), ("-color_primaries", meta["pri"]),
                      ("-colorspace", meta["mat"]), ("-color_range", meta["range"])):
        if val and val != "unknown":
            cmd += [flag, val]
    cmd += [str(fixed)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0 and fixed.exists() and fixed.stat().st_size > out.stat().st_size * 0.95:
        os.replace(fixed, out)
    else:
        fixed.unlink(missing_ok=True)
        log(f"  aviso: não consegui regravar metadados ({r.stderr[-200:]}), mantendo arquivo do Gyroflow")
    # datas do arquivo (Finder / Explorer / NLE) iguais às do bruto
    P.set_file_dates(out, meta["birth"], meta["mtime"])
    # confere 10-bit
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt",
                        "-of", "csv=p=0", str(out)], capture_output=True, text=True)
    pf = r.stdout.strip()
    if "10" in meta["pix_fmt"] and "10" not in pf:
        log(f"  ATENÇÃO: original {meta['pix_fmt']} mas saída {pf} (perdeu 10-bit)")
        notify("Atenção: saiu 8-bit", out.name, sound="Basso")


def process_cached_job(job, cfg, event_dir: Path, reg):
    cache_files = job["cache"]
    jobdir = cache_files[0].parent
    src = cache_files[0]
    meta = job.get("meta") or read_source_meta(src)
    if len(cache_files) > 1:
        merged = jobdir / (src.stem + "_JUNTO.MP4")
        log(f"  juntando {len(cache_files)} partes -> {merged.name}")
        r = subprocess.run([str(MP4_MERGE)] + [str(p) for p in cache_files] + ["--out", str(merged)],
                           capture_output=True, text=True, errors="replace")
        if r.returncode != 0 or not merged.exists():
            raise RuntimeError(f"mp4_merge falhou: {r.stdout[-300:]} {r.stderr[-300:]}")
        for p in cache_files:
            p.unlink(missing_ok=True)  # libera espaço
        src = merged
        job["info"] = probe(merged)
    out_name = src.stem + cfg["sufixo"] + ".mp4"
    rendered = run_gyroflow(src, cfg, job["info"], jobdir, out_name)
    restore_metadata(rendered, meta, cfg["codec"])
    final = event_dir / out_name
    if final.exists():
        final = event_dir / (src.stem + cfg["sufixo"] + f"_{datetime.now():%H%M%S}.mp4")
    shutil.move(str(rendered), str(final))
    with reg_lock:
        for k in job["keys"]:
            reg[k] = {"saida": str(final), "data": datetime.now().isoformat(timespec="seconds")}
        save_json(REGISTRY_FILE, reg)
    shutil.rmtree(jobdir, ignore_errors=True)  # apaga o bruto do cache
    log(f"  OK -> {final}")


def find_event(cfg, t_ini, t_fim):
    """Evento já conhecido cujas gravações estão perto (pela data/hora) destas."""
    margem = cfg["horas_novo_evento"] * 3600
    for ev in cfg.get("eventos", []):
        if t_ini <= ev["fim"] + margem and t_fim >= ev["inicio"] - margem:
            return ev
    return None


def handle_card(vol: Path, worker: Worker):
    cfg = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    vname = P.volume_label(vol)
    reg = load_json(REGISTRY_FILE, {})
    vids = scan_card(vol)
    if not vids:
        return
    with reg_lock:
        pending = [(c, f) for c, f in vids if file_key(f) not in reg and file_key(f) not in INFLIGHT]
        for _, f in pending:
            INFLIGHT.add(file_key(f))
    log(f"Cartão {vname}: {len(vids)} vídeos, {len(pending)} novos")
    if not pending:
        notify(vname, "Nada novo: tudo já foi estabilizado ou já está na fila.")
        return

    try:
        jobs = group_files(pending, cfg)
    except Exception:
        with reg_lock:
            for _, f in pending:
                INFLIGHT.discard(file_key(f))
        raise
    for job in jobs:
        job["meta"] = read_source_meta(job["parts"][0])  # infos do arquivo no cartão
        job["t"] = job["meta"]["birth"]
    jobs.sort(key=lambda j: j["t"])

    # separa por sessão de gravação: intervalo grande entre takes = outro evento
    sessions = []
    for job in jobs:
        if sessions and job["t"] - sessions[-1][-1]["t"] <= cfg["horas_novo_evento"] * 3600:
            sessions[-1].append(job)
        else:
            sessions.append([job])

    plan = []
    for sess in sessions:
        t_ini, t_fim = sess[0]["t"], sess[-1]["t"]
        ev = find_event(cfg, t_ini, t_fim)
        dia = datetime.fromtimestamp(t_ini).strftime("%d/%m/%Y %H:%M")
        if ev:
            log(f"  sessão de {dia}: evento conhecido '{ev['nome']}' (sem perguntar)")
        else:
            # só pergunta quando é evento novo; se ninguém responder, usa o nome padrão
            padrao = "Evento " + datetime.fromtimestamp(t_ini).strftime("%d-%m-%Y")
            desc = f"{vname} — {len(sess)} vídeo(s) gravados em {dia}"
            nome = ask_event_name(padrao, desc)
            if not nome:
                log(f"  sessão de {dia} ignorada pelo usuário")
                continue
            ev = next((e for e in cfg.get("eventos", []) if e["nome"] == nome), None)
            if not ev:
                ev = {"nome": nome, "inicio": t_ini, "fim": t_fim}
                cfg.setdefault("eventos", []).append(ev)
        ev["inicio"], ev["fim"] = min(ev["inicio"], t_ini), max(ev["fim"], t_fim)
        cfg["ultimo_evento"] = ev["nome"]
        save_json(CONFIG_FILE, cfg)
        plan.append((ev["nome"], sess))

    # o que o usuário ignorou volta a ficar disponível para o próximo plug
    planned = {file_key(p) for _, sess in plan for j in sess for p in j["parts"]}
    with reg_lock:
        for _, f in pending:
            if file_key(f) not in planned:
                INFLIGHT.discard(file_key(f))
    if not plan:
        return
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    all_jobs = [j for _, s in plan for j in s]
    total = sum(p.stat().st_size for j in all_jobs for p in j["parts"])
    free = shutil.disk_usage(CACHE_ROOT).free
    copy_all_first = free > total * 2 + cfg["folga_disco_gb"] * 1e9  # bruto + render
    nomes = ", ".join(sorted({n for n, _ in plan}))
    notify(nomes, f"Copiando {len(all_jobs)} vídeo(s) ({total / 1e9:.1f} GB) para o cache…")

    n = 0
    for event, sess in plan:
        event_dir = Path(cfg["pasta_destino"]) / event
        event_dir.mkdir(parents=True, exist_ok=True)
        for job in sess:
            n += 1
            jobdir = CACHE_ROOT / f"{datetime.now():%Y%m%d_%H%M%S}_{n:03d}_{job['parts'][0].stem}"
            jobdir.mkdir(parents=True, exist_ok=True)
            job["keys"] = [file_key(p) for p in job["parts"]]
            job["cache"] = []
            try:
                for p in job["parts"]:
                    dst = jobdir / p.name
                    copy_verified(p, dst)
                    job["cache"].append(dst)
            except Exception as e:
                log(f"ERRO copiando {job['parts'][0].name}: {e}")
                notify("Erro na cópia", f"{job['parts'][0].name}: {e}", sound="Basso")
                shutil.rmtree(jobdir, ignore_errors=True)
                with reg_lock:
                    for k in job["keys"]:
                        INFLIGHT.discard(k)
                continue
            log(f"  copiado [{n}/{len(all_jobs)}] {', '.join(p.name for p in job['parts'])} -> {event}")
            if copy_all_first:
                worker.submit(job, cfg, event_dir, reg)
            else:
                try:  # pouco espaço: processa um por vez
                    process_cached_job(job, cfg, event_dir, reg)
                except Exception as e:
                    log(f"ERRO: {e}")
                    notify("Erro ao estabilizar", f"{job['parts'][0].name}: {e}", sound="Basso")
                    shutil.rmtree(jobdir, ignore_errors=True)
                finally:
                    with reg_lock:
                        for k in job["keys"]:
                            INFLIGHT.discard(k)
    notify(nomes, "Cópia terminada — pode tirar o cartão. Estabilizando…", sound="Hero")


def main():
    global GYROFLOW
    APP_DIR.mkdir(parents=True, exist_ok=True)
    lock = P.SingleInstance(APP_DIR / "motor.lock")  # só UM motor rodando
    if not lock.ok:
        print("já está rodando — saindo")
        return
    PID_FILE.write_text(str(os.getpid()))
    if not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, DEFAULT_CONFIG)
    cfg = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    GYROFLOW = P.find_gyroflow(cfg)
    if not GYROFLOW:
        log("ERRO: Gyroflow não encontrado. Instale o Gyroflow ou coloque o caminho em gyroflow_path no config.json")
        notify("Gyroflow não encontrado", "Instale o Gyroflow (gyroflow.xyz) e abra o Gyroflow Auto de novo.", sound="Basso")
        P.write_status("erro", "Gyroflow não encontrado")
        return
    # limpa cache de execuções interrompidas
    if CACHE_ROOT.exists():
        for d in CACHE_ROOT.iterdir():
            shutil.rmtree(d, ignore_errors=True) if d.is_dir() else d.unlink(missing_ok=True)
    log(f"=== Gyroflow Auto iniciado ({sys.platform}) — Gyroflow: {GYROFLOW} ===")
    P.write_status("ligado")
    notify("Ligado", "Esperando cartão de memória…")
    worker = Worker()
    busy = set()

    def process(key, vol):
        try:
            handle_card(vol, worker)
        except Exception as e:
            log(f"ERRO no cartão {key}: {e}\n{traceback.format_exc()}")
            notify("Erro", str(e), sound="Basso")
        finally:
            busy.discard(key)

    def start(key, vol):
        if (vol / "DCIM").is_dir() and key not in busy:
            busy.add(key)
            threading.Thread(target=process, args=(key, vol), daemon=True).start()

    seen = P.mounted_volumes()  # cartões já plugados quando abriu: processa também
    for k, v in sorted(seen.items()):
        start(k, v)

    while True:
        time.sleep(3)
        now = P.mounted_volumes()
        for k in sorted(set(now) - set(seen)):
            time.sleep(2)  # dá tempo de montar
            start(k, now[k])
        seen = now


if __name__ == "__main__":
    def bye(*_):
        try:
            if PID_FILE.read_text().strip() == str(os.getpid()):
                PID_FILE.unlink()
            P.write_status("desligado")
        except Exception:
            pass
        sys.exit(0)
    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    main()
