// Vitest runs in Node, where the WASM file is read from disk instead of
// fetched; every test file can then use the core directly.
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { initSync } from '../wasm/weiqi_wasm.js'
import { repositoryFile } from './files'

initSync({ module: repositoryFile('web/src/wasm/weiqi_wasm_bg.wasm') })

// Testing Library unmounts automatically only with Vitest globals enabled.
afterEach(() => {
  if (typeof document !== 'undefined') cleanup()
})
