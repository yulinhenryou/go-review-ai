// Manual entry: click to play, pass, undo. The Game handle lives in a
// ManualSession; React state holds only the plain snapshots it returns.
import { useState, type FormEvent } from 'react'
import { isCoreError } from '../core'
import { ManualSession, type GameSettings, type ManualView } from '../session/manual'
import { RULE_NAMES, useMessages } from '../i18n'
import { Board } from './Board'
import { PositionStatus } from './PositionStatus'

const SIZES = [19, 13, 9]
const DEFAULT_SETTINGS: GameSettings = { width: 19, height: 19, rules: 'chinese', komi: 7.5 }

interface Current {
  session: ManualSession
  view: ManualView
}

function start(settings: GameSettings): Current {
  const session = new ManualSession(settings)
  return { session, view: session.view() }
}

export function ManualPlay() {
  const t = useMessages()
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  // A game created here and dropped (e.g. by StrictMode's double render) is
  // freed by wasm-bindgen's FinalizationRegistry; replaced games are freed
  // explicitly below.
  const [current, setCurrent] = useState(() => start(DEFAULT_SETTINGS))
  const [formError, setFormError] = useState<string | null>(null)

  const { session, view } = current
  const update = (next: ManualView) => setCurrent({ session, view: next })
  const last = view.moves.at(-1)
  const lastMove = last && last.move !== 'pass' ? last.move : null

  function newGame(event: FormEvent) {
    event.preventDefault()
    let next: Current
    try {
      next = start(settings)
    } catch (error) {
      if (!isCoreError(error)) throw error
      setFormError(error.code)
      return
    }
    session.dispose()
    setFormError(null)
    setCurrent(next)
  }

  return (
    <div className="workspace">
      <div className="board-column">
        <Board
          position={view.position}
          lastMove={lastMove}
          onPoint={(p) => update(session.play(p))}
        />
      </div>
      <aside className="panel">
        <PositionStatus position={view.position} moveCount={view.moves.length} />
        <p className="message" role="status" data-rejected={view.rejected ?? ''}>
          {view.rejected ? t.error(view.rejected) : ' '}
        </p>
        <div className="actions">
          <button type="button" onClick={() => update(session.play('pass'))}>
            {t.pass}
          </button>
          <button
            type="button"
            onClick={() => update(session.undo())}
            disabled={view.moves.length === 0}
          >
            {t.undo}
          </button>
        </div>
        <form className="settings" onSubmit={newGame}>
          <label>
            {t.boardSize}
            <select
              value={settings.width}
              onChange={(e) => {
                const n = Number(e.target.value)
                setSettings({ ...settings, width: n, height: n })
              }}
            >
              {SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}×{n}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t.rules}
            <select
              value={settings.rules}
              onChange={(e) => setSettings({ ...settings, rules: e.target.value })}
            >
              {RULE_NAMES.map((name) => (
                <option key={name} value={name}>
                  {t.rulesName[name]}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t.komi}
            <input
              type="number"
              step={0.5}
              value={settings.komi}
              onChange={(e) => setSettings({ ...settings, komi: e.target.valueAsNumber })}
            />
          </label>
          <button type="submit">{t.newGame}</button>
          {formError && <p className="message">{t.error(formError)}</p>}
        </form>
      </aside>
    </div>
  )
}
