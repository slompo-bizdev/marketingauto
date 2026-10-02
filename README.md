# marketingauto: máquina de carrosséis da VS Solutions

Gera carrosséis 1080×1350 e o story 1080×1920 a partir de um arquivo JSON, sem Orshot e sem custo.
Roda no GitHub Actions, e as imagens ficam públicas no GitHub Pages para o Metricool publicar.

```
insight  →  posts/AAAA-MM-DD-slug.json  →  git push  →  GitHub Actions renderiza
         →  docs/posts/<slug>/1.png … N.png, story.png, meta.json  →  GitHub Pages (URL pública)
         →  Metricool agenda no Instagram/LinkedIn
```

## Configurar uma vez

1. Crie o repositório **público** `marketingauto` no GitHub (o GitHub Pages grátis exige repositório público;
   só ficam lá os specs e as imagens, que vão ser publicadas de qualquer forma).
2. Suba esta pasta: `git init && git add . && git commit -m "init" && git push`.
3. Em **Settings → Pages**: Source = *Deploy from a branch*, Branch = `main`, pasta `/docs`.
4. Em **Settings → Actions → General → Workflow permissions**: marque *Read and write permissions*.

As imagens ficam em:
`https://<seu-usuario>.github.io/marketingauto/posts/<slug>/1.png`

## Criar um post

1. Peça ao Claude: *"gera o spec do post sobre <insight>"*. Ele segue o `CLAUDE.md` (tom, pilares,
   regras de anonimização) e escreve `posts/AAAA-MM-DD-slug.json`.
2. `git push`. Em cerca de 2 minutos o Action renderiza e publica as imagens.
3. Peça ao Claude: *"publica o post <slug>"*. Ele lê o `meta.json` e agenda no Metricool com as URLs do Pages.

## Formato do spec

```json
{
  "slug": "2026-10-02-geo-workshop",
  "palette": ["tiffany", "yellow", "red", "black"],
  "accent": "tiffany",
  "decor": "hazard",
  "footer": "Victor Slompo · vssolutions.io",
  "slides": [
    {"type": "hook",    "eyebrow": "...", "headline": "...", "sub": "..."},
    {"type": "text",    "eyebrow": "...", "headline": "...", "body": "..."},
    {"type": "bullets", "eyebrow": "...", "headline": "...", "items": ["...", "...", "..."], "highlight_last": true},
    {"type": "stat",    "eyebrow": "...", "stat": "1.427", "label": "...", "sub": "..."},
    {"type": "cta",     "eyebrow": "...", "headline": "...", "body": "...", "button": "..."}
  ],
  "caption": "...",
  "first_comment": "vssolutions.io"
}
```

- `palette`: as cores se repetem em ciclo, uma por slide. Disponíveis: `black`, `offwhite`, `green`,
  `tiffany`, `yellow`, `red` ou qualquer `#HEX`. Uma cor específica num slide vai em `"bg": "red"`.
- **Contraste automático:** em fundo escuro o texto sai branco com acento colorido; em fundo colorido,
  sai preto com a etiqueta do topo em preto.
- `story_pergunta`: se existir, o story vira um card de "PERGUNTA DO DIA" com espaço livre no meio para a enquete ou caixinha (adicionada no app). Sem ele, o story repete a capa.
- `decor: "hazard"` coloca a faixa zebrada de obra no rodapé (tema Consult Eng).

Temas usados até agora: verde VS (`["black","offwhite"]` + `accent: green`),
SDR (`["red","black","red","black","red","offwhite","black","offwhite"]`), Consult Eng
(`["yellow","black"]` + `decor: hazard`), GEO (`["tiffany","yellow","red","black"]`).

## Rodar no seu computador

```bash
pip install -r requirements.txt && python -m playwright install chromium && npm install
python render/render.py posts/2026-10-02-geo-workshop.json
```
