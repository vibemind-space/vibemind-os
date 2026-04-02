import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { initWebAPI } from './api/webAPI'
import { initVibeMindAdapter, isEmbeddedMode } from './adapters/vibemindAdapter'

// Initialize API synchronously before rendering
// Priority: VibeMind embedded > Electron standalone > Web fallback
if (window.vibemind) {
  // Running inside VibeMind as embedded BrowserView
  initVibeMindAdapter()
  console.log('[Dashboard] Running in VibeMind embedded mode')
} else if (!window.electronAPI) {
  // No Electron API available - use web API fallback
  initWebAPI()
  console.log('[Dashboard] Running in web mode')
} else {
  console.log('[Dashboard] Running in Electron standalone mode')
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
