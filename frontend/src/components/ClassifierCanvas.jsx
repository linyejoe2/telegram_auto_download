import { forwardRef, memo, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { fmtDuration } from '../api.js'
import { PreviewVideo, useHoverPreview } from './VideoCard.jsx'

// 分類器 canvas for the items without a 系列: every item shows its whole picture (portrait videos stay
// recognisable), laid out in justified rows (same height per row, rows fill the width) and free to move.
// Positions are not saved: the canvas is arranged again whenever the page opens or the filters / order change.
//
// Mouse: drag an item (or the selection) to move it, or onto a series card to add it; drag on empty space =
// selection box (Shift adds, Ctrl toggles); wheel pans, Shift + wheel (or a trackpad pinch) zooms at the
// pointer; Space + drag or the middle button pans. Touch: drag on empty space pans.

const ROW_H = 220 // target row height of the justified layout, in canvas units (= px at 100 %)
const GAP = 14
const CAPTION = 24 // title line under each picture
const PAD = 24
export const CANVAS_ZOOM_MIN = 0.1
export const CANVAS_ZOOM_MAX = 4
const clampZoom = (z) => Math.min(CANVAS_ZOOM_MAX, Math.max(CANVAS_ZOOM_MIN, z))
const clampAspect = (a) => Math.min(4, Math.max(0.3, a || 16 / 9))

function readZoom() {
  try {
    return clampZoom(Number(localStorage.getItem('tad.canvasZoom')) || 1)
  } catch {
    return 1
  }
}

// greedy justified rows: fill a row at ROW_H until it is wider than `width`, then scale the row to fit exactly
// (the last row keeps ROW_H). Returns Map id -> { x, y, w, h } (h = picture height, the title goes below).
function justify(list, width, aspectOf, startY = PAD) {
  const pos = new Map()
  const avail = Math.max(ROW_H, width - PAD * 2)
  let y = startY
  let row = []
  let rowW = 0
  const flush = (last) => {
    if (!row.length) return
    const gaps = GAP * (row.length - 1)
    let h = ((avail - gaps) / rowW) * ROW_H
    if (last) h = Math.min(h, ROW_H)
    h = Math.min(h, ROW_H * 1.8) // a single very narrow item doesn't become huge
    let x = PAD
    for (const { v, a } of row) {
      pos.set(v.id, { x, y, w: a * h, h })
      x += a * h + GAP
    }
    y += h + CAPTION + GAP
    row = []
    rowW = 0
  }
  for (const v of list) {
    const a = aspectOf(v)
    row.push({ v, a })
    rowW += a * ROW_H
    if (rowW + GAP * (row.length - 1) >= avail) flush(false)
  }
  flush(true)
  return pos
}

const CanvasItem = memo(function CanvasItem({ v, p, z, selected, offset, still, onAspect, onMenu }) {
  const preview = useHoverPreview(v)
  const ring = Math.max(2, 3 / z) // stays visible when zoomed out
  return (
    <div
      data-id={v.id}
      {...(still ? preview.handlers : {})}
      onContextMenu={(e) => {
        e.preventDefault()
        onMenu(e.clientX, e.clientY, v)
      }}
      style={{
        left: p.x + (offset ? offset.dx : 0),
        top: p.y + (offset ? offset.dy : 0),
        width: p.w,
        height: p.h + CAPTION,
        zIndex: offset ? 20 : undefined,
      }}
      className={`group absolute ${offset ? 'pointer-events-none opacity-80' : ''}`}
    >
      <div
        style={{ height: p.h, boxShadow: selected ? `0 0 0 ${ring}px var(--color-accent)` : undefined }}
        className={`relative overflow-hidden rounded-md bg-neutral-900 ${selected ? '' : 'ring-1 ring-white/10 group-hover:ring-accent/60'}`}
      >
        {v.cover ? (
          <img
            src={v.cover}
            alt=""
            loading="lazy"
            draggable={false}
            onLoad={(e) => onAspect(v.id, e.currentTarget.naturalWidth / e.currentTarget.naturalHeight)}
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full items-center justify-center px-2 text-center text-xs text-neutral-500">{v.error ? '⚠ 無法讀取' : '產生截圖中…'}</div>
        )}
        {still && preview.on && <PreviewVideo id={v.id} contain />}
        {selected && (
          <span
            aria-hidden
            className="absolute left-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-accent text-sm font-bold text-white ring-2 ring-accent"
          >
            ✓
          </span>
        )}
        {v.kind !== 'photo' && v.duration ? (
          <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/70 px-1 text-[11px] tabular-nums text-neutral-200">
            {fmtDuration(v.duration)}
          </span>
        ) : null}
      </div>
      <p className="truncate pt-1 text-xs leading-[18px] text-neutral-300" title={v.title}>
        {v.title}
      </p>
    </div>
  )
})

const ClassifierCanvas = forwardRef(function ClassifierCanvas(
  { items, layoutKey, selected, setSelected, onSelect, onOpen, onMenu, onDragAt, onDropItems, onZoom },
  ref,
) {
  const box = useRef(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [pos, setPos] = useState(() => new Map())
  const [view, setView] = useState(() => ({ x: 0, y: 0, z: readZoom() }))
  const [drag, setDrag] = useState(null) // { ids: Set, dx, dy (canvas units), x, y (client), outside }
  const [marq, setMarq] = useState(null) // selection box in canvas-element px { l, t, w, h }
  const [space, setSpace] = useState(false) // Space held: drag pans
  const [busy, setBusy] = useState(false) // dragging / panning / box-selecting: no hover previews
  const action = useRef(null)
  const lastClick = useRef({ id: null, t: 0 })
  const moved = useRef(false) // items moved by hand since the last arrangement
  const lastKey = useRef(null)
  const aspects = useRef(new Map()) // id -> real picture shape, from the loaded cover (rotated phone videos)
  const arrangeTimer = useRef(null)

  // latest values for event handlers and the imperative handle
  const live = useRef({})
  live.current = { items, pos, view, size, selected }
  const byId = useMemo(() => new Map(items.map((v) => [v.id, v])), [items])

  const aspectOf = (v) => clampAspect(aspects.current.get(v.id) || (v.width && v.height ? v.width / v.height : 0))

  const bounds = useMemo(() => {
    let r = 0
    let b = 0
    for (const p of pos.values()) {
      r = Math.max(r, p.x + p.w)
      b = Math.max(b, p.y + p.h + CAPTION)
    }
    return { r: r + PAD, b: b + PAD }
  }, [pos])
  const boundsRef = useRef(bounds)
  boundsRef.current = bounds

  // keep some of the content on screen
  function clampView(v) {
    const { w, h } = live.current.size
    const { r, b } = boundsRef.current
    return {
      z: v.z,
      x: Math.min(w * 0.5, Math.max(Math.min(0, w - r * v.z) - w * 0.5, v.x)),
      y: Math.min(h * 0.5, Math.max(Math.min(0, h - b * v.z) - h * 0.5, v.y)),
    }
  }

  function zoomAt(z2, cx, cy) {
    setView((v) => {
      const z = clampZoom(z2)
      const k = z / v.z
      return clampView({ z, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k })
    })
  }

  // lay everything out again (the rows fill the visible width at the current zoom)
  function arrange(resetView = true) {
    const { items, size, view } = live.current
    const width = (size.w || box.current?.clientWidth || 1000) / view.z
    setPos(justify(items, width, aspectOf))
    moved.current = false
    if (resetView) setView((v) => ({ ...v, x: 0, y: 0 }))
  }

  useImperativeHandle(ref, () => ({
    arrange: () => arrange(true),
    zoomTo: (z) => zoomAt(z, live.current.size.w / 2, live.current.size.h / 2),
  }))

  useEffect(() => {
    try {
      localStorage.setItem('tad.canvasZoom', String(view.z))
    } catch {}
    onZoom?.(view.z)
  }, [view.z])

  useEffect(() => {
    const el = box.current
    const fit = () => setSize({ w: el.clientWidth, h: el.clientHeight })
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // new filters / order: arrange again; otherwise keep the places, drop items that left (got a series)
  // and put new ones below everything
  useEffect(() => {
    if (!size.w) return
    if (lastKey.current !== layoutKey || !live.current.pos.size) {
      lastKey.current = layoutKey
      arrange(true)
      return
    }
    const cur = live.current.pos
    const ids = new Set(items.map((v) => v.id))
    // nothing moved by hand yet: just flow again (closes the holes left by items that got a series)
    if (!moved.current && (items.length !== cur.size || items.some((v) => !cur.has(v.id)))) {
      arrange(false)
      return
    }
    const next = new Map()
    let changed = false
    for (const [id, p] of cur) {
      if (ids.has(id)) next.set(id, p)
      else changed = true
    }
    const fresh = items.filter((v) => !next.has(v.id))
    if (fresh.length) {
      let bottom = PAD
      for (const p of next.values()) bottom = Math.max(bottom, p.y + p.h + CAPTION + GAP)
      for (const [id, p] of justify(fresh, size.w / live.current.view.z, aspectOf, bottom)) next.set(id, p)
      changed = true
    }
    if (changed) setPos(next)
  }, [items, layoutKey, size.w])

  // a cover with another shape than its recorded size (rotated phone video): use the real shape
  function onAspect(id, a) {
    const v = byIdRef.current.get(id)
    if (!v || !a) return
    const now = aspectOf(v)
    const real = clampAspect(a)
    if (Math.abs(real - now) / now < 0.08) return
    aspects.current.set(id, real)
    if (!moved.current) {
      clearTimeout(arrangeTimer.current)
      arrangeTimer.current = setTimeout(() => arrange(false), 250)
    } else {
      setPos((p) => {
        const q = p.get(id)
        if (!q) return p
        const n = new Map(p)
        n.set(id, { ...q, w: real * q.h })
        return n
      })
    }
  }
  const byIdRef = useRef(byId)
  byIdRef.current = byId
  useEffect(() => () => clearTimeout(arrangeTimer.current), [])

  const onMenuRef = useRef(onMenu)
  onMenuRef.current = onMenu
  const stableMenu = useMemo(() => (x, y, v) => onMenuRef.current(x, y, v), [])
  const stableAspect = useMemo(() => (id, a) => onAspectRef.current(id, a), [])
  const onAspectRef = useRef(onAspect)
  onAspectRef.current = onAspect

  // wheel: pan; Shift + wheel or a trackpad pinch (Ctrl + wheel): zoom at the pointer
  useEffect(() => {
    const el = box.current
    const onWheel = (e) => {
      e.preventDefault()
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? el.clientHeight : 1 // Firefox: lines
      const v = live.current.view
      if (e.shiftKey || e.ctrlKey) {
        const d = (e.deltaY || e.deltaX) * unit // Shift + wheel arrives as deltaX in some browsers
        if (!d) return
        const r = el.getBoundingClientRect()
        zoomAt(v.z * Math.exp(-d * (e.ctrlKey ? 0.01 : 0.0015)), e.clientX - r.left, e.clientY - r.top)
      } else {
        setView(clampView({ ...v, x: v.x - e.deltaX * unit, y: v.y - e.deltaY * unit }))
      }
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  // Space held: drag pans the canvas
  useEffect(() => {
    const down = (e) => {
      if (e.code !== 'Space' || /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(e.target.tagName)) return
      e.preventDefault()
      setSpace(true)
    }
    const up = (e) => e.code === 'Space' && setSpace(false)
    const reset = () => setSpace(false)
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', reset)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', reset)
    }
  }, [])

  function onPointerDown(e) {
    if (e.button === 2) return // context menu
    const itemEl = e.target.closest('[data-id]')
    const pan = e.button === 1 || (e.button === 0 && space) || (e.pointerType !== 'mouse' && !itemEl)
    if (!pan && e.button !== 0) return
    e.preventDefault()
    document.activeElement?.blur?.()
    box.current.setPointerCapture(e.pointerId)
    const r = box.current.getBoundingClientRect()
    setBusy(true)
    if (pan) {
      action.current = { type: 'pan', sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y }
    } else if (itemEl) {
      action.current = { type: 'item', id: itemEl.dataset.id, sx: e.clientX, sy: e.clientY, mods: { shiftKey: e.shiftKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey } }
    } else {
      action.current = {
        type: 'marquee',
        sx: e.clientX - r.left,
        sy: e.clientY - r.top,
        mode: e.ctrlKey || e.metaKey ? 'toggle' : e.shiftKey ? 'add' : 'replace',
        base: selected,
        hitKey: null,
      }
    }
  }

  function onPointerMove(e) {
    const a = action.current
    if (!a) return
    const { view } = live.current
    if (a.type === 'pan') {
      setView(clampView({ ...view, x: a.vx + e.clientX - a.sx, y: a.vy + e.clientY - a.sy }))
      return
    }
    if (a.type === 'item') {
      const dx = e.clientX - a.sx
      const dy = e.clientY - a.sy
      if (!a.ids) {
        if (Math.hypot(dx, dy) < 5) return
        // a selected item drags the whole selection, an unselected one only itself
        a.ids = live.current.selected.has(a.id) ? new Set(live.current.selected) : new Set([a.id])
      }
      const r = box.current.getBoundingClientRect()
      const outside = e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom
      a.dx = dx / view.z
      a.dy = dy / view.z
      setDrag({ ids: a.ids, dx: a.dx, dy: a.dy, x: e.clientX, y: e.clientY, outside })
      onDragAt(e.clientX, e.clientY)
      return
    }
    // selection box
    const r = box.current.getBoundingClientRect()
    const cx = e.clientX - r.left
    const cy = e.clientY - r.top
    if (!a.active) {
      if (Math.hypot(cx - a.sx, cy - a.sy) < 6) return
      a.active = true
    }
    const l = Math.min(a.sx, cx)
    const t = Math.min(a.sy, cy)
    const w = Math.abs(cx - a.sx)
    const h = Math.abs(cy - a.sy)
    setMarq({ l, t, w, h })
    const wl = (l - view.x) / view.z
    const wt = (t - view.y) / view.z
    const wr = (l + w - view.x) / view.z
    const wb = (t + h - view.y) / view.z
    const hits = []
    for (const [id, p] of live.current.pos) {
      if (p.x < wr && p.x + p.w > wl && p.y < wb && p.y + p.h + CAPTION > wt) hits.push(id)
    }
    const key = hits.join()
    if (key === a.hitKey) return
    a.hitKey = key
    const next = a.mode === 'replace' ? new Set() : new Set(a.base)
    for (const id of hits) {
      if (a.mode === 'toggle' && a.base.has(id)) next.delete(id)
      else next.add(id)
    }
    setSelected(next)
  }

  function onPointerUp() {
    const a = action.current
    action.current = null
    setBusy(false)
    if (!a) return
    if (a.type === 'item') {
      if (a.ids) {
        setDrag(null)
        const consumed = onDropItems([...a.ids]) // dropped on a series: it leaves the canvas after the reload
        if (!consumed) {
          setPos((p) => {
            const n = new Map(p)
            for (const id of a.ids) {
              const q = p.get(id)
              if (q) n.set(id, { ...q, x: q.x + a.dx, y: q.y + a.dy })
            }
            return n
          })
          moved.current = true
        }
        return
      }
      const now = Date.now()
      if (lastClick.current.id === a.id && now - lastClick.current.t < 350) {
        lastClick.current = { id: null, t: 0 }
        onOpen(a.id)
        return
      }
      lastClick.current = { id: a.id, t: now }
      const v = live.current.items.find((x) => x.id === a.id)
      if (v) onSelect(v, a.mods)
    } else if (a.type === 'marquee') {
      setMarq(null)
      if (!a.active && a.mode === 'replace') setSelected((prev) => (prev.size ? new Set() : prev))
    }
  }

  // only what is (nearly) on screen is drawn
  const visible = useMemo(() => {
    const { x, y, z } = view
    const m = 400 / z
    const l = -x / z - m
    const t = -y / z - m
    const r = (size.w - x) / z + m
    const b = (size.h - y) / z + m
    return items.filter((v) => {
      const p = pos.get(v.id)
      return p && p.x < r && p.x + p.w > l && p.y < b && p.y + p.h + CAPTION > t
    })
  }, [items, pos, view, size])

  const cursor = busy && action.current?.type === 'pan' ? 'grabbing' : space ? 'grab' : 'default'

  return (
    <div
      ref={box}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onMouseDown={(e) => e.button === 1 && e.preventDefault()} // no auto-scroll on the middle button
      onContextMenu={(e) => e.preventDefault()}
      style={{ cursor, touchAction: 'none' }}
      className="relative h-full select-none overflow-hidden bg-neutral-950"
    >
      <div
        style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})`, transformOrigin: '0 0' }}
        className="absolute left-0 top-0"
      >
        {visible.map((v) => (
          <CanvasItem
            key={v.id}
            v={v}
            p={pos.get(v.id)}
            z={view.z}
            selected={selected.has(v.id)}
            offset={drag && drag.ids.has(v.id) ? drag : null}
            still={!busy}
            onAspect={stableAspect}
            onMenu={stableMenu}
          />
        ))}
      </div>
      {marq && (
        <div
          aria-hidden
          style={{ left: marq.l, top: marq.t, width: marq.w, height: marq.h }}
          className="pointer-events-none absolute rounded-sm border border-accent bg-accent/15"
        />
      )}
      {drag && drag.outside && (
        <div
          aria-hidden
          style={{ left: drag.x + 14, top: drag.y + 14 }}
          className="pointer-events-none fixed z-50 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white shadow-lg"
        >
          {drag.ids.size} 個項目
        </div>
      )}
    </div>
  )
})

export default ClassifierCanvas
