// @vitest-environment node
// The weiqi-wasm binding: error shapes, input checks and the copy-out
// boundary. Rule behavior is tested in Rust and by the conformance cases.

import { describe, expect, it } from 'vitest'
import { Game, parseSgf, replaySgf, type CoreError, type Move } from './wasm/weiqi_wasm.js'

function thrown(action: () => unknown): CoreError {
  try {
    action()
  } catch (error) {
    return error as CoreError
  }
  throw new Error('expected an error')
}

describe('Game', () => {
  it('plays, captures and undoes', () => {
    using game = new Game(19, 19, 'japanese', 6.5)
    game.play({ x: 1, y: 0 })
    game.play({ x: 0, y: 0 })
    const effect = game.play({ x: 0, y: 1 })
    expect(effect.captured).toEqual([{ x: 0, y: 0 }])
    expect(game.position().captures).toEqual({ black: 0, white: 1 })
    expect(game.moveCount).toBe(3)
    expect(game.undo()).toEqual({ color: 'B', move: { x: 0, y: 1 } })
    expect(game.toPlay).toBe('B')
  })

  it('throws coded errors and leaves the game unchanged', () => {
    using game = new Game(19, 19, 'chinese', 7.5)
    game.play({ x: 3, y: 3 })
    const before = game.position().situationHash

    const occupied = thrown(() => game.play({ x: 3, y: 3 }))
    expect(occupied).toBeInstanceOf(Error)
    expect([occupied.name, occupied.code]).toEqual(['IllegalMoveError', 'occupied'])

    const cases: [unknown, string, string][] = [
      [{ x: 19, y: 0 }, 'IllegalMoveError', 'off_board'],
      [{ x: -1, y: 0 }, 'IllegalMoveError', 'off_board'],
      [{ x: 1e9, y: 0 }, 'IllegalMoveError', 'off_board'],
      [{ x: 1.5, y: 0 }, 'CoreError', 'malformed_move'],
      [{ x: Number.NaN, y: 0 }, 'CoreError', 'malformed_move'],
      [{ x: 1 }, 'CoreError', 'malformed_move'],
      ['tt', 'CoreError', 'malformed_move'],
      [null, 'CoreError', 'malformed_move'],
    ]
    for (const [move, name, code] of cases) {
      const error = thrown(() => game.play(move as Move))
      expect([error.name, error.code], JSON.stringify(move)).toEqual([name, code])
    }
    expect(thrown(() => game.playAs('X' as 'B', 'pass', 'strict')).code).toBe('malformed_color')
    expect(thrown(() => game.playAs('W', 'pass', 'lenient' as 'strict')).code).toBe(
      'malformed_mode',
    )
    expect(game.position().situationHash).toBe(before)
  })

  it('validates construction', () => {
    expect(thrown(() => new Game(0, 19, 'chinese', 7.5)).code).toBe('unsupported_size')
    expect(thrown(() => new Game(19, 26, 'chinese', 7.5)).code).toBe('unsupported_size')
    expect(thrown(() => new Game(19, 19, 'ing', 7.5)).code).toBe('unknown_rules')
    for (const komi of [Number.NaN, Number.POSITIVE_INFINITY, -151, 151, 0.25]) {
      expect(thrown(() => new Game(19, 19, 'chinese', komi)).code).toBe('invalid_komi')
    }
    const offBoard = { black: [{ x: 9, y: 0 }], white: [], toPlay: 'B' as const }
    expect(thrown(() => Game.withSetup(9, 9, 'japanese', 0.5, offBoard)).code).toBe(
      'setup_off_board',
    )
    const conflict = { black: [{ x: 0, y: 0 }], white: [{ x: 0, y: 0 }], toPlay: 'B' as const }
    expect(thrown(() => Game.withSetup(9, 9, 'japanese', 0.5, conflict)).code).toBe(
      'setup_conflict',
    )
  })

  it('returns snapshots that later moves do not change', () => {
    using game = new Game(9, 9, 'japanese', 6.5)
    const position = game.position()
    game.play({ x: 4, y: 4 })
    expect(position.cells[4 * 9 + 4]).toBeNull()
    expect(game.position().cells[4 * 9 + 4]).toBe('B')
  })
})

describe('SGF', () => {
  const data = new TextEncoder().encode(
    '(;FF[4]GM[1]SZ[9]RU[Japanese]KM[6.5]PB[A\\]B];B[ee];W[tt])',
  )

  it('parses and replays', () => {
    const collection = parseSgf(data)
    const record = collection.games[0].record
    expect(record?.info.blackPlayer).toBe('A]B')
    expect(record?.moves).toEqual([
      { color: 'B', move: { x: 4, y: 4 } },
      { color: 'W', move: 'pass' },
    ])
    expect(replaySgf(data, 0, 'japanese', 6.5).positions).toHaveLength(3)
  })

  it('throws coded errors', () => {
    const notSgf = thrown(() => parseSgf(new TextEncoder().encode('hello')))
    expect([notSgf.name, notSgf.code, notSgf.offset]).toEqual(['SgfError', 'no_game', 5])
    expect(thrown(() => replaySgf(data, 1, 'japanese', 6.5)).code).toBe('no_such_game')
    const occupied = new TextEncoder().encode('(;SZ[9];B[aa];W[bb];B[bb])')
    const error = thrown(() => replaySgf(occupied, 0, 'chinese', 7.5))
    expect([error.name, error.code, error.moveNumber]).toEqual(['ReplayError', 'occupied', 3])
  })
})
