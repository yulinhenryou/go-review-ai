import test from "node:test";
import assert from "node:assert/strict";
import {
  reviewNavigationState,
  stepReviewMove,
  timelineBounds,
} from "../../frontend/review-navigation.mjs";

test("the last move remains distinct from the post-game position", () => {
  const bounds = timelineBounds([{ move_number: 1 }, { move_number: 6 }]);
  assert.deepEqual(bounds, { first: 1, last: 6 });
  assert.equal(stepReviewMove(5, 1, bounds), 6);
  assert.equal(stepReviewMove(6, 1, bounds), null);
  assert.equal(stepReviewMove(null, -1, bounds), 6);
});

test("review navigation exposes the correct controls at each boundary", () => {
  const bounds = { first: 1, last: 6 };
  assert.deepEqual(reviewNavigationState(1, bounds), { canPrevious: false, canNext: true });
  assert.deepEqual(reviewNavigationState(6, bounds), { canPrevious: true, canNext: true });
  assert.deepEqual(reviewNavigationState(null, bounds), { canPrevious: true, canNext: false });
  assert.deepEqual(reviewNavigationState(null, null), { canPrevious: false, canNext: false });
});
