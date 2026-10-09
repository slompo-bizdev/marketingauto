"""Deep Dive do meio-dia: segunda pesquisa sobre o assunto da manhã, em vídeo 9:16 (estilo C · Data Sheet).

Uso:
    python reel/deepdive.py deepdive/<slug>.json             # gera docs/reels/deepdive/<slug>.mp4 + .srt + .json
    python reel/deepdive.py deepdive/<slug>.json --tts dummy # teste sem Kokoro (áudio mudo, tempos estimados)

O spec vem do n8n (pesquisa + checagem de fatos). Formato:
{
  "slug": "...", "topic": "DECISIONS API", "keyword": "AGENTES",
  "hook":  {"claim": "10× faster.", "line": "Now the numbers around it.", "say": "..."},
  "findings": [  # exatamente 3
    {"label": "SPEED", "big": "10×", "headline": "...", "detail": "...",          # detail opcional
     "bars": [{"label": "...", "value": 1, "display": "1×", "kind": "solid|accent|dashed"}],  # opcional
     "source": 1, "say": "...", "status": "confirmed|unconfirmed"}   # unconfirmed: máx. 1, vira "CLAIMED · NOT CONFIRMED"
  ],
  "take": {"headline": "...", "say": "..."},
  "sources": [{"n": 1, "title": "...", "url": "https://..."}],
  "caption": "...", "first_comment": "...",
  "cta": {"keyword": "CHECK", "line": "I will DM you what I find"},  # opcional (dia com dado não confirmado)
  "check_dm": "..."                                                  # texto da DM para quem comentar CHECK
}
Cenas: abertura, 3 descobertas e a leitura do Victor são narradas (Kokoro am_adam, legenda palavra a palavra).
A última cena (CTA vssolutions.io) é muda: só o botão pulsando e o "link in bio" piscando.
"""
import argparse, html, json, os, pathlib, re, shutil, subprocess, sys, tempfile, wave
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reel"))
import reel as RL  # noqa: E402  (reaproveita voz, legenda e ffmpeg do Reels narrado)

OUT = ROOT / "docs" / "reels" / "deepdive"
FONTS = ROOT / "node_modules"
W, H, FPS, SR = RL.W, RL.H, RL.FPS, RL.SR
GROUND, ACCENT = "#1F3BD6", "#FFE14D"
PAD = 0.3
CAP_Y = 1300          # faixa da legenda (acima da interface do Instagram)
BAR_X, BAR_Y, BAR_W, BAR_H = 72, 1560, W - 144, 14
CTA_SECONDS, CTA_BLINK = 3.2, 0.4
esc = html.escape


def fontface():
    a = FONTS / "@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2"
    m = FONTS / "@fontsource/ibm-plex-mono/files"
    return (f"@font-face{{font-family:Archivo;font-weight:100 900;font-stretch:62% 125%;src:url('file://{a}')}}"
            f"@font-face{{font-family:Plex;font-weight:400;src:url('file://{m}/ibm-plex-mono-latin-400-normal.woff2')}}"
            f"@font-face{{font-family:Plex;font-weight:600;src:url('file://{m}/ibm-plex-mono-latin-600-normal.woff2')}}")


def page(body, transparent=False, h=H):
    bg = "transparent" if transparent else GROUND
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{fontface()}"
            f"html,body{{margin:0;background:{bg}}}"
            f".r{{position:relative;width:{W}px;height:{h}px;overflow:hidden;color:#fff;font-family:Archivo,sans-serif;-webkit-font-smoothing:antialiased}}"
            f".a{{position:absolute;box-sizing:border-box}}"
            f".mono{{font-family:Plex,monospace;letter-spacing:1px}}"
            f".cond{{font-stretch:62%;font-weight:900;text-transform:uppercase}}"
            f".semi{{font-stretch:75%;font-weight:800;text-transform:uppercase}}"
            f"</style></head><body><div class='r'>{body}</div></body></html>")


