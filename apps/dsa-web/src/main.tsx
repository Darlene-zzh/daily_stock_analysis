import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import './index.css'
import App from './App.tsx'
import { ThemeProvider } from './components/theme/ThemeProvider'
import { FamilyThemeProvider } from './components/theme/FamilyThemeProvider'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <ThemeProvider>
        <FamilyThemeProvider>
          <App />
        </FamilyThemeProvider>
      </ThemeProvider>
    </MotionConfig>
  </StrictMode>,
)
