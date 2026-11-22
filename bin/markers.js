"use strict";
// marcadores de personalização em core/: {{chave}} com as chaves de kaizen.config.json
const MARKER_KEYS = ["userFullName", "userName", "agentName", "agentSlug"];
// defeitos neutros (iguais aos de core/scripts/kaizen_config.py) para quem instala sem config
const DEFAULTS = { userFullName: "the user", userName: "user", agentName: "the agent", agentSlug: "kaizen" };
const RE = new RegExp(`\\{\\{(${MARKER_KEYS.join("|")})\\}\\}`, "g");

const render = (text, cfg = {}) => text.replace(RE, (_, k) => (cfg[k] != null && cfg[k] !== "" ? cfg[k] : DEFAULTS[k]));

module.exports = { MARKER_KEYS, render };