def header(left, right, grid=None):
    if grid:
        cells = "".join(f"<div style='padding:14px 0;display:flex;flex-direction:column;gap:6px'>"
                        f"<span style='opacity:.7'>{esc(k)}</span><span>{esc(v)}</span></div>" for k, v in grid)
        return (f"<div class='a mono' style='left:72px;right:72px;top:150px;display:grid;grid-template-columns:repeat(3,1fr);"
                f"border-top:2px solid #fff;font-size:22px'>{cells}</div>")
    return (f"<div class='a mono' style='left:72px;right:72px;top:150px;display:flex;justify-content:space-between;"
            f"border-top:2px solid #fff;padding-top:14px;font-size:22px'><span>{esc(left)}</span><span>{esc(right)}</span></div>")


def footer(text):
    return (f"<div class='a mono' style='left:72px;top:1600px;font-size:24px;white-space:nowrap;overflow:hidden;"
            f"text-overflow:ellipsis;right:72px'>{esc(text)}</div>"
            f"<div class='a' style='left:{BAR_X}px;top:{BAR_Y}px;width:{BAR_W}px;height:{BAR_H}px;border:2px solid rgba(255,255,255,.5)'></div>")


def fit(text, big, small, limit):
    """Tamanho de fonte simples pelo comprimento do texto."""
    return big if len(text) <= limit else max(small, int(big * limit / len(text)))


def scene_hook(sp):
    hk, fs = sp["hook"], sp["findings"]
    chips = "".join(f"<span style='border:2px solid #fff;padding:8px 14px'>{i:02d} {esc(f['label'][:14])}</span>"
                    for i, f in enumerate(fs, 1))
    line = f"This morning: {hk['claim']}"
    return page(
        header("", "", grid=[("SERIES", "DEEP DIVE"), ("TOPIC", sp["topic"][:18]), ("DATA POINTS", f"{len(fs):02d}")])
        + "<div class='a cond' style='left:60px;right:140px;top:330px;font-size:300px;line-height:.8;letter-spacing:-4px'>Deep<br>dive</div>"
        + f"<div class='a' style='left:72px;right:140px;top:860px;display:flex;flex-direction:column;gap:28px'>"
          f"<div class='semi' style='font-size:{fit(line + hk['line'], 72, 52, 70)}px;line-height:1'>{esc(line)}<br>"
          f"<span style='color:{ACCENT}'>{esc(hk['line'])}</span></div>"
          f"<div class='mono' style='display:flex;flex-wrap:wrap;gap:12px;font-size:24px'>{chips}</div></div>"
        + footer("@victorslompo · sources in first comment"))


def bars_html(bars):
    top = max(b["value"] for b in bars) or 1
    out = ""
    for b in bars:
        pct = max(4, 100 * b["value"] / top)
        if b.get("kind") == "dashed":
            bar = (f"<div style='width:{pct:.1f}%;height:44px;border:3px dashed #fff;box-sizing:border-box'></div>")
        else:
            col = ACCENT if b.get("kind") == "accent" else "#fff"
            bar = f"<div style='width:{pct:.1f}%;height:44px;background:{col}'></div>"
        out += (f"<div style='display:flex;flex-direction:column;gap:10px'><div style='display:flex;justify-content:space-between;gap:20px'>"
                f"<span>{esc(b['label'])}</span><span>{esc(b.get('display', ''))}</span></div>{bar}</div>")
    return f"<div class='mono' style='display:flex;flex-direction:column;gap:30px;font-size:24px'>{out}</div>"


