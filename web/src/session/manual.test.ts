import { describe, expect, it } from 'vitest'
import type { Move } from '../core'
import { ManualSession } from './manual'

// The 5×5 ko from testdata/conformance/games.json: Black takes at cb (2, 1).
const KO: Move[] = [
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
  { x: 2, y: 0 },
  { x: 1, y: 2 },
  { x: 2, y: 2 },
  { x: 4, y: 4 },
  { x: 3, y: 1 },
  { x: 2, y: 1 },
]

describe('ManualSession', () => {
  it('rejects an immediate ko recapture and leaves the position unchanged', () => {
    const session = new ManualSession({ width: 5, height: 5, rules: 'japanese', komi: 6.5 })
    let view = session.view()
    for (const move of KO) view = session.play(move)
    expect(view.position.koBan).toEqual({ x: 1, y: 1 })
    expect(view.position.captures).toEqual({ black: 0, white: 1 })

    const rejected = session.play({ x: 1, y: 1 })
    expect(rejected.rejected).toBe('ko_violation')
    expect(rejected.position).toEqual(view.position)
    expect(rejected.moves).toHaveLength(KO.length)
    session.dispose()
  })

  it('passes and undoes', () => {
    const session = new ManualSession({ width: 9, height: 9, rules: 'chinese', komi: 7.5 })
    session.play({ x: 4, y: 4 })
    const passed = session.play('pass')
    expect(passed.position.toPlay).toBe('B')
    expect(passed.moves.at(-1)).toEqual({ color: 'W', move: 'pass' })
    const undone = session.undo()
    expect(undone.moves).toEqual([{ color: 'B', move: { x: 4, y: 4 } }])
    expect(session.undo().position.cells.every((cell) => cell === null)).toBe(true)
    session.dispose()
  })

  it('reports suicide', () => {
    const session = new ManualSession({ width: 9, height: 9, rules: 'chinese', komi: 7.5 })
    for (const move of [{ x: 1, y: 0 }, 'pass', { x: 0, y: 1 }] as Move[]) session.play(move)
    expect(session.play({ x: 0, y: 0 }).rejected).toBe('suicide')
    session.dispose()
  })

  it('throws the core error for invalid settings', () => {
    expect(() => new ManualSession({ width: 19, height: 19, rules: 'chinese', komi: 0.3 })).toThrow(
      expect.objectContaining({ code: 'invalid_komi' }),
    )
  })
})
