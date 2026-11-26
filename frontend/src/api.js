// Thin fetch wrapper for the Python API (library/server.py). Cookies carry the session.

export class Unauthorized extends Error {}

// the app is served under /library (see library/server.py PREFIX and vite.config.js base)
export const BASE = '/library'
export const API = `${BASE}/api`
export const MEDIA = `${BASE}/media`

// Stop a <video> for good before React drops it: a removed element keeps downloading (a live transcode
// never ends) until it is garbage collected, and the browser allows only 6 connections to the server.
export function releaseVideo(el) {
  if (!el) return
  try {
    el.pause()
    el.removeAttribute('src')
    el.load()
  } catch {}
}

async function request(method, url, body) {
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && url !== `${API}/login`) throw new Unauthorized()
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

export const api = {
  session: () => request('GET', `${API}/session`),
  login: (password) => request('POST', `${API}/login`, { password }),
  logout: () => request('POST', `${API}/logout`),
  videos: (kind) => request('GET', `${API}/videos${kind ? `?kind=${kind}` : ''}`),
  history: (params) => request('GET', `${API}/history?${new URLSearchParams(params)}`),
  redownload: (key) => request('POST', `${API}/history/redownload`, { key }),
  video: (id) => request('GET', `${API}/videos/${id}`),
  update: (id, fields) => request('PATCH', `${API}/videos/${id}`, fields),
  remove: (id) => request('DELETE', `${API}/videos/${id}`),
  regenerateShots: (id) => request('POST', `${API}/videos/${id}/screenshots`),
  tags: () => request('GET', `${API}/tags`),
  rescan: () => request('POST', `${API}/rescan`),
  folders: () => request('GET', `${API}/folders`),
  createFolder: (parent, name) => request('POST', `${API}/folders`, { parent, name }),
  renameFolder: (path, name) => request('POST', `${API}/folders/rename`, { path, name }),
  deleteFolder: (path) => request('POST', `${API}/folders/delete`, { path }),
  renameVideo: (id, name) => request('POST', `${API}/videos/${id}/rename`, { name }),
  move: (videos, folders, dest) => request('POST', `${API}/move`, { videos, folders, dest }),
  ungroup: (id) => request('POST', `${API}/videos/${id}/ungroup`),
  redownloadVideo: (id) => request('POST', `${API}/videos/${id}/redownload`),
  // multi-select: { add_actors, remove_actors, series? } ('' clears 系列, leave it out to keep it)
  renameSeries: (old, name) => request('POST', `${API}/series/rename`, { old, new: name }),
  batchUpdate: (ids, changes) => request('POST', `${API}/batch/update`, { ids, ...changes }),
  batchDelete: (ids) => request('POST', `${API}/batch/delete`, { ids }),
  batchCompare: (ids) => request('POST', `${API}/batch/compare`, { ids }),
  batchMerge: (groups) => request('POST', `${API}/batch/merge`, { groups }),
  deepCompare: (ids) => request('POST', `${API}/batch/deep-compare`, { ids }),
  // AI 辨識 (library/recognize.py): kind 'actor' (主演, by face) | 'series' (系列, by outfit)
  recognize: (kind, ids) => request('POST', `${API}/recognition`, { kind, ids }),
  recognitionJobs: () => request('GET', `${API}/recognition`),
  recognitionStatus: () => request('GET', `${API}/recognition/status`),
  recognitionJob: (id) => request('GET', `${API}/recognition/${id}`),
  cancelRecognition: (id) => request('POST', `${API}/recognition/${id}/cancel`),
  removeRecognition: (id) => request('DELETE', `${API}/recognition/${id}`),
  // entries: [{ key, action: 'apply' | 'reject', name?, items? }]
  applyRecognition: (id, entries) => request('POST', `${API}/recognition/${id}/apply`, { entries }),
  // 人物資料庫 (library/people.py); renaming / merging / deleting changes the 主演 tags on the items
  people: () => request('GET', `${API}/people`),
  person: (id) => request('GET', `${API}/people/${id}`),
  peopleScan: (on) => request('POST', `${API}/people/scan`, { on }),
  renamePerson: (id, name) => request('POST', `${API}/people/${id}/rename`, { name }),
  mergePerson: (id, into) => request('POST', `${API}/people/${id}/merge`, { into }),
  removeFromPerson: (id, items) => request('POST', `${API}/people/${id}/remove`, { items }),
  deletePerson: (id) => request('DELETE', `${API}/people/${id}`),
}

