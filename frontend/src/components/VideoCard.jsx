import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { dimensions, fmtBitrate, fmtDuration, fmtSize, MEDIA, releaseVideo, resolutionLabel, setDragItems } from '../api.js'

// hover preview: resting the mouse on a video for HOVER_DELAY plays its preview clip (a few short pieces
// from across the video, made by the server on the first request and kept; library/media.py make_preview)
const HOVER_DELAY = 1000

function useHoverPreview(video) {
  const [on, setOn] = useState(false)
  const timer = useRef(null)
  const usable = video.kind !== 'photo' && video.ready && !video.error
  const stop = () => {
    clearTimeout(timer.current)
    setOn(false)
  }
  useEffect(() => () => clearTimeout(timer.current), [])
  useEffect(stop, [video.id])
  return {
    on: on && usable,
    handlers: usable
      ? {
          // mouse only, and not while a button is held (drag-select / dragging over the cards)
          onPointerEnter: (e) => {
            if (e.pointerType !== 'mouse' || e.buttons) return
            clearTimeout(timer.current)
            timer.current = setTimeout(() => setOn(true), HOVER_DELAY)
          },
          onPointerLeave: stop,
          onDragStartCapture: stop,
        }
      : {},
  }
}

function PreviewVideo({ id }) {
  const ref = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (el) el.muted = true // set before it loads so autoplay is allowed
    return () => releaseVideo(el)
  }, [])
  if (failed) return null
  return (
    <>
      <video
        ref={ref}
        src={`${MEDIA}/${id}/preview.mp4`}
        muted
        autoPlay
        loop
        playsInline
        disablePictureInPicture
        onLoadedData={(e) => e.currentTarget.play().catch(() => {})}
        onPlaying={() => setPlaying(true)}
        onError={() => setFailed(true)}
        className={`pointer-events-none absolute inset-0 h-full w-full bg-black object-cover transition-opacity duration-300 ${playing ? 'opacity-100' : 'opacity-0'}`}
      />
      {!playing && (
        <span aria-hidden className="pointer-events-none absolute bottom-1.5 right-1.5 h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
      )}
    </>
  )
}

// shared by the card and list views: drag to a folder to move (all selected items when this one is
// selected), right-click for rename / delete; in select mode a click toggles the item, Ctrl/⌘/Shift-click
// always selects (Shift = range, see Library.jsx select())
function itemProps(video, { onMenu, selecting, onSelect, dragIds }) {
  return {
    'data-id': video.id, // found by drag-select (Library.jsx)
    draggable: true,
    // Shift+click must not select page text
    onMouseDown: (e) => onSelect && e.shiftKey && e.preventDefault(),
    onDragStart: (e) => setDragItems(e, { videos: dragIds?.length ? dragIds : [video.id], folders: [] }),
    onContextMenu: (e) => {
      e.preventDefault()
      onMenu(e.clientX, e.clientY, video)
    },
    onClick: (e) => {
      if (onSelect && (selecting || e.ctrlKey || e.metaKey || e.shiftKey)) {
        e.preventDefault()
        onSelect(video, e)
      }
    },
  }
}

function placeholder(video) {
  if (video.error) return '⚠ 檔案不完整或無法讀取'
  if (video.ready) return video.kind === 'photo' ? '沒有縮圖' : '沒有截圖'
  return video.kind === 'photo' ? '產生縮圖中…' : '產生截圖中…'
}

