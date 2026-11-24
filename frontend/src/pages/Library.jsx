import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, baseName, KINDS, parentOf, qualityKey, rememberKind, storedKind } from '../api.js'
import VideoCard, { VideoRow } from '../components/VideoCard.jsx'
import FolderTree from '../components/FolderTree.jsx'
import { BulkEditDialog, ContextMenu, PromptDialog } from '../components/Dialogs.jsx'

const SORTS = {
  added: { label: '最新加入', fn: (a, b) => (b.added || 0) - (a.added || 0) },
  title: { label: '標題', fn: (a, b) => a.title.localeCompare(b.title, 'zh-Hant') },
  duration: { label: '片長', fn: (a, b) => (b.duration || 0) - (a.duration || 0) },
  size: { label: '檔案大小', fn: (a, b) => (b.size || 0) - (a.size || 0) },
  // resolution (short side, so portrait videos count the same) first, then bit rate
  quality: {
    label: '畫質',
    fn: (a, b) =>
      Math.min(b.width || 0, b.height || 0) - Math.min(a.width || 0, a.height || 0) || (b.bit_rate || 0) - (a.bit_rate || 0),
  },
}

function readView() {
  try {
    return localStorage.getItem('tad.view') === 'list' ? 'list' : 'grid'
  } catch {
    return 'grid'
  }
}

function Select({ value, onChange, children, label }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-neutral-400">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="max-w-48 rounded-lg bg-neutral-800 px-2 py-1.5 outline-none ring-1 ring-white/10 focus:ring-accent"
      >
        {children}
      </select>
    </label>
  )
}

// a path after `from` was renamed / moved to `to` (for keeping the selected folder)
function remap(path, from, to) {
  if (path === from) return to
  if (path.startsWith(from + '/')) return to + path.slice(from.length)
  return path
}

