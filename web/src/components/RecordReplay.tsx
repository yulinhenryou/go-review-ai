// SGF review: open a file, confirm rules and komi, then step through the
// positions the core replayed. Nothing here is computed by the page.
import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import type { GameRecord, Replay } from '../core'
import { RULE_NAMES, useMessages } from '../i18n'
import { openSgf, replayGame, stepIndex, type Parsed } from '../session/record'
import { Board } from './Board'
import { PositionStatus } from './PositionStatus'

interface Confirmed {
  replay: Replay
  index: number
}

/** The record's rules name if the core recognized `RU`, else blank. */
function recordRules(record: GameRecord): string {
  return record.rules !== null && record.rulesText !== null ? record.rulesText.toLowerCase() : ''
}

interface RecordReplayProps {
  /** Whether the view is shown; arrow keys navigate only then. */
  active: boolean
}

export function RecordReplay({ active }: RecordReplayProps) {
  const t = useMessages()
  const [parsed, setParsed] = useState<Parsed | null>(null)
  const [gameIndex, setGameIndex] = useState(0)
  const [rules, setRules] = useState('')
  const [komi, setKomi] = useState('')
  const [replayError, setReplayError] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState<Confirmed | null>(null)

  const collection = parsed?.ok ? parsed.collection : null
  const game = collection?.games[gameIndex] ?? null
  const record = game?.record ?? null

  function selectGame(next: Parsed, index: number) {
    setGameIndex(index)
    setConfirmed(null)
    setReplayError(null)
    const chosen = next.ok ? next.collection.games[index]?.record : null
    setRules(chosen ? recordRules(chosen) : '')
    setKomi(chosen?.komi != null ? String(chosen.komi) : '')
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    const next = openSgf(new Uint8Array(await file.arrayBuffer()))
    setParsed(next)
    selectGame(next, 0)
  }

  function onReplay(event: FormEvent) {
    event.preventDefault()
    if (!parsed?.ok) return
    const result = replayGame(
      parsed.data,
      gameIndex,
      rules,
      komi === '' ? Number.NaN : Number(komi),
    )
    if (result.ok) {
      setReplayError(null)
      setConfirmed({ replay: result.replay, index: 0 })
    } else {
      setReplayError(
        result.moveNumber === null
          ? t.error(result.code)
          : `${t.atMove(result.moveNumber)}: ${t.error(result.code)}`,
      )
    }
  }

  const last = confirmed ? confirmed.replay.positions.length - 1 : 0
  const go = (target: number) =>
    setConfirmed((c) =>
      c ? { ...c, index: stepIndex(target, 0, c.replay.positions.length - 1) } : c,
    )

  const replaying = active && confirmed !== null
  useEffect(() => {
    if (!replaying) return
    const onKey = (event: KeyboardEvent) => {
      const target = event.target
      if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement) return
      const steps: Record<string, number> = {
        ArrowLeft: -1,
        ArrowRight: 1,
        Home: -Infinity,
        End: Infinity,
      }
      const step = steps[event.key]
      if (step === undefined) return
      event.preventDefault()
      setConfirmed((c) =>
        c ? { ...c, index: stepIndex(c.index, step, c.replay.positions.length - 1) } : c,
      )
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [replaying])

  // File-level notes first (collection, then this game's record), then the
  // replay's; only replay warnings point at a move.
  const warnings = [
    ...(collection?.warnings ?? []).map((w, i) => ({
      key: `c${i}`,
      code: w.code,
      moveNumber: null,
    })),
    ...(record?.warnings ?? []).map((w, i) => ({ key: `e${i}`, code: w.code, moveNumber: null })),
    ...(confirmed?.replay.warnings ?? []).map((w, i) => ({
      key: `r${i}`,
      code: w.code,
      moveNumber: w.moveNumber,
    })),
  ]

  const position = confirmed?.replay.positions[confirmed.index]
  const played =
    confirmed && record && confirmed.index > 0 ? record.moves[confirmed.index - 1] : null
  const lastMove = played && played.move !== 'pass' ? played.move : null

  return (
    <div className="workspace">
      <div className="board-column">
        {position ? (
          <Board position={position} lastMove={lastMove} />
        ) : (
          <div className="board-placeholder" />
        )}
      </div>
      <aside className="panel">
        <label className="file">
          {t.chooseFile}
          <input
            type="file"
            accept=".sgf,application/x-go-sgf"
            onChange={onFile}
            data-testid="sgf-file"
          />
        </label>
        {parsed && !parsed.ok && (
          <p className="message" role="alert">
            {t.error(parsed.code)}
          </p>
        )}

        {collection && collection.games.length > 1 && (
          <select
            value={gameIndex}
            onChange={(e) => parsed && selectGame(parsed, Number(e.target.value))}
            aria-label={t.gameOf(gameIndex + 1, collection.games.length)}
          >
            {collection.games.map((_, i) => (
              <option key={i} value={i}>
                {t.gameOf(i + 1, collection.games.length)}
              </option>
            ))}
          </select>
        )}

        {game?.extractError && (
          <p className="message" role="alert">
            {t.error(game.extractError.code)}
          </p>
        )}

        {record && (
          <>
            <dl className="info">
              <dt>{t.black}</dt>
              <dd data-testid="black-player">
                {[record.info.blackPlayer, record.info.blackRank].filter(Boolean).join(' ') ||
                  t.notInFile}
              </dd>
              <dt>{t.white}</dt>
              <dd data-testid="white-player">
                {[record.info.whitePlayer, record.info.whiteRank].filter(Boolean).join(' ') ||
                  t.notInFile}
              </dd>
              <dt>{t.result}</dt>
              <dd>{record.info.resultText ?? t.notInFile}</dd>
              <dt>{t.date}</dt>
              <dd>{record.info.date ?? t.notInFile}</dd>
              <dt>{t.rules}</dt>
              <dd>{record.rulesText ?? t.notInFile}</dd>
              <dt>{t.komi}</dt>
              <dd>{record.komi ?? t.notInFile}</dd>
              <dt>{t.encoding}</dt>
              <dd>{collection?.encoding}</dd>
            </dl>

            <form className="settings" onSubmit={onReplay}>
              <p>{t.confirmToReplay}</p>
              <label>
                {t.rules}
                <select value={rules} onChange={(e) => setRules(e.target.value)} required>
                  <option value="">{t.chooseRules}</option>
                  {[...new Set([...RULE_NAMES, ...(rules ? [rules] : [])])].map((name) => (
                    <option key={name} value={name}>
                      {t.rulesName[name] ?? name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t.komi}
                <input
                  type="number"
                  step={0.5}
                  value={komi}
                  onChange={(e) => setKomi(e.target.value)}
                  required
                />
              </label>
              <button type="submit">{t.replay}</button>
              {replayError && (
                <p className="message" role="alert">
                  {replayError}
                </p>
              )}
            </form>
          </>
        )}

        {confirmed && position && (
          <>
            <PositionStatus position={position} moveCount={confirmed.index} total={last} />
            <div className="actions">
              <button type="button" onClick={() => go(0)} aria-label={t.first}>
                ⏮
              </button>
              <button type="button" onClick={() => go(confirmed.index - 1)} aria-label={t.previous}>
                ◀
              </button>
              <button type="button" onClick={() => go(confirmed.index + 1)} aria-label={t.next}>
                ▶
              </button>
              <button type="button" onClick={() => go(last)} aria-label={t.last}>
                ⏭
              </button>
            </div>
            <input
              type="range"
              min={0}
              max={last}
              value={confirmed.index}
              onChange={(e) => go(Number(e.target.value))}
              aria-label={t.moveNumber(confirmed.index, last)}
            />
          </>
        )}

        {warnings.length > 0 && (
          <details className="warnings" data-testid="warnings">
            <summary>
              {t.warnings} ({warnings.length})
            </summary>
            <ul>
              {warnings.map(({ key, code, moveNumber }) => (
                <li key={key}>
                  {moveNumber !== null && (
                    <>
                      <button type="button" className="link" onClick={() => go(moveNumber)}>
                        {t.atMove(moveNumber)}
                      </button>
                      :{' '}
                    </>
                  )}
                  {t.error(code)}
                </li>
              ))}
            </ul>
          </details>
        )}
      </aside>
    </div>
  )
}
