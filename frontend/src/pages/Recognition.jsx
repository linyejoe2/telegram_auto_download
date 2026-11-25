import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import AppMenu from '../components/AppMenu.jsx'

// AI 辨識: the queue of 辨識主演 / 辨識系列 jobs (started from the library's select bar) and their
// results. Nothing changes in the library until a result is applied here (套用); 略過 just hides it.
// Jobs run one at a time on the server (library/recognize.py) and keep running with this page closed.

const STATUS = {
  queued: ['排隊中', 'bg-neutral-700 text-neutral-200'],
  running: ['執行中', 'bg-sky-500/20 text-sky-300'],
  done: ['完成', 'bg-emerald-500/15 text-emerald-300'],
  failed: ['失敗', 'bg-red-500/15 text-red-300'],
  cancelled: ['已取消', 'bg-neutral-800 text-neutral-400'],
}
const ICON = { actor: '👤', series: '👗' }
const active = (j) => j.status === 'queued' || j.status === 'running'
const when = (t) =>
  t ? new Date(t * 1000).toLocaleString('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : ''

function useGuarded(guard, notify) {
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

export default function Recognition({ guard, onLogout }) {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState(null)
  const [status, setStatus] = useState(null)
  const [open, setOpen] = useState(() => new Set())
  const [details, setDetails] = useState({}) // job id -> full job (with result)
  const [tags, setTags] = useState({ actors: [], series: [] })
  const [toast, setToast] = useState(null)
  const toastTimer = useRef(null)
  const autoOpened = useRef(false)

  function notify(text, error = false) {
    setToast({ text, error })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(null), error ? 6000 : 3500)
  }
  const run = useGuarded(guard, notify)

  async function loadJobs() {
    const data = await run(() => api.recognitionJobs())
    if (data) setJobs(data.jobs)
    return data?.jobs
  }

  async function loadDetail(id) {
    const job = await run(() => api.recognitionJob(id))
    if (job) setDetails((d) => ({ ...d, [id]: job }))
  }

  useEffect(() => {
    loadJobs().then((list) => {
      // open the newest finished job that still has results to confirm
      const first = list?.find((j) => j.status === 'done' && j.pending)
      if (first && !autoOpened.current) {
        autoOpened.current = true
        setOpen(new Set([first.id]))
        loadDetail(first.id)
      }
    })
    run(() => api.recognitionStatus()).then((s) => s && setStatus(s))
    api.tags().then(setTags).catch(() => {})
  }, [])

  // poll while something is queued / running; load a job's result when it finishes
  const busy = jobs?.some(active)
  useEffect(() => {
    if (!busy) return
    const timer = setInterval(async () => {
      const before = jobs
      const list = await loadJobs()
      for (const j of list || []) {
        const old = before?.find((b) => b.id === j.id)
        if (old && active(old) && j.status === 'done' && open.has(j.id)) loadDetail(j.id)
      }
    }, 2000)
    return () => clearInterval(timer)
  }, [busy, jobs, open])

  function toggle(job) {
    setOpen((s) => {
      const next = new Set(s)
      if (next.has(job.id)) next.delete(job.id)
      else {
        next.add(job.id)
        if (job.status === 'done') loadDetail(job.id)
      }
      return next
    })
  }

  async function cancel(job) {
    if (await run(() => api.cancelRecognition(job.id))) loadJobs()
  }

  async function remove(job) {
    if (job.pending && !window.confirm(`這個工作還有 ${job.pending} 個結果沒有確認，確定要刪除？`)) return
    if (await run(() => api.removeRecognition(job.id))) {
      setDetails(({ [job.id]: _, ...rest }) => rest)
      loadJobs()
    }
  }

  // entries: [{ key, action, name?, items? }]
  async function apply(jobId, entries) {
    const result = await run(() => api.applyRecognition(jobId, entries))
    if (!result) return false
    setDetails((d) => ({ ...d, [jobId]: result.job }))
    loadJobs()
    const applied = entries.some((e) => e.action === 'apply')
    if (applied) {
      notify(`已更新 ${result.updated} 個項目${result.missing ? `（${result.missing} 個已不在媒體庫）` : ''}`)
      api.tags().then(setTags).catch(() => {})
    }
    return true
  }

  const openItem = (id) => navigate(`/v/${id}`, { state: { backPath: '/recognition' } })

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-16">
      <header className="sticky top-0 z-10 -mx-4 mb-4 bg-neutral-950/90 px-4 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">AI 辨識</h1>
          {jobs && <span className="text-sm text-neutral-400">{jobs.length} 個工作</span>}
          <div className="ml-auto">
            <AppMenu onLogout={onLogout} />
          </div>
        </div>
        <StatusLine status={status} />
      </header>

      {jobs === null ? (
        <p className="text-neutral-400">載入中…</p>
      ) : jobs.length === 0 ? (
        <div className="py-16 text-center text-neutral-500">
          <p>還沒有辨識工作</p>
          <p className="mt-2 text-sm">在媒體庫按 ☑ 選取，選好影片或圖片後按 👤 辨識主演 或 👗 辨識系列。</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {jobs.map((job) => (
            <li key={job.id} className="rounded-xl bg-neutral-900 ring-1 ring-white/10">
              <JobHeader job={job} open={open.has(job.id)} onToggle={() => toggle(job)} onCancel={() => cancel(job)} onRemove={() => remove(job)} />
              {open.has(job.id) && (
                <div className="border-t border-white/10 p-3 sm:p-4">
                  {job.status === 'failed' ? (
                    <p className="text-sm text-red-300">辨識失敗：{job.error}</p>
                  ) : job.status === 'done' ? (
                    details[job.id]?.result ? (
                      job.kind === 'actor' ? (
                        <ActorResult job={details[job.id]} tags={tags} onApply={apply} onOpen={openItem} />
                      ) : (
                        <SeriesResult job={details[job.id]} tags={tags} onApply={apply} onOpen={openItem} />
                      )
                    ) : (
                      <p className="text-sm text-neutral-400">載入結果中…</p>
                    )
                  ) : active(job) ? (
                    <p className="text-sm text-neutral-400">完成後會在這裡顯示結果，可以先離開這個頁面。</p>
                  ) : (
                    <p className="text-sm text-neutral-400">已取消</p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {toast && (
        <div
          className={`fixed bottom-4 left-1/2 z-50 max-w-[90vw] -translate-x-1/2 whitespace-pre-line rounded-lg px-4 py-2 text-sm shadow-xl ${
            toast.error ? 'bg-red-900 text-red-100' : 'bg-neutral-800 text-neutral-100'
          }`}
        >
          {toast.text}
        </div>
      )}
    </div>
  )
}

function StatusLine({ status }) {
  if (!status) return null
  const o = status.ollama || {}
  return (
    <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
      <span>人臉模型：{status.face_models ? '✓ 已安裝' : '第一次辨識時自動下載（約 38 MB）'}</span>
      <span className={o.ok ? '' : 'text-amber-300'}>
        Ollama（辨識系列用）：{o.ok ? `✓ ${o.model}` : `✗ ${o.error || '無法連線'}`}
        {!o.ok && '　→ 到 Windows 程式的 Web Library 分頁設定'}
      </span>
    </p>
  )
}

function JobHeader({ job, open, onToggle, onCancel, onRemove }) {
  const [label, color] = STATUS[job.status] || [job.status, 'bg-neutral-800']
  const p = job.progress
  const pct = p && p.total ? Math.round((p.done / p.total) * 100) : null
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3 sm:px-4">
      <button onClick={onToggle} className="flex min-w-[min(16rem,100%)] flex-1 items-center gap-3 text-left" aria-expanded={open}>
        <span className="text-xl" aria-hidden>
          {ICON[job.kind]}
        </span>
        <span className="min-w-0">
          <span className="block font-medium">
            {job.title}
            <span className="ml-2 whitespace-nowrap text-sm font-normal text-neutral-400">{job.count} 個項目</span>
          </span>
          <span className="block truncate text-xs text-neutral-500">
            {job.label} · {when(job.created)}
          </span>
        </span>
      </button>
      {job.status === 'running' && p && (
        <div className="w-full min-w-40 sm:w-56">
          <div className="mb-1 flex justify-between text-xs text-neutral-400">
            <span>{p.phase}</span>
            {p.total > 0 && (
              <span className="tabular-nums">
                {p.done} / {p.total}
              </span>
            )}
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-neutral-800">
            <div className={`h-full bg-sky-400 transition-all ${pct === null ? 'w-1/3 animate-pulse' : ''}`} style={pct === null ? undefined : { width: `${pct}%` }} />
          </div>
        </div>
      )}
      <div className="ml-auto flex items-center gap-2">
        {job.status === 'done' && job.pending > 0 && (
          <span className="rounded bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300">{job.pending} 個待確認</span>
        )}
        <span className={`rounded px-2 py-0.5 text-xs ${color}`}>{label}</span>
        {active(job) ? (
          <button onClick={onCancel} className="rounded-lg bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700">
            取消
          </button>
        ) : (
          <button onClick={onRemove} className="rounded-lg bg-neutral-800 px-2.5 py-1 text-xs hover:bg-neutral-700" title="從清單移除（已套用的結果不受影響）">
            刪除
          </button>
        )}
        <button onClick={onToggle} className="rounded-lg px-2 py-1 text-neutral-400 hover:bg-white/5" aria-label={open ? '收合' : '展開'}>
          {open ? '▴' : '▾'}
        </button>
      </div>
    </div>
  )
}

// ── shared pieces ──

function Img({ src, className = '', alt = '' }) {
  return src ? (
    <img src={src} alt={alt} loading="lazy" className={`bg-neutral-800 object-cover ${className}`} />
  ) : (
    <div className={`bg-neutral-800 ${className}`} />
  )
}

function ItemLink({ item, onOpen, className = '' }) {
  return (
    <button onClick={() => onOpen(item.id)} className={`block max-w-full truncate text-left hover:text-accent hover:underline ${className}`} title={`${item.folder ? `/${item.folder}/` : ''}${item.name}`}>
      {item.name}
    </button>
  )
}

function StateBadge({ state, name }) {
  if (state === 'applied')
    return <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300">✓ 已套用{name ? `「${name}」` : ''}</span>
  if (state === 'rejected') return <span className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-400">已略過</span>
  return null
}

function Section({ title, count, children, right }) {
  return (
    <section className="mb-6 last:mb-0">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="font-medium">
          {title} <span className="text-sm font-normal text-neutral-500">{count}</span>
        </h3>
        <div className="ml-auto flex flex-wrap gap-2">{right}</div>
      </div>
      {children}
    </section>
  )
}

function Skipped({ list, label = '無法辨識' }) {
  if (!list?.length) return null
  return (
    <details className="mt-4 text-sm text-neutral-400">
      <summary className="cursor-pointer select-none">
        {label}（{list.length}）
      </summary>
      <ul className="mt-2 space-y-1 pl-4">
        {list.map((s, i) => (
          <li key={i} className="truncate">
            {s.item ? s.item.name : ''}
            {s.item ? '：' : ''}
            <span className="text-neutral-500">{s.reason}</span>
          </li>
        ))}
      </ul>
    </details>
  )
}

// name input with suggestions from the library (主演 / 系列)
function NameInput({ value, onChange, options, placeholder, id }) {
  return (
    <>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        list={id}
        placeholder={placeholder}
        className="min-w-0 flex-1 rounded-lg bg-neutral-800 px-3 py-1.5 text-sm outline-none ring-1 ring-white/10 focus:ring-accent"
      />
      <datalist id={id}>
        {options.map((o) => (
          <option key={o} value={o} />
        ))}
      </datalist>
    </>
  )
}

// a member that can be left out of 套用 by tapping it
function Pick({ checked, disabled, onToggle, children }) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onToggle}
      aria-pressed={checked}
      className={`relative overflow-hidden rounded-lg text-left ring-2 ${checked && !disabled ? 'ring-accent' : 'ring-transparent opacity-50'} ${disabled ? 'cursor-default opacity-100 ring-transparent' : ''}`}
    >
      {children}
      {!disabled && (
        <span className={`absolute left-1 top-1 flex h-5 w-5 items-center justify-center rounded-full text-xs ${checked ? 'bg-accent text-white' : 'bg-black/60 text-transparent ring-1 ring-white/50'}`}>
          ✓
        </span>
      )}
    </button>
  )
}

// ── 辨識主演 ──

function ActorResult({ job, tags, onApply, onOpen }) {
  const r = job.result
  const pending = r.matches.filter((m) => m.state === 'pending')
  const [checked, setChecked] = useState(() => new Set(pending.map((m) => m.key)))
  const [busy, setBusy] = useState(false)
  const chosen = pending.filter((m) => checked.has(m.key))

  async function act(action, list) {
    setBusy(true)
    await onApply(job.id, list.map((m) => ({ key: m.key, action })))
    setBusy(false)
  }

  const toggle = (key) =>
    setChecked((s) => {
      const next = new Set(s)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })

  return (
    <div>
      {r.actors === 0 && (
        <p className="mb-4 rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          媒體庫裡還沒有標好主演的影片 / 圖片可以比對，所以只能把相同的臉分組。先幫幾部標上主演，之後的辨識就能直接建議名字。
        </p>
      )}
      <Section
        title="建議主演"
        count={r.matches.length}
        right={
          pending.length > 0 && (
            <>
              <button onClick={() => setChecked(new Set(chosen.length === pending.length ? [] : pending.map((m) => m.key)))} className="rounded-lg bg-neutral-800 px-3 py-1 text-sm hover:bg-neutral-700">
                {chosen.length === pending.length ? '全不選' : '全選'}
              </button>
              <button disabled={!chosen.length || busy} onClick={() => act('reject', chosen)} className="rounded-lg bg-neutral-800 px-3 py-1 text-sm hover:bg-neutral-700 disabled:opacity-40">
                略過已選
              </button>
              <button disabled={!chosen.length || busy} onClick={() => act('apply', chosen)} className="rounded-lg bg-accent px-3 py-1 text-sm font-medium hover:bg-accent-hover disabled:opacity-40">
                套用已選（{chosen.length}）
              </button>
            </>
          )
        }
      >
        {r.matches.length === 0 ? (
          <p className="text-sm text-neutral-500">沒有可以建議的主演{r.already ? `（${r.already} 個人臉已經標好了）` : ''}</p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {r.matches.map((m) => {
              const isPending = m.state === 'pending'
              return (
                <li key={m.key} className={`flex items-center gap-3 rounded-lg p-2 ring-1 ${isPending && checked.has(m.key) ? 'bg-accent/10 ring-accent/50' : 'bg-neutral-800/50 ring-white/5'} ${isPending ? '' : 'opacity-60'}`}>
                  {isPending && <input type="checkbox" checked={checked.has(m.key)} onChange={() => toggle(m.key)} className="h-4 w-4 shrink-0 accent-accent" aria-label="選取" />}
                  <Img src={m.face} className="h-14 w-14 shrink-0 rounded-lg" alt="臉" />
                  <Img src={m.item.cover} className="hidden h-14 w-20 shrink-0 rounded-lg sm:block" />
                  <div className="min-w-0 flex-1 text-sm">
                    <ItemLink item={m.item} onOpen={onOpen} />
                    <p className="truncate">
                      → <span className="font-medium text-accent">{m.actor}</span>
                      <span className="ml-2 text-xs text-neutral-400">相似度 {m.score}</span>
                    </p>
                    {m.item.actors.length > 0 && <p className="truncate text-xs text-neutral-500">目前：{m.item.actors.join('、')}</p>}
                  </div>
                  <StateBadge state={m.state} />
                </li>
              )
            })}
          </ul>
        )}
      </Section>

      <Section title="未知人物" count={r.unknown.length}>
        {r.unknown.length === 0 ? (
          <p className="text-sm text-neutral-500">沒有認不出來的人</p>
        ) : (
          <ul className="space-y-3">
            {r.unknown.map((u) => (
              <UnknownCard key={u.key} u={u} job={job} tags={tags} onApply={onApply} onOpen={onOpen} />
            ))}
          </ul>
        )}
      </Section>

      <p className="text-xs text-neutral-500">
        相似度是臉部特徵的接近程度，{r.threshold} 以上通常是同一個人。比對對象：{r.actors} 位已標記的主演。
        {r.already > 0 && ` 另有 ${r.already} 個人臉已經標了正確的主演，沒有列出。`}
      </p>
      <Skipped list={r.skipped} />
    </div>
  )
}

function UnknownCard({ u, job, tags, onApply, onOpen }) {
  const [name, setName] = useState(u.name || '')
  const [picked, setPicked] = useState(() => new Set(u.members.map((m) => m.item.id)))
  const [busy, setBusy] = useState(false)
  const isPending = u.state === 'pending'

  async function act(action) {
    setBusy(true)
    await onApply(job.id, [{ key: u.key, action, name: name.trim(), items: [...picked] }])
    setBusy(false)
  }

  return (
    <li className={`rounded-lg bg-neutral-800/50 p-3 ring-1 ring-white/5 ${isPending ? '' : 'opacity-60'}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{u.members.length} 個項目裡的同一個人</span>
        {u.hint && (
          <span className="text-xs text-neutral-400">
            最像 {u.hint.actor}（相似度 {u.hint.score}，未達門檻）
          </span>
        )}
        <span className="ml-auto">
          <StateBadge state={u.state} name={u.name} />
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {u.members.map((m) => (
          <div key={m.item.id} className="w-20">
            <Pick
              checked={picked.has(m.item.id)}
              disabled={!isPending}
              onToggle={() =>
                setPicked((s) => {
                  const next = new Set(s)
                  next.has(m.item.id) ? next.delete(m.item.id) : next.add(m.item.id)
                  return next
                })
              }
            >
              <Img src={m.face} className="h-20 w-20" alt="臉" />
            </Pick>
            <ItemLink item={m.item} onOpen={onOpen} className="mt-1 text-xs text-neutral-400" />
          </div>
        ))}
      </div>
      {isPending && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <NameInput id={`actors-${u.key}`} value={name} onChange={setName} options={tags.actors.map((a) => a.name)} placeholder="輸入主演名字（可選已有的）" />
          <button disabled={busy} onClick={() => act('reject')} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-40">
            略過
          </button>
          <button disabled={busy || !name.trim() || !picked.size} onClick={() => act('apply')} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-40">
            設為主演（{picked.size}）
          </button>
        </div>
      )}
    </li>
  )
}

// ── 辨識系列 ──

function SeriesResult({ job, tags, onApply, onOpen }) {
  const r = job.result
  return (
    <div>
      <Section title="建議系列" count={r.groups.length}>
        {r.groups.length === 0 ? (
          <p className="text-sm text-neutral-500">沒有找到同一個人穿同一套衣服的項目</p>
        ) : (
          <ul className="space-y-3">
            {r.groups.map((g) => (
              <GroupCard key={g.key} g={g} job={job} tags={tags} onApply={onApply} onOpen={onOpen} />
            ))}
          </ul>
        )}
      </Section>

      {r.loose?.length > 0 && (
        <details className="mb-4 text-sm">
          <summary className="cursor-pointer select-none text-neutral-300">沒有配對到的（{r.loose.length}）</summary>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {r.loose.map((l) => (
              <li key={l.item.id} className="flex items-center gap-3 rounded-lg bg-neutral-800/50 p-2">
                <Img src={l.body} className="h-20 w-14 shrink-0 rounded" />
                <div className="min-w-0 text-xs">
                  <ItemLink item={l.item} onOpen={onOpen} className="text-sm" />
                  <p className="text-neutral-400">{l.person}</p>
                  <p className="line-clamp-2 text-neutral-500">{l.outfit}</p>
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs text-neutral-500">
        同一個人（主演標記或人臉）穿同一套衣服才會歸為同一系列。服裝由 {r.model} 描述並兩兩確認，共比對 {r.checked} 組。
        {r.limited && ' 項目太多，只比對了最像的一部分，可以分批再辨識一次。'}
      </p>
      <Skipped list={r.skipped} />
    </div>
  )
}

function GroupCard({ g, job, tags, onApply, onOpen }) {
  const [name, setName] = useState(g.name || g.suggested || '')
  const [picked, setPicked] = useState(() => new Set(g.members.map((m) => m.item.id)))
  const [busy, setBusy] = useState(false)
  const isPending = g.state === 'pending'
  const changing = g.members.filter((m) => picked.has(m.item.id) && m.item.series && m.item.series !== name.trim())

  async function act(action) {
    setBusy(true)
    await onApply(job.id, [{ key: g.key, action, name: name.trim(), items: [...picked] }])
    setBusy(false)
  }

  return (
    <li className={`rounded-lg bg-neutral-800/50 p-3 ring-1 ring-white/5 ${isPending ? '' : 'opacity-60'}`}>
      <div className="mb-2 flex flex-wrap items-center gap-3 text-sm">
        <Img src={g.face} className="h-10 w-10 rounded-full" alt="臉" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {g.person}
            <span className="ml-2 whitespace-nowrap font-normal text-neutral-400">{g.members.length} 個項目</span>
            {g.existing && <span className="ml-2 inline-block whitespace-nowrap rounded bg-accent/15 px-1.5 py-0.5 text-xs text-accent">已有的系列</span>}
          </p>
          <p className="text-xs text-neutral-400">{g.outfit}</p>
        </div>
        <StateBadge state={g.state} name={g.name} />
      </div>
      <div className="flex flex-wrap gap-2">
        {g.members.map((m) => (
          <div key={m.item.id} className="w-24">
            <Pick
              checked={picked.has(m.item.id)}
              disabled={!isPending}
              onToggle={() =>
                setPicked((s) => {
                  const next = new Set(s)
                  next.has(m.item.id) ? next.delete(m.item.id) : next.add(m.item.id)
                  return next
                })
              }
            >
              <Img src={m.body} className="h-32 w-24" alt="服裝" />
            </Pick>
            <ItemLink item={m.item} onOpen={onOpen} className="mt-1 text-xs text-neutral-400" />
            {m.item.series && <p className="truncate text-[11px] text-neutral-500">目前：{m.item.series}</p>}
          </div>
        ))}
        {g.refs.length > 0 && (
          <div className="ml-2 border-l border-white/10 pl-3">
            <p className="mb-1 text-[11px] text-neutral-500">已在系列裡的</p>
            <div className="flex flex-wrap gap-2">
              {g.refs.map((m) => (
                <div key={m.item.id} className="w-16">
                  <Img src={m.body} className="h-20 w-16 rounded-lg" alt="服裝" />
                  <ItemLink item={m.item} onOpen={onOpen} className="mt-1 text-[11px] text-neutral-500" />
                  <p className="truncate text-[11px] text-accent">{m.item.series}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      {isPending && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <NameInput id={`series-${g.key}`} value={name} onChange={setName} options={tags.series.map((s) => s.name)} placeholder="系列名稱" />
            <button disabled={busy} onClick={() => act('reject')} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-40">
              略過
            </button>
            <button disabled={busy || !name.trim() || !picked.size} onClick={() => act('apply')} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-40">
              設為系列（{picked.size}）
            </button>
          </div>
          {changing.length > 0 && <p className="mt-1 text-xs text-amber-300">{changing.length} 個項目原本有別的系列，會被改掉</p>}
        </>
      )}
    </li>
  )
}
