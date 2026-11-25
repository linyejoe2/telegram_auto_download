import { useEffect, useMemo, useRef, useState } from 'react'
import { api, fmtDuration } from '../api.js'
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

// Multi-select 「嘗試合併」: `data` is the comparison of the selected videos ({items, pairs: [[id, id, score]],
// photos, threshold}, nothing merged yet). The slider sets this merge's similarity threshold and the
// groups follow it at once (a match of a match joins too), highest similarity first; 確定合併 calls
// onConfirm(groups as id lists), 取消 merges nothing.
const MIN_THRESHOLD = 40
const MAX_THRESHOLD = 99

function groupAt(data, threshold) {
  const ok = data.items.filter((i) => i.status === 'ok')
  const parent = new Map(ok.map((i) => [i.id, i.id]))
  const root = (v) => {
    while (parent.get(v) !== v) {
      parent.set(v, parent.get(parent.get(v)))
      v = parent.get(v)
    }
    return v
  }
  const join = (a, b) => parent.set(root(a), root(b))
  const firstOfGroup = {}
  for (const i of ok) {
    if (!i.group) continue
    if (firstOfGroup[i.group]) join(i.id, firstOfGroup[i.group]) // already versions of each other
    else firstOfGroup[i.group] = i.id
  }
  const best = new Map() // id -> best score with any selected video of similar length, any threshold
  for (const [a, b, score] of data.pairs) {
    best.set(a, Math.max(best.get(a) ?? 0, score))
    best.set(b, Math.max(best.get(b) ?? 0, score))
  }
  const edges = data.pairs.filter((p) => p[2] >= threshold)
  for (const [a, b] of edges) join(a, b)

  const comps = new Map()
  for (const i of ok) {
    const r = root(i.id)
    if (!comps.has(r)) comps.set(r, { items: [], scores: [] })
    comps.get(r).items.push(i)
  }
  for (const [a, , score] of edges) comps.get(root(a)).scores.push(score)

  const groups = []
  const single = []
  let already = 0
  for (const c of comps.values()) {
    if (c.items.length === 1) {
      const i = c.items[0]
      single.push({ ...i, best: best.has(i.id) ? best.get(i.id) : null })
    } else if (!c.scores.length) already += 1
    else groups.push({ items: c.items, ids: c.items.map((i) => i.id), min: Math.min(...c.scores), max: Math.max(...c.scores) })
  }
  groups.sort((a, b) => b.max - a.max || b.min - a.min) // highest similarity first
  single.sort((a, b) => (b.best ?? -1) - (a.best ?? -1))
  return { groups, single, already }
}

const pct = (n) => `${Math.round(n)}%`
const range = (g) => (Math.round(g.min) === Math.round(g.max) ? pct(g.max) : `${pct(g.max)}–${pct(g.min)}`)

