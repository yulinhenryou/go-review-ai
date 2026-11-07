import { useEffect, useState } from 'react'
import { ManualPlay } from './components/ManualPlay'
import { RecordReplay } from './components/RecordReplay'
import { LocaleContext, initialLocale, messages, type Locale } from './i18n'
import { projectInfo } from './project'

type Mode = 'manual' | 'record'

export default function App() {
  const [locale, setLocale] = useState<Locale>(() => initialLocale(navigator.languages))
  const [mode, setMode] = useState<Mode>('manual')
  const t = messages[locale]

  useEffect(() => {
    document.title = projectInfo.name
    document.documentElement.lang = locale
  }, [locale])

  return (
    <LocaleContext value={t}>
      <header className="header">
        <div>
          <h1 className="title">{projectInfo.name}</h1>
          <p className="tagline">{projectInfo.tagline}</p>
        </div>
        <button
          type="button"
          className="link"
          onClick={() => setLocale(locale === 'en' ? 'zh-CN' : 'en')}
        >
          {t.languageToggle}
        </button>
      </header>
      <nav className="tabs" aria-label={projectInfo.name}>
        <button type="button" aria-pressed={mode === 'manual'} onClick={() => setMode('manual')}>
          {t.enterMoves}
        </button>
        <button type="button" aria-pressed={mode === 'record'} onClick={() => setMode('record')}>
          {t.openSgf}
        </button>
      </nav>
      {/* Both views stay mounted so that switching keeps the game and the file. */}
      <main>
        <section hidden={mode !== 'manual'}>
          <ManualPlay />
        </section>
        <section hidden={mode !== 'record'}>
          <RecordReplay active={mode === 'record'} />
        </section>
      </main>
    </LocaleContext>
  )
}
