import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import AppMenu from '../components/AppMenu.jsx'

// 人物: the people database behind the 主演 tags (library/people.py). New videos / photos are recognised
// by themselves and get the 主演 tag of every matching person; unknown faces collect as 未命名人物.
// Naming / renaming / merging / deleting a person here changes the 主演 tags on its items.

function useToast() {
  const [toast, setToast] = useState(null)
  const timer = useRef(null)
  const notify = (text, error = false) => {
    setToast({ text, error })
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setToast(null), error ? 6000 : 3500)
  }
  const view = toast && (
    <div
      className={`fixed bottom-4 left-1/2 z-50 max-w-[90vw] -translate-x-1/2 whitespace-pre-line rounded-lg px-4 py-2 text-sm shadow-xl ${
        toast.error ? 'bg-red-900 text-red-100' : 'bg-neutral-800 text-neutral-100'
      }`}
    >
      {toast.text}
    </div>
  )
  return [notify, view]
}

function guarded(guard, notify) {
  return async (fn) => {
    try {
      return await fn()
    } catch (e) {
      try {
        guard(e)
      } catch (err) {
        notify(err.message, true)
      }
    }
  }
}

function Face({ src, className = '' }) {
  return src ? (
    <img src={src} alt="" loading="lazy" className={`bg-neutral-800 object-cover ${className}`} />
  ) : (
    <div className={`flex items-center justify-center bg-neutral-800 text-2xl text-neutral-600 ${className}`}>👤</div>
  )
}

function Header({ title, children, onLogout }) {
  return (
    <header className="sticky top-0 z-10 -mx-4 mb-4 space-y-2 bg-neutral-950/90 px-4 py-3 backdrop-blur">
      <div className="flex items-center gap-3">
        {title}
        <div className="ml-auto">
          <AppMenu onLogout={onLogout} />
        </div>
      </div>
      {children}
    </header>
  )
}

function StatusLine({ data }) {
  const s = data.status || {}
  const busy = s.phase === 'sync' ? '建立人物資料庫' : s.phase === 'scan' ? '辨識中' : null
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-400">
      {busy ? (
        <span className="text-sky-300">
          {busy}
          {s.total > 0 && ` ${s.done} / ${s.total}`}…
        </span>
      ) : (
        <span>新加入的影片 / 圖片會自動辨識並加上主演</span>
      )}
      {s.error && <span className="text-red-300">錯誤：{s.error}</span>}
    </div>
  )
}

// ── list ──

