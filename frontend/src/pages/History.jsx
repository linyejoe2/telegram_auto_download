import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, fmtSize } from '../api.js'
import AppMenu from '../components/AppMenu.jsx'

// 下載紀錄: every file the bot downloaded. Existing videos / photos open their page; deleted files
// can be downloaded again (the running bot puts it in its queue, progress shows in Telegram).

const PAGE = 100
const KIND_ICON = { video: '🎬', photo: '🖼', file: '📄' }
const STATUS = [
  ['', '全部', 'all'],
  ['exists', '存在', 'exists'],
  ['deleted', '已刪除', 'deleted'],
]

export default function History({ guard, onLogout }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const status = params.get('status') || ''
  const kind = params.get('kind') || ''
  const [data, setData] = useState(null) // { total, counts, items, redownload }
  const [loadingMore, setLoadingMore] = useState(false)
  const [queued, setQueued] = useState(() => new Set())
  const [toast, setToast] = useState(null)
  const toastTimer = useRef(null)

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  function notify(text, error = false) {
    setToast({ text, error })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(null), error ? 6000 : 4000)
  }

  async function fetchPage(offset) {
    return api.history({ q, status, kind, offset, limit: PAGE })
  }

  // reload when the filters change (typing is debounced)
  useEffect(() => {
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const page = await fetchPage(0)
        if (!cancelled) setData(page)
      } catch (e) {
        if (!cancelled) {
          try {
            guard(e)
          } catch (err) {
            notify(err.message, true)
          }
        }
      }
    }, q ? 250 : 0)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [q, status, kind])

  async function loadMore() {
    setLoadingMore(true)
    try {
      const page = await fetchPage(data.items.length)
      setData((d) => ({ ...page, items: [...d.items, ...page.items] }))
    } catch (e) {
      guard(e)
    } finally {
      setLoadingMore(false)
    }
  }

  async function redownload(item) {
    const where = item.folder ? `/${item.folder}` : '下載資料夾根目錄'
    if (!window.confirm(`重新下載「${item.file}」到 ${where}？\n會排進 Bot 的下載佇列，進度會顯示在 Telegram。`)) return
    try {
      await api.redownload(item.key)
      setQueued((s) => new Set(s).add(item.key))
      notify('已加入下載佇列，進度會顯示在 Telegram；下載完成後重新整理即可看到')
    } catch (e) {
      try {
        guard(e)
      } catch (err) {
        notify(err.message, true)
      }
    }
  }

  function open(item) {
    navigate(`/v/${item.id}`, { state: { backPath: `/history${params.toString() ? `?${params}` : ''}` } })
  }

  const counts = data?.counts || {}

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-16">
      <header className="sticky top-0 z-10 -mx-4 mb-4 space-y-3 bg-neutral-950/90 px-4 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">下載紀錄</h1>
          {data && <span className="text-sm text-neutral-400">{data.total} 筆</span>}
          <div className="ml-auto">
            <AppMenu onLogout={onLogout} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex overflow-hidden rounded-lg ring-1 ring-white/10" role="group" aria-label="狀態">
            {STATUS.map(([value, label, key]) => (
              <button
                key={key}
                onClick={() => setParam('status', value)}
                aria-pressed={status === value}
                className={`px-3 py-1.5 text-sm ${status === value ? 'bg-accent/80 text-white' : 'bg-neutral-800 hover:bg-neutral-700'}`}
              >
                {label}
                {counts[key] != null && <span className="ml-1 text-xs opacity-70 tabular-nums">{counts[key]}</span>}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-neutral-400">類型</span>
            <select
              value={kind}
              onChange={(e) => setParam('kind', e.target.value)}
              className="rounded-lg bg-neutral-800 px-2 py-1.5 outline-none ring-1 ring-white/10 focus:ring-accent"
            >
              <option value="">全部</option>
              <option value="video">影片</option>
              <option value="photo">圖片</option>
              <option value="file">其他檔案</option>
            </select>
          </label>
          <input
            value={q}
            onChange={(e) => setParam('q', e.target.value)}
            placeholder="搜尋檔名、資料夾、連結…"
            className="min-w-56 flex-1 rounded-lg bg-neutral-800 px-3 py-1.5 text-sm outline-none ring-1 ring-white/10 focus:ring-accent"
          />
        </div>
        {data && !data.redownload && (
          <p className="text-xs text-amber-300">這台電腦的程式沒有在執行 Bot，已刪除的檔案暫時無法重新下載。</p>
        )}
      </header>

      {data === null ? (
        <p className="text-neutral-400">載入中…</p>
      ) : data.items.length === 0 ? (
        <p className="py-16 text-center text-neutral-500">{counts.all ? '沒有符合的紀錄' : '還沒有下載紀錄'}</p>
      ) : (
        <>
          <div className="hidden grid-cols-[28px_minmax(0,3fr)_80px_140px_minmax(0,1.2fr)_120px] gap-3 border-b border-white/5 px-2 pb-2 text-xs text-neutral-500 md:grid">
            <span />
            <span>檔案 / 資料夾</span>
            <span className="text-right">大小</span>
            <span>下載時間</span>
            <span>來源</span>
            <span className="text-right">狀態</span>
          </div>
          <ul>
            {data.items.map((item) => {
              const clickable = !item.deleted && item.id
              const isQueued = queued.has(item.key)
              return (
                <li
                  key={item.key}
                  onClick={clickable ? () => open(item) : undefined}
                  title={
                    clickable ? '開啟' : !item.deleted ? '這種檔案不會顯示在媒體庫（或尚未掃描到）' : item.deleted_date ? `刪除於 ${item.deleted_date}` : undefined
                  }
                  className={`grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-2 py-2 md:grid-cols-[28px_minmax(0,3fr)_80px_140px_minmax(0,1.2fr)_120px] ${
                    clickable ? 'cursor-pointer hover:bg-white/5' : ''
                  } ${item.deleted ? 'text-neutral-400' : ''}`}
                >
                  <span className="text-center" aria-hidden>{KIND_ICON[item.kind]}</span>
                  <div className="min-w-0">
                    <p className={`truncate text-sm ${item.deleted ? 'line-through decoration-neutral-600' : 'font-medium'}`}>{item.file}</p>
                    <p className="truncate text-xs text-neutral-500">
                      {item.inside ? `/${item.folder}` : item.folder}
                      <span className="md:hidden">{` · ${fmtSize(item.size)} · ${(item.date || '').slice(0, 16)}`}</span>
                    </p>
                  </div>
                  <span className="hidden text-right text-sm tabular-nums text-neutral-400 md:block">{fmtSize(item.size)}</span>
                  <span className="hidden text-sm tabular-nums text-neutral-400 md:block">{(item.date || '').slice(0, 16) || '-'}</span>
                  <span className="hidden min-w-0 md:block">
                    {item.source ? (
                      <a
                        href={item.source}
                        target="_blank"
                        rel="noreferrer noopener"
                        onClick={(e) => e.stopPropagation()}
                        className="block truncate text-xs text-accent hover:underline"
                      >
                        {item.source.replace(/^https?:\/\//, '')}
                      </a>
                    ) : (
                      <span className="text-xs text-neutral-600">-</span>
                    )}
                  </span>
                  <span className="text-right">
                    {!item.deleted ? (
                      <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300">存在</span>
                    ) : isQueued ? (
                      <span className="rounded bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300">已排入佇列</span>
                    ) : (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          redownload(item)
                        }}
                        disabled={!data.redownload}
                        className="rounded-lg bg-neutral-800 px-2.5 py-1 text-xs text-neutral-100 hover:bg-neutral-700 disabled:opacity-40"
                        title={data.redownload ? '重新下載到原本的資料夾' : 'Bot 沒有在執行'}
                      >
                        ⬇ 重新下載
                      </button>
                    )}
                  </span>
                </li>
              )
            })}
          </ul>
          {data.items.length < data.total && (
            <div className="pt-4 text-center">
              <button onClick={loadMore} disabled={loadingMore} className="rounded-lg bg-neutral-800 px-4 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-50">
                {loadingMore ? '載入中…' : `載入更多（還有 ${data.total - data.items.length} 筆）`}
              </button>
            </div>
          )}
        </>
      )}

      {toast && (
        <div
          className={`fixed bottom-4 left-1/2 z-50 max-w-[90vw] -translate-x-1/2 whitespace-pre-line rounded-lg px-4 py-2 text-sm shadow-xl ${
            toast.error ? 'bg-red-900 text-red-100' : 'bg-neutral-800 text-neutral-100'
          }`}
        >
          {toast.text}
        </div>
      )}
    </div>
  )
}