// drag & drop payload between video items and folder tree nodes
export const DRAG_TYPE = 'application/x-tad-items'

export function setDragItems(e, items) {
  e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(items))
  e.dataTransfer.effectAllowed = 'move'
}

export function getDragItems(e) {
  try {
    return JSON.parse(e.dataTransfer.getData(DRAG_TYPE))
  } catch {
    return null
  }
}

// higher = better: resolution (short side) first, then bit rate
export function qualityKey(v) {
  return Math.min(v.width || 0, v.height || 0) * 1e9 + (v.bit_rate || 0)
}

// what the library shows: 影片 / 圖片 / 全部 (kept in the URL as ?kind=, remembered per browser)
export const KINDS = {
  video: { label: '影片', title: '影片庫', unit: '部' },
  photo: { label: '圖片', title: '圖片庫', unit: '張' },
  all: { label: '全部', title: '媒體庫', unit: '個' },
}

export function storedKind() {
  try {
    const k = localStorage.getItem('tad.kind')
    return KINDS[k] ? k : 'all'
  } catch {
    return 'all'
  }
}

export function rememberKind(kind) {
  try {
    localStorage.setItem('tad.kind', kind)
  } catch {}
}

export const dimensions = (w, h) => (w && h ? `${w}×${h}` : null)

// sessionStorage (this tab, survives reloads); can be blocked, so never required
export function readSession(key) {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeSession(key, value) {
  try {
    sessionStorage.setItem(key, String(value))
  } catch {}
}

// The library's current video order (this tab only), so the video page can swipe to the previous /
// next one. `back` is the library's query string: the list is used only when the page was opened from
// that view. Items are [id, group] so another version of a shown video finds its place too.
const LIST_KEY = 'tad.list'

export function saveList(back, videos) {
  try {
    sessionStorage.setItem(LIST_KEY, JSON.stringify({ back, items: videos.map((v) => [v.id, v.group || '']) }))
  } catch {}
}

export function listNeighbors(video, back) {
  let list
  try {
    list = JSON.parse(sessionStorage.getItem(LIST_KEY))
  } catch {}
  if (!list || typeof back !== 'string' || list.back !== back || !Array.isArray(list.items)) return {}
  let i = list.items.findIndex(([id]) => id === video.id)
  if (i < 0 && video.group) i = list.items.findIndex(([, group]) => group === video.group)
  if (i < 0) return {}
  return { prev: list.items[i - 1]?.[0] || null, next: list.items[i + 1]?.[0] || null, index: i + 1, total: list.items.length }
}

export const baseName = (path) => path.split('/').pop()
export const parentOf = (path) => (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '')

export function fmtDuration(seconds) {
  if (seconds == null || isNaN(seconds)) return '--:--'
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${String(m).padStart(2, '0')}:${sec}`
}

export function fmtSize(bytes) {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i ? 1 : 0)} ${units[i]}`
}

export function fmtBitrate(bps) {
  if (!bps) return '-'
  return bps >= 1e6 ? `${(bps / 1e6).toFixed(2)} Mbps` : `${Math.round(bps / 1e3)} kbps`
}

export function resolutionLabel(w, h) {
  if (!w || !h) return null
  const p = Math.min(w, h)
  if (p >= 2160) return '4K'
  if (p >= 1440) return '1440p'
  if (p >= 1080) return '1080p'
  if (p >= 720) return '720p'
  return `${p}p`
}
