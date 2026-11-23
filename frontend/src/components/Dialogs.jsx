import { useEffect, useMemo, useRef, useState } from 'react'
import TagInput from './TagInput.jsx'

// Small modal asking for a name (rename / new folder). Resolves via onSubmit / onCancel.
export function PromptDialog({ title, label, initial = '', confirmText = '確定', onSubmit, onCancel }) {
  const [value, setValue] = useState(initial)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef(null)

  useEffect(() => {
    const el = input.current
    if (!el) return
    el.focus()
    // select the name without the extension, like a file manager
    const dot = initial.lastIndexOf('.')
    el.setSelectionRange(0, dot > 0 ? dot : initial.length)
  }, [])

  async function submit(e) {
    e.preventDefault()
    if (!value.trim()) return
    setBusy(true)
    setError('')
    try {
      await onSubmit(value.trim())
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onMouseDown={onCancel}>
      <form
        onSubmit={submit}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        className="w-full max-w-md space-y-3 rounded-xl bg-neutral-900 p-5 shadow-2xl ring-1 ring-white/10"
      >
        <h2 className="font-medium">{title}</h2>
        {label && <p className="text-sm text-neutral-400">{label}</p>}
        <input
          ref={input}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-full rounded-lg bg-neutral-800 px-3 py-2 text-sm outline-none ring-1 ring-white/10 focus:ring-accent"
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">取消</button>
          <button disabled={busy || !value.trim()} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50">
            {busy ? '處理中…' : confirmText}
          </button>
        </div>
      </form>
    </div>
  )
}

// Multi-select metadata edit: add 主演, tap existing 主演 to remove them, set / clear / keep 系列.
// `items` are the selected summaries; onSubmit({ add_actors, remove_actors, series? }).
export function BulkEditDialog({ items, actorSuggestions = [], seriesSuggestions = [], onSubmit, onCancel }) {
  const [add, setAdd] = useState([])
  const [remove, setRemove] = useState([])
  const [seriesMode, setSeriesMode] = useState('keep') // keep | set | clear
  const [series, setSeries] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // 主演 on the selected items, most used first
  const current = useMemo(() => {
    const count = new Map()
    for (const v of items) for (const a of v.actors) count.set(a, (count.get(a) || 0) + 1)
    return [...count.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-Hant'))
  }, [items])
  const seriesNow = useMemo(() => [...new Set(items.map((v) => v.series || ''))], [items])

  const changed = add.length || remove.length || seriesMode === 'clear' || (seriesMode === 'set' && series.trim())

  async function submit(e) {
    e.preventDefault()
    if (!changed) return
    setBusy(true)
    setError('')
    try {
      const changes = { add_actors: add, remove_actors: remove }
      if (seriesMode === 'clear') changes.series = ''
      else if (seriesMode === 'set' && series.trim()) changes.series = series.trim()
      await onSubmit(changes)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const radio = (mode, label) => (
    <label className="flex items-center gap-1.5 text-sm">
      <input type="radio" name="series-mode" checked={seriesMode === mode} onChange={() => setSeriesMode(mode)} />
      {label}
    </label>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onMouseDown={onCancel}>
      <form
        onSubmit={submit}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        className="max-h-[90vh] w-full max-w-lg space-y-4 overflow-y-auto rounded-xl bg-neutral-900 p-5 shadow-2xl ring-1 ring-white/10"
      >
        <h2 className="font-medium">編輯 {items.length} 個項目的資訊</h2>

        <section className="space-y-2">
          <h3 className="text-sm text-neutral-400">目前的主演（點一下標記為移除）</h3>
          {current.length ? (
            <div className="flex flex-wrap gap-1.5">
              {current.map(([name, n]) => {
                const off = remove.includes(name)
                return (
                  <button
                    key={name}
                    type="button"
                    aria-pressed={off}
                    onClick={() => setRemove(off ? remove.filter((r) => r !== name) : [...remove, name])}
                    className={`rounded-md px-2 py-0.5 text-sm ${
                      off ? 'bg-red-900/60 text-red-200 line-through' : 'bg-accent/20 text-red-100 hover:bg-accent/30'
                    }`}
                    title={off ? '取消移除' : `從 ${n} 個項目移除`}
                  >
                    {name} <span className="text-xs opacity-70">{n}/{items.length}</span>
                    {!off && <span className="ml-1 opacity-70">×</span>}
                  </button>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-neutral-500">選取的項目都沒有主演</p>
          )}
        </section>

        <section className="space-y-2">
          <h3 className="text-sm text-neutral-400">新增主演（加到全部選取的項目）</h3>
          <TagInput value={add} onChange={setAdd} suggestions={actorSuggestions} placeholder="輸入名字後按 Enter" />
        </section>

        <section className="space-y-2">
          <h3 className="text-sm text-neutral-400">
            系列
            <span className="ml-2 text-xs text-neutral-500">
              目前：{seriesNow.length === 1 ? seriesNow[0] || '（無）' : `${seriesNow.length} 種不同`}
            </span>
          </h3>
          <div className="flex flex-wrap gap-4">
            {radio('keep', '不變更')}
            {radio('set', '設為')}
            {radio('clear', '清除')}
          </div>
          {seriesMode === 'set' && (
            <>
              <input
                autoFocus
                list="bulk-series"
                value={series}
                onChange={(e) => setSeries(e.target.value)}
                placeholder="系列名稱"
                className="w-full rounded-lg bg-neutral-800 px-3 py-1.5 text-sm outline-none ring-1 ring-white/10 focus:ring-accent"
              />
              <datalist id="bulk-series">
                {seriesSuggestions.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
            </>
          )}
        </section>

        {error && <p className="text-sm text-red-400">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">取消</button>
          <button disabled={busy || !changed} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50">
            {busy ? '處理中…' : '套用'}
          </button>
        </div>
      </form>
    </div>
  )
}

// Right-click menu at the mouse position; closes on outside click, scroll or Escape.
export function ContextMenu({ x, y, items, onClose }) {
  const ref = useRef(null)
  const [pos, setPos] = useState({ left: x, top: y })

  useEffect(() => {
    const el = ref.current
    if (el) {
      // keep the menu inside the window
      const { width, height } = el.getBoundingClientRect()
      setPos({ left: Math.min(x, window.innerWidth - width - 8), top: Math.min(y, window.innerHeight - height - 8) })
    }
    const close = () => onClose()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('mousedown', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
      window.removeEventListener('keydown', onKey)
    }
  }, [x, y])

  return (
    <div
      ref={ref}
      style={pos}
      onMouseDown={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.preventDefault()}
      className="fixed z-50 min-w-44 overflow-hidden rounded-lg bg-neutral-800 py-1 text-sm shadow-2xl ring-1 ring-white/10"
    >
      {items.map((item, i) =>
        item === '-' ? (
          <div key={i} className="my-1 border-t border-white/10" />
        ) : (
          <button
            key={i}
            disabled={item.disabled}
            onClick={() => {
              onClose()
              item.onClick()
            }}
            className={`block w-full px-3 py-1.5 text-left hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-transparent ${
              item.danger ? 'text-red-300' : ''
            }`}
          >
            {item.label}
          </button>
        ),
      )}
    </div>
  )
}
