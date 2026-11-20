import { Link } from 'react-router-dom'
import { fmtBitrate, fmtDuration, fmtSize, resolutionLabel, setDragItems } from '../api.js'

// shared by the card and list views: drag to a folder to move, right-click for rename / delete
function itemProps(video, onMenu) {
  return {
    draggable: true,
    onDragStart: (e) => setDragItems(e, { videos: [video.id], folders: [] }),
    onContextMenu: (e) => {
      e.preventDefault()
      onMenu(e.clientX, e.clientY, video)
    },
  }
}

export default function VideoCard({ video, search, onMenu }) {
  const res = resolutionLabel(video.width, video.height)
  return (
    <Link
      to={`/v/${video.id}`}
      state={{ back: search }}
      {...itemProps(video, onMenu)}
      className="group block overflow-hidden rounded-xl bg-neutral-900 ring-1 ring-white/5 transition hover:ring-accent/60"
    >
      <div className="relative aspect-video bg-neutral-800">
        {video.cover ? (
          <img src={video.cover} alt="" loading="lazy" draggable={false} className="h-full w-full object-cover transition group-hover:scale-[1.03]" />
        ) : (
          <div className="flex h-full items-center justify-center px-3 text-center text-xs text-neutral-500" title={video.error || undefined}>
            {video.error ? '⚠ 檔案不完整或無法讀取' : video.ready ? '沒有截圖' : '產生截圖中…'}
          </div>
        )}
        {res && <span className="absolute left-2 top-2 rounded bg-black/70 px-1.5 py-0.5 text-[11px] font-medium">{res}</span>}
        {video.versions > 1 && (
          <span className="absolute right-2 top-2 rounded bg-accent/90 px-1.5 py-0.5 text-[11px] font-medium">{video.versions} 個版本</span>
        )}
        {video.duration != null && (
          <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-[11px] tabular-nums">
            {fmtDuration(video.duration)}
          </span>
        )}
      </div>
      <div className="space-y-1 p-3">
        <h3 className="line-clamp-2 text-sm font-medium leading-snug" title={video.title}>{video.title}</h3>
        {video.series && <p className="truncate text-xs text-accent">{video.series}</p>}
        {video.actors.length > 0 && <p className="truncate text-xs text-neutral-400">{video.actors.join('、')}</p>}
      </div>
    </Link>
  )
}

export function VideoRow({ video, search, onMenu }) {
  return (
    <Link
      to={`/v/${video.id}`}
      state={{ back: search }}
      {...itemProps(video, onMenu)}
      className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-white/5 md:grid-cols-[96px_minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_88px_64px_80px]"
    >
      <div className="aspect-video overflow-hidden rounded bg-neutral-800">
        {video.cover && <img src={video.cover} alt="" loading="lazy" draggable={false} className="h-full w-full object-cover" />}
      </div>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium" title={video.title}>
          {video.title}
          {video.versions > 1 && <span className="ml-2 rounded bg-accent/30 px-1.5 py-0.5 text-[11px] font-normal">{video.versions} 個版本</span>}
        </p>
        <p className="truncate text-xs text-neutral-500" title={`${video.folder}/${video.file}`}>
          {video.folder ? `${video.folder}/` : ''}{video.file}
        </p>
        <p className="truncate text-xs text-neutral-400 md:hidden">
          {[fmtDuration(video.duration), resolutionLabel(video.width, video.height), video.bit_rate && fmtBitrate(video.bit_rate), video.actors.join('、')].filter(Boolean).join(' · ')}
        </p>
      </div>
      <p className="hidden truncate text-sm text-neutral-300 md:block">{video.actors.join('、') || '-'}</p>
      <p className="hidden truncate text-sm text-accent md:block">{video.series || '-'}</p>
      <div className="hidden leading-tight tabular-nums md:block" title={video.width ? `${video.width} × ${video.height}` : undefined}>
        <p className="text-sm text-neutral-300">{resolutionLabel(video.width, video.height) || '-'}</p>
        {video.bit_rate ? <p className="text-xs text-neutral-500">{fmtBitrate(video.bit_rate)}</p> : null}
      </div>
      <p className="hidden text-sm tabular-nums text-neutral-400 md:block">{fmtDuration(video.duration)}</p>
      <p className="hidden text-right text-sm tabular-nums text-neutral-400 md:block">{fmtSize(video.size)}</p>
    </Link>
  )
}
