import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Paths go through strings: under jsdom, the global `URL` is jsdom's, which
// Node's `fs` does not accept.
const repository = join(dirname(fileURLToPath(import.meta.url)), '../../..')

/** The bytes of a file, by its path from the repository root. */
export function repositoryFile(path: string): Uint8Array<ArrayBuffer> {
  return new Uint8Array(readFileSync(join(repository, path)))
}
