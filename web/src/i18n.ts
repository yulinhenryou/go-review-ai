// User-facing text, one catalog per locale (CLAUDE.md §8). The core reports
// stable codes; this module chooses the words.
import { createContext, useContext } from 'react'

export type Locale = 'en' | 'zh-CN'

export interface Messages {
  languageToggle: string
  enterMoves: string
  openSgf: string
  boardSize: string
  rules: string
  komi: string
  newGame: string
  toPlay: (color: 'B' | 'W') => string
  captures: (byBlack: number, byWhite: number) => string
  moveNumber: (n: number, total?: number) => string
  bothPassed: string
  pass: string
  undo: string
  chooseFile: string
  gameOf: (n: number, total: number) => string
  black: string
  white: string
  result: string
  date: string
  encoding: string
  notInFile: string
  chooseRules: string
  confirmToReplay: string
  replay: string
  first: string
  previous: string
  next: string
  last: string
  warnings: string
  atMove: (n: number) => string
  board: (width: number, height: number) => string
  rulesName: Record<string, string>
  error: (code: string) => string
}

const errors: Record<Locale, Record<string, string>> = {
  en: {
    ko_violation: 'Ko: this stone cannot be retaken at once; play elsewhere first.',
    superko_violation: 'This move would repeat an earlier position (superko).',
    suicide: 'Suicide: this move would leave the stone without liberties.',
    occupied: 'That point is already occupied.',
    off_board: 'That point is not on the board.',
    out_of_turn: 'Played out of turn.',
    repeated_position: 'The position repeats an earlier one.',
    no_game: 'No SGF game was found in this file.',
    invalid_komi: 'Komi must be a multiple of 0.5 between −150 and 150.',
    unknown_rules: 'The rule set is not recognized.',
    unsupported_size: 'Board sides must be between 1 and 25.',
    encoding_guessed: 'The file does not declare its encoding; it was detected.',
    lossy_decode: 'Some characters could not be decoded.',
    charset_mismatch: 'The declared encoding did not match the bytes.',
    first_variation_only: 'Only the main line is shown; other variations are ignored.',
    missing_rules: 'The file does not state the rules.',
    missing_komi: 'The file does not state the komi.',
    tt_pass: 'A move at tt was read as a pass.',
    malformed_result: 'The result could not be read.',
    missing_gm: 'The file does not declare that it is a Go game.',
    missing_ff: 'The file does not declare its SGF version.',
    junk_outside_tree: 'Text outside the game tree was ignored.',
    unclosed_tree: 'The game tree is not closed.',
    two_moves_in_node: 'A node contains two moves.',
  },
  'zh-CN': {
    ko_violation: '打劫：不能立即提回，须先在别处走一手。',
    superko_violation: '这手棋会重复之前的局面（全局同形）。',
    suicide: '禁着点：这手棋落下后没有气。',
    occupied: '该点已有棋子。',
    off_board: '该点不在棋盘上。',
    out_of_turn: '不该这一方落子。',
    repeated_position: '局面与之前重复。',
    no_game: '文件中没有找到 SGF 棋谱。',
    invalid_komi: '贴目须为 0.5 的倍数，范围 −150 到 150。',
    unknown_rules: '无法识别的规则。',
    unsupported_size: '棋盘边长须在 1 到 25 之间。',
    encoding_guessed: '文件未声明编码，已自动识别。',
    lossy_decode: '部分字符无法解码。',
    charset_mismatch: '声明的编码与实际内容不符。',
    first_variation_only: '只显示主线，其他变化图已忽略。',
    missing_rules: '棋谱未注明规则。',
    missing_komi: '棋谱未注明贴目。',
    tt_pass: '位于 tt 的一手按停一手处理。',
    malformed_result: '无法读取对局结果。',
    missing_gm: '文件未声明是围棋棋谱。',
    missing_ff: '文件未声明 SGF 版本。',
    junk_outside_tree: '棋谱树之外的文字已忽略。',
    unclosed_tree: '棋谱树没有闭合。',
    two_moves_in_node: '一个节点中有两手棋。',
  },
}

