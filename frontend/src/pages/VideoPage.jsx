import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, fmtBitrate, fmtDuration, fmtSize } from '../api.js'
import Player from '../components/Player.jsx'
import TagInput from '../components/TagInput.jsx'

function InfoRow({ label, children }) {
  return (
    <div className="flex justify-between gap-4 border-b border-white/5 py-1.5 text-sm last:border-0">
      <span className="shrink-0 text-neutral-400">{label}</span>
      <span className="break-all text-right tabular-nums">{children ?? '-'}</span>
    </div>
  )
}

const field = 'w-full rounded-lg bg-neutral-800 px-3 py-1.5 text-sm outline-none ring-1 ring-white/10 focus:ring-accent'

export default function VideoPage({ guard }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const backTo = location.state?.back ? `/?${location.state.back}` : '/'

  const [video, setVideo] = useState(null)
  const [error, setError] = useState('')
  const [tags, setTags] = useState({ actors: [], series: [] })
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [playFrom, setPlayFrom] = useState(null) // null = show screenshots, number = playing from there

  async function load() {
    try {
      const v = await api.video(id)
      setVideo(v)
      setForm((f) => f ?? { title: v.title, actors: v.actors, series: v.series, source: v.source })
      return v
    } catch (e) {
      try {
        guard(e)
      } catch (err) {
        setError(err.message)
      }
    }
  }

  useEffect(() => {
    setForm(null)
    setPlayFrom(null)
    load()
    api.tags().then(setTags).catch(() => {})
  }, [id])

  // screenshots / info still being generated: poll until ready
  useEffect(() => {
    if (!video?.processing && video?.ready) return
    if (!video || video.error) return
    const timer = setTimeout(load, 3000)
    return () => clearTimeout(timer)
  }, [video])

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const v = await api.update(id, form)
      setVideo(v)
      setForm({ title: v.title, actors: v.actors, series: v.series, source: v.source })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      api.tags().then(setTags).catch(() => {})
    } catch (err) {
      guard(err)
    } finally {
      setSaving(false)
    }
  }

  async function regenerate() {
    try {
      await api.regenerateShots(id)
      setVideo((v) => ({ ...v, processing: true }))
    } catch (err) {
      guard(err)
    }
  }

  async function remove() {
    if (!window.confirm(`確定要刪除「${video.file}」嗎？\n影片檔與它的資訊、截圖都會刪除，無法復原。`)) return
    try {
      await api.remove(id)
      navigate(backTo, { replace: true })
    } catch (err) {
      alert(err.message)
    }
  }

  if (error) return <p className="p-8 text-red-400">{error === 'not found' ? '找不到這部影片' : error}</p>
  if (!video || !form) return <p className="p-8 text-neutral-400">載入中…</p>

  const info = video.info || {}
  const duration = info.duration || video.duration || 0
  const shotTime = (i) => (duration * (i + 1)) / (video.shots.length + 1)
  const dirty =
    form.title !== video.title ||
    form.series !== video.series ||
    form.source !== video.source ||
    form.actors.join('\n') !== video.actors.join('\n')

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-16">
      <div className="flex items-center gap-3 py-3">
        <Link to={backTo} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">← 返回</Link>
        <h1 className="truncate text-lg font-semibold" title={video.title}>{video.title}</h1>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="space-y-4">
          {playFrom !== null ? (
            <Player key={playFrom} video={video} startAt={playFrom} />
          ) : (
            <>
              <button
                onClick={() => setPlayFrom(0)}
                className="group relative block aspect-video w-full overflow-hidden rounded-xl bg-neutral-900"
              >
                {video.shots[0] && <img src={video.shots[0]} alt="" className="h-full w-full object-cover opacity-80 transition group-hover:opacity-100" />}
                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="flex h-20 w-20 items-center justify-center rounded-full bg-accent/90 text-3xl shadow-lg transition group-hover:scale-110">▶</span>
                </span>
              </button>
              {video.shots.length > 0 ? (
                <div className="grid grid-cols-3 gap-2">
                  {video.shots.map((src, i) => (
                    <button key={src} onClick={() => setPlayFrom(shotTime(i))} className="group relative overflow-hidden rounded-lg" title="從這裡開始播放">
                      <img src={src} alt="" loading="lazy" className="aspect-video w-full object-cover transition group-hover:scale-105" />
                      <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 text-[11px] tabular-nums">{fmtDuration(shotTime(i))}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-neutral-500">{video.error ? `無法產生截圖：${video.error}` : '截圖產生中…'}</p>
              )}
            </>
          )}
        </section>

        <aside className="space-y-6">
          <form onSubmit={save} className="space-y-3 rounded-xl bg-neutral-900 p-4 ring-1 ring-white/5">
            <h2 className="font-medium">影片資訊</h2>
            <label className="block space-y-1">
              <span className="text-xs text-neutral-400">標題</span>
              <input className={field} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label className="block space-y-1">
              <span className="text-xs text-neutral-400">主演（可複選，Enter 新增）</span>
              <TagInput
                value={form.actors}
                onChange={(actors) => setForm({ ...form, actors })}
                suggestions={tags.actors.map((a) => a.name)}
                placeholder="輸入主演名稱"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs text-neutral-400">系列</span>
              <input className={field} list="series-list" value={form.series} onChange={(e) => setForm({ ...form, series: e.target.value })} />
              <datalist id="series-list">
                {tags.series.map((s) => (
                  <option key={s.name} value={s.name} />
                ))}
              </datalist>
            </label>
            <label className="block space-y-1">
              <span className="text-xs text-neutral-400">來源</span>
              <input className={field} value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder="https://…" />
            </label>
            {/^https?:\/\//i.test(video.source) && (
              <a href={video.source} target="_blank" rel="noreferrer noopener" className="block truncate text-xs text-accent hover:underline">
                🔗 {video.source}
              </a>
            )}
            <button disabled={!dirty || saving} className="w-full rounded-lg bg-accent py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-40">
              {saving ? '儲存中…' : saved ? '已儲存 ✓' : '儲存'}
            </button>
          </form>

          <div className="rounded-xl bg-neutral-900 p-4 ring-1 ring-white/5">
            <h2 className="mb-2 font-medium">Video Info</h2>
            <InfoRow label="長寬">{info.width ? `${info.width} × ${info.height}` : null}</InfoRow>
            <InfoRow label="Bit rate">{fmtBitrate(info.bit_rate)}{info.video_bit_rate ? `（影像 ${fmtBitrate(info.video_bit_rate)}）` : ''}</InfoRow>
            <InfoRow label="Bit depth">{info.bit_depth ? `${info.bit_depth}-bit` : null}</InfoRow>
            <InfoRow label="影像編碼">{info.video_codec ? `${info.video_codec}${info.profile ? ` (${info.profile})` : ''}` : null}</InfoRow>
            <InfoRow label="影格率">{info.fps ? `${info.fps} fps` : null}</InfoRow>
            <InfoRow label="音訊">{info.audio_codec ? `${info.audio_codec}${info.audio_channels ? ` · ${info.audio_channels}ch` : ''}${info.audio_sample_rate ? ` · ${info.audio_sample_rate / 1000} kHz` : ''}` : null}</InfoRow>
            <InfoRow label="片長">{duration ? fmtDuration(duration) : null}</InfoRow>
            <InfoRow label="檔案大小">{fmtSize(info.size || video.size)}</InfoRow>
            <InfoRow label="播放方式">{video.direct ? '原始檔（不支援時自動轉檔）' : '即時轉檔'}</InfoRow>
            <InfoRow label="位置">{`${video.folder ? video.folder + '/' : ''}${video.file}`}</InfoRow>
          </div>

          <div className="flex flex-wrap gap-2">
            <a href={`/media/${video.id}/file`} download={video.file} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">下載原檔</a>
            <button onClick={regenerate} disabled={video.processing} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-50">
              {video.processing ? '處理中…' : '重新產生截圖'}
            </button>
            <button onClick={remove} className="ml-auto rounded-lg bg-red-900/60 px-3 py-1.5 text-sm text-red-100 hover:bg-red-800">刪除影片</button>
          </div>
        </aside>
      </div>
    </div>
  )
}
