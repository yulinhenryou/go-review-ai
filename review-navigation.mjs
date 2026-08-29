export function timelineBounds(timeline) {
  if (!Array.isArray(timeline) || !timeline.length) return null;
  const first = timeline[0]?.move_number;
  const last = timeline.at(-1)?.move_number;
  return {
    first: Number.isInteger(first) ? first : 1,
    last: Number.isInteger(last) ? last : timeline.length,
  };
}

// null represents the post-game position, which is distinct from the last move.
export function stepReviewMove(viewedMoveNumber, offset, bounds) {
  if (!bounds || !offset) return viewedMoveNumber;
  if (viewedMoveNumber === null) return offset < 0 ? bounds.last : null;

  const next = viewedMoveNumber + offset;
  if (next < bounds.first) return bounds.first;
  if (next > bounds.last) return null;
  return next;
}

export function reviewNavigationState(viewedMoveNumber, bounds) {
  if (!bounds) return { canPrevious: false, canNext: false };
  if (viewedMoveNumber === null) return { canPrevious: true, canNext: false };
  return {
    canPrevious: viewedMoveNumber > bounds.first,
    canNext: viewedMoveNumber <= bounds.last,
  };
}
