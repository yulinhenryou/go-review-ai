// @vitest-environment node
// Golden conformance cases (ROADMAP M2 acceptance 1): the WASM side.
//
// Runs every case in testdata/conformance through the weiqi-wasm build
// (`npm run wasm`) and compares the transcript with the one the Rust runner
// recorded in expected.json. Text forms: testdata/conformance/README.md.

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  Game,
  parseSgf,
  replaySgf,
  zobristVersion,
  type Color,
  type CoreError,
  type Mode,
  type Move,
  type Point,
  type Position,
  type Rules,
  type SgfGame,
} from './wasm/weiqi_wasm.js'

const testdata = new URL('../../testdata/', import.meta.url)

function load(name: string): unknown {
  return JSON.parse(readFileSync(new URL(`conformance/${name}`, testdata), 'utf8'))
}

type Json = null | boolean | number | string | Json[] | { [key: string]: Json }

interface GameCase {
  name: string
  size: [number, number]
  rules: string
  komi: number
  mode: Mode
  setup?: { black: string[]; white: string[]; to_play: Color }
  moves: (string | { play: string })[]
}

interface SgfCase {
  name: string
  file?: string
  text?: string
  rules: string
  komi: number
}

const expected = load('expected.json') as {
  zobrist_version: number
  games: Record<string, Json>
  sgf: Record<string, Json>
}
const gameCases = (load('games.json') as { cases: GameCase[] }).cases
const sgfCases = (load('sgf.json') as { cases: SgfCase[] }).cases

// --- Text forms ---

const pointText = ({ x, y }: Point): string =>
  String.fromCharCode(97 + x) + String.fromCharCode(97 + y)

const parsePoint = (text: string): Point => ({
  x: text.charCodeAt(0) - 97,
  y: text.charCodeAt(1) - 97,
})

const moveText = (color: Color, move: Move): string =>
  `${color} ${move === 'pass' ? 'pass' : pointText(move)}`

function parseMove(text: string): [Color, Move] {
  const [color, point] = text.split(' ')
  return [color as Color, point === 'pass' ? 'pass' : parsePoint(point)]
}

function positionJson(position: Position): Json {
  const symbol = (cell: Color | null) => (cell === null ? '.' : cell === 'B' ? 'X' : 'O')
  const rows: string[] = []
  for (let y = 0; y < position.height; y++) {
    const row = position.cells.slice(y * position.width, (y + 1) * position.width)
    rows.push(row.map(symbol).join(''))
  }
  return {
    board: rows,
    to_play: position.toPlay,
    ko_ban: position.koBan === null ? null : pointText(position.koBan),
    captures: { black: position.captures.black, white: position.captures.white },
    consecutive_passes: position.consecutivePasses,
    stones_hash: position.stonesHash,
    situation_hash: position.situationHash,
  }
}

const rulesJson = (rules: Rules): Json => ({
  ko: rules.ko,
  scoring: rules.scoring,
  tax: rules.tax,
  suicide: rules.suicide,
  button: rules.button,
  white_handicap_bonus: rules.whiteHandicapBonus,
  friendly_pass_ok: rules.friendlyPassOk,
})

function isCoreError(error: unknown, name: CoreError['name']): error is CoreError {
  return error instanceof Error && error.name === name && 'code' in error
}

// --- Game cases ---

