import { describe, expect, it } from 'vitest'
import { repositoryFile } from '../test/files'
import { openSgf, replayGame, stepIndex } from './record'

const sgf = (name: string) => repositoryFile(`testdata/sgf/${name}`)

describe('record session', () => {
  it('opens a GBK record and replays it with confirmed rules', () => {
    const data = sgf('kejie-2025-11-27-gbk.sgf')
    const parsed = openSgf(data)
    if (!parsed.ok) throw new Error(parsed.code)
    expect(parsed.collection.encoding).toBe('gb18030')
    const record = parsed.collection.games[0].record
    expect(record?.info.blackPlayer).toBe('柯洁')
    expect(record?.moves).toHaveLength(111)

    const replayed = replayGame(data, 0, 'chinese', 7.5)
    if (!replayed.ok) throw new Error(replayed.code)
    expect(replayed.replay.positions).toHaveLength(112)
  })

  it('reports codes instead of throwing', () => {
    expect(openSgf(new TextEncoder().encode('hello'))).toEqual({ ok: false, code: 'no_game' })
    const data = new TextEncoder().encode('(;SZ[9];B[aa];W[bb];B[bb])')
    expect(replayGame(data, 0, 'chinese', 7.5)).toEqual({
      ok: false,
      code: 'occupied',
      moveNumber: 3,
    })
    expect(replayGame(data, 0, '', 7.5)).toMatchObject({ ok: false, code: 'unknown_rules' })
    expect(replayGame(data, 0, 'chinese', Number.NaN)).toMatchObject({
      ok: false,
      code: 'invalid_komi',
    })
  })

  it('keeps the move index in range', () => {
    expect(stepIndex(0, -1, 10)).toBe(0)
    expect(stepIndex(9, 1, 10)).toBe(10)
    expect(stepIndex(10, 1, 10)).toBe(10)
    expect(stepIndex(5, Number.NEGATIVE_INFINITY, 10)).toBe(0)
    expect(stepIndex(5, Number.POSITIVE_INFINITY, 10)).toBe(10)
  })
})
