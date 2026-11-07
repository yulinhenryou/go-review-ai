# Web app

TypeScript + React + Vite. So far it is a placeholder page that reads the
project name from `config/project.json`. Board rules come from the Rust core
compiled to WebAssembly: `npm run wasm` builds `crates/weiqi-wasm` and writes
the generated module to `src/wasm/` (not committed). It needs the
`wasm32-unknown-unknown` target (from `rust-toolchain.toml`) and
`wasm-bindgen-cli` 0.2.130.

```bash
npm ci
npm run wasm
npm run dev
npm run lint && npm run typecheck && npm test && npm run build
```