function runGame(c: GameCase): Json {
  const [width, height] = c.size
  const game = c.setup
    ? Game.withSetup(width, height, c.rules, c.komi, {
        black: c.setup.black.map(parsePoint),
        white: c.setup.white.map(parsePoint),
        toPlay: c.setup.to_play,
      })
    : new Game(width, height, c.rules, c.komi)
  try {
    const start = positionJson(game.position())
    const steps: Json[] = []
    for (const entry of c.moves) {
      const text = typeof entry === 'string' ? entry : entry.play
      const [color, move] = parseMove(text)
      try {
        const effect = game.playAs(color, move, c.mode)
        steps.push({
          move: text,
          result: 'ok',
          captured: effect.captured.map(pointText),
          suicided: effect.suicided.map(pointText),
          violations: effect.violations,
          repeated_position: effect.repeatedPosition,
          position: positionJson(game.position()),
        })
      } catch (error) {
        if (!isCoreError(error, 'IllegalMoveError')) throw error
        steps.push({ move: text, result: error.code })
      }
    }
    const undo: Json[] = []
    for (let undone = game.undo(); undone !== null; undone = game.undo()) {
      undo.push({
        undone: moveText(undone.color, undone.move),
        situation_hash: game.position().situationHash,
      })
    }
    return { start, steps, undo }
  } finally {
    game.free()
  }
}

// --- SGF cases ---

function sgfGameJson(game: SgfGame, data: Uint8Array, index: number, c: SgfCase): Json {
  const { record, extractError } = game
  if (record === null) {
    if (extractError === null) throw new Error('a game has a record or an extract error')
    return { extract_error: { code: extractError.code, node: extractError.node } }
  }
  const info = record.info
  let replay: Json
  try {
    const result = replaySgf(data, index, c.rules, c.komi)
    replay = {
      warnings: result.warnings.map((w) => ({ move_number: w.moveNumber, code: w.code })),
      situation_hashes: result.positions.map((p) => p.situationHash),
      final: positionJson(result.positions[result.positions.length - 1]),
    }
  } catch (error) {
    if (!isCoreError(error, 'ReplayError')) throw error
    replay = { error: { code: error.code, move_number: error.moveNumber ?? null } }
  }
  return {
    record: {
      size: [record.width, record.height],
      rules: record.rules === null ? null : rulesJson(record.rules),
      rules_text: record.rulesText,
      komi: record.komi,
      handicap: record.handicap,
      setup: {
        black: record.setup.black.map(pointText),
        white: record.setup.white.map(pointText),
        to_play: record.setup.toPlay,
      },
      moves: record.moves.map((m) => moveText(m.color, m.move)),
      info: {
        black_player: info.blackPlayer,
        white_player: info.whitePlayer,
        black_rank: info.blackRank,
        white_rank: info.whiteRank,
        date: info.date,
        event: info.event,
        round: info.round,
        place: info.place,
        name: info.name,
        result_text: info.resultText,
      },
    },
    extract_warnings: record.warnings.map((w) => ({ code: w.code, node: w.node })),
    replay,
  }
}

function runSgf(c: SgfCase): Json {
  const data =
    c.file !== undefined
      ? new Uint8Array(readFileSync(new URL(`sgf/${c.file}`, testdata)))
      : new TextEncoder().encode(c.text)
  let collection
  try {
    collection = parseSgf(data)
  } catch (error) {
    if (!isCoreError(error, 'SgfError')) throw error
    return { error: { code: error.code, offset: error.offset ?? null } }
  }
  return {
    encoding: collection.encoding,
    sgf_warnings: collection.warnings.map((w) => ({ code: w.code, offset: w.offset })),
    games: collection.games.map((game, index) => sgfGameJson(game, data, index, c)),
  }
}

// --- Tests ---

describe('conformance', () => {
  it('uses the Zobrist version of the transcripts', () => {
    expect(zobristVersion()).toBe(expected.zobrist_version)
  })

  it('has a transcript for every case', () => {
    expect(gameCases.map((c) => c.name).sort()).toEqual(Object.keys(expected.games).sort())
    expect(sgfCases.map((c) => c.name).sort()).toEqual(Object.keys(expected.sgf).sort())
  })

  it.each(gameCases.map((c) => [c.name, c] as const))('game case %s matches Rust', (name, c) => {
    expect(runGame(c)).toEqual(expected.games[name])
  })

  it.each(sgfCases.map((c) => [c.name, c] as const))('SGF case %s matches Rust', (name, c) => {
    expect(runSgf(c)).toEqual(expected.sgf[name])
  })
})
