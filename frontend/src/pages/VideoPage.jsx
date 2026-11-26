import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, fmtBitrate, fmtDuration, fmtSize, listNeighbors, MEDIA, resolutionLabel } from '../api.js'
import Player from '../components/Player.jsx'
import AppMenu from '../components/AppMenu.jsx'
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

// Photos: the details and the image files of the 2 photos on each side are loaded ahead, so
// switching (buttons, ←/→, swipe) shows the next photo at once instead of a loading screen.
const detailCache = new Map() // id -> detail JSON
const preloaded = new Map() // id -> Image (kept so the browser doesn't drop the request)
const CACHE_LIMIT = 40

function remember(map, key, value) {
  map.delete(key)
  map.set(key, value)
  while (map.size > CACHE_LIMIT) map.delete(map.keys().next().value)
}

const formOf = (v) => ({ _id: v.id, title: v.title, actors: v.actors, series: v.series, source: v.source, description: v.description || '' })
const SWIPE_MIN = 60 // px a finger must travel to switch photo

export default function VideoPage({ guard, onLogout }) {
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
  const currentId = useRef(id) // ignore answers for a photo the user already swiped past
  const swipe = useRef(null) // touch in progress: { x, y, dx, dir }
  const [dragX, setDragX] = useState(0)
  const stage = useRef(null) // what goes fullscreen; stays while swiping to the next video
  // videos: previous / next in the library's order (only when opened from the library)
  const vnav = useMemo(
    () => (video && video.kind !== 'photo' ? listNeighbors(video, location.state?.back) : {}),
    [video?.id, location.state?.back],
  )

  // opened from a scrolled list: start at the top (block body: newer browsers return a Promise from
  // scrollTo, which React would take for the cleanup function)
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  async function load() {
    try {
      const v = await api.video(id)
      if (currentId.current !== id) return
      remember(detailCache, id, v)
      setVideo(v)
      // keep unsaved edits while polling the same file
      setForm((f) => (f && f._id === v.id ? f : formOf(v)))
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
    currentId.current = id
    const cached = detailCache.get(id)
    setVideo(cached || null)
    setForm(cached ? formOf(cached) : null)
    setDragX(0)
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

  // photos: load the neighbors' details and image files ahead
  useEffect(() => {
    if (video?.kind !== 'photo') return
    for (const nid of video.neighbors?.preload || []) {
      if (!preloaded.has(nid)) {
        const img = new Image()
        img.src = `${MEDIA}/${nid}/file`
        remember(preloaded, nid, img)
      }
      if (!detailCache.has(nid)) {
        api.video(nid).then((d) => remember(detailCache, nid, d)).catch(() => {})
      }
    }
  }, [video])

  // videos: load the neighbors' details and first screenshots ahead (shown while swiping)
  useEffect(() => {
    for (const nid of [vnav.next, vnav.prev].filter(Boolean)) {
      const cached = detailCache.get(nid)
      const shot = (d) => {
        const url = d?.shots?.[0]
        if (url && !preloaded.has(url)) {
          const img = new Image()
          img.src = url
          remember(preloaded, url, img)
        }
      }
      if (cached) shot(cached)
      else api.video(nid).then((d) => (remember(detailCache, nid, d), shot(d))).catch(() => {})
    }
  }, [vnav.prev, vnav.next])

  // videos: swiped on the player -> the next one plays from the start (fullscreen stays on); swiped / ‹ › /
  // ← → on the screenshots before playing -> the next one's screenshots (play = false)
  async function swipeTo(dir, play = true) {
    const nid = vnav[dir]
    if (!nid) return
    if (!detailCache.has(nid)) {
      try {
        remember(detailCache, nid, await api.video(nid))
      } catch {}
    }
    navigate(`/v/${nid}`, { replace: true, state: { back: location.state?.back, resume: play ? 0 : null } })
  }

  // videos before playing: ← / → switch video (while playing they seek)
  useEffect(() => {
    if (!video || video.kind === 'photo' || playFrom !== null || !(vnav.prev || vnav.next)) return
    function onKey(e) {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.altKey || e.ctrlKey || e.metaKey) return
      const dir = e.key === 'ArrowLeft' ? 'prev' : e.key === 'ArrowRight' ? 'next' : null
      if (dir && vnav[dir]) {
        e.preventDefault()
        swipeTo(dir, false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [video?.id, playFrom, vnav.prev, vnav.next])

  // touch screens: drag sideways to switch (the picture follows the finger): photos, and videos before
  // they play (the player has its own swipe)
  const swipeNav = () => (video?.kind === 'photo' ? video.neighbors || {} : vnav)
  const swipedAt = useRef(0) // a swipe must not also count as a tap on the picture (= play)

  function onTouchStart(e) {
    swipe.current = e.touches.length === 1 ? { x: e.touches[0].clientX, y: e.touches[0].clientY, dx: 0, dir: null } : null
    if (!swipe.current) setDragX(0) // second finger: pinch zoom, not a swipe
  }

  function onTouchMove(e) {
    const s = swipe.current
    if (!s || e.touches.length !== 1) return
    const dx = e.touches[0].clientX - s.x
    const dy = e.touches[0].clientY - s.y
    if (!s.dir && Math.max(Math.abs(dx), Math.abs(dy)) > 8) s.dir = Math.abs(dx) > Math.abs(dy) ? 'h' : 'v'
    if (s.dir !== 'h') return
    s.dx = dx
    const nav = swipeNav()
    const edge = (dx > 0 && !nav.prev) || (dx < 0 && !nav.next)
    setDragX(edge ? dx / 4 : dx) // resist at the first / last item
  }

  function onTouchEnd() {
    const s = swipe.current
    swipe.current = null
    const nav = swipeNav()
    const dir = s?.dir !== 'h' ? null : s.dx <= -SWIPE_MIN ? 'next' : s.dx >= SWIPE_MIN ? 'prev' : null
    if (s?.dir === 'h') swipedAt.current = Date.now()
    if (!dir || !nav[dir]) setDragX(0)
    else if (video?.kind === 'photo') goTo(nav[dir])
    else swipeTo(dir, false)
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
      remember(detailCache, id, v)
      setVideo(v)
      setForm(formOf(v))
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
      setForm(formOf(v))
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
      detailCache.clear() // neighbors of the other photos changed
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
    form.description !== (video.description || '') ||
    form.actors.join('\n') !== video.actors.join('\n')

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-16">
      <div className="flex items-center gap-3 py-3">
        <Link to={backTo} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">← 返回</Link>
        <h1 className="min-w-0 truncate text-lg font-semibold" title={video.title}>{video.title}</h1>
        <div className="ml-auto">
          <AppMenu onLogout={onLogout} />
        </div>
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
            <div
              className="relative flex min-h-[40vh] select-none items-center justify-center overflow-hidden rounded-xl bg-black"
              style={{ touchAction: 'pan-y pinch-zoom' }}
              onTouchStart={onTouchStart}
              onTouchMove={onTouchMove}
              onTouchEnd={onTouchEnd}
              onTouchCancel={onTouchEnd}
            >
              <a
                href={fileUrl}
                target="_blank"
                rel="noreferrer"
                title="開啟原圖"
                draggable={false}
                style={{ transform: `translateX(${dragX}px)` }}
                className={swipe.current ? '' : 'transition-transform duration-200'}
              >
                <img key={video.id} src={fileUrl} alt={video.title} draggable={false} className="max-h-[80vh] w-auto max-w-full object-contain" />
              </a>
              {nav.prev && (
                <button
                  onClick={() => goTo(nav.prev)}
                  className="absolute left-2 top-1/2 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/60 text-2xl hover:bg-black/80 pointer-coarse:hidden"
                  aria-label="上一張"
                  title="上一張（←）"
                >
                  ‹
                </button>
              )}
              {nav.next && (
                <button
                  onClick={() => goTo(nav.next)}
                  className="absolute right-2 top-1/2 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/60 text-2xl hover:bg-black/80 pointer-coarse:hidden"
                  aria-label="下一張"
                  title="下一張（→）"
                >
                  ›
                </button>
              )}
              {nav.total > 1 && (
                <span className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-0.5 text-xs tabular-nums">
                  {nav.index} / {nav.total}
                  <span className="hidden pointer-coarse:inline"> · 左右滑動切換</span>
                </span>
              )}
            </div>
          ) : playFrom !== null ? (
            <div ref={stage}>
              {/* keyed by the shown video: right after a swipe the old one is still shown for a moment */}
              <Player
                key={`${video.id}-${playFrom}`}
                video={video}
                startAt={playFrom}
                onTime={(t) => (playTime.current = t)}
                container={stage}
                nav={vnav}
                onSwipe={swipeTo}
                posterOf={(dir) => detailCache.get(vnav[dir])?.shots?.[0]}
              />
            </div>
          ) : (
            <>
              {/* before playing: swipe (touch), ‹ › or ← → switch video; the neighbor's cover slides in */}
              <div
                className="relative select-none overflow-hidden rounded-xl bg-neutral-900"
                style={vnav.prev || vnav.next ? { touchAction: 'pan-y pinch-zoom' } : undefined}
                onTouchStart={vnav.prev || vnav.next ? onTouchStart : undefined}
                onTouchMove={vnav.prev || vnav.next ? onTouchMove : undefined}
                onTouchEnd={vnav.prev || vnav.next ? onTouchEnd : undefined}
                onTouchCancel={vnav.prev || vnav.next ? onTouchEnd : undefined}
              >
                <div
                  style={{ transform: dragX ? `translateX(${dragX}px)` : undefined }}
                  className={`relative ${swipe.current ? '' : 'transition-transform duration-200'}`}
                >
                  {['prev', 'next'].map((dir) => {
                    const url = dragX !== 0 && vnav[dir] ? detailCache.get(vnav[dir])?.shots?.[0] : null
                    return (
                      <div key={dir} className={`absolute inset-y-0 w-full bg-neutral-900 ${dir === 'prev' ? 'right-full' : 'left-full'}`}>
                        {url && <img src={url} alt="" draggable={false} className="h-full w-full object-cover opacity-80" />}
                      </div>
                    )
                  })}
                  <button
                    onClick={() => Date.now() - swipedAt.current > 400 && setPlayFrom(0)}
                    className="group relative block aspect-video w-full"
                  >
                    {video.shots[0] && (
                      <img key={video.id} src={video.shots[0]} alt="" draggable={false} className="h-full w-full object-cover opacity-80 transition group-hover:opacity-100" />
                    )}
                    <span className="absolute inset-0 flex items-center justify-center">
                      <span className="flex h-20 w-20 items-center justify-center rounded-full bg-accent/90 text-3xl shadow-lg transition group-hover:scale-110">▶</span>
                    </span>
                  </button>
                </div>
                {vnav.prev && (
                  <button
                    onClick={() => swipeTo('prev', false)}
                    className="absolute left-2 top-1/2 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/60 text-2xl hover:bg-black/80 pointer-coarse:hidden"
                    aria-label="上一部"
                    title="上一部（←）"
                  >
                    ‹
                  </button>
                )}
                {vnav.next && (
                  <button
                    onClick={() => swipeTo('next', false)}
                    className="absolute right-2 top-1/2 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/60 text-2xl hover:bg-black/80 pointer-coarse:hidden"
                    aria-label="下一部"
                    title="下一部（→）"
                  >
                    ›
                  </button>
                )}
                {vnav.total > 1 && (
                  <span className="pointer-events-none absolute right-2 top-2 rounded bg-black/70 px-2 py-0.5 text-xs tabular-nums">
                    {vnav.index} / {vnav.total}
                    <span className="hidden pointer-coarse:inline"> · 左右滑動切換</span>
                  </span>
                )}
              </div>
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
            <label className="block space-y-1">
              <span className="text-xs text-neutral-400">描述（Telegram 下載時為原始訊息的文字）</span>
              <textarea
                className={`${field} min-h-24 resize-y leading-relaxed`}
                rows={Math.min(12, Math.max(3, (form.description.match(/\n/g) || []).length + 2))}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="沒有描述"
              />
            </label>
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
            <InfoRow label="播放方式">{video.direct ? '原始檔或即時轉檔（播放器右下選畫質）' : '即時轉檔（播放器右下選畫質）'}</InfoRow>
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
