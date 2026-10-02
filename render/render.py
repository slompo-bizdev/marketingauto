"""VS Content — gerador de carrosséis a partir de um spec JSON (sem Orshot, sem custo).

Uso:
    python render/render.py posts/2026-10-02-geo-workshop.json            # gera docs/posts/<slug>/
    python render/render.py posts/*.json --only-changed                   # usado no GitHub Actions

Cada spec descreve os slides (hook, text, bullets, stat, cta), a paleta (ciclo de cores)
e a legenda. Saída: 1.png..N.png (1080x1350), story.png (1080x1920) e meta.json.
"""
import argparse, html, json, os, pathlib, sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = ROOT / "node_modules" / "@fontsource"
OUT_DIR = ROOT / "docs" / "posts"

COLORS = {
    "black": "#0A0A0A", "white": "#FFFFFF", "offwhite": "#F5F5F2",
    "green": "#00FF88", "tiffany": "#81D8D0", "yellow": "#FFE600", "red": "#FF1E1E",
}
K, W = COLORS["black"], COLORS["white"]
W_, H_ = 1080, 1350


def col(c):
    return COLORS.get(c, c)


def is_dark(hex_):
    h = hex_.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.2


class Theme:
    """Cores de uma página: fundo, texto, texto secundário, acento."""

    def __init__(self, bg, accent):
        self.bg = bg
        self.dark = is_dark(bg)
        if self.dark:
            self.text, self.body, self.muted, self.accent = W, "#B5B5B5", "#8A8A8A", accent
            self.pill_fg, self.pill_bg = K, accent
            self.num = accent
        else:
            self.text, self.body, self.muted, self.accent = K, "#1A1A1A", K, K
            # em fundo claro neutro o acento vira etiqueta; em fundo colorido, etiqueta preta
            if bg.upper() in (COLORS["offwhite"].upper(), W.upper()):
                self.pill_fg, self.pill_bg, self.muted, self.body = K, accent, "#8A8A8A", "#3A3A3A"
            else:
                self.pill_fg, self.pill_bg = bg, K
            self.num = K


# ---------- blocos de HTML ----------

def box(x, y, w, h, text, size, weight, color, lh=1.2, ls=0, font="Inter", fit=False, minsize=None, extra=""):
    t = html.escape(text).replace("\n", "<br>")
    fitattr = f'data-fit="1" data-min="{minsize or size // 2}"' if fit else ""
    return (f'<div class="b" {fitattr} style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'font-family:{font};font-size:{size}px;font-weight:{weight};color:{color};line-height:{lh};'
            f'letter-spacing:{ls}px;{extra}">{t}</div>')


def pill(text, th):
    return (f'<div class="b" style="left:96px;top:96px;height:40px;display:flex;align-items:center;">'
            f'<span style="font-family:Inter;font-size:26px;font-weight:800;letter-spacing:4px;color:{th.pill_fg};'
            f'background:{th.pill_bg};border-radius:4px;padding:2px 8px">{html.escape(text)}</span></div>')


def footer(spec, i, n, th, right=None):
    r = right or f"{i:02d} / {n:02d}"
    rc = th.accent if (th.dark and not right) else (th.accent if th.dark else K)
    left = spec.get("footer_last", spec["footer"]) if i == n else spec["footer"]
    return (box(96, 1230, 640, 40, left, 24, 600, th.muted, extra="display:flex;align-items:center")
            + box(704, 1230, 280, 40, r, 26 if right else 24, 800 if right else 600, rc,
                  extra="display:flex;align-items:center;justify-content:flex-end"))


def hazard():
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='1080' height='48'><defs><pattern id='p' width='56' "
           "height='56' patternUnits='userSpaceOnUse' patternTransform='rotate(45)'><rect width='28' height='56' "
           "fill='#0A0A0A'/></pattern></defs><rect width='1080' height='48' fill='#FFE600'/>"
           "<rect width='1080' height='48' fill='url(#p)'/></svg>")
    import urllib.parse
    return (f'<img class="b" style="left:0;top:1302px;width:1080px;height:48px" '
            f'src="data:image/svg+xml,{urllib.parse.quote(svg)}">')


