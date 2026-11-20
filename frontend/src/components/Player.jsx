import { useEffect, useMemo, useRef, useState } from 'react'
import { fmtDuration } from '../api.js'

const QUALITIES = [480, 720, 1080]

// Plays the original file when the browser can (native controls). Otherwise the server transcodes
// live (ffmpeg -> fragmented MP4 from `offset` seconds), which can't be seeked by the browser itself,
// so seeking restarts the stream at the new position and the controls show offset + currentTime.
export default function Player({ video, startAt = 0 }) {
  const ref = useRef(null)
  const box = useRef(null)
  const duration = video.info?.duration || video.duration || 0
  const canDirect = useMemo(
    () => video.direct && document.createElement('video').canPlayType(video.mime) !== '',
    [video.id],
  )
  const [mode, setMode] = useState(canDirect ? 'direct' : 'stream')
  const [offset, setOffset] = useState(startAt)
  const [quality, setQuality] = useState(720)
  const [time, setTime] = useState(startAt)
  const [playing, setPlaying] = useState(false)
  const [waiting, setWaiting] = useState(true)
  const [volume, setVolume] = useState(1)
  const [dragging, setDragging] = useState(null)

  const src = mode === 'direct' ? `/media/${video.id}/file` : `/media/${video.id}/stream?t=${offset.toFixed(2)}&h=${quality}`
  const now = () => (mode === 'direct' ? ref.current?.currentTime || 0 : offset + (ref.current?.currentTime || 0))

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
    onTimeUpdate: () => dragging === null && setTime(now()),
    onLoadedMetadata: () => {
      if (mode === 'direct' && startAt && ref.current.currentTime < 1) ref.current.currentTime = startAt
    },
    onError: () => {
      if (mode === 'direct') {
        // the browser could not decode the original after all: fall back to live transcoding
        setOffset(time)
        setMode('stream')
      }
    },
  }

  if (mode === 'direct') {
    return (
      <div ref={box} className="overflow-hidden rounded-xl bg-black">
        <video ref={ref} src={src} controls autoPlay playsInline className="aspect-video w-full bg-black" {...events} />
        <p className="px-3 py-1.5 text-xs text-neutral-500">原始檔播放 · 快捷鍵：空白鍵播放/暫停，←/→ 跳 10 秒，F 全螢幕</p>
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
          <select
            value={quality}
            onChange={(e) => {
              setOffset(now())
              setQuality(Number(e.target.value))
              setWaiting(true)
            }}
            className="ml-auto rounded bg-white/10 px-1 py-0.5 text-xs"
            title="轉檔畫質"
          >
            {QUALITIES.map((q) => (
              <option key={q} value={q} className="bg-neutral-900">{q}p</option>
            ))}
          </select>
          <span className="hidden text-xs text-amber-300 sm:inline">即時轉檔</span>
          <button onClick={fullscreen} className="rounded bg-white/10 px-2 py-0.5 hover:bg-white/20">全螢幕</button>
        </div>
      </div>
    </div>
  )
}
