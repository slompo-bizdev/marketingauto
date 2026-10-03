"""Gera docs/index.json com todos os posts já renderizados (usado pelo vssolutions.io/radar)."""
import json, pathlib, re, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://slompo-bizdev.github.io/marketingauto"

posts = []
for p in sorted((ROOT / "posts").glob("*.json"), reverse=True):
    s = json.loads(p.read_text())
    slug = s["slug"]
    meta_file = ROOT / "docs" / "posts" / slug / "meta.json"
    if not meta_file.exists():
        continue  # ainda não renderizado
    m = json.loads(meta_file.read_text())
    meta = s.get("meta", {})
    slides = s.get("slides", [])
    hook = slides[0] if slides else {}
    imgs = [f"{BASE}/posts/{slug}/{f}" for f in m.get("slides_jpg", [])]
    data = slug[:10] if re.match(r"\d{4}-\d{2}-\d{2}", slug) else ""
    # Traduções feitas pelo motor (en, ru): o site mostra cada idioma em /radar, /ru/radar
    traducoes = {}
    for lang, t in (s.get("traducoes") or {}).items():
        ts = t.get("slides") or []
        if len(ts) != len(slides):
            continue
        th = ts[0] if ts else {}
        traducoes[lang] = {
            "titulo": th.get("headline", "").replace("\n", " "),
            "subtitulo": th.get("sub", "").replace("\n", " "),
            "slides": ts,
            "legenda": t.get("caption", ""),
        }
    posts.append({
        "slug": slug,
        "data": data,
        "titulo": hook.get("headline", "").replace("\n", " "),
        "subtitulo": hook.get("sub", "").replace("\n", " "),
        "tema": meta.get("tema") or hook.get("headline", "").replace("\n", " "),
        "tipo": meta.get("tipo", ""),
        "case_id": meta.get("case_id"),
        "palavra": meta.get("palavra", ""),
        "valor": meta.get("valor", ""),
        "fontes": meta.get("fontes", []),
        "slides": slides,
        "legenda": s.get("caption", ""),
        "imagens": imgs,
        "capa": imgs[0] if imgs else "",
        "gerado_em": meta.get("gerado_em", ""),
        "traducoes": traducoes,
    })

out = ROOT / "docs" / "index.json"
out.write_text(json.dumps({"atualizado_em": datetime.datetime.utcnow().isoformat() + "Z", "posts": posts}, ensure_ascii=False, indent=2))
print(f"index.json: {len(posts)} posts")