export default function People({ guard, onLogout }) {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'unnamed' ? 'unnamed' : 'named'
  const q = params.get('q') || ''
  const [singles, setSingles] = useState(false)
  const [data, setData] = useState(null)
  const [notify, toastView] = useToast()
  const run = guarded(guard, notify)

  async function load() {
    const d = await run(() => api.people())
    if (d) setData(d)
  }

  useEffect(() => {
    load()
  }, [])

  const busy = data && (data.status?.phase !== 'idle' || data.scan_all)
  useEffect(() => {
    const timer = setInterval(load, busy ? 2500 : 15000)
    return () => clearInterval(timer)
  }, [busy])

  function setParam(key, value) {
    const next = new URLSearchParams(params)
    value ? next.set(key, value) : next.delete(key)
    setParams(next, { replace: true })
  }

  async function scan(on) {
    if (on && !window.confirm(`辨識媒體庫裡 ${data.unscanned} 個還沒掃描的項目？\n比對到的人物會自動加上主演；項目多的話會花比較久（在背景執行，可以隨時停止）。`)) return
    if (await run(() => api.peopleScan(on))) load()
  }

  const people = data?.people || []
  const named = people.filter((p) => p.name)
  const unnamed = people.filter((p) => !p.name)
  const hiddenSingles = unnamed.filter((p) => p.count < 2).length
  let shown = tab === 'named' ? named : unnamed.filter((p) => singles || p.count >= 2)
  if (q) shown = shown.filter((p) => p.label.toLowerCase().includes(q.toLowerCase()))
  shown = [...shown].sort((a, b) => (tab === 'named' ? a.label.localeCompare(b.label, 'zh-Hant') : b.count - a.count || a.num - b.num))

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-16">
      <Header
        onLogout={onLogout}
        title={
          <>
            <h1 className="text-lg font-semibold">人物</h1>
            {data && <span className="text-sm text-neutral-400">{named.length} 位已命名</span>}
          </>
        }
      >
        {data && (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex overflow-hidden rounded-lg ring-1 ring-white/10" role="group">
                {[
                  ['named', '已命名', named.length],
                  ['unnamed', '未命名', unnamed.length],
                ].map(([key, label, n]) => (
                  <button
                    key={key}
                    onClick={() => setParam('tab', key === 'named' ? '' : key)}
                    aria-pressed={tab === key}
                    className={`px-3 py-1.5 text-sm ${tab === key ? 'bg-accent/80 text-white' : 'bg-neutral-800 hover:bg-neutral-700'}`}
                  >
                    {label}
                    <span className="ml-1 text-xs opacity-70 tabular-nums">{n}</span>
                  </button>
                ))}
              </div>
              <input
                value={q}
                onChange={(e) => setParam('q', e.target.value)}
                placeholder="搜尋人物…"
                className="min-w-40 flex-1 rounded-lg bg-neutral-800 px-3 py-1.5 text-sm outline-none ring-1 ring-white/10 focus:ring-accent"
              />
              {data.scan_all ? (
                <button onClick={() => scan(false)} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">
                  ⏹ 停止掃描
                </button>
              ) : (
                <button
                  onClick={() => scan(true)}
                  disabled={!data.unscanned}
                  className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-40"
                  title="辨識還沒掃描過的舊項目（新項目會自動辨識）"
                >
                  🔍 掃描全部未掃描的項目（{data.unscanned}）
                </button>
              )}
            </div>
            <StatusLine data={data} />
          </>
        )}
      </Header>

      {data === null ? (
        <p className="text-neutral-400">載入中…</p>
      ) : shown.length === 0 ? (
        <div className="py-16 text-center text-sm text-neutral-500">
          {tab === 'named'
            ? q
              ? '沒有符合的人物'
              : '還沒有人物：在影片或圖片標上主演，或為「未命名」裡的人取名字'
            : hiddenSingles && !singles
              ? `只有出現一次的未命名人物（${hiddenSingles}）`
              : '沒有未命名的人物'}
        </div>
      ) : (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(130px,1fr))] gap-3">
          {shown.map((p) => (
            <li key={p.id}>
              <Link to={`/people/${p.id}`} className="block rounded-xl bg-neutral-900 p-2 ring-1 ring-white/10 hover:ring-accent/60">
                <Face src={p.cover} className="aspect-square w-full rounded-lg" />
                <p className="mt-2 truncate text-sm font-medium" title={p.label}>
                  {p.label}
                </p>
                <p className="text-xs text-neutral-500">
                  {p.count} 個項目{p.auto > 0 && ` · ${p.auto} 自動`}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {tab === 'unnamed' && hiddenSingles > 0 && (
        <label className="mt-4 flex items-center gap-2 text-sm text-neutral-400">
          <input type="checkbox" checked={singles} onChange={(e) => setSingles(e.target.checked)} className="accent-accent" />
          顯示只出現一次的（{hiddenSingles}）
        </label>
      )}
      {toastView}
    </div>
  )
}

// ── one person ──

export function PersonPage({ guard, onLogout }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const [person, setPerson] = useState(null)
  const [others, setOthers] = useState([])
  const [name, setName] = useState('')
  const [picked, setPicked] = useState(() => new Set())
  const [mergeTo, setMergeTo] = useState('')
  const [busy, setBusy] = useState(false)
  const [notify, toastView] = useToast()
  const run = guarded(guard, notify)

  async function load(pid = id) {
    const [p, list] = await Promise.all([run(() => api.person(pid)), run(() => api.people())])
    if (p) {
      setPerson(p)
      setName(p.name)
      setPicked(new Set())
    } else setPerson(false)
    if (list) setOthers(list.people.filter((x) => x.id !== pid))
  }

  useEffect(() => {
    setPerson(null)
    load()
  }, [id])

  async function act(fn, done) {
    setBusy(true)
    const result = await run(fn)
    setBusy(false)
    if (result) done(result)
  }

  const existing = others.find((o) => o.name && o.name.toLowerCase() === name.trim().toLowerCase())

  function rename() {
    const n = name.trim()
    if (!n || n === person.name) return
    if (existing && !window.confirm(`已經有「${existing.name}」，要把這個人合併過去嗎？\n兩邊的項目都會標上主演「${existing.name}」。`)) return
    act(
      () => api.renamePerson(person.id, n),
      (r) => {
        notify(person.name ? `已改名為「${n}」，項目的主演也一起改了` : `已命名為「${n}」，${person.items.length} 個項目加上主演`)
        if (r.id !== person.id) navigate(`/people/${r.id}`, { replace: true })
        else load()
      },
    )
  }

  function merge() {
    const target = others.find((o) => o.id === mergeTo)
    if (!target) return
    if (!window.confirm(`把「${person.label}」合併到「${target.label}」？\n${target.name || person.name ? `項目的主演會變成「${target.name || person.name}」。` : ''}`)) return
    act(
      () => api.mergePerson(person.id, target.id),
      (r) => {
        notify('已合併')
        navigate(`/people/${r.id}`, { replace: true })
      },
    )
  }

  function remove() {
    const text = person.name
      ? `刪除人物「${person.name}」？\n會從 ${person.items.length} 個項目移除主演「${person.name}」，臉部資料也會刪除。`
      : `刪除「${person.label}」的臉部資料？（項目本身不受影響）`
    if (!window.confirm(text)) return
    act(
      () => api.deletePerson(person.id),
      () => navigate(person.name ? '/people' : '/people?tab=unnamed', { replace: true }),
    )
  }

  function notThis() {
    const ids = [...picked]
    if (!ids.length) return
    act(
      () => api.removeFromPerson(person.id, ids),
      (r) => {
        notify(`已從「${person.label}」移除 ${r.removed} 個項目${person.name ? '（主演標籤也移除了，之後不會再自動加上）' : ''}`)
        load()
      },
    )
  }

  const toggle = (vid) =>
    setPicked((s) => {
      const next = new Set(s)
      next.has(vid) ? next.delete(vid) : next.add(vid)
      return next
    })

  if (person === false)
    return (
      <div className="mx-auto max-w-[1400px] px-4 py-16 text-center text-neutral-400">
        找不到這個人物（可能已經合併或刪除）。<Link to="/people" className="text-accent hover:underline">回到人物</Link>
      </div>
    )

  const cover = person?.items.find((i) => i.face)?.face
  const mergeOptions = [...others].sort((a, b) => (!!b.name - !!a.name) || a.label.localeCompare(b.label, 'zh-Hant'))

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-24">
      <Header
        onLogout={onLogout}
        title={
          <>
            <Link to={person && !person.name ? '/people?tab=unnamed' : '/people'} className="text-sm text-neutral-400 hover:text-white">
              ← 人物
            </Link>
            <h1 className="min-w-0 truncate text-lg font-semibold">{person ? person.label : '載入中…'}</h1>
          </>
        }
      />
      {person && (
        <>
          <section className="mb-6 flex flex-wrap gap-4 rounded-xl bg-neutral-900 p-4 ring-1 ring-white/10">
            <Face src={cover} className="h-28 w-28 shrink-0 rounded-xl" />
            <div className="min-w-0 flex-1 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && rename()}
                  list="people-names"
                  placeholder={person.name ? '名字' : '輸入名字來命名'}
                  className="min-w-0 flex-1 rounded-lg bg-neutral-800 px-3 py-1.5 text-sm outline-none ring-1 ring-white/10 focus:ring-accent"
                />
                <datalist id="people-names">
                  {others.filter((o) => o.name).map((o) => (
                    <option key={o.id} value={o.name} />
                  ))}
                </datalist>
                <button
                  onClick={rename}
                  disabled={busy || !name.trim() || name.trim() === person.name}
                  className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-40"
                >
                  {existing ? '合併' : person.name ? '改名' : '命名'}
                </button>
              </div>
              <p className="text-xs text-neutral-500">
                {existing
                  ? `「${existing.name}」已經存在，會合併成同一個人。`
                  : person.name
                    ? '改名會同時修改所有項目的主演標籤。'
                    : '命名後，這些項目會加上主演，之後出現這張臉的新項目也會自動加上。'}
              </p>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {person.name && (
                  <button
                    onClick={() => navigate(`/?actor=${encodeURIComponent(person.name)}&kind=all`)}
                    className="rounded-lg bg-neutral-800 px-3 py-1.5 hover:bg-neutral-700"
                  >
                    🎬 在媒體庫查看
                  </button>
                )}
                <select
                  value={mergeTo}
                  onChange={(e) => setMergeTo(e.target.value)}
                  className="max-w-56 rounded-lg bg-neutral-800 px-2 py-1.5 outline-none ring-1 ring-white/10"
                  aria-label="合併到"
                >
                  <option value="">合併到…</option>
                  {mergeOptions.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.label}（{o.count}）
                    </option>
                  ))}
                </select>
                <button onClick={merge} disabled={busy || !mergeTo} className="rounded-lg bg-neutral-800 px-3 py-1.5 hover:bg-neutral-700 disabled:opacity-40">
                  合併
                </button>
                <button onClick={remove} disabled={busy} className="rounded-lg bg-red-900/70 px-3 py-1.5 text-red-100 hover:bg-red-800 disabled:opacity-40">
                  🗑 刪除人物
                </button>
              </div>
            </div>
          </section>

          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h2 className="font-medium">
              項目 <span className="text-sm font-normal text-neutral-500">{person.items.length}</span>
            </h2>
            <span className="text-xs text-neutral-500">點選認錯的項目，再按「不是這個人」</span>
            {picked.size > 0 && (
              <div className="ml-auto flex gap-2">
                <button onClick={() => setPicked(new Set())} className="rounded-lg bg-neutral-800 px-3 py-1 text-sm hover:bg-neutral-700">
                  清除選取
                </button>
                <button onClick={notThis} disabled={busy} className="rounded-lg bg-red-900/70 px-3 py-1 text-sm text-red-100 hover:bg-red-800 disabled:opacity-40">
                  不是這個人（{picked.size}）
                </button>
              </div>
            )}
          </div>
          {person.items.length === 0 ? (
            <p className="text-sm text-neutral-500">沒有項目</p>
          ) : (
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
              {person.items.map((item) => {
                const on = picked.has(item.id)
                return (
                  <li key={item.id} className={`overflow-hidden rounded-xl bg-neutral-900 ring-2 ${on ? 'ring-red-500' : 'ring-transparent'}`}>
                    <button type="button" onClick={() => toggle(item.id)} className="relative block w-full" aria-pressed={on} title="選取（不是這個人）">
                      <Face src={item.cover} className="aspect-video w-full" />
                      {item.face && <img src={item.face} alt="" className="absolute bottom-1 right-1 h-12 w-12 rounded-lg object-cover ring-2 ring-neutral-900" />}
                      {item.auto && <span className="absolute left-1 top-1 rounded bg-sky-600/90 px-1.5 py-0.5 text-[11px] text-white">自動</span>}
                      <span
                        className={`absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full text-xs ${
                          on ? 'bg-red-500 text-white' : 'bg-black/60 text-transparent ring-1 ring-white/50'
                        }`}
                      >
                        ✕
                      </span>
                    </button>
                    <button
                      onClick={() => navigate(`/v/${item.id}`, { state: { backPath: `/people/${person.id}` } })}
                      className="block w-full truncate px-2 py-1.5 text-left text-xs text-neutral-300 hover:text-accent"
                      title={`${item.folder ? `/${item.folder}/` : ''}${item.name}`}
                    >
                      {item.name}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
      {toastView}
    </div>
  )
}
