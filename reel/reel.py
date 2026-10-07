"""Reels narrado diário: o carrossel do dia, em inglês, narrado pelo Kokoro (voz am_adam).

Uso:
    python reel/reel.py posts/<slug>.json             # gera docs/reels/daily/<slug>.mp4 + .srt
    python reel/reel.py posts/<slug>.json --tts dummy # teste sem Kokoro (áudio mudo, tempos estimados)

Fluxo: renderiza os slides com a tradução em inglês (mesmo template do carrossel),
narra cada slide com o Kokoro, monta o vídeo 1080x1920 com legenda grande e barra de progresso.
O texto narrado vem de traducoes.en.reel (lista de {slide, say}) quando existir;
senão é montado a partir dos próprios slides em inglês, que já passaram pela checagem de fatos.
"""
import argparse, copy, html, json, os, pathlib, re, shutil, subprocess, sys, tempfile, wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "render"))
import render as R  # noqa: E402

OUT = ROOT / "docs" / "reels" / "daily"
W, H, FPS, SR = 1080, 1920, 30, 24000
VOICE = os.environ.get("REEL_VOICE", "am_adam")
PAD = 0.35            # respiro depois de cada cena (s)
SLIDE_W, SLIDE_H = 900, 1125
SLIDE_X, SLIDE_Y = 90, 200
CAP_Y = 1370          # topo da área de legenda (fica acima da zona coberta pela interface do Instagram)


# ---------- texto ----------

def clean(t):
    t = re.sub(r"[·•→←]", " ", t or "")
    t = re.sub(r"\s+", " ", t).strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t


ORD = ["First", "Second", "Third", "Fourth"]


def lower_first(t):
    # "First, they have..." (mantém siglas e nomes: só baixa se a 2ª letra for minúscula)
    return t[0].lower() + t[1:] if len(t) > 1 and t[0].isupper() and t[1].islower() else t


def first_sentences(t, n):
    parts = re.split(r"(?<=[.!?])\s+", clean(t))
    return " ".join(parts[:n])


def narration_from_slides(slides):
    """Uma fala por slide, direto do texto em inglês do carrossel."""
    scenes = []
    for i, s in enumerate(slides, 1):
        t = s["type"]
        if t == "hook":
            say = f"{clean(s['headline'])} {clean(s.get('sub', ''))}"
        elif t == "text":
            say = f"{clean(s['headline'])} {first_sentences(s.get('body', ''), 2)}"
        elif t == "stat":
            say = f"{clean(s['stat'] + ' ' + s['label'])} {clean(s.get('sub', ''))}"
        elif t == "bullets":
            items = " ".join(f"{ORD[k]}, {lower_first(clean(x))}" for k, x in enumerate(s["items"][:4]))
            say = f"{clean(s['headline'])} {items}"
        elif t == "cta":
            say = f"{clean(s['headline'])} {clean(s.get('body', ''))}"
        else:
            say = clean(s.get("headline", ""))
        scenes.append({"slide": i, "say": re.sub(r"\s+", " ", say).strip()})
    return scenes


# ---------- voz ----------

def tts_kokoro(scenes, tmp):
    from kokoro import KPipeline
    import numpy as np
    import soundfile as sf
    pipe = KPipeline(lang_code="a")
    for k, sc in enumerate(scenes):
        chunks, words, offset = [], [], 0.0
        for res in pipe(sc["say"], voice=VOICE, speed=1.0):
            audio = res.audio.numpy() if hasattr(res.audio, "numpy") else np.asarray(res.audio)
            for tk in (getattr(res, "tokens", None) or []):
                if getattr(tk, "start_ts", None) is not None and tk.text.strip() and re.search(r"\w", tk.text):
                    words.append({"w": tk.text, "s": offset + tk.start_ts, "e": offset + (tk.end_ts or tk.start_ts)})
            chunks.append(audio)
            offset += len(audio) / SR
        wav = tmp / f"a{k}.wav"
        sf.write(wav, np.concatenate(chunks), SR)
        sc["wav"], sc["dur"] = wav, offset
        sc["words"] = words or estimate_words(sc["say"], offset)