export const messages: Record<Locale, Messages> = {
  en: {
    languageToggle: '中文',
    enterMoves: 'Enter moves',
    openSgf: 'Open SGF',
    boardSize: 'Board',
    rules: 'Rules',
    komi: 'Komi',
    newGame: 'New game',
    toPlay: (color) => (color === 'B' ? 'Black to play' : 'White to play'),
    captures: (byBlack, byWhite) => `Captures: Black ${byBlack} · White ${byWhite}`,
    moveNumber: (n, total) => (total === undefined ? `Move ${n}` : `Move ${n} of ${total}`),
    bothPassed: 'Both players passed.',
    pass: 'Pass',
    undo: 'Undo',
    chooseFile: 'Choose an SGF file',
    gameOf: (n, total) => `Game ${n} of ${total}`,
    black: 'Black',
    white: 'White',
    result: 'Result',
    date: 'Date',
    encoding: 'Encoding',
    notInFile: 'not in the file',
    chooseRules: 'Choose…',
    confirmToReplay: 'Confirm the rules and komi to replay the game.',
    replay: 'Replay',
    first: 'First move',
    previous: 'Previous move',
    next: 'Next move',
    last: 'Last move',
    warnings: 'Warnings',
    atMove: (n) => `Move ${n}`,
    board: (width, height) => `${width}×${height} board`,
    rulesName: {
      japanese: 'Japanese',
      chinese: 'Chinese',
      'chinese-ogs': 'Chinese (superko)',
      aga: 'AGA',
      'new-zealand': 'New Zealand',
      'tromp-taylor': 'Tromp-Taylor',
    },
    error: (code) => errors.en[code] ?? code,
  },
  'zh-CN': {
    languageToggle: 'English',
    enterMoves: '摆棋',
    openSgf: '打开棋谱',
    boardSize: '棋盘',
    rules: '规则',
    komi: '贴目',
    newGame: '新对局',
    toPlay: (color) => (color === 'B' ? '黑方落子' : '白方落子'),
    captures: (byBlack, byWhite) => `提子：黑 ${byBlack} · 白 ${byWhite}`,
    moveNumber: (n, total) => (total === undefined ? `第 ${n} 手` : `第 ${n} 手 / 共 ${total} 手`),
    bothPassed: '双方连续停一手。',
    pass: '停一手',
    undo: '悔棋',
    chooseFile: '选择 SGF 文件',
    gameOf: (n, total) => `第 ${n} 局 / 共 ${total} 局`,
    black: '黑',
    white: '白',
    result: '结果',
    date: '日期',
    encoding: '编码',
    notInFile: '棋谱未注明',
    chooseRules: '请选择…',
    confirmToReplay: '请确认规则和贴目后回放。',
    replay: '回放',
    first: '第一手',
    previous: '上一手',
    next: '下一手',
    last: '最后一手',
    warnings: '提示',
    atMove: (n) => `第 ${n} 手`,
    board: (width, height) => `${width}×${height} 棋盘`,
    rulesName: {
      japanese: '日本规则',
      chinese: '中国规则',
      'chinese-ogs': '中国规则（超级劫）',
      aga: 'AGA 规则',
      'new-zealand': '新西兰规则',
      'tromp-taylor': 'Tromp-Taylor 规则',
    },
    error: (code) => errors['zh-CN'][code] ?? code,
  },
}

/** The rule sets offered in forms, by KataGo name. */
export const RULE_NAMES = [
  'chinese',
  'japanese',
  'chinese-ogs',
  'aga',
  'new-zealand',
  'tromp-taylor',
]

export function initialLocale(languages: readonly string[]): Locale {
  return languages.some((language) => language.toLowerCase().startsWith('zh')) ? 'zh-CN' : 'en'
}

export const LocaleContext = createContext<Messages>(messages.en)

export function useMessages(): Messages {
  return useContext(LocaleContext)
}
