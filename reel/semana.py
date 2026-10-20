"""Reels da semana: monta o vídeo do HeyGen com os posts da semana em cima, o Victor embaixo,
legenda palavra a palavra e uma trilha original gerada aqui mesmo (sem direitos de terceiros).

Uso:
    python reel/semana.py semana/<slug>.json                 # gera docs/reels/semana/<slug>.mp4 + .json
    python reel/semana.py semana/<slug>.json --sem-whisper   # teste sem transcrição (tempos estimados, sem legenda)

O spec vem do n8n (formulário do Reels da semana):
{
  "slug": "reels-2026-10-20-abc", "video": "semana/reels-2026-10-20-abc-raw.mp4",
  "roteiro": "texto que o avatar falou, com quebras de linha entre os blocos",
  "posts": ["2026-10-17-...", "2026-10-20-..."], "legenda": "..."
}
Layout 1080x1920: posts (slides já renderizados em docs/posts/<slug>/) em cima, legenda no meio,
o avatar recortado embaixo. A troca de slide segue o momento em que cada bloco do roteiro é falado
(tempos das palavras pelo faster-whisper). Velocidade final 1.125x e trilha com abaixamento automático
quando há voz.
"""
import argparse, html, json, math, os, pathlib, re, shutil, subprocess, sys, tempfile, unicodedata, wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reel"))
import reel as RL  # noqa: E402  (html_png, run)

OUT = ROOT / "docs" / "reels" / "semana"
W, H, FPS = 1080, 1920, 30
TOP_H = 700            # painel dos posts
CAP_Y, CAP_H = 700, 110  # faixa da legenda entre os posts e o vídeo
VID_Y, VID_S = 810, 1080  # avatar: quadrado 1080x1080
BG = "#111111"
GREEN = "#00FF88"
SPEED = float(os.environ.get("REELS_SPEED", "1.125"))
FONTS = ROOT / "node_modules" / "@fontsource" / "inter" / "files"
esc = html.escape


def fontface():
    return "".join(f"@font-face{{font-family:I;font-weight:{w};src:url('file://{FONTS}/inter-latin-{w}-normal.woff2')}}"
                   for w in (500, 800))


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", t)


STOP = set("a o e de da do das dos que em no na nos nas um uma para por com como mais menos se sem ao aos isso essa esse "
           "este esta nao sobre ja agora ainda entre pra pelo pela tambem so muito ter tem foi ser sao vai ou".split())


# ---------- transcrição ----------

