import type { Position } from '../core'
import { useMessages } from '../i18n'

interface PositionStatusProps {
  position: Position
  moveCount: number
  total?: number
}

export function PositionStatus({ position, moveCount, total }: PositionStatusProps) {
  const t = useMessages()
  // `captures.white` counts white stones removed, i.e. Black's captures.
  const { black, white } = position.captures
  return (
    <ul className="status-list">
      <li data-testid="move-number">{t.moveNumber(moveCount, total)}</li>
      <li data-testid="to-play">{t.toPlay(position.toPlay)}</li>
      <li data-testid="captures">{t.captures(white, black)}</li>
      {position.consecutivePasses >= 2 && <li>{t.bothPassed}</li>}
    </ul>
  )
}
