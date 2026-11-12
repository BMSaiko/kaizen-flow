# Layouts do `wez layout`

Um ficheiro `<nome>.json` por layout nesta pasta (ou em `$WEZ_LAYOUTS_DIR`).
`python -I scripts/wez.py layout ls` lista; `layout open <nome>` abre.

```json
{
  "titulo": "dev",                 // título do separador (defeito: nome do ficheiro)
  "descricao": "texto livre",
  "janela_nova": false,            // true = spawn --new-window
  "paineis": [
    {"nome": "vault", "cwd": "~/Documents/Second-Brain"},
    {"nome": "atlas", "cwd": "~/Documents/code/atlas-desktop", "cmd": ["pwsh"],
     "split": {"de": "vault", "dir": "right", "percent": 50}}
  ]
}
```

- O 1.º painel abre com `wezterm cli spawn` e não leva `split`.
- Os seguintes abrem com `split-pane --pane-id <de> --<dir> --percent <n>`.
  `de` (defeito: o painel anterior) tem de ser um painel já aberto; `dir` ∈ right, left, top, bottom; `percent` 1–99 (defeito 50).
- `cwd` aceita `~` e variáveis de ambiente; `cmd` é texto ou lista (defeito: a shell).
- Nomes únicos. (Os comentários `//` acima são só explicação; JSON real não os aceita.)
- Exemplo: [dev.json](dev.json).
