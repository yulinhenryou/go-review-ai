// SGF review: the core decodes, extracts and replays the file in the page.
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { expectNoHorizontalScroll, openApp, press, recordRequests, view } from './helpers'

// The GBK copy of a public professional game (testdata/sgf/PROVENANCE.md).
const KE_JIE = join(import.meta.dirname, '../../testdata/sgf/kejie-2025-11-27-gbk.sgf')

test('opens a GBK SGF file, replays it and steps through it', async ({ page }) => {
  await openApp(page)
  const requests = recordRequests(page)
  await press(page.getByRole('button', { name: 'Open SGF' }))
  await view(page).getByTestId('sgf-file').setInputFiles(KE_JIE)

  await expect(view(page).getByTestId('black-player')).toHaveText('柯洁 ?')
  await expect(view(page).getByText('gb18030', { exact: true })).toBeVisible()
  await press(view(page).getByRole('button', { name: 'Replay' }))
  const moveNumber = view(page).getByTestId('move-number')
  await expect(moveNumber).toHaveText('Move 0 of 111')

  await press(view(page).getByRole('button', { name: 'Next move' }))
  await expect(moveNumber).toHaveText('Move 1 of 111')
  await expect(view(page).locator('[data-stone]')).toHaveCount(1)
  await expect(view(page).locator('[data-last-move]')).toHaveCount(1)

  await page.keyboard.press('End')
  await expect(moveNumber).toHaveText('Move 111 of 111')
  await page.keyboard.press('ArrowLeft')
  await expect(moveNumber).toHaveText('Move 110 of 111')
  await press(view(page).getByRole('button', { name: 'First move' }))
  await expect(moveNumber).toHaveText('Move 0 of 111')
  await expect(view(page).locator('[data-stone]')).toHaveCount(0)

  await expectNoHorizontalScroll(page)
  // Choosing a local file is not a request; nothing else may be either.
  expect(requests).toEqual([])
})
