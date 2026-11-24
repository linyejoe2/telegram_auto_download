import { useEffect, useMemo, useRef, useState } from 'react'
import { fmtBitrate, fmtDuration, MEDIA } from '../api.js'

// transcode levels, best first (library/media.py STREAM_LEVELS); the server sends the ones that fit the video
const RANK = ['2160', '1080h', '1080l', '720h', '720l', '480h', '480l']
const ORIGINAL = 'orig'
const QUALITY_KEY = 'tad.quality'

function storedQuality() {
  try {
    return localStorage.getItem(QUALITY_KEY)
  } catch {
    return null
  }
}

function rememberQuality(q) {
  try {
    localStorage.setItem(QUALITY_KEY, q)
  } catch {}
}

// the best offered level not above `wanted`
function levelAtMost(levels, wanted) {
  const max = Math.max(0, RANK.indexOf(wanted))
  return (levels.find((l) => RANK.indexOf(l.key) >= max) || levels[levels.length - 1])?.key || '720h'
}

function initialQuality(levels, canDirect) {
  const saved = storedQuality()
  if (saved === ORIGINAL) return canDirect ? ORIGINAL : levels[0]?.key || '720h'
  if (RANK.includes(saved)) return levelAtMost(levels, saved)
  return canDirect ? ORIGINAL : levelAtMost(levels, '720h')
}

const kbpsText = (kbps) => (kbps >= 1000 ? `${(kbps / 1000).toFixed(1)} Mbps` : `${kbps} kbps`)

function QualitySelect({ value, onChange, levels, canDirect, bitRate, className = '' }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} title="畫質（較低的畫質用較少流量）"
      className={`rounded bg-white/10 px-1 py-0.5 text-xs text-neutral-200 ${className}`}>
      {canDirect && (
        <option value={ORIGINAL} className="bg-neutral-900">原始{bitRate ? ` · ${fmtBitrate(bitRate)}` : ''}</option>
      )}
      {levels.map((l) => (
        <option key={l.key} value={l.key} className="bg-neutral-900">{l.label} · ≤{kbpsText(l.kbps)}</option>
      ))}
    </select>
  )
}

