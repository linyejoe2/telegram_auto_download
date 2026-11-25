import { useCallback, useEffect, useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { api, Unauthorized } from './api.js'
import Login from './pages/Login.jsx'
import Library from './pages/Library.jsx'
import VideoPage from './pages/VideoPage.jsx'
import History from './pages/History.jsx'
import Settings from './pages/Settings.jsx'
import Recognition from './pages/Recognition.jsx'

export default function App() {
  const [authed, setAuthed] = useState(null) // null = checking

  useEffect(() => {
    api.session().then((s) => setAuthed(s.authenticated)).catch(() => setAuthed(false))
  }, [])

  // any API call that comes back 401 sends the user to the login screen
  const guard = useCallback((err) => {
    if (err instanceof Unauthorized) setAuthed(false)
    else throw err
  }, [])

  if (authed === null) return <div className="p-8 text-neutral-400">載入中…</div>
  if (!authed) return <Login onLogin={() => setAuthed(true)} />

  // every page has the ☰ side bar (AppMenu) with 登出
  const onLogout = () => setAuthed(false)
  return (
    <Routes>
      <Route path="/" element={<Library guard={guard} onLogout={onLogout} />} />
      <Route path="/v/:id" element={<VideoPage guard={guard} onLogout={onLogout} />} />
      <Route path="/history" element={<History guard={guard} onLogout={onLogout} />} />
      <Route path="/settings" element={<Settings onLogout={onLogout} />} />
      <Route path="/recognition" element={<Recognition guard={guard} onLogout={onLogout} />} />
      <Route path="*" element={<Library guard={guard} onLogout={onLogout} />} />
    </Routes>
  )
}