def scene_finding(sp, i):
    f = sp["findings"][i]
    src = next((s for s in sp["sources"] if s["n"] == f.get("source")), None)
    dom = urlparse(src["url"]).netloc.replace("www.", "") if src else ""
    big = f["big"]
    unconf = f.get("status") == "unconfirmed"
    if unconf:
        # dado que a checagem não confirmou: número vazado e carimbo "CLAIMED · NOT CONFIRMED"
        num = (f"<div style='display:flex;align-items:flex-end;gap:28px;flex-wrap:wrap'>"
               f"<div class='cond' style='font-size:{fit(big, 300, 160, 4)}px;line-height:.85;letter-spacing:-6px;color:transparent;"
               f"-webkit-text-stroke:4px {ACCENT}'>{esc(big)}</div>"
               f"<div class='mono' style='border:3px dashed {ACCENT};color:{ACCENT};font-size:26px;font-weight:600;padding:10px 16px;"
               f"transform:rotate(-4deg);margin-bottom:24px'>CLAIMED · NOT CONFIRMED</div></div>")
    else:
        num = f"<div class='cond' style='font-size:{fit(big, 330, 170, 4)}px;line-height:.85;letter-spacing:-6px;color:{ACCENT}'>{esc(big)}</div>"
    body = num + f"<div class='semi' style='font-size:{fit(f['headline'], 60, 44, 60)}px;line-height:1.02'>{esc(f['headline'])}</div>"
    extra = ""
    if f.get("bars"):
        extra = bars_html(f["bars"])
    elif f.get("detail"):
        extra = (f"<div style='font-size:40px;line-height:1.25;font-weight:500;font-stretch:90%;border-top:2px solid rgba(255,255,255,.5);"
                 f"padding-top:24px'>{esc(f['detail'])}</div>")
    return page(
        header(f"DATA POINT {i + 1:02d} / {len(sp['findings']):02d}", f["label"] + (" · UNCONFIRMED" if unconf else ""))
        + f"<div class='a' style='left:72px;right:140px;top:260px;display:flex;flex-direction:column;gap:28px'>{body}</div>"
        + (f"<div class='a' style='left:72px;right:140px;top:860px'>{extra}</div>" if extra else "")
        + footer((f"[{f.get('source')}] {dom}" + (" · not confirmed on the page" if unconf else "")) if dom else "@victorslompo"))


def scene_take(sp):
    t = sp["take"]["headline"]
    return page(
        header("BOTTOM LINE", "MY TAKE")
        + f"<div class='a' style='left:72px;right:140px;top:300px;display:flex;flex-direction:column;gap:40px'>"
          f"<div class='mono' style='font-size:26px;color:{ACCENT}'>BASED ON 3 DATA POINTS</div>"
          f"<div class='cond' style='font-size:{fit(t, 150, 96, 60)}px;line-height:.92;font-stretch:70%'>{esc(t)}</div></div>"
        + footer("@victorslompo"))


def scene_cta(sp, on):
    scale = 1.05 if on else 1.0
    return page(
        header("BOTTOM LINE", "03 / 03 ✓")
        + f"<div class='a' style='left:72px;right:140px;top:300px;display:flex;flex-direction:column;gap:44px'>"
          f"<div class='cond' style='font-size:220px;line-height:.85;color:{ACCENT}'>More<br>data →</div>"
          f"<div style='font-size:46px;font-weight:600;font-stretch:85%;line-height:1.2'>Every source and the daily AI Radar:</div>"
          f"<div style='transform:scale({scale});transform-origin:center;display:flex;align-items:center;justify-content:space-between;"
          f"background:{ACCENT};color:{GROUND};padding:40px 48px;font-size:84px;font-weight:900;font-stretch:75%;text-transform:uppercase'>"
          f"<span>vssolutions.io</span><svg width='76' height='76' viewBox='0 0 24 24' fill='none' stroke='{GROUND}' stroke-width='2.6' "
          f"stroke-linecap='square'><path d='M5 12h14M13 6l6 6-6 6'/></svg></div>"
          f"<div class='mono' style='display:flex;flex-wrap:wrap;row-gap:14px;gap:16px;align-items:center;font-size:28px'>"
          f"<span style='background:#fff;color:{GROUND};padding:8px 14px;font-weight:600;white-space:nowrap;opacity:{1 if on else .25}'>LINK IN BIO</span>"
          f"<span>{cta_line(sp)}</span></div></div>"
        + footer("@victorslompo"))


