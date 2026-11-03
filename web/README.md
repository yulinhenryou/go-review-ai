# Web app

TypeScript + React + Vite. M0 contains only a placeholder page that reads the
project name from `config/project.json`. Board rules arrive via the WASM core
in M2 (see `docs/ROADMAP.md`).

```bash
npm ci
npm run dev
npm run lint && npm run typecheck && npm test && npm run build
```
