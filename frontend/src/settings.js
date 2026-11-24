// Per-browser playback settings (設定 page), kept in localStorage so a phone and a PC can differ.

export const ORIGINAL = 'orig'
// transcode levels, best first: mirrors library/media.py STREAM_LEVELS (kbps = video + audio cap)
export const LEVELS = [
  { key: '2160', label: '2160p', kbps: 16160 },
  { key: '1080h', label: '1080p 高', kbps: 8160 },
  { key: '1080l', label: '1080p 低', kbps: 4628 },
  { key: '720h', label: '720p 高', kbps: 4128 },
  { key: '720l', label: '720p 低', kbps: 2128 },
  { key: '480h', label: '480p 高', kbps: 1596 },
  { key: '480l', label: '480p 低', kbps: 896 },
]
export const RANK = LEVELS.map((l) => l.key)

const QUALITY_KEY = 'tad.quality'
const FILL_KEY = 'tad.fill'

function load(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function save(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {}
}

// default 畫質: 'orig' or a level key (原始 when nothing is set)
export function defaultQuality() {
  const saved = load(QUALITY_KEY)
  return saved === ORIGINAL || RANK.includes(saved) ? saved : ORIGINAL
}

export const setDefaultQuality = (q) => save(QUALITY_KEY, q)

// fullscreen: true = 填滿 (no black bars, edges cropped), false = 完整
export const fillScreen = () => load(FILL_KEY) !== 'contain'
export const setFillScreen = (fill) => save(FILL_KEY, fill ? 'cover' : 'contain')

export const kbpsText = (kbps) => (kbps >= 1000 ? `${(kbps / 1000).toFixed(1)} Mbps` : `${kbps} kbps`)

// data used per hour of playback at a level's cap
export const perHourText = (kbps) => {
  const mb = (kbps * 3600) / 8 / 1000
  return mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${Math.round(mb)} MB`
}
