// Manual move entry: a core Game handle plus the snapshots the UI renders.
// Every legality decision (captures, ko, superko, suicide) is the core's.
import { Game, isCoreError, type Move, type PlayedMove, type Position } from '../core'

export interface GameSettings {
  width: number
  height: number
  /** KataGo rules name, e.g. "chinese". */
  rules: string
  komi: number
}

/** What the UI shows: plain snapshots copied out of the core. */
export interface ManualView {
  position: Position
  moves: PlayedMove[]
  /** The code of the last rejected action, or `null`. */
  rejected: string | null
}

export class ManualSession {
  private readonly game: Game

  /** Throws the core's error for invalid settings. */
  constructor(settings: GameSettings) {
    this.game = new Game(settings.width, settings.height, settings.rules, settings.komi)
  }

  view(rejected: string | null = null): ManualView {
    return { position: this.game.position(), moves: this.game.moves(), rejected }
  }

  /** Plays for the side to move; an illegal move leaves the game unchanged. */
  play(move: Move): ManualView {
    try {
      this.game.play(move)
      return this.view()
    } catch (error) {
      if (!isCoreError(error)) throw error
      return this.view(error.code)
    }
  }

  undo(): ManualView {
    this.game.undo()
    return this.view()
  }

  /** Releases the core game; the session must not be used afterwards. */
  dispose(): void {
    this.game.free()
  }
}
