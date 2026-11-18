"use strict";
// Formato único das mensagens de erro (espelho de core/scripts/kf_erros.py `formatar`):
// EC-NNN O quê / Porquê / Estado guardado / Próximo, uma linha por parte, código do docs/catalogo.json.
const EC_RE = /^EC-\d{3}$/;
const umaLinha = (t) => String(t).split(/\r\n|[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]/).join(" ").trim(); // mesmas quebras que str.splitlines

function formatar(ec, oque, porque, estado, proximo) {
  if (!EC_RE.test(String(ec))) throw new Error(`código EC inválido: ${ec} (forma EC-NNN)`);
  const partes = [oque, porque, estado, proximo].map((p) => (p == null ? "" : umaLinha(p)));
  if (partes.some((p) => !p)) throw new Error(`parte vazia na mensagem ${ec}`);
  const [o, p, e, n] = partes;
  return `${ec} O quê: ${o}\n  Porquê: ${p}\n  Estado guardado: ${e}\n  Próximo: ${n}`;
}

module.exports = { formatar, EC_RE };
