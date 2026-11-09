# Security Policy

## Supported versions

Only the latest release of `kaizen-flow` receives security fixes.

## Reporting a vulnerability

Do not open a public issue. Report privately through GitHub Security Advisories:
<https://github.com/BMSaiko/kaizen-flow/security/advisories/new>

Include the affected version, steps to reproduce and the impact. You will get an acknowledgement as soon as the maintainer can, and a fix or a decision before any public disclosure.

## Scope

kaizen-flow uses the Node and Python standard libraries only and has no telemetry. Relevant reports include path traversal or unsafe file writes in `kaizen init`/`sync`, command injection in the scripts, and leaks of secrets or conversation content in usage reports.

## Supply chain

- CodeQL (JavaScript e Python) corre em cada PR, em push para `main` e semanalmente (`.github/workflows/codeql.yml`); os alertas ficam em Security > Code scanning.
- `npm audit --omit=dev` corre no CI sem bloquear e escreve o resumo no job.
- As actions dos workflows estão fixadas por SHA de commit, com a versão em comentário; o Dependabot (`github-actions`) propõe as atualizações.
- Cada workflow declara `permissions` mínimas (`contents: read`; só o necessário em CodeQL, publish e release).
