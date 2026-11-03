export const BOARD_SIZE = 19;
export const SGF_LETTERS = "abcdefghijklmnopqrstuvwxyz";
export const DISPLAY_COLUMNS = "ABCDEFGHJKLMNOPQRST";
export function colorName(color) {
  return color === "B" ? "黑棋" : "白棋";
}

export function toSgf(x, y) {
  return SGF_LETTERS.charAt(x) + SGF_LETTERS.charAt(y);
}

export function fromSgf(sgf) {
  if (typeof sgf !== "string" || sgf.length !== 2) return null;

  var x = SGF_LETTERS.indexOf(sgf.charAt(0));
  var y = SGF_LETTERS.indexOf(sgf.charAt(1));

  if (x < 0 || y < 0 || x >= BOARD_SIZE || y >= BOARD_SIZE) return null;

  return { x: x, y: y };
}

export function fromDisplayCoord(display) {
  if (typeof display !== "string") return null;

  var normalized = display.trim().toUpperCase();
  var match = /^([A-HJ-T])\s*(\d{1,2})$/.exec(normalized);
  var x;
  var row;
  var y;

  if (!match) return null;

  x = DISPLAY_COLUMNS.indexOf(match[1]);
  row = Number(match[2]);
  y = BOARD_SIZE - row;

  if (x < 0 || row < 1 || row > BOARD_SIZE || y < 0 || y >= BOARD_SIZE) return null;

  return { x: x, y: y };
}