// Plays the original file when the browser can and 原始 is chosen (native controls). Otherwise the server
// transcodes live at the chosen level (ffmpeg -> fragmented MP4 from `offset` seconds, bit rate capped),
// which can't be seeked by the browser itself, so seeking restarts the stream at the new position and
// the controls show offset + currentTime. The 畫質 choice is remembered per browser.
export default function Player({ video, startAt = 0, onTime }) {
  const ref = useRef(null)
  const box = useRef(null)
  const duration = video.info?.duration || video.duration || 0
  const canDirect = useMemo(
    () => video.direct && document.createElement('video').canPlayType(video.mime) !== '',
    [video.id],
  )
  const levels = video.qualities?.length ? video.qualities : [{ key: '720h', label: '720p', kbps: 4128 }]
  const [quality, setQuality] = useState(() => initialQuality(levels, canDirect))
  const mode = quality === ORIGINAL && canDirect ? 'direct' : 'stream'
  const [offset, setOffset] = useState(startAt)
  const [time, setTime] = useState(startAt)
  const [playing, setPlaying] = useState(false)
  const [waiting, setWaiting] = useState(true)
  const [volume, setVolume] = useState(1)
  const [dragging, setDragging] = useState(null)

  const src = mode === 'direct' ? `${MEDIA}/${video.id}/file` : `${MEDIA}/${video.id}/stream?t=${offset.toFixed(2)}&q=${quality}`
  const now = () => (mode === 'direct' ? ref.current?.currentTime || 0 : offset + (ref.current?.currentTime || 0))

  function changeQuality(q) {
    const t = now()
    setOffset(t)
    setTime(t)
    setWaiting(true)
    setQuality(q)
    rememberQuality(q)
  }

  function seek(t) {
    t = Math.max(0, Math.min(duration ? duration - 1 : t, t))
    if (mode === 'direct') ref.current.currentTime = t
    else {
      setOffset(t)
      setWaiting(true)
    }
    setTime(t)
  }

  function toggle() {
    const v = ref.current
    if (!v) return
    v.paused ? v.play().catch(() => {}) : v.pause()
  }

  function fullscreen() {
    if (document.fullscreenElement) document.exitFullscreen()
    else box.current?.requestFullscreen?.()
  }

  // keyboard: space = play/pause, arrows = -/+ 10 s, f = fullscreen
  useEffect(() => {
    function onKey(e) {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return
      if (e.code === 'Space') {
        e.preventDefault()
        toggle()
      } else if (e.code === 'ArrowLeft') seek(now() - 10)
      else if (e.code === 'ArrowRight') seek(now() + 10)
      else if (e.code === 'KeyF') fullscreen()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  useEffect(() => {
    if (ref.current) ref.current.volume = volume
  }, [volume, src])

  const events = {
    onPlay: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onWaiting: () => setWaiting(true),
    onPlaying: () => setWaiting(false),
    onCanPlay: () => setWaiting(false),
    onTimeUpdate: () => {
      onTime?.(now())
      if (dragging === null) setTime(now())
    },
    onLoadedMetadata: () => {
      // direct play starts at `offset` (the page's start time, or where the stream was when switching)
      if (mode === 'direct' && offset > 0.5 && ref.current.currentTime < 1) ref.current.currentTime = offset
    },
    onError: () => {
      if (mode === 'direct') {
        // the browser could not decode the original after all: fall back to live transcoding (not remembered)
        setOffset(time)
        setQuality(levelAtMost(levels, '720h'))
      }
    },
  }

  const select = (cls) => (
    <QualitySelect value={quality} onChange={changeQuality} levels={levels} canDirect={canDirect}
      bitRate={video.info?.bit_rate} className={cls} />
  )

  if (mode === 'direct') {
    return (
      <div ref={box} className="overflow-hidden rounded-xl bg-black">
        <video ref={ref} src={src} controls autoPlay playsInline className="aspect-video w-full bg-black" {...events} />
        <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-neutral-500">
          <span className="min-w-0">原始檔播放 · 快捷鍵：空白鍵播放/暫停，←/→ 跳 10 秒，F 全螢幕</span>
          {select('ml-auto shrink-0')}
        </div>
      </div>
    )
  }

  const shown = dragging ?? time
  return (
    <div ref={box} className="group relative overflow-hidden rounded-xl bg-black">
      <video ref={ref} key={src} src={src} autoPlay playsInline onClick={toggle} className="aspect-video w-full bg-black" {...events} />
      {waiting && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/30 border-t-white" />
        </div>
      )}
      <div
        className={`absolute inset-x-0 bottom-0 space-y-2 bg-gradient-to-t from-black/90 to-transparent px-3 pb-2 pt-8 transition group-hover:opacity-100 ${
          playing ? 'sm:opacity-0' : ''
        }`}
      >
        <input
          type="range"
          className="seek"
          min={0}
          max={duration || 1}
          step={0.5}
          value={Math.min(shown, duration || shown)}
          onChange={(e) => setDragging(Number(e.target.value))}
          onPointerUp={() => {
            if (dragging !== null) seek(dragging)
            setDragging(null)
          }}
          onKeyUp={() => {
            if (dragging !== null) seek(dragging)
            setDragging(null)
          }}
        />
        <div className="flex items-center gap-3 text-sm">
          <button onClick={toggle} className="w-14 rounded bg-white/10 px-2 py-0.5 hover:bg-white/20">
            {playing ? '暫停' : '播放'}
          </button>
          <button onClick={() => seek(now() - 10)} className="rounded bg-white/10 px-2 py-0.5 hover:bg-white/20">-10s</button>
          <button onClick={() => seek(now() + 10)} className="rounded bg-white/10 px-2 py-0.5 hover:bg-white/20">+10s</button>
          <span className="tabular-nums text-neutral-300">
            {fmtDuration(shown)} / {fmtDuration(duration)}
          </span>
          <input
            type="range"
            className="seek !w-20"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onChange={(e) => setVolume(Number(e.target.value))}
            title="音量"
          />
          {select('ml-auto')}
          <span className="hidden text-xs text-amber-300 sm:inline">即時轉檔</span>
          <button onClick={fullscreen} className="rounded bg-white/10 px-2 py-0.5 hover:bg-white/20">全螢幕</button>
        </div>
      </div>
    </div>
  )
}
