import { useEffect } from 'react'
import { projectInfo } from './project'

export default function App() {
  useEffect(() => {
    document.title = projectInfo.name
  }, [])

  return (
    <main className="page">
      <h1 className="title">{projectInfo.name}</h1>
      <p className="tagline">{projectInfo.tagline}</p>
      <p className="status">Early development · under active rebuild</p>
    </main>
  )
}
