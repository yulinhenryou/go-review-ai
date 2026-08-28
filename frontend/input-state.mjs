const empty = () => ({
  game: { board_size: 19, rules: null, komi: null, players: null, result: null, moves: [] },
  positions: [{ next_player: "B", stones: [] }], warnings: [], source: "manual"
});

export function gamePayload(game) {
  const { board_size, rules, komi, players, result, moves } = game;
  return structuredClone({ board_size, rules, komi, players, result, moves });
}

export function createInputState(replay) {
  let value = empty();
  let revision = 0;
  function replace(preview, source = "manual") {
    if (preview.positions?.length !== preview.game.moves.length + 1) {
      throw new Error("局面快照不完整，请更新后端。");
    }
    value = structuredClone({ ...preview, source });
    revision++;
  }
  return {
    get: () => value,
    revision: () => revision,
    replace,
    invalidate: () => ++revision,
    clear: () => { revision++; value = empty(); },
    undo: () => {
      revision++;
      value = { ...value, source: "manual", warnings: [],
        game: { ...value.game, result: null, moves: value.game.moves.slice(0, -1) },
        positions: value.positions.slice(0, Math.max(1, value.positions.length - 1)) };
    },
    async place(sgf, settings) {
      const token = ++revision;
      const game = gamePayload(value.game);
      Object.assign(game, settings, { result: null });
      game.moves.push({ color: value.positions.at(-1).next_player, sgf });
      const preview = await replay(game);
      if (token !== revision) return false;
      replace(preview);
      return true;
    }
  };
}
