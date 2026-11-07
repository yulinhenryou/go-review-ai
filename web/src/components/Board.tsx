// An SVG board drawn from a core Position snapshot. It renders only; it
// never decides whether a move is legal.
import type { Point, Position } from '../core'
import { useMessages } from '../i18n'

interface BoardProps {
  position: Position
  /** The last move played, marked on its stone. */
  lastMove?: Point | null
  /** Called with the clicked intersection; omit for a read-only board. */
  onPoint?: (point: Point) => void
}

/** Conventional star points for the common square sizes. */
function starPoints(width: number, height: number): Point[] {
  const lines: Record<number, number[]> = { 9: [2, 4, 6], 13: [3, 6, 9], 19: [3, 9, 15] }
  const at = width === height ? lines[width] : undefined
  return at ? at.flatMap((x) => at.map((y) => ({ x, y }))) : []
}

const MARGIN = 0.75

export function Board({ position, lastMove = null, onPoint }: BoardProps) {
  const t = useMessages()
  const { width, height } = position
  const range = (n: number) => Array.from({ length: n }, (_, i) => i)
  const cells = range(width * height).map((i) => ({
    x: i % width,
    y: Math.floor(i / width),
    stone: position.cells[i],
  }))

  return (
    <svg
      className="board"
      viewBox={`${-MARGIN} ${-MARGIN} ${width - 1 + 2 * MARGIN} ${height - 1 + 2 * MARGIN}`}
      role="group"
      aria-label={`${t.board(width, height)}, ${t.toPlay(position.toPlay)}`}
      data-to-play={position.toPlay}
    >
      <rect
        className="board-surface"
        x={-MARGIN}
        y={-MARGIN}
        width={width - 1 + 2 * MARGIN}
        height={height - 1 + 2 * MARGIN}
      />
      {range(width).map((x) => (
        <line key={`v${x}`} className="board-line" x1={x} y1={0} x2={x} y2={height - 1} />
      ))}
      {range(height).map((y) => (
        <line key={`h${y}`} className="board-line" x1={0} y1={y} x2={width - 1} y2={y} />
      ))}
      {starPoints(width, height).map(({ x, y }) => (
        <circle key={`s${x}-${y}`} className="board-star" cx={x} cy={y} r={0.1} />
      ))}
      {cells.map(({ x, y, stone }) =>
        stone === null ? null : (
          <circle
            key={`c${x}-${y}`}
            className={stone === 'B' ? 'stone stone-black' : 'stone stone-white'}
            cx={x}
            cy={y}
            r={0.47}
            data-stone={stone}
            data-point={`${x}-${y}`}
          />
        ),
      )}
      {lastMove && position.cells[lastMove.y * width + lastMove.x] !== null && (
        <circle
          className={`last-move last-move-on-${position.cells[lastMove.y * width + lastMove.x]}`}
          cx={lastMove.x}
          cy={lastMove.y}
          r={0.2}
          data-last-move={`${lastMove.x}-${lastMove.y}`}
        />
      )}
      {position.koBan && (
        <rect
          className="ko-ban"
          x={position.koBan.x - 0.18}
          y={position.koBan.y - 0.18}
          width={0.36}
          height={0.36}
          data-ko-ban={`${position.koBan.x}-${position.koBan.y}`}
        />
      )}
      {onPoint &&
        cells.map(({ x, y }) => (
          <rect
            key={`p${x}-${y}`}
            className="hit"
            x={x - 0.5}
            y={y - 0.5}
            width={1}
            height={1}
            data-point={`${x}-${y}`}
            onClick={() => onPoint({ x, y })}
          />
        ))}
    </svg>
  )
}