def bullets(items, th, highlight_last):
    out, ys = "", [580, 790, 1000][: len(items)]
    for k, (y, txt) in enumerate(zip(ys, items)):
        last = highlight_last and k == len(items) - 1
        out += box(96, y, 110, 60, f"{k + 1:02d}", 38, 800, th.num, font="'JetBrains Mono'")
        color = th.accent if (last and th.dark) else th.text
        out += box(220, y, 764, 170, txt, 36, 700 if last else 500, color, lh=1.3, fit=True, minsize=24)
    return out


# ---------- tipos de slide ----------

def s_hook(s, th, spec, i, n):
    return (pill(s["eyebrow"], th)
            + box(96, 300, 888, 520, s["headline"], 112, 900, th.text, lh=1, ls=-3, fit=True, minsize=52)
            + box(96, 880, 888, 180, s.get("sub", ""), 48, 700, th.accent if th.dark else th.text, lh=1.2, fit=True, minsize=28)
            + footer(spec, i, n, th, right=s.get("swipe", "Arrasta →")))


def s_text(s, th, spec, i, n):
    return (pill(s["eyebrow"], th)
            + box(96, 260, 888, 380, s["headline"], 72, 800, th.text, lh=1.06, ls=-1.5, fit=True, minsize=40)
            + box(96, 700, 888, 420, s["body"], 38, 400, th.body, lh=1.4, fit=True, minsize=24)
            + footer(spec, i, n, th))


def s_bullets(s, th, spec, i, n):
    return (pill(s["eyebrow"], th)
            + box(96, 240, 888, 300, s["headline"], 64, 800, th.text, lh=1.08, ls=-1, fit=True, minsize=36)
            + bullets(s["items"], th, s.get("highlight_last", False))
            + footer(spec, i, n, th))


def s_stat(s, th, spec, i, n):
    stat_color = th.accent if th.dark else K
    return (pill(s["eyebrow"], th)
            + box(96, 300, 888, 360, s["stat"], s.get("stat_size", 300), 800, stat_color, lh=1, ls=-12,
                  font="'JetBrains Mono'", fit=True, minsize=100,
                  extra="display:flex;align-items:center;white-space:nowrap")
            + box(96, 720, 888, 170, s["label"], 58, 800, th.text, lh=1.1, ls=-1, fit=True, minsize=32)
            + box(96, 940, 888, 170, s.get("sub", ""), 34, 500, th.body, lh=1.3, fit=True, minsize=22)
            + footer(spec, i, n, th))


def s_cta(s, th, spec, i, n):
    btn_bg = th.accent if th.dark else K
    btn_fg = K if th.dark else (th.bg if th.bg.upper() not in (COLORS["offwhite"].upper(), W.upper()) else COLORS["green"])
    return (pill(s["eyebrow"], th)
            + box(96, 300, 888, 360, s["headline"], 96, 900, th.text, lh=1.02, ls=-2.5, fit=True, minsize=44)
            + box(96, 700, 888, 200, s.get("body", ""), 40, 500, th.body, lh=1.35, fit=True, minsize=24)
            + f'<div class="b" style="left:96px;top:960px;width:680px;height:110px;background:{btn_bg};border-radius:14px;'
              f'display:flex;align-items:center;justify-content:center;font-family:Inter;font-size:36px;font-weight:800;'
              f'color:{btn_fg}">{html.escape(s["button"])}</div>'
            + footer(spec, i, n, th))


TYPES = {"hook": s_hook, "text": s_text, "bullets": s_bullets, "stat": s_stat, "cta": s_cta}

FIT_JS = """
document.querySelectorAll('[data-fit]').forEach(el=>{
  let s=parseFloat(getComputedStyle(el).fontSize), min=parseFloat(el.dataset.min);
  while((el.scrollHeight>el.clientHeight+1||el.scrollWidth>el.clientWidth+1)&&s>min){s-=2;el.style.fontSize=s+'px';}
});
"""


def fontface():
    css = ""
    for w in (400, 500, 600, 700, 800, 900):
        css += f"@font-face{{font-family:Inter;font-weight:{w};src:url('file://{FONTS}/inter/files/inter-latin-{w}-normal.woff2')}}\n"
    css += (f"@font-face{{font-family:'JetBrains Mono';font-weight:800;"
            f"src:url('file://{FONTS}/jetbrains-mono/files/jetbrains-mono-latin-800-normal.woff2')}}\n")
    return css