function Check({ on, className = '' }) {
  return (
    <span
      aria-hidden
      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-sm font-bold ring-2 ${
        on ? 'bg-accent text-white ring-accent' : 'bg-black/50 text-transparent ring-white/70'
      } ${className}`}
    >
      ✓
    </span>
  )
}

// the cover stays clean (only the select check in select mode); length, resolution and versions go
// under the title
// compact (small cards in the 分類器): only a one-line title under the cover
export default function VideoCard({ video, search, onMenu, selecting, selected, onSelect, dragIds, compact = false }) {
  const photo = video.kind === 'photo'
  const meta = [
    photo ? dimensions(video.width, video.height) : video.duration != null && fmtDuration(video.duration),
    !photo && resolutionLabel(video.width, video.height),
    video.versions > 1 && `${video.versions} 個版本`,
  ].filter(Boolean)
  const preview = useHoverPreview(video)
  return (
    <Link
      to={`/v/${video.id}`}
      state={{ back: search }}
      aria-selected={selecting ? !!selected : undefined}
      {...itemProps(video, { onMenu, selecting, onSelect, dragIds })}
      {...preview.handlers}
      className={`group block overflow-hidden ${compact ? 'rounded-lg' : 'rounded-xl'} bg-neutral-900 ring-1 transition ${
        selected ? 'ring-2 ring-accent' : 'ring-white/5 hover:ring-accent/60'
      }`}
    >
      <div className="relative aspect-video bg-neutral-800">
        {video.cover ? (
          <img
            src={video.cover}
            alt=""
            loading="lazy"
            draggable={false}
            className={`h-full w-full object-cover transition group-hover:scale-[1.03] ${selected ? 'opacity-80' : ''}`}
          />
        ) : (
          <div className="flex h-full items-center justify-center px-3 text-center text-xs text-neutral-500" title={video.error || undefined}>
            {placeholder(video)}
          </div>
        )}
        {preview.on && <PreviewVideo id={video.id} />}
        {selecting && <Check on={selected} className={compact ? 'absolute left-1 top-1 h-5 w-5 text-xs' : 'absolute left-2 top-2'} />}
      </div>
      {compact ? (
        <p className="truncate px-2 py-1 text-xs" title={video.title}>{video.title}</p>
      ) : (
      <div className="space-y-1 p-3">
        <h3 className="line-clamp-2 text-sm font-medium leading-snug" title={video.title}>{video.title}</h3>
        {meta.length > 0 && <p className="truncate text-xs tabular-nums text-neutral-500">{meta.join(' · ')}</p>}
        {video.series && <p className="truncate text-xs text-accent">{video.series}</p>}
        {video.actors.length > 0 && <p className="truncate text-xs text-neutral-400">{video.actors.join('、')}</p>}
      </div>
      )}
    </Link>
  )
}

export function VideoRow({ video, search, onMenu, selecting, selected, onSelect, dragIds }) {
  const photo = video.kind === 'photo'
  const quality = photo ? dimensions(video.width, video.height) : resolutionLabel(video.width, video.height)
  const preview = useHoverPreview(video)
  return (
    <Link
      to={`/v/${video.id}`}
      state={{ back: search }}
      aria-selected={selecting ? !!selected : undefined}
      {...itemProps(video, { onMenu, selecting, onSelect, dragIds })}
      {...preview.handlers}
      className={`grid grid-cols-[96px_minmax(0,1fr)] items-center gap-3 rounded-lg px-2 py-1.5 md:grid-cols-[96px_minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_88px_64px_80px] ${
        selected ? 'bg-accent/20 ring-1 ring-accent/60' : 'hover:bg-white/5'
      }`}
    >
      <div className="relative aspect-video overflow-hidden rounded bg-neutral-800">
        {video.cover && <img src={video.cover} alt="" loading="lazy" draggable={false} className="h-full w-full object-cover" />}
        {preview.on && <PreviewVideo id={video.id} />}
        {selecting && <Check on={selected} className="absolute left-1 top-1 h-5 w-5 text-xs" />}
      </div>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium" title={video.title}>
          {photo && <span className="mr-1" aria-label="圖片">🖼</span>}
          {video.title}
          {video.versions > 1 && <span className="ml-2 rounded bg-accent/30 px-1.5 py-0.5 text-[11px] font-normal">{video.versions} 個版本</span>}
        </p>
        <p className="truncate text-xs text-neutral-500" title={`${video.folder}/${video.file}`}>
          {video.folder ? `${video.folder}/` : ''}{video.file}
        </p>
        <p className="truncate text-xs text-neutral-400 md:hidden">
          {[!photo && fmtDuration(video.duration), quality, !photo && video.bit_rate && fmtBitrate(video.bit_rate), video.actors.join('、')]
            .filter(Boolean)
            .join(' · ')}
        </p>
      </div>
      <p className="hidden truncate text-sm text-neutral-300 md:block">{video.actors.join('、') || '-'}</p>
      <p className="hidden truncate text-sm text-accent md:block">{video.series || '-'}</p>
      <div className="hidden leading-tight tabular-nums md:block" title={video.width ? `${video.width} × ${video.height}` : undefined}>
        <p className="text-sm text-neutral-300">{quality || '-'}</p>
        {!photo && video.bit_rate ? <p className="text-xs text-neutral-500">{fmtBitrate(video.bit_rate)}</p> : null}
      </div>
      <p className="hidden text-sm tabular-nums text-neutral-400 md:block">{photo ? '' : fmtDuration(video.duration)}</p>
      <p className="hidden text-right text-sm tabular-nums text-neutral-400 md:block">{fmtSize(video.size)}</p>
    </Link>
  )
}