export default function Library({ guard, onLogout }) {
  const navigate = useNavigate()
  const [videos, setVideos] = useState(null)
  const [folders, setFolders] = useState([{ path: '', videos: 0 }])
  const [tags, setTags] = useState({ actors: [], series: [] })
  const [processing, setProcessing] = useState(0)
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState(readView)
  const [menu, setMenu] = useState(null) // { x, y, items }
  const [dialog, setDialog] = useState(null) // PromptDialog props
  const [toast, setToast] = useState(null)
  const [sidebar, setSidebar] = useState(false) // mobile drawer
  const [selecting, setSelecting] = useState(false) // multi-select mode
  const [selected, setSelected] = useState(() => new Set()) // ids
  const [bulk, setBulk] = useState(false) // BulkEditDialog open
  const anchor = useRef(null) // last clicked item, start of a Shift-click range
  const toastTimer = useRef(null)
  const [params, setParams] = useSearchParams() // filters live in the URL so "back" keeps them

  const q = params.get('q') || ''
  const actor = params.get('actor') || ''
  const series = params.get('series') || ''
  const folder = params.get('folder') || ''
  const sort = params.get('sort') || 'added'
  const kind = KINDS[params.get('kind')] ? params.get('kind') : storedKind() // 影片 / 圖片 / 全部
  const apiKind = kind === 'all' ? '' : kind
  const K = KINDS[kind]

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  function notify(text, error = false) {
    setToast({ text, error })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(null), error ? 6000 : 3000)
  }

  async function load() {
    try {
      const [v, t, f] = await Promise.all([api.videos(apiKind), api.tags(), api.folders()])
      setVideos(v.videos)
      setProcessing(v.processing)
      setTags(t)
      setFolders(f.folders)
    } catch (e) {
      guard(e)
    }
  }

  useEffect(() => {
    load()
  }, [apiKind])

  function switchKind(k) {
    rememberKind(k)
    setVideos(null)
    setParam('kind', k)
  }

  // while screenshots / info are being generated, refresh so new covers appear
  useEffect(() => {
    if (!processing) return
    const timer = setTimeout(load, 4000)
    return () => clearTimeout(timer)
  }, [processing, videos])

  function switchView(v) {
    setView(v)
    try {
      localStorage.setItem('tad.view', v)
    } catch {}
  }

  async function act(fn, success) {
    try {
      const result = await fn()
      if (success) notify(success)
      await load()
      return result
    } catch (e) {
      try {
        guard(e)
      } catch (err) {
        notify(err.message, true)
      }
    }
  }

  async function rescan() {
    setBusy(true)
    await act(() => api.rescan())
    setBusy(false)
  }

  async function logout() {
    await api.logout().catch(() => {})
    onLogout()
  }

  // ── folder / file actions ──

  function addFolder(parent) {
    setDialog({
      title: '新增資料夾',
      label: `位置：/${parent}`,
      confirmText: '建立',
      onSubmit: async (name) => {
        const { path } = await api.createFolder(parent, name)
        setDialog(null)
        notify(`已建立「${name}」`)
        await load()
        setParam('folder', path)
      },
    })
  }

  function renameFolder(path) {
    setDialog({
      title: '重新命名資料夾',
      initial: baseName(path),
      confirmText: '重新命名',
      onSubmit: async (name) => {
        const { path: renamed } = await api.renameFolder(path, name)
        setDialog(null)
        notify('已重新命名')
        await load()
        if (folder) setParam('folder', remap(folder, path, renamed))
      },
    })
  }

  function renameVideo(video) {
    setDialog({
      title: video.kind === 'photo' ? '重新命名圖片檔' : '重新命名影片檔',
      label: '副檔名不輸入會自動保留；資訊與截圖會一起改名',
      initial: video.file,
      confirmText: '重新命名',
      onSubmit: async (name) => {
        await api.renameVideo(video.id, name)
        setDialog(null)
        notify('已重新命名')
        await load()
      },
    })
  }

  async function deleteFolder(path) {
    if (!window.confirm(`確定要刪除空資料夾「${baseName(path)}」嗎？`)) return
    await act(() => api.deleteFolder(path), '已刪除資料夾')
    if (folder === path || folder.startsWith(path + '/')) setParam('folder', parentOf(path))
  }

  async function deleteVideo(video) {
    const what = video.kind === 'photo' ? '圖片' : '影片'
    if (!window.confirm(`確定要刪除「${video.file}」嗎？\n${what}檔與它的資訊、截圖都會刪除，無法復原。\n（下載紀錄會保留，之後可在「下載紀錄」重新下載）`)) return
    await act(() => api.remove(video.id), `已刪除${what}`)
  }

  async function dropItems(dest, items) {
    const folderMoves = (items.folders || []).filter((p) => p !== dest && parentOf(p) !== dest && !dest.startsWith(p + '/'))
    const videoMoves = (items.videos || []).filter((id) => videos?.find((v) => v.id === id)?.folder !== dest)
    if (!folderMoves.length && !videoMoves.length) return
    const result = await act(() => api.move(videoMoves, folderMoves, dest))
    if (!result) return
    if (result.failed.length) notify(result.failed.map((f) => `${f.name}：${f.error}`).join('\n'), true)
    else notify(`已移到 /${dest}`)
    for (const p of folderMoves) {
      if (folder === p || folder.startsWith(p + '/')) setParam('folder', remap(folder, p, dest ? `${dest}/${baseName(p)}` : baseName(p)))
    }
  }

  function folderMenu(x, y, path) {
    const info = folders.find((f) => f.path === path)
    const hasChildren = folders.some((f) => f.path && parentOf(f.path) === path)
    const items = [{ label: '📁 新增子資料夾', onClick: () => addFolder(path) }]
    if (path) {
      items.push(
        { label: '✏️ 重新命名', onClick: () => renameFolder(path) },
        '-',
        { label: '🗑 刪除（僅空資料夾）', danger: true, disabled: hasChildren || (info?.videos || 0) + (info?.photos || 0) > 0, onClick: () => deleteFolder(path) },
      )
    }
    setMenu({ x, y, items })
  }

  // ── multi-select ──

  // like Windows Explorer: click / Ctrl+click toggles the item and makes it the anchor; Shift+click selects
  // anchor..item (and only that); Ctrl+Shift+click adds anchor..item to the selection; the anchor stays
  function select(video, e = {}) {
    setSelecting(true)
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

  function exitSelect() {
    setSelecting(false)
    setSelected(new Set())
    anchor.current = null
  }

  const selectAll = () => setSelected(new Set(shown.map((v) => v.id)))

  function describe(items) {
    const photos = items.filter((v) => v.kind === 'photo').length
    return [items.length - photos && `${items.length - photos} 部影片`, photos && `${photos} 張圖片`].filter(Boolean).join('、')
  }

  async function deleteSelected(items = picked) {
    if (!items.length) return
    const multi = items.filter((v) => v.versions > 1).length
    const lines = [
      `確定要刪除選取的 ${describe(items)} 嗎？`,
      '檔案與它們的資訊、截圖都會刪除，無法復原。',
      multi ? `其中 ${multi} 個有多個版本，只會刪除顯示的那個版本。` : '',
      '（下載紀錄會保留，之後可在「下載紀錄」重新下載）',
    ]
    if (!window.confirm(lines.filter(Boolean).join('\n'))) return
    setBusy(true)
    const result = await act(() => api.batchDelete(items.map((v) => v.id)))
    setBusy(false)
    if (!result) return
    if (result.failed.length) {
      const shownErrors = result.failed.slice(0, 5).map((f) => `${f.name}：${f.error}`)
      if (result.failed.length > 5) shownErrors.push(`…另外 ${result.failed.length - 5} 個`)
      notify(`已刪除 ${result.deleted} 個，${result.failed.length} 個失敗：\n${shownErrors.join('\n')}`, true)
    } else notify(`已刪除 ${result.deleted} 個項目`)
  }

  async function bulkUpdate(changes) {
    const result = await api.batchUpdate(picked.map((v) => v.id), changes)
    setBulk(false)
    notify(`已更新 ${result.updated} 個項目的資訊`)
    await load()
  }

  function videoMenu(x, y, video) {
    if (selected.has(video.id) && picked.length > 1) {
      setMenu({
        x,
        y,
        items: [
          { label: `🏷 編輯已選 ${picked.length} 個的主演 / 系列`, onClick: () => setBulk(true) },
          { label: '✖ 取消選取', onClick: exitSelect },
          '-',
          { label: `🗑 刪除已選 ${picked.length} 個`, danger: true, onClick: () => deleteSelected() },
        ],
      })
      return
    }
    setMenu({
      x,
      y,
      items: [
        { label: selected.has(video.id) ? '☐ 取消選取' : '☑ 選取', onClick: () => select(video) },
        { label: video.kind === 'photo' ? '🖼 開啟' : '▶ 開啟', onClick: () => navigate(`/v/${video.id}`, { state: { back: params.toString() } }) },
        { label: '✏️ 重新命名', onClick: () => renameVideo(video) },
        { label: '📂 前往所在資料夾', onClick: () => setParam('folder', video.folder) },
        '-',
        { label: video.kind === 'photo' ? '🗑 刪除圖片' : '🗑 刪除影片', danger: true, onClick: () => deleteVideo(video) },
      ],
    })
  }

  const shown = useMemo(() => {
    if (!videos) return []
    const needle = q.trim().toLowerCase()
    const matching = videos
      .filter((v) => !actor || v.actors.includes(actor))
      .filter((v) => !series || v.series === series)
      .filter((v) => !folder || v.folder === folder || v.folder.startsWith(folder + '/'))
      .filter(
        (v) =>
          !needle ||
          [v.title, v.file, v.folder, v.series, v.description, ...v.actors].some((s) => (s || '').toLowerCase().includes(needle)),
      )
    // versions of the same video show once: the best quality one that passes the filters
    const groupSize = {}
    for (const v of videos) if (v.group) groupSize[v.group] = (groupSize[v.group] || 0) + 1
    const best = {}
    const items = []
    for (const v of matching) {
      if (!v.group) items.push(v)
      else if (!best[v.group] || qualityKey(v) > qualityKey(best[v.group])) best[v.group] = v
    }
    for (const v of Object.values(best)) items.push({ ...v, versions: groupSize[v.group] })
    return items.sort(SORTS[sort]?.fn || SORTS.added.fn)
  }, [videos, q, actor, series, folder, sort])

  // only what is on screen can be selected: filtering / deleting drops the rest
  const picked = useMemo(() => shown.filter((v) => selected.has(v.id)), [shown, selected])
  const pickedIds = useMemo(() => picked.map((v) => v.id), [picked])
  useEffect(() => {
    if (picked.length !== selected.size) setSelected(new Set(pickedIds))
  }, [picked])

  // select mode keys: Esc ends, Ctrl/⌘+A selects all, Delete deletes
  useEffect(() => {
    if (!selecting) return
    const onKey = (e) => {
      if (dialog || bulk || menu || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return
      if (e.key === 'Escape') exitSelect()
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        e.preventDefault()
        selectAll()
      } else if (e.key === 'Delete' && picked.length) deleteSelected()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selecting, shown, picked, dialog, bulk, menu])

  // ── drag-select (mouse only; on touch screens a drag scrolls): press on empty space and drag a box,
  // every item it touches is selected. No key: replaces the selection · Shift: adds · Ctrl/⌘: toggles.
  // A plain click on empty space clears the selection. Near the top / bottom edge the page scrolls.
  const marquee = useRef(null) // { x0, y0 (page), x, y (client), mode, base, active, rects, hitKey }
  const boxEl = useRef(null) // the box, drawn by changing its style (no re-render while dragging)

  function onPointerDown(e) {
    if (e.pointerType !== 'mouse' || e.button !== 0) return
    if (e.target.closest('header, a, button, input, select, textarea, label, [data-id]')) return
    e.preventDefault() // no text selection while dragging
    document.activeElement?.blur?.()
    marquee.current = {
      x0: e.clientX + window.scrollX,
      y0: e.clientY + window.scrollY,
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
      if (!m) return
      const px = m.x + window.scrollX
      const py = m.y + window.scrollY
      if (!m.active) {
        if (Math.hypot(px - m.x0, py - m.y0) < 6) return
        m.active = true
        // item positions in page coordinates, read once (they don't move while the page scrolls)
        m.rects = [...document.querySelectorAll('[data-select-root] [data-id]')].map((el) => {
          const r = el.getBoundingClientRect()
          return { id: el.dataset.id, l: r.left + window.scrollX, t: r.top + window.scrollY, r: r.right + window.scrollX, b: r.bottom + window.scrollY }
        })
        setSelecting(true)
        raf = requestAnimationFrame(tick)
      }
      const l = Math.min(m.x0, px)
      const r = Math.max(m.x0, px)
      const t = Math.min(m.y0, py)
      const b = Math.max(m.y0, py)
      const box = boxEl.current
      if (box) {
        Object.assign(box.style, { display: 'block', left: `${l - window.scrollX}px`, top: `${t - window.scrollY}px`, width: `${r - l}px`, height: `${b - t}px` })
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
      if (!m) return
      const edge = 60
      const dy = m.y < edge ? -(edge - m.y) / 3 : m.y > window.innerHeight - edge ? (m.y - window.innerHeight + edge) / 3 : 0
      if (dy) window.scrollBy(0, dy)
      update() // also follows wheel scrolling
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

  const itemProps = (v) => ({
    video: v,
    search: params.toString(),
    onMenu: videoMenu,
    selecting,
    selected: selected.has(v.id),
    onSelect: select,
    dragIds: selected.has(v.id) ? pickedIds : undefined,
  })

  const filtered = q || actor || series || folder
  // folder counts of what is shown (影片 / 圖片 / both)
  const counted = useMemo(
    () => folders.map((f) => ({ ...f, videos: kind === 'photo' ? f.photos || 0 : kind === 'video' ? f.videos : f.videos + (f.photos || 0) })),
    [folders, kind],
  )
  const tree = (
    <FolderTree
      folders={counted}
      rootLabel={`全部${K.label === '全部' ? '' : K.label}`}
      selected={folder}
      onSelect={(p) => {
        setParam('folder', p)
        setSidebar(false)
      }}
      onDrop={dropItems}
      onMenu={folderMenu}
      onAdd={() => addFolder(folder)}
    />
  )

  return (
    <div className="flex min-h-screen">
      {/* folder tree: fixed column on desktop, drawer on mobile */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 overflow-y-auto border-r border-white/5 bg-neutral-950 px-2 py-3 lg:block">
        {tree}
      </aside>
      {sidebar && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setSidebar(false)}>
          <aside className="h-full w-72 overflow-y-auto bg-neutral-900 px-2 py-3" onClick={(e) => e.stopPropagation()}>
            {tree}
          </aside>
        </div>
      )}

      <main className={`min-w-0 flex-1 px-4 ${selecting ? 'pb-36 select-none' : 'pb-16'}`} onPointerDown={onPointerDown}>
        <header className="sticky top-0 z-10 -mx-4 mb-4 space-y-3 bg-neutral-950/90 px-4 py-3 backdrop-blur">
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebar(true)} className="rounded-lg bg-neutral-800 px-2.5 py-1.5 text-sm lg:hidden" aria-label="資料夾">
              📁
            </button>
            <h1 className="truncate text-lg font-semibold">{folder ? baseName(folder) : K.title}</h1>
            <span className="shrink-0 text-sm text-neutral-400">
              {videos ? `${shown.length}${filtered ? ` / ${videos.length}` : ''} ${K.unit}` : ''}
            </span>
            {processing > 0 && (
              <span className="hidden rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300 sm:inline">產生資訊/截圖中：{processing}</span>
            )}
            <div className="ml-auto flex shrink-0 gap-2">
              <div className="flex overflow-hidden rounded-lg ring-1 ring-white/10" role="group" aria-label="檢視方式">
                <button
                  onClick={() => switchView('grid')}
                  className={`px-2.5 py-1.5 text-sm ${view === 'grid' ? 'bg-white/15' : 'bg-neutral-800 hover:bg-neutral-700'}`}
                  title="卡片"
                >
                  ▦
                </button>
                <button
                  onClick={() => switchView('list')}
                  className={`px-2.5 py-1.5 text-sm ${view === 'list' ? 'bg-white/15' : 'bg-neutral-800 hover:bg-neutral-700'}`}
                  title="列表"
                >
                  ☰
                </button>
              </div>
              <button onClick={rescan} disabled={busy} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-50">
                {busy ? '掃描中…' : '重新掃描'}
              </button>
              <button onClick={logout} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">
                登出
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex overflow-hidden rounded-lg ring-1 ring-white/10" role="group" aria-label="顯示類型">
              {['video', 'photo', 'all'].map((k) => (
                <button
                  key={k}
                  onClick={() => switchKind(k)}
                  aria-pressed={kind === k}
                  className={`px-3 py-1.5 text-sm ${kind === k ? 'bg-accent/80 text-white' : 'bg-neutral-800 hover:bg-neutral-700'}`}
                >
                  {KINDS[k].label}
                </button>
              ))}
            </div>
            <button
              onClick={() => navigate('/history')}
              className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700"
              title="所有下載過的檔案，已刪除的可以重新下載"
            >
              📜 下載紀錄
            </button>
            <button
              onClick={() => (selecting ? exitSelect() : setSelecting(true))}
              aria-pressed={selecting}
              className={`rounded-lg px-3 py-1.5 text-sm ${selecting ? 'bg-accent/80 text-white' : 'bg-neutral-800 hover:bg-neutral-700'}`}
              title="選取多個項目來一起刪除或編輯主演 / 系列（也可以 Ctrl / Shift + 點選）"
            >
              ☑ 選取
            </button>
            <input
              value={q}
              onChange={(e) => setParam('q', e.target.value)}
              placeholder="搜尋標題、主演、系列、描述、資料夾…"
              className="min-w-56 flex-1 rounded-lg bg-neutral-800 px-3 py-1.5 text-sm outline-none ring-1 ring-white/10 focus:ring-accent"
            />
            <Select label="主演" value={actor} onChange={(v) => setParam('actor', v)}>
              <option value="">全部</option>
              {tags.actors.map((a) => (
                <option key={a.name} value={a.name}>{`${a.name} (${a.count})`}</option>
              ))}
            </Select>
            <Select label="系列" value={series} onChange={(v) => setParam('series', v)}>
              <option value="">全部</option>
              {tags.series.map((s) => (
                <option key={s.name} value={s.name}>{`${s.name} (${s.count})`}</option>
              ))}
            </Select>
            <Select label="排序" value={sort} onChange={(v) => setParam('sort', v === 'added' ? '' : v)}>
              {Object.entries(SORTS).map(([k, s]) => (
                <option key={k} value={k}>{s.label}</option>
              ))}
            </Select>
            {filtered && (
              <button onClick={() => setParams(kind === storedKind() ? {} : { kind }, { replace: true })} className="text-sm text-neutral-400 hover:text-white">
                清除篩選
              </button>
            )}
          </div>
        </header>

        {videos === null ? (
          <p className="text-neutral-400">載入中…</p>
        ) : shown.length === 0 ? (
          <p className="py-16 text-center text-neutral-500">
            {videos.length ? `沒有符合的${kind === 'all' ? '項目' : K.label}` : `下載資料夾中還沒有${kind === 'all' ? '影片或圖片' : K.label}`}
          </p>
        ) : view === 'grid' ? (
          <div data-select-root className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
            {shown.map((v) => (
              <VideoCard key={v.id} {...itemProps(v)} />
            ))}
          </div>
        ) : (
          <div data-select-root>
            <div className="hidden grid-cols-[96px_minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_88px_64px_80px] gap-3 border-b border-white/5 px-2 pb-2 text-xs text-neutral-500 md:grid">
              <span />
              <span>標題 / 檔案</span>
              <span>主演</span>
              <span>系列</span>
              <button
                onClick={() => setParam('sort', sort === 'quality' ? '' : 'quality')}
                className={`text-left hover:text-white ${sort === 'quality' ? 'text-white' : ''}`}
                title="依畫質排序（解析度，再比 bit rate）"
              >
                畫質 / bit rate{sort === 'quality' ? ' ↓' : ''}
              </button>
              <span>{kind === 'photo' ? '' : '片長'}</span>
              <span className="text-right">大小</span>
            </div>
            {shown.map((v) => (
              <VideoRow key={v.id} {...itemProps(v)} />
            ))}
          </div>
        )}
      </main>

      {selecting && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-white/10 bg-neutral-900/95 px-4 py-2.5 backdrop-blur lg:left-64">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium tabular-nums">已選 {picked.length} 個</span>
            <button onClick={selectAll} disabled={!shown.length || picked.length === shown.length} className="rounded-lg bg-neutral-800 px-3 py-1.5 hover:bg-neutral-700 disabled:opacity-40">
              全選 ({shown.length})
            </button>
            {picked.length > 0 && (
              <button onClick={() => setSelected(new Set())} className="rounded-lg bg-neutral-800 px-3 py-1.5 hover:bg-neutral-700">
                清除選取
              </button>
            )}
            <div className="ml-auto flex gap-2">
              <button onClick={() => setBulk(true)} disabled={!picked.length} className="rounded-lg bg-neutral-800 px-3 py-1.5 hover:bg-neutral-700 disabled:opacity-40">
                🏷 編輯主演 / 系列
              </button>
              <button
                onClick={() => deleteSelected()}
                disabled={!picked.length || busy}
                className="rounded-lg bg-red-900/70 px-3 py-1.5 text-red-100 hover:bg-red-800 disabled:opacity-40"
              >
                🗑 刪除
              </button>
              <button onClick={exitSelect} className="rounded-lg bg-accent px-3 py-1.5 font-medium hover:bg-accent-hover">
                完成
              </button>
            </div>
          </div>
          <p className="mt-1 hidden text-xs text-neutral-500 md:block">
            點選切換 · 在空白處拖曳框選（Shift 加入、Ctrl 切換）· Shift + 點選選取範圍（Ctrl + Shift 加入）· Ctrl + A 全選 · Delete 刪除 · Esc 結束 · 拖曳已選的項目到左側資料夾可一起移動
          </p>
        </div>
      )}
      {bulk && picked.length > 0 && (
        <BulkEditDialog
          items={picked}
          actorSuggestions={tags.actors.map((a) => a.name)}
          seriesSuggestions={tags.series.map((s) => s.name)}
          onSubmit={bulkUpdate}
          onCancel={() => setBulk(false)}
        />
      )}
      <div ref={boxEl} aria-hidden className="pointer-events-none fixed z-40 hidden rounded-sm border border-accent bg-accent/15" />
      {menu && <ContextMenu {...menu} onClose={() => setMenu(null)} />}
      {dialog && <PromptDialog {...dialog} onCancel={() => setDialog(null)} />}
      {toast && (
        <div
          className={`fixed ${selecting ? 'bottom-28 md:bottom-24' : 'bottom-4'} left-1/2 z-50 max-w-[90vw] -translate-x-1/2 whitespace-pre-line rounded-lg px-4 py-2 text-sm shadow-xl ${
            toast.error ? 'bg-red-900 text-red-100' : 'bg-neutral-800 text-neutral-100'
          }`}
        >
          {toast.text}
        </div>
      )}
    </div>
  )
}
