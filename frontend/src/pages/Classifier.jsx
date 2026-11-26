import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, KINDS, qualityKey } from '../api.js'
import ClassifierCanvas, { CANVAS_ZOOM_MAX, CANVAS_ZOOM_MIN } from '../components/ClassifierCanvas.jsx'
import AppMenu from '../components/AppMenu.jsx'
import { ContextMenu, PromptDialog } from '../components/Dialogs.jsx'

// 分類器: put items into 系列 by drag & drop. Top quarter: the series as folder-like cards (a 2×2 of
// covers, scrolls sideways; picking a 主演 shows only that actor's series), each one a drop target; bottom
// three quarters: items without a 系列 on a canvas (ClassifierCanvas.jsx; they leave it once they get one).

const byAdded = (a, b) => (b.added || 0) - (a.added || 0)

// share of the page the series get (the divider), remembered per browser
const SPLIT_DEFAULT = 0.25
const SPLIT_MIN = 0.15
const SPLIT_MAX = 0.8
const clampSplit = (n) => Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, n))

function readSplit() {
  try {
    return clampSplit(Number(localStorage.getItem('tad.classifySplit')) || SPLIT_DEFAULT)
  } catch {
    return SPLIT_DEFAULT
  }
}

// versions of the same video show once (the best quality one), like the library page
function collapse(list, all) {
  const size = {}
  for (const v of all) if (v.group) size[v.group] = (size[v.group] || 0) + 1
  const best = {}
  const out = []
  for (const v of list) {
    if (!v.group) out.push(v)
    else if (!best[v.group] || qualityKey(v) > qualityKey(best[v.group])) best[v.group] = v
  }
  for (const v of Object.values(best)) out.push({ ...v, versions: size[v.group] })
  return out.sort(byAdded)
}

