import { Link } from 'react-router-dom'
import { fmtDuration, resolutionLabel } from '../api.js'

export default function VideoCard({ video, search }) {
  const res = resolutionLabel(video.width, video.height)
  return (
    <Link
      to={`/v/${video.id}`}
      state={{ back: search }}
      className="group block overflow-hidden rounded-xl bg-neutral-900 ring-1 ring-white/5 transition hover:ring-accent/60"
    >
      <div className="relative aspect-video bg-neutral-800">
        {video.cover ? (
          <img src={video.cover} alt="" loading="lazy" className="h-full w-full object-cover transition group-hover:scale-[1.03]" />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-neutral-500">
            {video.ready ? '沒有截圖' : '產生截圖中…'}
          </div>
        )}
        {res && <span className="absolute left-2 top-2 rounded bg-black/70 px-1.5 py-0.5 text-[11px] font-medium">{res}</span>}
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