def page(bg, body, height=H_, top=0):
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{fontface()}"
            f"html,body{{margin:0}}.s{{position:relative;width:{W_}px;height:{height}px;background:{bg};overflow:hidden}}"
            f".in{{position:absolute;left:0;top:{top}px;width:{W_}px;height:{H_}px}}"
            f".b{{position:absolute;box-sizing:border-box;overflow:hidden;-webkit-font-smoothing:antialiased}}"
            f"</style></head><body><div class='s'><div class='in'>{body}</div></div></body></html>")


def render(spec_path, browser):
    spec = json.loads(pathlib.Path(spec_path).read_text())
    palette = [col(c) for c in spec.get("palette", ["black", "offwhite"])]
    accent = col(spec.get("accent", next((c for c in spec.get("palette", []) if c not in ("black", "white", "offwhite")), "green")))
    slides = spec["slides"]
    n = len(slides)
    out = OUT_DIR / spec["slug"]
    out.mkdir(parents=True, exist_ok=True)
    pg = browser.new_page(viewport={"width": W_, "height": H_})

    def shoot(doc, path, height=H_):
        tmp = out / "_tmp.html"
        tmp.write_text(doc)
        pg.set_viewport_size({"width": W_, "height": height})
        pg.goto(f"file://{tmp}")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(150)
        pg.evaluate(FIT_JS)
        pg.screenshot(path=str(path))
        tmp.unlink()
        # Instagram (API oficial) só aceita JPEG: grava uma cópia .jpg ao lado do .png
        from PIL import Image
        Image.open(path).convert("RGB").save(str(path).replace(".png", ".jpg"), quality=92, optimize=True)

    files = []
    for i, s in enumerate(slides, 1):
        bg = col(s.get("bg", palette[(i - 1) % len(palette)]))
        th = Theme(bg, col(s.get("accent", accent)))
        body = TYPES[s["type"]](s, th, spec, i, n)
        if spec.get("decor") == "hazard":
            body += hazard()
        shoot(page(bg, body), out / f"{i}.png")
        files.append(f"{i}.png")

    s0 = dict(slides[0])
    bg0 = col(s0.get("bg", palette[0]))
    th0 = Theme(bg0, col(s0.get("accent", accent)))
    if spec.get("story_pergunta"):
        # story de conversa: pergunta grande + espaço livre para a enquete/caixinha (adicionada no app)
        body = (pill(spec.get("story_eyebrow", "PERGUNTA DO DIA"), th0)
                + box(96, 230, 888, 560, spec["story_pergunta"], 96, 900, th0.text, lh=1.04, ls=-2.5, fit=True, minsize=48)
                + box(96, 1290, 888, 150, "Post novo no feed: " + s0["headline"].replace("\n", " "), 34, 600,
                      th0.accent if th0.dark else th0.text, lh=1.25, fit=True, minsize=24)
                + box(96, 1460, 888, 60, spec.get("footer", "Victor Slompo · vssolutions.io"), 26, 500, th0.body))
        # a área "in" começa em y=200 para fugir do cabeçalho do Instagram; 800-1250 fica livre para o sticker
        shoot(page(bg0, body, height=1920, top=200), out / "story.png", height=1920)
    else:
        # story 1080x1920 a partir da capa
        s0["eyebrow"] = spec.get("story_eyebrow", "NOVO POST · " + s0["eyebrow"].split("·")[-1].strip())
        s0["swipe"] = spec.get("story_cta", "No meu feed")
        shoot(page(bg0, TYPES[s0["type"]](s0, th0, spec, 1, n), height=1920, top=285), out / "story.png", height=1920)
    pg.close()

    meta = {"slug": spec["slug"], "slides": files, "slides_jpg": [f.replace(".png", ".jpg") for f in files],
            "story": "story.png", "story_jpg": "story.jpg",
            "caption": spec.get("caption", ""), "first_comment": spec.get("first_comment", "")}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"ok  {spec['slug']}: {n} slides + story -> {out.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    a = ap.parse_args()
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
        for sp in a.specs:
            render(sp, b)
        b.close()


if __name__ == "__main__":
    sys.exit(main())
