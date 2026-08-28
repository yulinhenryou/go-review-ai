import test from "node:test";
import assert from "node:assert/strict";
import { createBoardView } from "../../frontend/board-view.mjs";

test("board renderer uses supplied snapshots, move numbers, markers and responsive coordinates", () => {
  const calls = [];
  const context = new Proxy({}, {
    get: (_target, key) => key === "createRadialGradient" ? () => ({ addColorStop() {} })
      : (...args) => calls.push([key, ...args]),
    set: () => true
  });
  let resize;
  globalThis.window = { devicePixelRatio: 2, addEventListener: (_name, fn) => { resize = fn; } };
  const rect = { width: 400, left: 10, top: 20 };
  const board = { getBoundingClientRect: () => rect };
  const canvas = { style: {}, getContext: () => context, getBoundingClientRect: () => rect };
  try {
    const view = createBoardView(board, canvas);
    const position = { stones: [{ color: "B", sgf: "aa", move_number: 3 }] };
    const before = structuredClone(position);
    view.draw({ position, moveCount: 3, showNumbers: true,
      markers: [{ x: 3, y: 3, kind: "recommended", label: "1", selected: true }] });
    assert.equal(canvas.width, 800);
    assert.ok(calls.some(([name, text]) => name === "fillText" && text === "3"));
    assert.ok(calls.some(([name, text]) => name === "fillText" && text === "T"));
    assert.deepEqual(position, before);
    assert.deepEqual(view.pointAt({ clientX: 40, clientY: 50 }), { x: 0, y: 0 });
    assert.equal(view.pointAt({ clientX: 10, clientY: 20 }), null);
    rect.width = 300;
    resize();
    assert.equal(canvas.width, 600);
  } finally { delete globalThis.window; }
});
