import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import VideoCard from '../components/VideoCard.jsx'

const SORTS = {
  added: { label: '最新加入', fn: (a, b) => (b.added || 0) - (a.added || 0) },
  title: { label: '標題', fn: (a, b) => a.title.localeCompare(b.title, 'zh-Hant') },
  duration: { label: '片長', fn: (a, b) => (b.duration || 0) - (a.duration || 0) },
  size: { label: '檔案大小', fn: (a, b) => (b.size || 0) - (a.size || 0) },
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

export default function Library({ guard, onLogout }) {
  const [videos, setVideos] = useState(null)
  const [tags, setTags] = useState({ actors: [], series: [] })
  const [processing, setProcessing] = useState(0)
  const [busy, setBusy] = useState(false)
  const [params, setParams] = useSearchParams() // filters live in the URL so "back" keeps them

  const q = params.get('q') || ''
  const actor = params.get('actor') || ''
  const series = params.get('series') || ''
  const folder = params.get('folder') || ''
  const sort = params.get('sort') || 'added'

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  async function load() {
    try {
      const [v, t] = await Promise.all([api.videos(), api.tags()])
      setVideos(v.videos)
      setProcessing(v.processing)
      setTags(t)
    } catch (e) {
      guard(e)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // while screenshots / info are being generated, refresh so new covers appear
  useEffect(() => {
    if (!processing) return
    const timer = setTimeout(load, 4000)
    return () => clearTimeout(timer)
  }, [processing, videos])

  async function rescan() {
    setBusy(true)
    try {
      await api.rescan()
      await load()
    } catch (e) {
      guard(e)
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    await api.logout().catch(() => {})
    onLogout()
  }

  const folders = useMemo(
    () => [...new Set((videos || []).map((v) => v.folder))].sort((a, b) => a.localeCompare(b, 'zh-Hant')),
    [videos],
  )

  const shown = useMemo(() => {
    if (!videos) return []
    const needle = q.trim().toLowerCase()
    return videos
      .filter((v) => !actor || v.actors.includes(actor))
      .filter((v) => !series || v.series === series)
      .filter((v) => !folder || v.folder === folder || v.folder.startsWith(folder + '/'))
      .filter(
        (v) =>
          !needle ||
          [v.title, v.file, v.folder, v.series, ...v.actors].some((s) => (s || '').toLowerCase().includes(needle)),
      )
      .sort(SORTS[sort]?.fn || SORTS.added.fn)
  }, [videos, q, actor, series, folder, sort])

  const filtered = q || actor || series || folder

  return (
    <div className="mx-auto max-w-[1600px] px-4 pb-16">
      <header className="sticky top-0 z-10 -mx-4 mb-4 space-y-3 bg-neutral-950/90 px-4 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">影片庫</h1>
          <span className="text-sm text-neutral-400">
            {videos ? `${shown.length}${filtered ? ` / ${videos.length}` : ''} 部` : ''}
          </span>
          {processing > 0 && (
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300">產生資訊/截圖中：{processing}</span>
          )}
          <div className="ml-auto flex gap-2">
            <button onClick={rescan} disabled={busy} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-50">
              {busy ? '掃描中…' : '重新掃描'}
            </button>
            <button onClick={logout} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">
              登出
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={q}
            onChange={(e) => setParam('q', e.target.value)}
            placeholder="搜尋標題、主演、系列、資料夾…"
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
          <Select label="資料夾" value={folder} onChange={(v) => setParam('folder', v)}>
            <option value="">全部</option>
            {folders.map((f) => (
              <option key={f} value={f}>{f || '/'}</option>
            ))}
          </Select>
          <Select label="排序" value={sort} onChange={(v) => setParam('sort', v === 'added' ? '' : v)}>
            {Object.entries(SORTS).map(([k, s]) => (
              <option key={k} value={k}>{s.label}</option>
            ))}
          </Select>
          {filtered && (
            <button onClick={() => setParams({}, { replace: true })} className="text-sm text-neutral-400 hover:text-white">
              清除篩選
            </button>
          )}
        </div>
      </header>

      {videos === null ? (
        <p className="text-neutral-400">載入中…</p>
      ) : shown.length === 0 ? (
        <p className="py-16 text-center text-neutral-500">{videos.length ? '沒有符合的影片' : '下載資料夾中還沒有影片'}</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
          {shown.map((v) => (
            <VideoCard key={v.id} video={v} search={params.toString()} />
          ))}
        </div>
      )}
    </div>
  )
}
