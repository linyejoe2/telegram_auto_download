import { useState } from 'react'
import { api } from '../api.js'

export default function Login({ onLogin }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.login(password)
      onLogin()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl bg-neutral-900 p-8 shadow-xl ring-1 ring-white/10">
        <div>
          <h1 className="text-xl font-semibold">影片庫</h1>
          <p className="mt-1 text-sm text-neutral-400">請輸入在 Windows 程式中設定的密碼</p>
        </div>
        <input
          type="password"
          autoFocus
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="密碼"
          className="w-full rounded-lg bg-neutral-800 px-3 py-2 outline-none ring-1 ring-white/10 focus:ring-accent"
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          disabled={busy || !password}
          className="w-full rounded-lg bg-accent py-2 font-medium hover:bg-accent-hover disabled:opacity-50"
        >
          {busy ? '登入中…' : '登入'}
        </button>
      </form>
    </div>
  )
}
