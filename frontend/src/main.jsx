import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './index.css'

// the library page restores its own scroll position (after its list has loaded); the browser's guess
// on back / reload would jump around while the page is still short
if ('scrollRestoration' in history) history.scrollRestoration = 'manual'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter basename="/library">
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
