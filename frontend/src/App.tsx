import { useState } from 'react'
import HomePage from './components/HomePage'
import ProjectPage from './components/ProjectPage'
import DsaPage from './components/DsaPage'
import ResearchPage from './components/ResearchPage'

export type NavPage = 'home' | 'project' | 'dsa' | 'research'

export default function App() {
  const [currentPage, setCurrentPage] = useState<NavPage>('home')

  return (
    <div className="h-full w-full">
      {currentPage === 'home' && (
        <HomePage onNavigate={page => setCurrentPage(page)} />
      )}
      {currentPage === 'project' && (
        <ProjectPage onBack={() => setCurrentPage('home')} />
      )}
      {currentPage === 'dsa' && (
        <DsaPage onBack={() => setCurrentPage('home')} />
      )}
      {currentPage === 'research' && (
        <ResearchPage onBack={() => setCurrentPage('home')} />
      )}
    </div>
  )
}