def tts_dummy(scenes, tmp):
    """Sem Kokoro: áudio mudo com duração estimada (2,6 palavras/s). Só para testar a montagem."""
    for k, sc in enumerate(scenes):
        dur = max(2.0, len(sc["say"].split()) / 2.6)
        wav = tmp / f"a{k}.wav"
        with wave.open(str(wav), "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(b"\x00\x00" * int(dur * SR))
        sc["wav"], sc["dur"] = wav, dur
        sc["words"] = estimate_words(sc["say"], dur)


def estimate_words(text, dur):
    ws = text.split()
    total = sum(len(w) + 1 for w in ws) or 1
    out, t = [], 0.0
    for w in ws:
        d = dur * (len(w) + 1) / total
        out.append({"w": w, "s": t, "e": t + d})
        t += d
    return out


def chunk_words(words, max_words=4):
    """Agrupa as palavras em blocos curtos para a legenda (quebra também na pontuação)."""
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or re.search(r"[.,!?;:]$", w["w"]):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return [{"text": " ".join(x["w"] for x in c).strip(), "s": c[0]["s"], "e": c[-1]["e"]} for c in out]


# ---------- imagens ----------

def en_spec(spec):
    tr = (spec.get("traducoes") or {}).get("en") or {}
    if len(tr.get("slides", [])) != len(spec["slides"]):
        raise SystemExit(f"{spec['slug']}: sem tradução em inglês com o mesmo número de slides")
    s = copy.deepcopy(spec)
    s["slides"] = copy.deepcopy(tr["slides"])
    s["slides"][0]["swipe"] = "AI Radar"
    s["footer"] = "Victor Slompo · vssolutions.io"
    s["footer_last"] = "Victor Slompo · vssolutions.io/radar"
    s["story_pergunta"] = None
    return s, tr


def render_slides(spec, browser, tmp):
    old = R.OUT_DIR
    R.OUT_DIR = tmp
    try:
        p = tmp / "spec.json"
        p.write_text(json.dumps(spec, ensure_ascii=False))
        R.render(str(p), browser)
    finally:
        R.OUT_DIR = old
    return tmp / spec["slug"]


def html_png(browser, doc, path, w, h, transparent=False):
    pg = browser.new_page(viewport={"width": w, "height": h})
    f = path.with_suffix(".html")
    f.write_text(doc)
    pg.goto(f"file://{f}")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(100)
    pg.screenshot(path=str(path), omit_background=transparent)
    pg.close()
    f.unlink()


def base_png(browser, path):
    doc = (f"<!doctype html><html><head><meta charset='utf-8'><style>{R.fontface()}"
           f"html,body{{margin:0;background:#1A1A1A}}"
           f".t{{position:absolute;left:90px;top:112px;font-family:Inter;font-weight:800;font-size:28px;letter-spacing:5px;color:#00FF88}}"
           f".u{{position:absolute;right:90px;top:112px;font-family:Inter;font-weight:600;font-size:26px;color:#8A8A8A}}"
           f"</style></head><body><div class='t'>AI RADAR · DAILY</div><div class='u'>@victorslompo</div></body></html>")
    html_png(browser, doc, path, W, H)


def caption_png(browser, text, path):
    doc = (f"<!doctype html><html><head><meta charset='utf-8'><style>{R.fontface()}"
           f"html,body{{margin:0;background:transparent}}"
           f".c{{position:absolute;left:60px;right:60px;top:0;height:200px;display:flex;align-items:center;justify-content:center;"
           f"text-align:center;font-family:Inter;font-weight:800;font-size:64px;line-height:1.1;color:#FFFFFF;"
           f"letter-spacing:-1px;text-shadow:0 4px 18px rgba(0,0,0,.6)}}"
           f"</style></head><body><div class='c'>{html.escape(text)}</div></body></html>")
    html_png(browser, doc, path, W, 200, transparent=True)


# ---------- vídeo ----------

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise SystemExit("ffmpeg falhou")


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build(spec_path, tts, browser):
    spec = json.loads(pathlib.Path(spec_path).read_text())
    slug = spec["slug"]
    spec_en, tr = en_spec(spec)
    scenes = tr.get("reel") or narration_from_slides(spec_en["slides"])
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=".reel-", dir=ROOT))  # dentro do repo: o render imprime caminhos relativos a ele
    try:
        slides_dir = render_slides(spec_en, browser, tmp)
        (tts_kokoro if tts == "kokoro" else tts_dummy)(scenes, tmp)
        base = tmp / "base.png"
        base_png(browser, base)

        total = sum(sc["dur"] + PAD for sc in scenes)
        t0, clips, srt = 0.0, [], []
        for k, sc in enumerate(scenes):
            D = sc["dur"] + PAD
            caps = chunk_words(sc["words"])
            inputs = ["-loop", "1", "-t", f"{D:.3f}", "-i", str(base),
                      "-loop", "1", "-t", f"{D:.3f}", "-i", str(slides_dir / f"{sc['slide']}.png")]
            for j, c in enumerate(caps):
                p = tmp / f"c{k}_{j}.png"
                caption_png(browser, c["text"], p)
                inputs += ["-loop", "1", "-t", f"{D:.3f}", "-i", str(p)]
                srt.append((t0 + c["s"], t0 + c["e"], c["text"]))
            frames = int(D * FPS) + 1
            fc = (f"[1:v]scale={int(SLIDE_W * 1.25)}:-1,zoompan=z='min(1+0.05*on/{frames},1.05)':x='iw/2-(iw/zoom/2)':"
                  f"y='ih/2-(ih/zoom/2)':d={frames}:s={SLIDE_W}x{SLIDE_H}:fps={FPS}[sl];"
                  f"[0:v][sl]overlay={SLIDE_X}:{SLIDE_Y}[v0];"
                  f"color=c=0x00FF88:s={W}x10:r={FPS}:d={D:.3f}[bar];"
                  f"[v0][bar]overlay=x='-W+W*({t0:.3f}+t)/{total:.3f}':y={H - 10}[v1];")
            last = "v1"
            for j, c in enumerate(caps):
                end = caps[j + 1]["s"] if j + 1 < len(caps) else D
                fc += f"[{last}][{j + 2}:v]overlay=0:{CAP_Y}:enable='between(t,{c['s']:.3f},{end:.3f})'[w{j}];"
                last = f"w{j}"
            fc += f"[{last}]format=yuv420p,fps={FPS}[out]"
            clip = tmp / f"v{k}.mp4"
            run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[out]", "-t", f"{D:.3f}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), str(clip)])
            clips.append(clip)
            t0 += D

        # áudio: cada fala seguida do respiro, na mesma ordem das cenas
        alist = tmp / "a.txt"
        sil = tmp / "pad.wav"
        with wave.open(str(sil), "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(b"\x00\x00" * int(PAD * SR))
        alist.write_text("".join(f"file '{sc['wav']}'\nfile '{sil}'\n" for sc in scenes))
        audio = tmp / "a.wav"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alist), "-ar", str(SR), "-ac", "1", str(audio)])
        vlist = tmp / "v.txt"
        vlist.write_text("".join(f"file '{c}'\n" for c in clips))

        OUT.mkdir(parents=True, exist_ok=True)
        mp4 = OUT / f"{slug}.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(vlist), "-i", str(audio),
             "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-maxrate", "5M",
             "-bufsize", "12M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
             "-movflags", "+faststart", "-shortest", str(mp4)])
        (OUT / f"{slug}.srt").write_text("".join(
            f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(srt, 1)))
        meta = {"slug": slug, "video": f"{slug}.mp4", "duration": round(total, 2), "voice": VOICE, "tts": tts,
                "caption": tr.get("caption", ""), "scenes": [{"slide": s["slide"], "say": s["say"]} for s in scenes]}
        (OUT / f"{slug}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        print(f"ok  {slug}: {len(scenes)} cenas, {total:.1f}s -> {mp4.relative_to(ROOT)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--tts", choices=["kokoro", "dummy"], default="kokoro")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
        for sp in a.specs:
            spec = json.loads(pathlib.Path(sp).read_text())
            if len(((spec.get("traducoes") or {}).get("en") or {}).get("slides", [])) != len(spec.get("slides", [])):
                print(f"pulado {sp}: sem tradução em inglês")
                continue
            build(sp, a.tts, b)
        b.close()


if __name__ == "__main__":
    sys.exit(main())
