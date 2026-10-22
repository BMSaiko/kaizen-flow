# Privacy audit (F1 baseline)

`kaizen audit .` baseline before extracting the neutral core: 50 hits.

| pattern | hits | where | resolved in |
|---|---|---|---|
| heimdall | 29 | `template/` skills (super-prompt, michi refs, dp, da, one-shot, grill-me), `sp-list.py`, tests, `bin/kaizen.js` | F2 (neutral core), F3 (configurable SP root) |
| bruno | 12 | `template/` skills and `test_sp_*.py` fixtures, `bin/kaizen.js` (`KAIZEN_SOURCE` default) | F2, F3 |
| windows-user-path | 9 | `test_sp_*.py`, `bin/kaizen.js`, michi refs | F3 (tests use temp dirs) |

The copyright line in `LICENSE` is intentionally excluded. `kaizen audit` must report 0 hits before publishing (F6, also in CI).
