import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, fmtBitrate, fmtDuration, fmtSize, MEDIA, resolutionLabel } from '../api.js'
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
  // came from the library (its filters) or from 下載紀錄 (backPath)
  const backTo = location.state?.backPath || (location.state?.back ? `/?${location.state.back}` : '/')

  const [video, setVideo] = useState(null)
  const [error, setError] = useState('')
  const [tags, setTags] = useState({ actors: [], series: [] })
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [playFrom, setPlayFrom] = useState(null) // null = show screenshots, number = playing from there
  const [redl, setRedl] = useState(null) // broken file: null | 'busy' | { ok, text }
  const playTime = useRef(0) // where the player is, so switching version continues there

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
    setRedl(null)
    // switching version keeps playing at the same time
    setPlayFrom(location.state?.resume ?? null)
    load()
    api.tags().then(setTags).catch(() => {})
  }, [id])

  // photos: ← / → step through the photos of the same folder
  useEffect(() => {
    if (video?.kind !== 'photo') return
    function onKey(e) {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.altKey || e.ctrlKey || e.metaKey) return
      const target = e.key === 'ArrowLeft' ? video.neighbors?.prev : e.key === 'ArrowRight' ? video.neighbors?.next : null
      if (target) {
        e.preventDefault()
        goTo(target)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [video])

  function goTo(otherId) {
    navigate(`/v/${otherId}`, { replace: true, state: location.state })
  }

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

  function switchVersion(versionId) {
    if (versionId === id) return
    navigate(`/v/${versionId}`, {
      replace: true,
      state: { back: location.state?.back, resume: playFrom !== null ? playTime.current : null },
    })
  }

  async function splitOut() {
    if (!window.confirm(`把「${video.file}」從這個版本群組移出？\n之後自動比對不會再把它和這些影片歸類在一起。`)) return
    try {
      const v = await api.ungroup(id)
      setVideo(v)
      setForm({ title: v.title, actors: v.actors, series: v.series, source: v.source })
    } catch (err) {
      guard(err)
    }
  }

  async function redownload() {
    const note = video.redownload?.note ? `\n${video.redownload.note}` : ''
    if (!window.confirm(`重新下載「${video.file}」？${note}\n\n找到來源後會刪除這個損毀的檔案、下載新的一份到同一個資料夾；進度會顯示在 Telegram。`)) return
    setRedl('busy')
    try {
      await api.redownloadVideo(id)
      setRedl({ ok: true, text: '已加入 Bot 的下載佇列，進度會顯示在 Telegram。下載完成、影片庫重新掃描後（約 1–2 分鐘）就會出現新的檔案。' })
    } catch (err) {
      try {
        guard(err)
      } catch (e) {
        setRedl({ ok: false, text: e.message })
      }
    }
  }

  async function remove() {
    const what = video.kind === 'photo' ? '圖片' : '影片'
    if (!window.confirm(`確定要刪除「${video.file}」嗎？\n${what}檔與它的資訊、截圖都會刪除，無法復原。\n（下載紀錄會保留，之後可在「下載紀錄」重新下載）`)) return
    try {
      await api.remove(id)
      const next = video.neighbors?.next || video.neighbors?.prev // photos: continue with the next one
      if (next) goTo(next)
      else navigate(backTo, { replace: true })
    } catch (err) {
      alert(err.message)
    }
  }

  if (error) return <p className="p-8 text-red-400">{error === 'not found' ? '找不到這個檔案' : error}</p>
  if (!video || !form) return <p className="p-8 text-neutral-400">載入中…</p>

  const info = video.info || {}
  const photo = video.kind === 'photo'
  const nav = video.neighbors || {}
  const fileUrl = `${MEDIA}/${video.id}/file`
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
          {video.error && (
            <div className="space-y-2 rounded-xl bg-red-950/50 p-4 text-sm ring-1 ring-red-500/30">
              <p className="text-red-200">⚠ {photo ? '無法讀取這張圖片' : '無法產生截圖'}：{video.error}</p>
              {video.redownload && <p className="text-xs text-neutral-400">{video.redownload.note}</p>}
              {redl?.text ? (
                <p className={redl.ok ? 'text-emerald-300' : 'text-red-300'}>{redl.text}</p>
              ) : null}
              {!redl?.ok && (
                <button
                  onClick={redownload}
                  disabled={redl === 'busy' || !video.redownload?.possible || !video.redownload?.bot}
                  className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-40"
                  title={
                    !video.redownload?.bot ? '這台電腦的程式沒有在執行 Bot' : !video.redownload?.possible ? video.redownload?.note : '從來源重新下載這個檔案'
                  }
                >
                  {redl === 'busy' ? '送出中…' : '⬇ 重新下載'}
                </button>
              )}
              {video.redownload && !video.redownload.bot && (
                <p className="text-xs text-amber-300">這台電腦的程式沒有在執行 Bot，暫時無法重新下載。</p>
              )}
            </div>
          )}
          {photo ? (
            <div className="relative flex min-h-[40vh] items-center justify-center overflow-hidden rounded-xl bg-black">
              <a href={fileUrl} target="_blank" rel="noreferrer" title="開啟原圖">
                <img key={video.id} src={fileUrl} alt={video.title} className="max-h-[80vh] w-auto max-w-full object-contain" />
              </a>
              {nav.prev && (
                <button
                  onClick={() => goTo(nav.prev)}
                  className="absolute left-2 top-1/2 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/60 text-2xl hover:bg-black/80"
                  aria-label="上一張"
                  title="上一張（←）"
                >
                  ‹
                </button>
              )}
              {nav.next && (
                <button
                  onClick={() => goTo(nav.next)}
                  className="absolute right-2 top-1/2 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/60 text-2xl hover:bg-black/80"
                  aria-label="下一張"
                  title="下一張（→）"
                >
                  ›
                </button>
              )}
              {nav.total > 1 && (
                <span className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-0.5 text-xs tabular-nums">
                  {nav.index} / {nav.total}
                </span>
              )}
            </div>
          ) : playFrom !== null ? (
            <Player key={`${id}-${playFrom}`} video={video} startAt={playFrom} onTime={(t) => (playTime.current = t)} />
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
                <p className="text-sm text-neutral-500">{video.error ? '沒有截圖' : '截圖產生中…'}</p>
              )}
            </>
          )}
          {video.versions?.length > 1 && (
            <section className="rounded-xl bg-neutral-900 p-3 ring-1 ring-white/5">
              <div className="mb-2 flex items-center gap-2">
                <h2 className="text-sm font-medium">版本（{video.versions.length}）</h2>
                <span className="text-xs text-neutral-500">同一部片的不同畫質 / 檔案，切換時從目前時間繼續播放</span>
                <button onClick={splitOut} className="ml-auto rounded-lg bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700" title="這個檔案不是同一部片">
                  從群組移出
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {video.versions.map((v, i) => (
                  <button
                    key={v.id}
                    onClick={() => switchVersion(v.id)}
                    title={`${v.folder ? v.folder + '/' : ''}${v.file}`}
                    className={`rounded-lg px-3 py-1.5 text-left text-sm ring-1 ${
                      v.id === id ? 'bg-accent/25 ring-accent' : 'bg-neutral-800 ring-white/10 hover:bg-neutral-700'
                    }`}
                  >
                    <span className="font-medium">線路 {i + 1}</span>
                    <span className="ml-2 text-neutral-300">
                      {[resolutionLabel(v.width, v.height), fmtBitrate(v.bit_rate), v.video_codec, fmtSize(v.size)].filter(Boolean).join(' · ')}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </section>

        <aside className="space-y-6">
          <form onSubmit={save} className="space-y-3 rounded-xl bg-neutral-900 p-4 ring-1 ring-white/5">
            <h2 className="font-medium">{photo ? '圖片資訊' : '影片資訊'}</h2>
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

          {photo ? (
            <div className="rounded-xl bg-neutral-900 p-4 ring-1 ring-white/5">
              <h2 className="mb-2 font-medium">Photo Info</h2>
              <InfoRow label="長寬">{info.width ? `${info.width} × ${info.height}` : null}</InfoRow>
              <InfoRow label="格式">{info.format}</InfoRow>
              <InfoRow label="Bit depth">{info.bit_depth ? `${info.bit_depth}-bit` : null}</InfoRow>
              <InfoRow label="檔案大小">{fmtSize(info.size || video.size)}</InfoRow>
              <InfoRow label="位置">{`${video.folder ? video.folder + '/' : ''}${video.file}`}</InfoRow>            </div>
          ) : (
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
          )}

          <div className="flex flex-wrap gap-2">
            <a href={fileUrl} download={video.file} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">下載原檔</a>
            <button onClick={regenerate} disabled={video.processing} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-50">
              {video.processing ? '處理中…' : photo ? '重新產生縮圖' : '重新產生截圖'}
            </button>
            <button onClick={remove} className="ml-auto rounded-lg bg-red-900/60 px-3 py-1.5 text-sm text-red-100 hover:bg-red-800">
              {photo ? '刪除圖片' : '刪除影片'}
            </button>
          </div>
        </aside>
      </div>
    </div>
  )
}