def transcrever(video, tmp):
    wav = tmp / "voz.wav"
    RL.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    from faster_whisper import WhisperModel
    m = WhisperModel(os.environ.get("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    # lê o wav aqui mesmo: o decode_audio do faster-whisper quebra com versões novas do PyAV
    import numpy as np
    with wave.open(str(wav)) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, _ = m.transcribe(audio, language="pt", word_timestamps=True, vad_filter=True)
    out = []
    for s in segs:
        for w in (s.words or []):
            if w.word.strip():
                out.append({"w": w.word.strip(), "s": float(w.start), "e": float(w.end)})
    return out


def duracao(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def dims(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def inicio_dos_blocos(blocos, palavras, total):
    """Momento em que cada bloco do roteiro começa a ser falado (alinha as 5 primeiras palavras)."""
    tw = [norm(p["w"])[0] if norm(p["w"]) else "" for p in palavras]
    n_total = sum(len(norm(b)) for b in blocos) or 1
    starts, cursor, acc = [], 0, 0
    for b in blocos:
        alvo = norm(b)[:5]
        estimado = total * acc / n_total
        melhor, pos = 0, None
        for i in range(cursor, len(tw)):
            score = sum(1 for k, a in enumerate(alvo) if i + k < len(tw) and tw[i + k] == a)
            if score > melhor:
                melhor, pos = score, i
            if score == len(alvo):
                break
        if pos is not None and melhor >= min(3, len(alvo)):
            starts.append(palavras[pos]["s"]); cursor = pos + 1
        else:
            starts.append(estimado)
        acc += len(norm(b))
    starts[0] = 0.0
    for i in range(1, len(starts)):  # mantém em ordem
        starts[i] = max(starts[i], starts[i - 1] + 1.0)
    return starts


# ---------- painel de cima ----------

def card(eyebrow, title, extra=""):
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{fontface()}"
            f"body{{margin:0;width:{W}px;height:{TOP_H}px;background:{BG};font-family:I;color:#F5F3EE;display:flex;"
            f"flex-direction:column;justify-content:center;padding:0 90px;box-sizing:border-box}}"
            f".e{{color:{GREEN};font-weight:800;font-size:30px;letter-spacing:5px}}"
            f".t{{font-weight:800;font-size:74px;line-height:1.05;margin-top:24px;letter-spacing:-1px}}"
            f".b{{margin-top:44px;display:inline-block;background:{GREEN};color:#111;font-weight:800;font-size:44px;padding:22px 34px}}"
            f"</style></head><body><div class='e'>{esc(eyebrow)}</div><div class='t'>{esc(title)}</div>{extra}</body></html>")


def slide_png(slug, n, path):
    src = ROOT / "docs" / "posts" / slug / f"{n}.png"
    if not src.exists():
        return False
    RL.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf",
            f"scale=-2:{TOP_H - 40},pad={W}:{TOP_H}:(ow-iw)/2:20:color=0x111111", str(path)])
    return True


def escolher_post(bloco, posts):
    """Qual post da semana o bloco do roteiro está comentando (sobreposição de palavras)."""
    pal = set(norm(bloco)) - STOP
    melhor, alvo = 0, None
    for p in posts:
        chave = set(norm(p["tema"] + " " + p["headline"])) - STOP
        s = len(pal & chave)
        if s > melhor:
            melhor, alvo = s, p
    return alvo if melhor >= 2 else None


# ---------- legenda ----------

def legenda_png(browser, words, ativo, path):
    spans = "".join(f"<span style='padding:0 8px;{f'background:{GREEN};color:#111' if k == ativo else ''}'>{esc(w)}</span>"
                    for k, w in enumerate(words))
    doc = (f"<!doctype html><html><head><meta charset='utf-8'><style>{fontface()}html,body{{margin:0;background:transparent}}"
           f".c{{position:absolute;left:40px;right:40px;top:0;height:{CAP_H}px;display:flex;flex-wrap:wrap;align-items:center;"
           f"justify-content:center;font-family:I;font-weight:800;font-size:52px;line-height:1.05;color:#fff}}</style></head>"
           f"<body><div class='c'>{spans}</div></body></html>")
    RL.html_png(browser, doc, path, W, CAP_H, transparent=True)


# ---------- trilha original ----------

def trilha(path, segundos, semente=7):
    """Trilha ambiente original: acordes suaves (Am-F-C-G), pulso leve e chimbal discreto. 44,1 kHz, estéreo."""
    import numpy as np
    sr, bpm = 44100, 92
    rng = np.random.default_rng(semente)
    n = int(sr * (segundos + 2))
    t = np.arange(n) / sr
    beat = 60 / bpm
    bar = beat * 4
    acordes = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    pad = np.zeros(n)
    for i in range(int(math.ceil(len(t) / sr / bar)) + 1):
        a, b = int(i * bar * sr), min(n, int((i + 1) * bar * sr))
        if a >= n:
            break
        tt = t[a:b] - t[a]
        env = np.minimum(1, tt / 0.8) * np.minimum(1, (bar - tt) / 0.6)
        for m in acordes[i % 4]:
            f = hz(m)
            pad[a:b] += env * (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * 2 * f * tt + 0.3)
                               + 0.12 * np.sin(2 * np.pi * 3 * f * tt)) / 3
        f0 = hz(acordes[i % 4][0] - 12)  # baixo
        pad[a:b] += 0.5 * env * np.sin(2 * np.pi * f0 * tt)
    kick = np.zeros(n)
    hat = np.zeros(n)
    k_len = int(0.25 * sr)
    kt = np.arange(k_len) / sr
    k_wave = np.sin(2 * np.pi * (55 + 90 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 9)
    h_len = int(0.05 * sr)
    for j in range(int(len(t) / sr / beat)):
        p = int(j * beat * sr)
        if p + k_len < n and j % 2 == 0:
            kick[p:p + k_len] += k_wave
        q = int((j + 0.5) * beat * sr)
        if q + h_len < n:
            hat[q:q + h_len] += rng.standard_normal(h_len) * np.exp(-np.arange(h_len) / sr * 80)
    hat = np.diff(hat, prepend=0)  # agudo
    mix = 0.55 * pad + 0.35 * kick + 0.06 * hat
    fade = np.minimum(1, t / 1.5) * np.minimum(1, np.maximum(0, (segundos + 2 - t) / 2.5))
    mix = mix * fade
    mix = mix / (np.max(np.abs(mix)) + 1e-9) * 0.8
    esq = mix
    dirr = np.roll(mix, int(0.012 * sr))
    st = (np.stack([esq, dirr], axis=1) * 32767).astype(np.int16)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(st.tobytes())


# ---------- montagem ----------

def build(spec_path, usar_whisper, browser):
    sp = json.loads(pathlib.Path(spec_path).read_text())
    slug = sp["slug"]
    raw = ROOT / sp["video"]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=".sem-", dir=ROOT))
    try:
        total = duracao(raw)
        vw, vh = dims(raw)
        blocos = [b.strip() for b in re.split(r"\n\s*\n|\n", sp.get("roteiro", "")) if b.strip()] or ["."]
        palavras = transcrever(raw, tmp) if usar_whisper else []
        starts = inicio_dos_blocos(blocos, palavras, total) if palavras else \
            [total * sum(len(norm(b)) for b in blocos[:i]) / max(1, sum(len(norm(b)) for b in blocos)) for i in range(len(blocos))]

        posts = []
        for s in sp.get("posts", []):
            f = ROOT / "posts" / f"{s}.json"
            if f.exists():
                d = json.loads(f.read_text())
                posts.append({"slug": s, "tema": d.get("meta", {}).get("tema", ""), "headline": d["slides"][0].get("headline", "")})

        # um visual por bloco: abertura, posts citados (2 slides cada), leitura e chamada final
        cenas = []
        for i, b in enumerate(blocos):
            a = starts[i]
            z = starts[i + 1] if i + 1 < len(blocos) else total
            nb = norm(b)
            if i == 0:
                img = tmp / "c0.png"; RL.html_png(browser, card("A SEMANA EM IA · @victorslompo", sp.get("titulo") or "IA nas empresas, na prática"), img, W, TOP_H)
                cenas.append((img, a, z)); continue
            if nb[:1] == ["comenta"] or " ".join(nb).find("comenta projeto") >= 0:
                img = tmp / f"c{i}.png"
                RL.html_png(browser, card("QUER RESOLVER ISSO?", "Comenta PROJETO", f"<div><span class='b'>vssolutions.io →</span></div>"), img, W, TOP_H)
                cenas.append((img, a, z)); continue
            p = escolher_post(b, posts)
            if p:
                s1, s2 = tmp / f"s{i}a.png", tmp / f"s{i}b.png"
                ok1 = slide_png(p["slug"], 1, s1)
                ok2 = slide_png(p["slug"], 2, s2)
                if ok1 and ok2:
                    m = (a + z) / 2
                    cenas += [(s1, a, m), (s2, m, z)]; continue
                if ok1:
                    cenas.append((s1, a, z)); continue
            img = tmp / f"c{i}.png"
            RL.html_png(browser, card("MINHA LEITURA", re.split(r"(?<=[.!?:])\s", b)[0][:110]), img, W, TOP_H)
            cenas.append((img, a, z))

        lista = tmp / "top.txt"
        lista.write_text("".join(f"file '{img}'\nduration {max(0.2, z - a):.3f}\n" for img, a, z in cenas) + f"file '{cenas[-1][0]}'\n")

        # recorte do avatar: quadrado; no horizontal pega o centro, no vertical a parte de cima (rosto e tronco)
        lado = min(vw, vh)
        cx = (vw - lado) // 2
        cy = 0 if vh <= vw else int((vh - lado) * 0.3)
        inputs = ["-i", str(raw), "-f", "concat", "-safe", "0", "-i", str(lista)]
        fc = (f"color=c=0x111111:s={W}x{H}:r={FPS}:d={total:.3f}[bg];"
              f"[1:v]fps={FPS},scale={W}:{TOP_H},setsar=1[top];"
              f"[0:v]crop={lado}:{lado}:{cx}:{cy},scale={VID_S}:{VID_S},setsar=1[vid];"
              f"[bg][top]overlay=0:0[t1];[t1][vid]overlay=0:{VID_Y}:shortest=1[v0];")
        last = "v0"
        if palavras:
            # legenda como uma única faixa de imagens (rápido): cada palavra ativa vira um PNG com duração
            blank = tmp / "cap_blank.png"
            legenda_png(browser, [], -1, blank)
            itens, idx, t = [], 0, 0.0
            for c in RL.chunk_words(palavras, 3):
                ws = [w for w in c["text"].split() if w]
                tot = sum(len(w) + 1 for w in ws) or 1
                acc = max(c["s"], t)
                if acc > t:
                    itens.append((blank, acc - t))
                for j, w in enumerate(ws):
                    fim = max(acc + 0.04, c["s"] + (c["e"] - c["s"]) * sum(len(x) + 1 for x in ws[:j + 1]) / tot)
                    png = tmp / f"cap{idx}.png"; idx += 1
                    legenda_png(browser, ws, j, png)
                    itens.append((png, fim - acc)); acc = fim
                t = acc
            if total > t:
                itens.append((blank, total - t))
            capl = tmp / "cap.txt"
            capl.write_text("".join(f"file '{pth}'\nduration {d:.3f}\n" for pth, d in itens) + f"file '{blank}'\n")
            inputs += ["-f", "concat", "-safe", "0", "-i", str(capl)]
            fc += f"[2:v]fps={FPS},format=rgba[cap];[v0][cap]overlay=0:{CAP_Y}:shortest=0:eof_action=pass[vc];"
            last = "vc"
        fc += f"[{last}]setpts=PTS/{SPEED},format=yuv420p[v];[0:a]atempo={SPEED}[voz]"
        corpo = tmp / "corpo.mp4"
        RL.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[voz]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", str(corpo)])

        final_dur = duracao(corpo)
        musica = tmp / "trilha.wav"
        trilha(musica, final_dur, semente=sum(map(ord, slug)) % 1000)
        OUT.mkdir(parents=True, exist_ok=True)
        mp4 = OUT / f"{slug}.mp4"
        mix = ("[1:a]volume=0.16[m];[0:a]asplit=2[v1][v2];"
               "[m][v1]sidechaincompress=threshold=0.03:ratio=6:attack=30:release=400[md];"
               "[v2][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
        RL.run(["ffmpeg", "-y", "-v", "error", "-i", str(corpo), "-i", str(musica), "-filter_complex", mix,
                "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-maxrate", "3000k",
                "-bufsize", "6000k", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(mp4)])
        meta = {"slug": slug, "video": f"{slug}.mp4", "duracao": round(duracao(mp4), 2), "velocidade": SPEED,
                "legenda": sp.get("legenda", ""), "cenas": len(cenas), "legenda_palavra_a_palavra": bool(palavras)}
        (OUT / f"{slug}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        print(f"ok  {slug}: {meta['duracao']}s, {len(cenas)} cenas -> {mp4.relative_to(ROOT)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--sem-whisper", action="store_true")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        for s in a.specs:
            build(s, not a.sem_whisper, b)
        b.close()


if __name__ == "__main__":
    sys.exit(main())
