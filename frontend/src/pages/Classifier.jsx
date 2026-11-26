import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, DRAG_TYPE, getDragItems, KINDS, qualityKey } from '../api.js'
import VideoCard from '../components/VideoCard.jsx'
import AppMenu from '../components/AppMenu.jsx'
import { ContextMenu, PromptDialog } from '../components/Dialogs.jsx'

// 分類器: put items into 系列 by drag & drop. Top quarter: the series as folder-like cards (a 2×2 of
// covers, scrolls sideways; picking a 主演 shows only that actor's series), each one a drop target; bottom
// three quarters: items without a 系列 (they leave the list once they get one).

const byAdded = (a, b) => (b.added || 0) - (a.added || 0)

// card width of the 未分類 list (Shift + wheel / the slider), remembered per browser
const ZOOM_MIN = 90
const ZOOM_MAX = 360
const ZOOM_DEFAULT = 240
const COMPACT_BELOW = 170 // smaller cards show only the title
const clampZoom = (n) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(n)))

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

function readZoom() {
  try {
    return clampZoom(Number(localStorage.getItem('tad.classifyZoom')) || ZOOM_DEFAULT)
  } catch {
    return ZOOM_DEFAULT
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
function SeriesCard({ name, items, size, over, picked, onDrop, onDragOver, onDragLeave, onClick, onMenu, onRename }) {
  // as many columns as the size allows, but no empty rows: 6 items -> 3×3, not 4×4
  const cols = Math.min(size < 200 ? 2 : size < 360 ? 3 : 4, Math.max(2, Math.ceil(Math.sqrt(items.length))))
  const covers = items.slice(0, cols * cols)
  return (
    <div
      data-series={name}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
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
  const listEl = useRef(null)
  const boxEl = useRef(null)
  const ghost = useRef(null)
  const [zoom, setZoom] = useState(readZoom)
  const scrollRatio = useRef(null) // keeps the list's place while the cards change size
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
    return collapse(list, videos)
  }, [videos, kind, actor, onlyActor, q])

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

  function dropProps(name) {
    return {
      onDragOver: (e) => {
        if (!e.dataTransfer.types.includes(DRAG_TYPE)) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        setOver(name)
      },
      onDragLeave: (e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOver((o) => (o === name ? null : o))
      },
      onDrop: (e) => {
        e.preventDefault()
        setOver(null)
        const ids = getDragItems(e)?.videos || []
        if (name === '+') newSeries(ids)
        else addTo(name, ids)
      },
    }
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

  // ── card size: Shift + wheel over the list (down = smaller, up = bigger) or the slider ──
  function changeZoom(next) {
    const el = listEl.current
    if (el) scrollRatio.current = el.scrollTop / Math.max(1, el.scrollHeight - el.clientHeight)
    setZoom((z) => clampZoom(typeof next === 'function' ? next(z) : next))
  }

  useEffect(() => {
    const el = listEl.current
    if (!el) return
    const onWheel = (e) => {
      if (!e.shiftKey) return
      const d = e.deltaY || e.deltaX // Chrome turns Shift + wheel into a sideways scroll (deltaX)
      if (!d) return
      e.preventDefault()
      changeZoom((z) => z * Math.exp(-d * 0.0015)) // ~14 % per mouse notch, smooth on a touchpad
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  useLayoutEffect(() => {
    try {
      localStorage.setItem('tad.classifyZoom', String(zoom))
    } catch {}
    const el = listEl.current
    if (el && scrollRatio.current != null) {
      el.scrollTop = scrollRatio.current * (el.scrollHeight - el.clientHeight)
      scrollRatio.current = null
    }
  }, [zoom])

  function stripDragOver(e) {
    const el = strip.current
    const r = el.getBoundingClientRect()
    const edge = 60
    if (e.clientX < r.left + edge) el.scrollLeft -= 12
    else if (e.clientX > r.right - edge) el.scrollLeft += 12
  }

  // dragging several items shows a "N 個項目" badge instead of one card
  function onDragStart(e) {
    const id = e.target.closest?.('[data-id]')?.dataset.id
    const n = id && selected.has(id) ? picked.length : 1
    if (n > 1 && ghost.current) {
      ghost.current.textContent = `${n} 個項目`
      e.dataTransfer.setDragImage(ghost.current, 20, 20)
    }
  }

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

  // drag-select inside the bottom list (mouse only): press on empty space and drag a box. No key: replaces
  // the selection · Shift: adds · Ctrl/⌘: toggles; a plain click on empty space clears it
  const marquee = useRef(null)

  function onPointerDown(e) {
    if (e.pointerType !== 'mouse' || e.button !== 0) return
    if (e.target.closest('a, button, input, select, textarea, label, [data-id]')) return
    const c = listEl.current
    const r = c.getBoundingClientRect()
    if (e.clientX > r.left + c.clientWidth) return // the scroll bar
    e.preventDefault()
    document.activeElement?.blur?.()
    marquee.current = {
      x0: e.clientX - r.left + c.scrollLeft,
      y0: e.clientY - r.top + c.scrollTop,
      x: e.clientX,
      y: e.clientY,
      mode: e.ctrlKey || e.metaKey ? 'toggle' : e.shiftKey ? 'add' : 'replace',
      base: selected,
      active: false,
      hitKey: null,
    }
  }

  useEffect(() => {
    let raf = 0
    function update() {
      const m = marquee.current
      const c = listEl.current
      if (!m || !c) return
      const cr = c.getBoundingClientRect()
      const px = m.x - cr.left + c.scrollLeft
      const py = m.y - cr.top + c.scrollTop
      if (!m.active) {
        if (Math.hypot(px - m.x0, py - m.y0) < 6) return
        m.active = true
        // item positions in list coordinates, read once (they don't move while the list scrolls)
        m.rects = [...c.querySelectorAll('[data-select-root] [data-id]')].map((el) => {
          const r = el.getBoundingClientRect()
          return { id: el.dataset.id, l: r.left - cr.left + c.scrollLeft, t: r.top - cr.top + c.scrollTop, r: r.right - cr.left + c.scrollLeft, b: r.bottom - cr.top + c.scrollTop }
        })
        raf = requestAnimationFrame(tick)
      }
      const l = Math.min(m.x0, px)
      const r = Math.max(m.x0, px)
      const t = Math.min(m.y0, py)
      const b = Math.max(m.y0, py)
      const box = boxEl.current
      if (box) {
        // drawn in viewport coordinates, clipped to the list
        const top = Math.max(t - c.scrollTop + cr.top, cr.top)
        const bottom = Math.min(b - c.scrollTop + cr.top, cr.bottom)
        Object.assign(box.style, {
          display: 'block',
          left: `${l - c.scrollLeft + cr.left}px`,
          top: `${top}px`,
          width: `${r - l}px`,
          height: `${Math.max(0, bottom - top)}px`,
        })
      }
      const hits = m.rects.filter((x) => x.l < r && x.r > l && x.t < b && x.b > t).map((x) => x.id)
      const key = hits.join()
      if (key === m.hitKey) return
      m.hitKey = key
      const next = m.mode === 'replace' ? new Set() : new Set(m.base)
      for (const id of hits) {
        if (m.mode === 'toggle' && m.base.has(id)) next.delete(id)
        else next.add(id)
      }
      setSelected(next)
      if (hits.length) anchor.current = hits[0]
    }
    function tick() {
      const m = marquee.current
      const c = listEl.current
      if (!m || !c) return
      const cr = c.getBoundingClientRect()
      const edge = 50
      const dy = m.y < cr.top + edge ? -(cr.top + edge - m.y) / 3 : m.y > cr.bottom - edge ? (m.y - cr.bottom + edge) / 3 : 0
      if (dy) c.scrollTop += dy
      update()
      raf = requestAnimationFrame(tick)
    }
    function onMove(e) {
      const m = marquee.current
      if (!m) return
      m.x = e.clientX
      m.y = e.clientY
      update()
    }
    function onUp() {
      const m = marquee.current
      if (!m) return
      marquee.current = null
      cancelAnimationFrame(raf)
      if (boxEl.current) boxEl.current.style.display = 'none'
      if (!m.active && m.mode === 'replace') setSelected((prev) => (prev.size ? new Set() : prev))
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
  }, [])

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
        <div ref={strip} onDragOver={stripDragOver} className="flex min-h-0 flex-1 items-center gap-1 overflow-x-auto overflow-y-hidden px-3 py-2">
          <div
            {...dropProps('+')}
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
              {...dropProps(s.name)}
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
          <label className="flex items-center gap-1.5 text-sm text-neutral-400" title="卡片大小（也可以在清單上 Shift + 滾輪縮放）">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" aria-hidden="true">
              <path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z" fill="currentColor" />
            </svg>
            <input
              type="range"
              min={ZOOM_MIN}
              max={ZOOM_MAX}
              value={zoom}
              onChange={(e) => changeZoom(Number(e.target.value))}
              aria-label="卡片大小"
              className="w-24 accent-accent"
            />
          </label>
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
              <span className="hidden text-xs text-neutral-500 md:inline">點選 · Shift / Ctrl + 點選 · 空白處拖曳框選 · Ctrl + A 全選 · Shift + 滾輪縮放</span>
            )}
          </div>
        </div>
        <div ref={listEl} onPointerDown={onPointerDown} onDragStart={onDragStart} className="min-h-0 flex-1 select-none overflow-y-auto px-4 py-4">
          {loading ? (
            <p className="text-neutral-400">載入中…</p>
          ) : shown.length === 0 ? (
            <p className="py-16 text-center text-neutral-500">
              {videos.some((v) => !v.series) ? '沒有符合的項目' : '所有項目都已經加入系列了'}
            </p>
          ) : (
            <div
              data-select-root
              className="grid"
              style={{ gridTemplateColumns: `repeat(auto-fill, minmax(min(${zoom}px, 100%), 1fr))`, gap: zoom < COMPACT_BELOW ? 8 : 16 }}
            >
              {shown.map((v) => (
                <div key={v.id} onDoubleClick={() => navigate(`/v/${v.id}`, { state: { backPath } })}>
                  <VideoCard
                    compact={zoom < COMPACT_BELOW}
                    video={v}
                    onMenu={itemMenu}
                    selecting
                    selected={selected.has(v.id)}
                    onSelect={select}
                    dragIds={selected.has(v.id) ? pickedIds : undefined}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <div ref={boxEl} aria-hidden className="pointer-events-none fixed z-40 hidden rounded-sm border border-accent bg-accent/15" />
      <div ref={ghost} aria-hidden className="fixed -left-[999px] top-0 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white" />
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
