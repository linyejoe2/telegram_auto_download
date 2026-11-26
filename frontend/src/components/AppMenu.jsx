import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api.js'

// The ☰ button at the top right of every page opens the right side bar: the pages (媒體庫 / 下載紀錄 /
// 人物 / AI 辨識 / 設定) and 登出. The left side bar of the library is the folder tree. Closes on the backdrop, ✕, Esc
// or after choosing an item.

const PAGES = [
  { path: '/', icon: '🎬', label: '媒體庫', hint: '影片與圖片' },
  { path: '/history', icon: '📜', label: '下載紀錄', hint: '所有下載過的檔案，已刪除的可重新下載' },
  { path: '/classify', icon: '🗂', label: '分類器', hint: '把未分類的項目拖進系列、系列改名' },
  { path: '/people', icon: '👥', label: '人物', hint: '人臉資料庫：命名、合併，新影片自動加主演' },
  { path: '/recognition', icon: '🤖', label: 'AI 辨識', hint: '辨識主演 / 系列的進度與結果' },
  { path: '/settings', icon: '⚙', label: '設定', hint: '預設播放畫質、全螢幕' },
]

export default function AppMenu({ onLogout }) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const { pathname } = useLocation()

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  function go(path) {
    setOpen(false)
    if (path !== pathname) navigate(path)
  }

  async function logout() {
    setOpen(false)
    await api.logout().catch(() => {})
    onLogout?.()
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="選單"
        aria-haspopup="dialog"
        aria-expanded={open}
        title="選單"
        className="flex h-8 w-9 shrink-0 items-center justify-center rounded-lg bg-neutral-800 hover:bg-neutral-700"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
      {/* portal: the sticky headers use backdrop-blur, which would trap a fixed element inside them */}
      {open && createPortal(
        <div className="fixed inset-0 z-50 animate-fade-in bg-black/60" onClick={() => setOpen(false)}>
          <nav
            role="dialog"
            aria-label="選單"
            onClick={(e) => e.stopPropagation()}
            className="absolute inset-y-0 right-0 flex w-72 max-w-[85vw] animate-slide-in-right flex-col bg-neutral-900 shadow-2xl ring-1 ring-white/10
              pb-[max(0.75rem,env(safe-area-inset-bottom))] pr-[env(safe-area-inset-right)] pt-[max(0.75rem,env(safe-area-inset-top))]"
          >
            <div className="flex items-center px-4 pb-3">
              <span className="font-semibold">選單</span>
              <button onClick={() => setOpen(false)} aria-label="關閉" className="ml-auto rounded-lg px-2 py-1 text-neutral-400 hover:bg-white/10 hover:text-white">
                ✕
              </button>
            </div>
            <div className="flex-1 space-y-1 overflow-y-auto px-2">
              {PAGES.map((p) => {
                const current = p.path === '/' ? pathname === '/' : pathname.startsWith(p.path)
                return (
                  <button
                    key={p.path}
                    onClick={() => go(p.path)}
                    aria-current={current ? 'page' : undefined}
                    className={`flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left ${
                      current ? 'bg-accent/15 ring-1 ring-accent/50' : 'hover:bg-white/5'
                    }`}
                  >
                    <span className="w-6 text-center text-lg leading-6">{p.icon}</span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{p.label}</span>
                      <span className="block text-xs text-neutral-500">{p.hint}</span>
                    </span>
                  </button>
                )
              })}
            </div>
            <div className="border-t border-white/10 px-2 pt-2">
              <button onClick={logout} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-neutral-300 hover:bg-white/5">
                <span className="w-6 text-center text-lg leading-6">⎋</span>
                登出
              </button>
            </div>
          </nav>
        </div>,
        document.body,
      )}
    </>
  )
}
