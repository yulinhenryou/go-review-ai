// The Rust rules core, compiled to WebAssembly (crates/weiqi-wasm, built by
// `npm run wasm`). Every Go rule the page applies comes from here.
import init, { type CoreError } from './wasm/weiqi_wasm.js'
import wasmUrl from './wasm/weiqi_wasm_bg.wasm?url'

export * from './wasm/weiqi_wasm.js'

/** Fetches and instantiates the module; call once before using the core. */
export async function loadCore(): Promise<void> {
  await init({ module_or_path: wasmUrl })
}

/** Whether `error` is one the core threw (it carries a stable `code`). */
export function isCoreError(error: unknown): error is CoreError {
  return error instanceof Error && 'code' in error && typeof error.code === 'string'
}
