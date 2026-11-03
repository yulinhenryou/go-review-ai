import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import packageJson from '../package.json'
import App from './App'
import { projectInfo } from './project'

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
})
