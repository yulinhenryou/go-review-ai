import { expect, test, type Locator, type Page } from '@playwright/test'

/** The view that is currently shown (the other stays mounted but hidden). */
export const view = (page: Page) => page.locator('section:not([hidden])')

/** The clickable area of the intersection (x, y) on the shown board. */
export const point = (page: Page, x: number, y: number) =>
  view(page).locator(`.hit[data-point="${x}-${y}"]`)

/** Taps on touch projects and clicks elsewhere, so both input paths run. */
export async function press(target: Locator): Promise<void> {
  if (test.info().project.use.hasTouch) await target.tap()
  else await target.click()
}

/**
 * Records every request the page makes from now on. Called after the page
 * has loaded, an empty list proves the interaction needed no server.
 */
export function recordRequests(page: Page): string[] {
  const urls: string[] = []
  page.on('request', (request) => urls.push(request.url()))
  return urls
}

/** Opens the app and waits until the WASM core has drawn the board. */
export async function openApp(page: Page): Promise<void> {
  await page.goto('/')
  await expect(view(page).locator('svg.board')).toBeVisible()
}

/** The page never scrolls sideways at the project's width. */
export async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBe(0)
}
