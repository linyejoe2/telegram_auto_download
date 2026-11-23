// Thin fetch wrapper for the Python API (library/server.py). Cookies carry the session.

export class Unauthorized extends Error {}

// the app is served under /library (see library/server.py PREFIX and vite.config.js base)
export const BASE = '/library'
export const API = `${BASE}/api`
export const MEDIA = `${BASE}/media`

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
  batchUpdate: (ids, changes) => request('POST', `${API}/batch/update`, { ids, ...changes }),
  batchDelete: (ids) => request('POST', `${API}/batch/delete`, { ids }),
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
