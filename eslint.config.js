// Lint do JS (bin/, adapters/, tests/): só erros reais; dívida antiga entra na baseline (quality-ratchet.py).
"use strict";
const js = require("@eslint/js");
const globals = require("globals");

module.exports = [
  { ignores: ["node_modules/**", "coverage/**", "core/**", "catalog/**", "docs/**", "usage/**"] },
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: { sourceType: "commonjs", ecmaVersion: 2022, globals: { ...globals.node } },
    rules: {
      "no-undef": "error",
      "no-unused-vars": "error",
      "no-unreachable": "error",
      eqeqeq: ["error", "always"],
      "no-return-await": "error",
      "require-await": "error",
    },
  },
  { files: ["**/*.mjs"], languageOptions: { sourceType: "module", ecmaVersion: 2022, globals: { ...globals.node } } },
];
