import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Game } from '../core'
import { Board } from './Board'

describe('Board', () => {
  it('draws the stones, the last move and the ko ban of a core position', () => {
    const game = new Game(5, 5, 'japanese', 6.5)
    for (const move of [
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
      { x: 2, y: 0 },
      { x: 1, y: 2 },
      { x: 2, y: 2 },
      { x: 4, y: 4 },
      { x: 3, y: 1 },
      { x: 2, y: 1 },
    ])
      game.play(move)
    const { container } = render(<Board position={game.position()} lastMove={{ x: 2, y: 1 }} />)
    game.free()

    const stones = [...container.querySelectorAll('[data-stone]')]
    expect(stones).toHaveLength(8)
    expect(container.querySelector('[data-point="1-1"][data-stone]')).toBeNull()
    expect(container.querySelector('[data-point="2-1"]')?.getAttribute('data-stone')).toBe('B')
    expect(container.querySelector('[data-last-move]')?.getAttribute('data-last-move')).toBe('2-1')
    expect(container.querySelector('[data-ko-ban]')?.getAttribute('data-ko-ban')).toBe('1-1')
    // Read-only without onPoint.
    expect(container.querySelector('.hit')).toBeNull()
  })

  it('reports the clicked intersection and draws star points on 19×19', () => {
    const game = new Game(19, 19, 'chinese', 7.5)
    const onPoint = vi.fn()
    const { container } = render(<Board position={game.position()} onPoint={onPoint} />)
    game.free()
    fireEvent.click(container.querySelector('.hit[data-point="15-3"]') as Element)
    expect(onPoint).toHaveBeenCalledWith({ x: 15, y: 3 })
    expect(container.querySelectorAll('.board-star')).toHaveLength(9)
    expect(container.querySelectorAll('.hit')).toHaveLength(361)
  })
})
