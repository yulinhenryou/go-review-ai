import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import packageJson from '../package.json'
import App from './App'
import { projectInfo } from './project'
import { repositoryFile } from './test/files'

const point = (container: HTMLElement, x: number, y: number) =>
  container.querySelector(`.hit[data-point="${x}-${y}"]`) as Element

describe('App', () => {
  it('shows the project name and tagline from config/project.json', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(projectInfo.name)
    expect(screen.getByText(projectInfo.tagline)).toBeTruthy()
  })

  it('keeps the package name in step with the project slug', () => {
    // Guards the rename checklist in CLAUDE.md.
    expect(packageJson.name).toBe(`${projectInfo.slug}-web`)
  })

  it('places and captures stones through the core, then undoes', () => {
    const { container } = render(<App />)
    for (const [x, y] of [
      [1, 0],
      [0, 0],
      [0, 1],
    ])
      fireEvent.click(point(container, x, y))
    expect(container.querySelector('[data-stone][data-point="0-0"]')).toBeNull()
    expect(screen.getByTestId('captures').textContent).toBe('Captures: Black 1 · White 0')
    fireEvent.click(point(container, 1, 0))
    expect(screen.getByRole('status').textContent).toBe('That point is already occupied.')
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    // Undoing the capture puts the captured white stone back.
    expect(container.querySelectorAll('[data-stone]')).toHaveLength(2)
    expect(container.querySelector('[data-point="0-0"]')?.getAttribute('data-stone')).toBe('W')
  })

  it('switches the interface to Chinese', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: '中文' }))
    expect(screen.getByRole('button', { name: '停一手' })).toBeTruthy()
    expect(document.documentElement.lang).toBe('zh-CN')
  })

  it('opens an SGF file, replays it and navigates to the end', async () => {
    const { container } = render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open SGF' }))
    const bytes = repositoryFile('testdata/sgf/kejie-2025-11-27.sgf')
    const file = new File([bytes], 'kejie.sgf')
    fireEvent.change(screen.getByTestId('sgf-file'), { target: { files: [file] } })
    expect(await screen.findByTestId('black-player')).toHaveProperty('textContent', '柯洁 ?')

    const record = container.querySelector('section:not([hidden])') as HTMLElement
    fireEvent.click(within(record).getByRole('button', { name: 'Replay' }))
    expect(within(record).getByTestId('move-number').textContent).toBe('Move 0 of 111')
    fireEvent.click(within(record).getByRole('button', { name: 'Last move' }))
    expect(within(record).getByTestId('move-number').textContent).toBe('Move 111 of 111')
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(within(record).getByTestId('move-number').textContent).toBe('Move 110 of 111')
  })

  it('lists the file warnings with localized text', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open SGF' }))
    // No RU, so the rules must be chosen; W[tt] on 19×19 is the FF[3] pass.
    const sgf = '(;GM[1]FF[4]SZ[19]KM[6.5];B[dd];W[tt])'
    fireEvent.change(screen.getByTestId('sgf-file'), {
      target: { files: [new File([sgf], 'small.sgf')] },
    })
    const items = (await screen.findByTestId('warnings')).querySelectorAll('li')
    expect([...items].map((li) => li.textContent)).toEqual([
      'The file does not state the rules.',
      'A move at tt was read as a pass.',
    ])
  })
})