def cta_line(sp):
    cta = sp.get("cta") or {}
    if cta.get("keyword"):  # dia com dado não confirmado: CTA puxa conversa sobre ele
        return f"or comment {esc(cta['keyword'])} → {esc(cta.get('line') or 'I will DM you what I find')}"
    return f"or comment {esc(sp['keyword'])} → DM"


def caption_doc(words, active):
    spans = "".join(
        f"<span style='padding:0 10px;{f'background:{ACCENT};color:{GROUND}' if k == active else ''}'>{esc(w)}</span>"
        for k, w in enumerate(words))
    return page(f"<div class='a semi' style='left:62px;right:130px;top:0;height:220px;display:flex;flex-wrap:wrap;align-content:center;"
                f"row-gap:10px;font-size:70px;line-height:1'>{spans}</div>", transparent=True, h=220)


def build(spec_path, tts, browser):
    sp = json.loads(pathlib.Path(spec_path).read_text())
    slug = sp["slug"]
    if len(sp.get("findings", [])) != 3:
        raise SystemExit(f"{slug}: o deep dive precisa de exatamente 3 descobertas")
    docs = [scene_hook(sp)] + [scene_finding(sp, i) for i in range(3)] + [scene_take(sp)]
    says = [sp["hook"]["say"]] + [f["say"] for f in sp["findings"]] + [sp["take"]["say"]]
    scenes = [{"say": re.sub(r"\s+", " ", s).strip()} for s in says]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=".dd-", dir=ROOT))
    try:
        (RL.tts_kokoro if tts == "kokoro" else RL.tts_dummy)(scenes, tmp)
        spoken = sum(sc["dur"] + PAD for sc in scenes)
        total = spoken + CTA_SECONDS
        t0, clips, srt = 0.0, [], []
        for k, (doc, sc) in enumerate(zip(docs, scenes)):
            D = sc["dur"] + PAD
            bg = tmp / f"s{k}.png"
            RL.html_png(browser, doc, bg, W, H)
            inputs = ["-loop", "1", "-t", f"{D:.3f}", "-i", str(bg)]
            fc = (f"color=c={ACCENT.replace('#', '0x')}:s={BAR_W}x{BAR_H}:r={FPS}:d={D:.3f}[bar];"
                  f"[0:v][bar]overlay=x='{BAR_X - BAR_W}+{BAR_W}*({t0:.3f}+t)/{total:.3f}':y={BAR_Y}[b0];"
                  f"color=c={GROUND.replace('#', '0x')}:s={BAR_X}x{BAR_H}:r={FPS}:d={D:.3f}[mask];"
                  f"[b0][mask]overlay=0:{BAR_Y}[v0];")
            last, n = "v0", 1
            for c in RL.chunk_words(sc["words"], 3):
                ws = [w for w in re.split(r"\s+", c["text"]) if w]
                srt.append((t0 + c["s"], t0 + c["e"], c["text"]))
                # tempo de cada palavra dentro do bloco (proporcional ao tamanho)
                tot = sum(len(w) + 1 for w in ws) or 1
                ts, acc = [], c["s"]
                for w in ws:
                    ts.append(acc); acc += (c["e"] - c["s"]) * (len(w) + 1) / tot
                for j, w in enumerate(ws):
                    p = tmp / f"c{k}_{n}.png"
                    RL.html_png(browser, caption_doc(ws, j), p, W, 220, transparent=True)
                    a = ts[j]
                    b = ts[j + 1] if j + 1 < len(ws) else None
                    inputs += ["-loop", "1", "-t", f"{D:.3f}", "-i", str(p)]
                    srt_end = b if b is not None else c["e"]
                    fc += f"[{last}][{n}:v]overlay=0:{CAP_Y}:enable='between(t,{a:.3f},{srt_end:.3f})'[w{n}];"
                    last = f"w{n}"; n += 1
            fc += f"[{last}]format=yuv420p,fps={FPS}[out]"
            clip = tmp / f"v{k}.mp4"
            RL.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[out]", "-t", f"{D:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), str(clip)])
            clips.append(clip)
            t0 += D

        # CTA mudo: dois estados alternando (botão pulsa, "link in bio" pisca)
        on, off = tmp / "cta1.png", tmp / "cta0.png"
        RL.html_png(browser, scene_cta(sp, True), on, W, H)
        RL.html_png(browser, scene_cta(sp, False), off, W, H)
        steps = int(CTA_SECONDS / CTA_BLINK)
        clist = tmp / "cta.txt"
        clist.write_text("".join(f"file '{on if s % 2 == 0 else off}'\nduration {CTA_BLINK}\n" for s in range(steps))
                         + f"file '{off}'\n")
        cta = tmp / "cta.mp4"
        RL.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(clist),
                "-filter_complex", f"[0:v]fps={FPS},format=yuv420p,scale={W}:{H}[c];"
                f"color=c={ACCENT.replace('#', '0x')}:s={BAR_W}x{BAR_H}:r={FPS}:d={CTA_SECONDS}[bar];"
                f"[c][bar]overlay={BAR_X}:{BAR_Y}[out]",
                "-map", "[out]", "-t", f"{CTA_SECONDS}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-r", str(FPS), str(cta)])
        clips.append(cta)

        sil = tmp / "pad.wav"
        tail = tmp / "tail.wav"
        for path, secs in ((sil, PAD), (tail, CTA_SECONDS)):
            with wave.open(str(path), "w") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes(b"\x00\x00" * int(secs * SR))
        alist = tmp / "a.txt"
        alist.write_text("".join(f"file '{sc['wav']}'\nfile '{sil}'\n" for sc in scenes) + f"file '{tail}'\n")
        audio = tmp / "a.wav"
        RL.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alist), "-ar", str(SR), "-ac", "1", str(audio)])
        vlist = tmp / "v.txt"
        vlist.write_text("".join(f"file '{c}'\n" for c in clips))

        OUT.mkdir(parents=True, exist_ok=True)
        mp4 = OUT / f"{slug}.mp4"
        RL.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(vlist), "-i", str(audio),
                "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-maxrate", "5M",
                "-bufsize", "12M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                "-movflags", "+faststart", "-shortest", str(mp4)])
        (OUT / f"{slug}.srt").write_text("".join(
            f"{i}\n{RL.srt_time(a)} --> {RL.srt_time(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(srt, 1)))
        meta = {"slug": slug, "video": f"{slug}.mp4", "duration": round(total, 2), "voice": RL.VOICE, "tts": tts,
                "caption": sp.get("caption", ""), "first_comment": sp.get("first_comment", ""),
                "keyword": (sp.get("cta") or {}).get("keyword") or sp.get("keyword", ""), "check_dm": sp.get("check_dm", ""),
                "scenes": [sc["say"] for sc in scenes]}
        (OUT / f"{slug}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        print(f"ok  {slug}: {total:.1f}s -> {mp4.relative_to(ROOT)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--tts", choices=["kokoro", "dummy"], default="kokoro")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    ap.add_argument("--frames", help="só salva os PNGs das cenas nesta pasta (prévia)")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
        for sp_path in a.specs:
            if a.frames:
                sp = json.loads(pathlib.Path(sp_path).read_text())
                d = pathlib.Path(a.frames); d.mkdir(parents=True, exist_ok=True)
                docs = [scene_hook(sp)] + [scene_finding(sp, i) for i in range(3)] + [scene_take(sp), scene_cta(sp, True)]
                for k, doc in enumerate(docs):
                    RL.html_png(b, doc, d / f"{k}.png", W, H)
                RL.html_png(b, caption_doc(["the", "vendor", "number"], 1), d / "cap.png", W, 220, transparent=True)
                continue
            build(sp_path, a.tts, b)
        b.close()


if __name__ == "__main__":
    sys.exit(main())
