import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { loadCore } from './core'

const root = document.getElementById('root')
if (!root) throw new Error('Missing #root element in index.html')

// The board needs the rules core, so the app renders once it has loaded.
await loadCore()

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
