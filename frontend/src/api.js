// Thin fetch wrapper for the Python API (library/server.py). Cookies carry the session.

export class Unauthorized extends Error {}

async function request(method, url, body) {
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && url !== '/api/login') throw new Unauthorized()
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

export const api = {
  session: () => request('GET', '/api/session'),
  login: (password) => request('POST', '/api/login', { password }),
  logout: () => request('POST', '/api/logout'),
  videos: () => request('GET', '/api/videos'),
  video: (id) => request('GET', `/api/videos/${id}`),
  update: (id, fields) => request('PATCH', `/api/videos/${id}`, fields),
  remove: (id) => request('DELETE', `/api/videos/${id}`),
  regenerateShots: (id) => request('POST', `/api/videos/${id}/screenshots`),
  tags: () => request('GET', '/api/tags'),
  rescan: () => request('POST', '/api/rescan'),
  folders: () => request('GET', '/api/folders'),
  createFolder: (parent, name) => request('POST', '/api/folders', { parent, name }),
  renameFolder: (path, name) => request('POST', '/api/folders/rename', { path, name }),
  deleteFolder: (path) => request('POST', '/api/folders/delete', { path }),
  renameVideo: (id, name) => request('POST', `/api/videos/${id}/rename`, { name }),
  move: (videos, folders, dest) => request('POST', '/api/move', { videos, folders, dest }),
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
