// An opened SGF file: parsing, the user's confirmation of rules and komi,
// and replay, all done by the core.
import { isCoreError, parseSgf, replaySgf, type Replay, type SgfCollection } from '../core'

export type Parsed =
  | { ok: true; data: Uint8Array; collection: SgfCollection }
  | { ok: false; code: string }

export function openSgf(data: Uint8Array): Parsed {
  try {
    return { ok: true, data, collection: parseSgf(data) }
  } catch (error) {
    if (!isCoreError(error)) throw error
    return { ok: false, code: error.code }
  }
}

export type Replayed =
  | { ok: true; replay: Replay }
  | { ok: false; code: string; moveNumber: number | null }

/** Replays game `index` with the rules and komi the user confirmed. */
export function replayGame(data: Uint8Array, index: number, rules: string, komi: number): Replayed {
  try {
    return { ok: true, replay: replaySgf(data, index, rules, komi) }
  } catch (error) {
    if (!isCoreError(error)) throw error
    return { ok: false, code: error.code, moveNumber: error.moveNumber ?? null }
  }
}

/** `index` moved by `step` and kept within `0..=last`. */
export function stepIndex(index: number, step: number, last: number): number {
  return Math.min(Math.max(index + step, 0), last)
}
