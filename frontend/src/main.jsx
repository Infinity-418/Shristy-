import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as PIXI from 'pixi.js'
window.PIXI = PIXI
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