// size = the album's side in px, from the top section's height (drag the divider): bigger albums show
// more covers (2×2, 3×3, 4×4) so the items of a series can be compared
function SeriesCard({ name, items, size, over, picked, onClick, onMenu, onRename }) {
  // as many columns as the size allows, but no empty rows: 6 items -> 3×3, not 4×4
  const cols = Math.min(size < 200 ? 2 : size < 360 ? 3 : 4, Math.max(2, Math.ceil(Math.sqrt(items.length))))
  const covers = items.slice(0, cols * cols)
  return (
    <div
      data-series={name}
      onClick={onClick}
      onContextMenu={(e) => {
        e.preventDefault()
        onMenu(e.clientX, e.clientY)
      }}
      title={picked ? `點一下把已選的 ${picked} 個加入「${name}」` : `${name}（${items.length} 個）· 點一下在媒體庫查看 · 右鍵改名`}
      style={{ width: size + 16 }}
      className="group relative flex shrink-0 cursor-pointer flex-col items-center gap-1.5 rounded-xl p-1.5 hover:bg-white/5"
    >
      <div
        style={{ width: size, height: size, gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${cols}, 1fr)`, gap: size < 200 ? 4 : 6, padding: size < 200 ? 6 : 8 }}
        className={`grid rounded-2xl bg-neutral-800/80 ring-1 transition ${
          over ? 'scale-105 bg-accent/30 ring-2 ring-accent' : picked ? 'ring-accent/50' : 'ring-white/10'
        }`}
      >
        {covers.map((v) => (
          <div key={v.id} className="overflow-hidden rounded-md bg-neutral-700">
            {v.cover && <img src={v.cover} alt="" loading="lazy" draggable={false} className="h-full w-full object-cover" />}
          </div>
        ))}
        {Array.from({ length: cols * cols - covers.length }, (_, i) => (
          <div key={`e${i}`} className="rounded-md bg-neutral-700/40" />
        ))}
      </div>
      <p className={`line-clamp-2 w-full text-center leading-tight ${size < 200 ? 'text-xs' : 'text-sm'}`} title={name}>
        {name}
      </p>
      <span className="absolute right-1 top-1 rounded-full bg-neutral-950/90 px-1.5 text-[11px] tabular-nums text-neutral-300 ring-1 ring-white/10">
        {items.length}
      </span>
      <button
        onClick={(e) => {
          e.stopPropagation()
          onRename()
        }}
        className="absolute left-1 top-1 hidden rounded-full bg-neutral-950/90 p-1 text-neutral-300 ring-1 ring-white/10 hover:text-white group-hover:block"
        title="修改系列名稱"
        aria-label={`修改系列名稱「${name}」`}
      >
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </svg>
      </button>
    </div>
  )
}

export default function Classifier({ guard, onLogout }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [videos, setVideos] = useState(null)
  const [actors, setActors] = useState([])
  const [processing, setProcessing] = useState(0)
  const [selected, setSelected] = useState(() => new Set())
  const [over, setOver] = useState(null) // series name (or '+') under the dragged items
  const [dialog, setDialog] = useState(null)
  const [menu, setMenu] = useState(null)
  const [toast, setToast] = useState(null)
  const toastTimer = useRef(null)
  const anchor = useRef(null)
  const strip = useRef(null)
  const canvas = useRef(null)
  const [canvasZoom, setCanvasZoom] = useState(1) // shown in the toolbar (the canvas keeps the real value)
  const dropTarget = useRef(null) // series name / '+' under the pointer while items are dragged
  const page = useRef(null)
  const [split, setSplit] = useState(readSplit) // top section's share of the page
  const [album, setAlbum] = useState(96) // series album side in px, follows the strip's height

  function saveSplit(value) {
    const v = clampSplit(value)
    setSplit(v)
    try {
      localStorage.setItem('tad.classifySplit', String(v))
    } catch {}
  }

  // drag the divider: the top section follows the pointer, saved on release
  function startSplitDrag(e) {
    if (e.button !== 0) return
    e.preventDefault()
    const el = e.currentTarget
    el.setPointerCapture(e.pointerId)
    let last = split
    const move = (ev) => {
      const r = page.current.getBoundingClientRect()
      last = clampSplit((ev.clientY - r.top) / r.height)
      setSplit(last)
    }
    const up = () => {
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerup', up)
      el.removeEventListener('pointercancel', up)
      saveSplit(last)
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
    el.addEventListener('pointercancel', up)
  }

  // the albums fill the strip's height (minus the name under them)
  useEffect(() => {
    const el = strip.current
    if (!el) return
    const fit = () => setAlbum(Math.max(80, Math.min(640, Math.round(el.clientHeight - 70))))
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const actor = params.get('actor') || ''
  const q = params.get('q') || ''
  const sq = params.get('sq') || '' // series search
  const kind = KINDS[params.get('kind')] ? params.get('kind') : 'all'
  const onlyActor = params.get('mine') !== '0' // with a 主演 picked: only that actor's items below
  const order = params.get('order') === 'title' ? 'title' : 'added' // 排列 order of the canvas

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  function notify(text, error = false, action = null) {
    setToast({ text, error, action })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(null), error || action ? 7000 : 3000)
  }

  function fail(e) {
    try {
      guard(e)
    } catch (err) {
      notify(err.message, true)
    }
  }

  async function load() {
    try {
      const [v, t] = await Promise.all([api.videos(''), api.tags()])
      setVideos(v.videos)
      setProcessing(v.processing)
      setActors(t.actors)
    } catch (e) {
      fail(e)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // new covers appear while screenshots are being made
  useEffect(() => {
    if (!processing) return
    const timer = setTimeout(load, 5000)
    return () => clearTimeout(timer)
  }, [processing, videos])

  // ── series (top) ──
  const series = useMemo(() => {
    if (!videos) return []
    const names = new Set(videos.filter((v) => v.series && (!actor || v.actors.includes(actor))).map((v) => v.series))
    const needle = sq.trim().toLowerCase()
    return [...names]
      .filter((n) => !needle || n.toLowerCase().includes(needle))
      .sort((a, b) => a.localeCompare(b, 'zh-Hant'))
      .map((name) => ({ name, items: collapse(videos.filter((v) => v.series === name), videos) }))
  }, [videos, actor, sq])

  // ── items without a series (bottom) ──
  const shown = useMemo(() => {
    if (!videos) return []
    const needle = q.trim().toLowerCase()
    const list = videos.filter(
      (v) =>
        !v.series &&
        (kind === 'all' || v.kind === kind) &&
        (!actor || !onlyActor || v.actors.includes(actor)) &&
        (!needle || [v.title, v.file, v.folder, v.description, ...v.actors].some((s) => (s || '').toLowerCase().includes(needle))),
    )
    const items = collapse(list, videos)
    return order === 'title' ? items.sort((a, b) => a.title.localeCompare(b.title, 'zh-Hant', { numeric: true })) : items
  }, [videos, kind, actor, onlyActor, q, order])
  // the canvas is arranged again when these change (positions aren't kept)
  const layoutKey = [kind, q, actor, onlyActor, order].join('|')

  // only what is on screen stays selected (items that got a series leave the list)
  const picked = useMemo(() => shown.filter((v) => selected.has(v.id)), [shown, selected])
  const pickedIds = useMemo(() => picked.map((v) => v.id), [picked])
  useEffect(() => {
    if (picked.length !== selected.size) setSelected(new Set(pickedIds))
  }, [picked])

  // ── adding to a series ──
  async function addTo(name, ids) {
    if (!ids.length) return
    try {
      const result = await api.batchUpdate(ids, { series: name })
      setSelected(new Set())
      await load()
      notify(`已把 ${result.updated} 個項目加入「${name}」`, false, {
        label: '復原',
        onClick: async () => {
          setToast(null)
          try {
            await api.batchUpdate(ids, { series: '' })
            await load()
          } catch (e) {
            fail(e)
          }
        },
      })
    } catch (e) {
      fail(e)
    }
  }

  function newSeries(ids) {
    if (!ids.length) {
      notify('先在下方選取或拖曳項目到「新系列」，系列會在加入第一個項目時建立')
      return
    }
    setDialog({
      title: '建立新系列',
      label: `${ids.length} 個項目會加入這個系列`,
      initial: actor ? `${actor} ` : '',
      confirmText: '建立',
      onSubmit: async (name) => {
        setDialog(null)
        await addTo(name, ids)
      },
    })
  }

  function renameSeries(name) {
    setDialog({
      title: '修改系列名稱',
      label: `「${name}」的所有項目都會改成新名稱；改成已有的系列名稱會把兩個系列合併`,
      initial: name,
      confirmText: '修改',
      onSubmit: async (value) => {
        if (value === name) return setDialog(null)
        const result = await api.renameSeries(name, value)
        setDialog(null)
        notify(`已把 ${result.updated} 個項目的系列改為「${result.name}」`)
        await load()
      },
    })
  }

  const openSeries = (name) => navigate(`/?series=${encodeURIComponent(name)}&kind=all`)

  // items dragged on the canvas: which series card / 「＋ 新系列」 is under the pointer (the strip scrolls
  // near its ends); on release dropItems() adds them and tells the canvas not to keep the move
  function dragAt(x, y) {
    const el = document.elementFromPoint(x, y)
    const card = el?.closest?.('[data-series], [data-new-series]')
    const target = card ? (card.hasAttribute('data-new-series') ? '+' : card.dataset.series) : null
    dropTarget.current = target
    setOver(target)
    const st = strip.current
    const r = st.getBoundingClientRect()
    if (y >= r.top && y <= r.bottom) {
      if (x < r.left + 60) st.scrollLeft -= 16
      else if (x > r.right - 60) st.scrollLeft += 16
    }
  }

  function dropItems(ids) {
    const target = dropTarget.current
    dropTarget.current = null
    setOver(null)
    if (target === '+') newSeries(ids)
    else if (target) addTo(target, ids)
    return Boolean(target)
  }

  // the strip scrolls sideways with the wheel (with or without Shift) and while dragging near its ends
  useEffect(() => {
    const el = strip.current
    if (!el) return
    const onWheel = (e) => {
      const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
      if (!d || el.scrollWidth <= el.clientWidth) return
      e.preventDefault()
      el.scrollLeft += d
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [videos])

  // ── selection: click / Ctrl+click toggles, Shift+click selects a range (Ctrl+Shift adds it) ──
  function select(video, e = {}) {
    const ids = shown.map((v) => v.id)
    const a = anchor.current ? ids.indexOf(anchor.current) : -1
    const b = ids.indexOf(video.id)
    if (e.shiftKey && a >= 0 && b >= 0) {
      const range = ids.slice(Math.min(a, b), Math.max(a, b) + 1)
      setSelected((prev) => (e.ctrlKey || e.metaKey ? new Set([...prev, ...range]) : new Set(range)))
      return
    }
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(video.id)) next.delete(video.id)
      else next.add(video.id)
      return next
    })
    anchor.current = video.id
  }

  useEffect(() => {
    const onKey = (e) => {
      if (dialog || menu || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return
      if (e.key === 'Escape') setSelected(new Set())
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        e.preventDefault()
        setSelected(new Set(shown.map((v) => v.id)))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [shown, dialog, menu])

  function itemMenu(x, y, video) {
    const ids = selected.has(video.id) ? pickedIds : [video.id]
    setMenu({
      x,
      y,
      items: [
        { label: selected.has(video.id) ? '☐ 取消選取' : '☑ 選取', onClick: () => select(video) },
        { label: video.kind === 'photo' ? '🖼 開啟' : '▶ 開啟', onClick: () => navigate(`/v/${video.id}`, { state: { backPath } }) },
        { label: `➕ 加入新系列（${ids.length} 個）…`, onClick: () => newSeries(ids) },
      ],
    })
  }

  function seriesMenu(x, y, name) {
    setMenu({
      x,
      y,
      items: [
        picked.length > 0 && { label: `➕ 加入已選的 ${picked.length} 個`, onClick: () => addTo(name, pickedIds) },
        { label: '✏️ 修改系列名稱', onClick: () => renameSeries(name) },
        { label: '🎬 在媒體庫查看', onClick: () => openSeries(name) },
      ].filter(Boolean),
    })
  }

  const loading = videos === null
  const backPath = `/classify${params.toString() ? `?${params}` : ''}`

  return (
    <div ref={page} className="flex h-[100dvh] flex-col overflow-hidden">
      {/* top: series (a quarter of the page at first; drag the divider to resize) */}
      <section style={{ height: `${split * 100}%` }} className="flex min-h-40 shrink-0 flex-col bg-neutral-950">
        <div className="flex flex-wrap items-center gap-3 px-4 pt-3">
          <h1 className="text-lg font-semibold">分類器</h1>
          <span className="text-sm text-neutral-400">{loading ? '' : `${series.length} 個系列`}</span>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-neutral-400">主演</span>
            <select
              value={actor}
              onChange={(e) => setParam('actor', e.target.value)}
              className="max-w-48 rounded-lg bg-neutral-800 px-2 py-1.5 outline-none ring-1 ring-white/10 focus:ring-accent"
            >
              <option value="">全部</option>
              {actors.map((a) => (
                <option key={a.name} value={a.name}>{`${a.name} (${a.count})`}</option>
              ))}
            </select>
          </label>
          <input
            value={sq}
            onChange={(e) => setParam('sq', e.target.value)}
            placeholder="搜尋系列…"
            className="w-40 rounded-lg bg-neutral-800 px-3 py-1.5 text-sm outline-none ring-1 ring-white/10 focus:ring-accent"
          />
          <span className="hidden text-xs text-neutral-500 lg:inline">滾輪左右捲動 · 拖曳下方項目到系列加入 · 右鍵或 ✎ 改名 · 拖曳分隔線放大系列</span>
          <div className="ml-auto">
            <AppMenu onLogout={onLogout} />
          </div>
        </div>
        <div ref={strip} className="flex min-h-0 flex-1 items-center gap-1 overflow-x-auto overflow-y-hidden px-3 py-2">
          <div
            data-new-series
            onClick={() => newSeries(pickedIds)}
            title={picked.length ? `用已選的 ${picked.length} 個建立新系列` : '把項目拖到這裡建立新系列'}
            style={{ width: Math.min(album, 140) + 16 }}
            className="flex shrink-0 cursor-pointer flex-col items-center gap-1.5 rounded-xl p-1.5 hover:bg-white/5"
          >
            <div
              style={{ width: Math.min(album, 140), height: Math.min(album, 140) }}
              className={`flex items-center justify-center rounded-2xl border-2 border-dashed text-3xl transition ${
                over === '+' ? 'scale-105 border-accent bg-accent/20 text-white' : 'border-white/20 text-neutral-500'
              }`}
            >
              ＋
            </div>
            <p className="text-center text-xs text-neutral-400">新系列</p>
          </div>
          {series.map((s) => (
            <SeriesCard
              key={s.name}
              name={s.name}
              items={s.items}
              size={album}
              over={over === s.name}
              picked={picked.length}
              onClick={() => (picked.length ? addTo(s.name, pickedIds) : openSeries(s.name))}
              onMenu={(x, y) => seriesMenu(x, y, s.name)}
              onRename={() => renameSeries(s.name)}
            />
          ))}
          {!loading && !series.length && (
            <p className="self-center px-4 text-sm text-neutral-500">
              {sq ? '沒有符合的系列' : actor ? `「${actor}」還沒有系列，把下方項目拖到「＋ 新系列」建立` : '還沒有系列，把下方項目拖到「＋ 新系列」建立'}
            </p>
          )}
        </div>
      </section>

      {/* divider: drag to give the series more / less room (double-click: back to a quarter) */}
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="調整上下區塊大小"
        aria-valuenow={Math.round(split * 100)}
        tabIndex={0}
        onPointerDown={startSplitDrag}
        onDoubleClick={() => saveSplit(SPLIT_DEFAULT)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            e.preventDefault()
            saveSplit(split + (e.key === 'ArrowDown' ? 0.05 : -0.05))
          }
        }}
        title="拖曳調整上下大小 · 雙擊回到預設"
        className="group relative z-10 flex h-2 shrink-0 cursor-row-resize items-center justify-center border-y border-white/10 bg-neutral-900 outline-none hover:bg-accent/30 focus-visible:bg-accent/30"
      >
        <span className="h-1 w-10 rounded-full bg-white/25 group-hover:bg-white/60" />
      </div>

      {/* bottom: items without a series */}
      <section className="flex min-h-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-3 border-b border-white/5 px-4 py-2">
          <h2 className="text-sm font-medium">未分類</h2>
          <span className="text-sm text-neutral-400">{loading ? '' : `${shown.length} 個`}</span>
          <div className="flex overflow-hidden rounded-lg ring-1 ring-white/10" role="group" aria-label="顯示類型">
            {['all', 'video', 'photo'].map((k) => (
              <button
                key={k}
                onClick={() => setParam('kind', k === 'all' ? '' : k)}
                aria-pressed={kind === k}
                className={`px-3 py-1 text-sm ${kind === k ? 'bg-accent/80 text-white' : 'bg-neutral-800 hover:bg-neutral-700'}`}
              >
                {KINDS[k].label}
              </button>
            ))}
          </div>
          <input
            value={q}
            onChange={(e) => setParam('q', e.target.value)}
            placeholder="搜尋標題、主演、描述、資料夾…"
            className="min-w-48 flex-1 rounded-lg bg-neutral-800 px-3 py-1.5 text-sm outline-none ring-1 ring-white/10 focus:ring-accent sm:max-w-sm"
          />
          {actor && (
            <label className="flex items-center gap-1.5 text-sm text-neutral-300">
              <input type="checkbox" checked={onlyActor} onChange={(e) => setParam('mine', e.target.checked ? '' : '0')} className="accent-accent" />
              只顯示「{actor}」的項目
            </label>
          )}
          <label className="flex items-center gap-1.5 text-sm text-neutral-400" title="畫布縮放（也可以在畫布上 Shift + 滾輪）">
            <span aria-hidden>🔍</span>
            <input
              type="range"
              min={Math.log(CANVAS_ZOOM_MIN)}
              max={Math.log(CANVAS_ZOOM_MAX)}
              step={0.01}
              value={Math.log(canvasZoom)}
              onChange={(e) => canvas.current?.zoomTo(Math.exp(Number(e.target.value)))}
              aria-label="畫布縮放"
              className="w-24 accent-accent"
            />
            <button onClick={() => canvas.current?.zoomTo(1)} className="w-11 text-left tabular-nums hover:text-white" title="回到 100%">
              {Math.round(canvasZoom * 100)}%
            </button>
          </label>
          <div className="flex items-center overflow-hidden rounded-lg ring-1 ring-white/10">
            <select
              value={order}
              onChange={(e) => setParam('order', e.target.value === 'title' ? 'title' : '')}
              aria-label="排列順序"
              className="bg-neutral-800 px-2 py-1 text-sm outline-none"
            >
              <option value="added">最新加入</option>
              <option value="title">依標題</option>
            </select>
            <button onClick={() => canvas.current?.arrange()} className="bg-neutral-700 px-3 py-1 text-sm hover:bg-neutral-600" title="依順序重新排列所有項目">
              排列
            </button>
          </div>
          {processing > 0 && <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300">產生資訊/截圖中：{processing}</span>}
          <div className="ml-auto flex items-center gap-2 text-sm">
            {picked.length > 0 ? (
              <>
                <span className="text-neutral-300">已選 {picked.length} 個 · 拖到上方系列或點系列加入</span>
                <button onClick={() => setSelected(new Set())} className="rounded-lg bg-neutral-800 px-2.5 py-1 hover:bg-neutral-700">
                  清除選取
                </button>
              </>
            ) : (
              <span className="hidden text-xs text-neutral-500 md:inline">拖曳移動或拖到系列 · 空白處拖曳框選 · Shift + 滾輪縮放 · 滾輪 / 空白鍵 + 拖曳移動畫布 · 雙擊開啟</span>
            )}
          </div>
        </div>
        <div className="min-h-0 flex-1">
          {loading ? (
            <p className="p-4 text-neutral-400">載入中…</p>
          ) : shown.length === 0 ? (
            <p className="py-16 text-center text-neutral-500">
              {videos.some((v) => !v.series) ? '沒有符合的項目' : '所有項目都已經加入系列了'}
            </p>
          ) : (
            <ClassifierCanvas
              ref={canvas}
              items={shown}
              layoutKey={layoutKey}
              selected={selected}
              setSelected={setSelected}
              onSelect={select}
              onOpen={(id) => navigate(`/v/${id}`, { state: { backPath } })}
              onMenu={itemMenu}
              onDragAt={dragAt}
              onDropItems={dropItems}
              onZoom={setCanvasZoom}
            />
          )}
        </div>
      </section>

      {menu && <ContextMenu {...menu} onClose={() => setMenu(null)} />}
      {dialog && <PromptDialog {...dialog} onCancel={() => setDialog(null)} />}
      {toast && (
        <div
          className={`fixed bottom-4 left-1/2 z-50 max-w-[90vw] -translate-x-1/2 whitespace-pre-line rounded-lg px-4 py-2 text-sm shadow-xl ${
            toast.error ? 'bg-red-900 text-red-100' : 'bg-neutral-800 text-neutral-100'
          }`}
        >
          {toast.text}
          {toast.action && (
            <button onClick={toast.action.onClick} className="ml-3 font-medium text-accent hover:underline">
              {toast.action.label}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
