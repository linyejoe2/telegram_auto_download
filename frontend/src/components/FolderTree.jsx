import { useEffect, useMemo, useState } from 'react'
import { baseName, getDragItems, parentOf, setDragItems, DRAG_TYPE } from '../api.js'

// Left-side folder tree: click to filter, drag a video / folder onto a folder to move it there,
// right-click (or ⋯) for rename / new sub folder / delete.
export default function FolderTree({ folders, selected, onSelect, onDrop, onMenu, onAdd, rootLabel = '全部' }) {
  const [open, setOpen] = useState(() => new Set(['']))
  const [over, setOver] = useState(null)

  const { children, totals } = useMemo(() => {
    const children = {}
    const totals = {}
    for (const f of folders) {
      totals[f.path] = (totals[f.path] || 0) + f.videos
      if (f.path) (children[parentOf(f.path)] ||= []).push(f.path)
      // recursive video counts
      let p = f.path
      while (p) {
        p = parentOf(p)
        totals[p] = (totals[p] || 0) + f.videos
      }
    }
    for (const list of Object.values(children)) list.sort((a, b) => baseName(a).localeCompare(baseName(b), 'zh-Hant'))
    return { children, totals }
  }, [folders])

  // reveal the selected folder
  useEffect(() => {
    if (!selected) return
    setOpen((prev) => {
      const next = new Set(prev)
      let p = selected
      while (p) {
        p = parentOf(p)
        next.add(p)
      }
      return next
    })
  }, [selected])

  function toggle(path) {
    setOpen((prev) => {
      const next = new Set(prev)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
  }

  function dropHandlers(path) {
    return {
      onDragOver: (e) => {
        if (!e.dataTransfer.types.includes(DRAG_TYPE)) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        setOver(path)
      },
      onDragLeave: () => setOver((o) => (o === path ? null : o)),
      onDrop: (e) => {
        e.preventDefault()
        setOver(null)
        const items = getDragItems(e)
        if (items) onDrop(path, items)
      },
    }
  }

  // a plain render function (not a component) so nodes aren't remounted while dragging
  function renderNode(path, depth) {
    const kids = children[path] || []
    const isOpen = open.has(path)
    const isRoot = path === ''
    return (
      <li key={path}>
        <div
          draggable={!isRoot}
          onDragStart={(e) => {
            e.stopPropagation()
            setDragItems(e, { videos: [], folders: [path] })
          }}
          onClick={() => onSelect(path)}
          onContextMenu={(e) => {
            e.preventDefault()
            onMenu(e.clientX, e.clientY, path)
          }}
          {...dropHandlers(path)}
          style={{ paddingLeft: 6 + depth * 14 }}
          className={`group flex cursor-pointer select-none items-center gap-1 rounded-md py-1 pr-1 text-sm ${
            over === path ? 'bg-accent/30 ring-1 ring-accent' : selected === path ? 'bg-white/10 text-white' : 'text-neutral-300 hover:bg-white/5'
          }`}
        >
          <button
            onClick={(e) => {
              e.stopPropagation()
              toggle(path)
            }}
            className={`w-4 shrink-0 text-xs text-neutral-500 ${kids.length ? '' : 'invisible'}`}
            aria-label={isOpen ? '收合' : '展開'}
          >
            {isOpen ? '▾' : '▸'}
          </button>
          <span className="shrink-0">{isRoot ? '🏠' : isOpen && kids.length ? '📂' : '📁'}</span>
          <span className="truncate" title={path || rootLabel}>{isRoot ? rootLabel : baseName(path)}</span>
          <span className="ml-auto shrink-0 pl-1 text-xs tabular-nums text-neutral-500">{totals[path] || ''}</span>
          <button
            onClick={(e) => {
              e.stopPropagation()
              const r = e.currentTarget.getBoundingClientRect()
              onMenu(r.left, r.bottom, path)
            }}
            className="shrink-0 rounded px-1 text-neutral-500 opacity-0 hover:bg-white/10 hover:text-white group-hover:opacity-100"
            aria-label="更多動作"
          >
            ⋯
          </button>
        </div>
        {isOpen && kids.length > 0 && (
          <ul>
            {kids.map((k) => renderNode(k, depth + 1))}
          </ul>
        )}
      </li>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-xs font-medium uppercase tracking-wide text-neutral-500">資料夾</h2>
        <button onClick={onAdd} className="rounded-md px-2 py-0.5 text-sm text-neutral-300 hover:bg-white/10" title="在目前資料夾新增資料夾">
          ＋ 新增
        </button>
      </div>
      <ul>
        {renderNode('', 0)}
      </ul>
      <p className="px-1 text-[11px] leading-snug text-neutral-600">拖曳影片、圖片或資料夾到資料夾上即可移動；右鍵可重新命名</p>
    </div>
  )
}
