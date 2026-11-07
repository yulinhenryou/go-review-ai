// Manual entry: every legality decision comes from the WASM core in the page.
import { expect, test, type Page } from '@playwright/test'
import { expectNoHorizontalScroll, openApp, point, press, recordRequests, view } from './helpers'

const stones = (page: Page) => view(page).locator('[data-stone]')

// A wrapping label names its select by the label text plus the chosen
// option ("Board 19×19"), so the names are matched by prefix.
async function newGame(page: Page, size: string, rules: string) {
  await view(page)
    .getByRole('combobox', { name: /^Board/ })
    .selectOption(size)
  await view(page)
    .getByRole('combobox', { name: /^Rules/ })
    .selectOption({ label: rules })
  await press(view(page).getByRole('button', { name: 'New game' }))
}

async function play(page: Page, moves: [number, number][]) {
  for (const [x, y] of moves) await press(point(page, x, y))
}

test.beforeEach(async ({ page }) => {
  await openApp(page)
})

test('places stones, captures and undoes without a server call', async ({ page }) => {
  const requests = recordRequests(page)
  await play(page, [
    [1, 0],
    [0, 0],
    [0, 1],
  ])
  await expect(stones(page)).toHaveCount(2)
  await expect(view(page).getByTestId('captures')).toHaveText('Captures: Black 1 · White 0')

  await press(point(page, 1, 0))
  await expect(view(page).getByRole('status')).toHaveText('That point is already occupied.')

  await press(view(page).getByRole('button', { name: 'Undo' }))
  // The captured white stone comes back.
  await expect(stones(page)).toHaveCount(2)
  await expect(view(page).locator('[data-stone][data-point="0-0"]')).toHaveAttribute(
    'data-stone',
    'W',
  )
  await expect(view(page).getByTestId('captures')).toHaveText('Captures: Black 0 · White 0')
  await expectNoHorizontalScroll(page)
  expect(requests).toEqual([])
})

test('rejects an immediate ko recapture', async ({ page }) => {
  const requests = recordRequests(page)
  await newGame(page, '9', 'Japanese')
  // The ko from testdata/conformance/games.json: Black takes at (2, 1).
  await play(page, [
    [1, 0],
    [1, 1],
    [0, 1],
    [2, 0],
    [1, 2],
    [2, 2],
    [4, 4],
    [3, 1],
    [2, 1],
  ])
  await expect(view(page).locator('[data-ko-ban="1-1"]')).toBeVisible()
  await expect(stones(page)).toHaveCount(8)

  await press(point(page, 1, 1))
  await expect(view(page).getByRole('status')).toHaveAttribute('data-rejected', 'ko_violation')
  await expect(view(page).getByRole('status')).toHaveText(
    'Ko: this stone cannot be retaken at once; play elsewhere first.',
  )
  await expect(stones(page)).toHaveCount(8)
  await expect(view(page).getByTestId('move-number')).toHaveText('Move 9')
  expect(requests).toEqual([])
})

test('rejects suicide, passes and undoes', async ({ page }) => {
  const requests = recordRequests(page)
  await newGame(page, '9', 'Chinese')
  await press(point(page, 1, 0))
  await press(view(page).getByRole('button', { name: 'Pass' }))
  await expect(view(page).getByTestId('to-play')).toHaveText('Black to play')
  await press(point(page, 0, 1))

  await press(point(page, 0, 0))
  await expect(view(page).getByRole('status')).toHaveAttribute('data-rejected', 'suicide')
  await expect(view(page).locator('[data-stone][data-point="0-0"]')).toHaveCount(0)

  await press(view(page).getByRole('button', { name: 'Pass' }))
  await press(view(page).getByRole('button', { name: 'Pass' }))
  await expect(view(page).getByTestId('move-number')).toHaveText('Move 5')
  await expect(view(page).getByText('Both players passed.')).toBeVisible()

  const undo = view(page).getByRole('button', { name: 'Undo' })
  for (let i = 0; i < 5; i++) await press(undo)
  await expect(stones(page)).toHaveCount(0)
  await expect(undo).toBeDisabled()
  expect(requests).toEqual([])
})
