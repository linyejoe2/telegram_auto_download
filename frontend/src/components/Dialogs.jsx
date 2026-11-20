import { useEffect, useRef, useState } from 'react'

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