export function MergeDialog({ data, onConfirm, onCancel }) {
  const [threshold, setThreshold] = useState(data.threshold)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const { groups, single, already } = useMemo(() => groupAt(data, threshold), [data, threshold])
  const failed = data.items.filter((i) => i.status !== 'ok')
  const merging = groups.reduce((n, g) => n + g.items.length, 0)

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && !busy && onCancel()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy])

  async function confirm() {
    setBusy(true)
    setError('')
    try {
      await onConfirm(groups.map((g) => g.ids))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onMouseDown={() => !busy && onCancel()}>
      <div
        role="dialog"
        aria-label="嘗試合併"
        onMouseDown={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl bg-neutral-900 shadow-2xl ring-1 ring-white/10"
      >
        <div className="space-y-3 border-b border-white/10 p-5 pb-4">
          <h2 className="font-medium">嘗試合併 {data.items.length} 部影片</h2>
          <div>
            <div className="flex items-baseline justify-between text-sm">
              <label htmlFor="merge-threshold" className="text-neutral-300">
                相似度門檻 <span className="font-medium tabular-nums text-white">{threshold}%</span>
              </label>
              {threshold !== data.threshold && (
                <button onClick={() => setThreshold(data.threshold)} className="text-xs text-neutral-400 hover:text-white">
                  回到預設 {data.threshold}%
                </button>
              )}
            </div>
            <input
              id="merge-threshold"
              type="range"
              min={MIN_THRESHOLD}
              max={MAX_THRESHOLD}
              step={1}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="seek mt-2 w-full"
            />
            <div className="flex justify-between text-[11px] tabular-nums text-neutral-500">
              <span>{MIN_THRESHOLD}%（寬鬆）</span>
              <span>{MAX_THRESHOLD}%（嚴格）</span>
            </div>
          </div>
          <p className="text-sm" aria-live="polite">
            {groups.length ? (
              <>將合併成 <b className="tabular-nums">{groups.length}</b> 部片（共 <span className="tabular-nums">{merging}</span> 部影片）</>
            ) : (
              <span className="text-neutral-400">這個門檻下沒有可以合併的影片</span>
            )}
          </p>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5 py-4">
          {groups.length > 0 && (
            <section className="space-y-2">
              {groups.map((g) => (
                <div key={g.ids.join()} className="rounded-lg bg-neutral-800/70 px-3 py-2 text-sm ring-1 ring-white/10">
                  <div className="text-xs text-neutral-400">
                    相似度 <span className="font-medium tabular-nums text-emerald-300">{range(g)}</span> · {g.items.length} 部
                  </div>
                  <ul className="mt-1 space-y-0.5">
                    {g.items.map((i) => (
                      <li key={i.id} className="truncate" title={i.name}>{i.name}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          )}
          {single.length > 0 && (
            <section className="space-y-1.5">
              <h3 className="text-sm text-neutral-400">不合併的 {single.length} 部</h3>
              <ul className="space-y-1 text-sm">
                {single.map((i) => (
                  <li key={i.id} className="flex min-w-0 items-baseline gap-2">
                    <span className="min-w-0 flex-1 truncate" title={i.name}>{i.name}</span>
                    <span className="shrink-0 text-xs tabular-nums text-neutral-500">
                      {i.best === null ? '沒有長度相近（±3 秒）的影片' : `最相似 ${pct(i.best)}`}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {failed.length > 0 && (
            <section className="space-y-1.5">
              <h3 className="text-sm text-neutral-400">無法比對的 {failed.length} 部</h3>
              <ul className="space-y-1 text-sm">
                {failed.map((i) => (
                  <li key={i.id} className="min-w-0">
                    <span className="block truncate" title={i.name}>{i.name}</span>
                    <span className="block text-xs text-neutral-500">
                      {i.status === 'unreadable' ? '截圖無法讀取（可在影片頁按「重新產生截圖」）' : '還沒有截圖或影片資訊（處理中，稍後再試）'}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {(already > 0 || data.photos > 0) && (
            <p className="text-xs text-neutral-500">
              {[already && `${already} 組本來就是同一部片的版本`, data.photos && `${data.photos} 張圖片不比對`].filter(Boolean).join('；')}
            </p>
          )}
          <p className="text-xs text-neutral-500">
            用和自動歸類相同的方法比對：片長相差 3 秒內，比較截圖相似度。這裡調整的門檻只用在這次合併；自動歸類的門檻（預設 {data.threshold}%）在 Windows 程式的 Web Library 頁設定。合併錯了可以在影片頁按「從群組移出」。
          </p>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-white/10 p-4">
          {error && <p className="mr-auto text-sm text-red-400">{error}</p>}
          <button onClick={onCancel} disabled={busy} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-50">
            取消
          </button>
          <button
            onClick={confirm}
            disabled={busy || !groups.length}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50"
          >
            {busy ? '合併中…' : groups.length ? `確定合併 ${groups.length} 部片` : '確定合併'}
          </button>
        </div>
      </div>
    </div>
  )
}

// 加強比對 of exactly two videos (started by hand, never automatic): the server lines up the time (cut
// start / end) and the picture (scaling, crop, black borders) before comparing, which takes a while.
// onMerge([[a, b]]) puts them into one group.
const secs = (s) => (Math.abs(s) < 60 ? `${Number(Math.abs(s).toFixed(1))} 秒` : fmtDuration(Math.abs(s)))

export function DeepCompareDialog({ ids, onMerge, onClose }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    api.deepCompare(ids).then((r) => live && setResult(r)).catch((e) => live && setError(e.message))
    return () => {
      live = false // closing doesn't stop the server, the answer is just ignored
    }
  }, [])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && !busy && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy])

  async function merge() {
    setBusy(true)
    try {
      await onMerge([[result.a.id, result.b.id]])
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  let body
  if (!result && !error) {
    body = (
      <div className="flex flex-col items-center gap-3 py-8 text-center text-sm text-neutral-400">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/20 border-t-white" />
        <p>加強比對中…</p>
        <p className="text-xs text-neutral-500">會讀取兩部影片的前幾分鐘來對齊時間，再對齊畫面比較，通常需要 10 秒到 1 分鐘。</p>
      </div>
    )
  } else if (!result) {
    body = <p className="py-6 text-sm text-red-400">{error}</p>
  } else {
    const { a, b, score, threshold, offset, overlap, scale, aligned, pairs, regular, previews } = result
    const verdict =
      score >= threshold
        ? ['很可能是同一部片', 'text-emerald-300']
        : score >= threshold - 15
          ? ['可能是同一部片，請看下面的畫面確認', 'text-amber-300']
          : ['不像同一部片', 'text-neutral-400']
    const tail = a.duration - offset - b.duration // what B lacks at the end compared with A
    const timing = [
      Math.abs(offset) < 0.5 ? '開頭對齊' : offset > 0 ? `開頭少了 ${secs(offset)}` : `開頭多了 ${secs(offset)}`,
      Math.abs(tail) < 0.5 ? '結尾對齊' : tail > 0 ? `結尾少了 ${secs(tail)}` : `結尾多了 ${secs(tail)}`,
    ].join('、')
    const picture =
      scale === null ? '對不上特徵點，用整張畫面比較' : Math.abs(scale - 1) < 0.03 ? '畫面大小相同' : `畫面大小差 ×${scale.toFixed(2)}（縮放、裁切或黑邊）`
    body = (
      <div className="space-y-4">
        <div className="flex items-end gap-3">
          <span className="text-4xl font-semibold tabular-nums">{Math.round(score)}%</span>
          <span className={`pb-1 text-sm ${verdict[1]}`}>{verdict[0]}</span>
        </div>
        <dl className="space-y-1 text-sm">
          {[
            ['較長的', a.name],
            ['較短的', b.name],
            ['時間', `較短的比較長的${timing}（共同的部分 ${fmtDuration(overlap)}）`],
            ['畫面', picture],
            ['對齊成功', `${aligned} / ${pairs} 組畫面`],
            ['一般比對', regular === null ? '-' : `${regular}%（固定時間點的截圖，門檻 ${threshold}%）`],
          ].map(([k, v]) => (
            <div key={k} className="flex gap-3">
              <dt className="w-16 shrink-0 text-neutral-500">{k}</dt>
              <dd className="min-w-0 break-all">{v}</dd>
            </div>
          ))}
        </dl>
        {previews.length > 0 && (
          <section className="space-y-2">
            <h3 className="text-sm text-neutral-400">對齊後的畫面（左：較長的，右：較短的）</h3>
            {previews.map((p, i) => (
              <figure key={i} className="space-y-1">
                <div className="grid grid-cols-2 gap-1.5">
                  <img src={p.a} alt="" className="w-full rounded bg-black object-contain" />
                  <img src={p.b} alt="" className="w-full rounded bg-black object-contain" />
                </div>
                <figcaption className="flex justify-between text-xs tabular-nums text-neutral-500">
                  <span>{fmtDuration(p.time_a)}</span>
                  <span>相似度 {p.score}%</span>
                  <span>{fmtDuration(p.time_b)}</span>
                </figcaption>
              </figure>
            ))}
          </section>
        )}
        {result.same_group && <p className="text-sm text-neutral-400">這兩部已經是同一部片的版本。</p>}
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onMouseDown={() => !busy && onClose()}>
      <div
        role="dialog"
        aria-label="加強比對"
        onMouseDown={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl bg-neutral-900 shadow-2xl ring-1 ring-white/10"
      >
        <h2 className="border-b border-white/10 px-5 py-4 font-medium">🔬 加強比對</h2>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{body}</div>
        <div className="flex justify-end gap-2 border-t border-white/10 p-4">
          <button onClick={onClose} disabled={busy} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-50">
            {result ? '關閉' : '取消'}
          </button>
          {result && !result.same_group && (
            <button onClick={merge} disabled={busy} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50">
              {busy ? '合併中…' : '合併為同一部片'}
            </button>
          )}
        </div>
      </div>
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
