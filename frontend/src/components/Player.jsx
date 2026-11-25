import { useEffect, useMemo, useRef, useState } from 'react'
import { fmtBitrate, fmtDuration, MEDIA } from '../api.js'
import { defaultQuality, fillScreen, kbpsText, ORIGINAL, RANK, setFillScreen } from '../settings.js'

const HIDE_AFTER = 3000 // ms without touching / moving before the controls hide while playing
const SWIPE_MIN = 60 // px a finger must travel to switch video (or a quick flick of half that)

// the best offered level not above `wanted`
function levelAtMost(levels, wanted) {
  const max = Math.max(0, RANK.indexOf(wanted))
  return (levels.find((l) => RANK.indexOf(l.key) >= max) || levels[levels.length - 1])?.key || '720h'
}

// the 設定 page's default; 原始 falls back to the best level when the browser can't play the file
function initialQuality(levels, canDirect) {
  const wanted = defaultQuality()
  if (wanted === ORIGINAL) return canDirect ? ORIGINAL : levels[0]?.key || '720h'
  return levelAtMost(levels, wanted)
}

// Fullscreen on phones: let the video reach into the display cutout (notch) only while fullscreen;
// the controls keep clear of it with the safe-area insets.
function setViewportFit(cover) {
  const meta = document.querySelector('meta[name="viewport"]')
  if (!meta) return
  const base = meta.content.replace(/,\s*viewport-fit=\w+/g, '')
  meta.content = cover ? `${base}, viewport-fit=cover` : base
}

// one listener for the whole app: fullscreen may outlive a player (swiping to the next video keeps it)
document.addEventListener('fullscreenchange', () => {
  if (document.fullscreenElement) return
  setViewportFit(false)
  screen.orientation?.unlock?.()
})

function lockOrientation(v) {
  if (document.fullscreenElement && v?.videoWidth && screen.orientation?.lock) {
    screen.orientation.lock(v.videoWidth >= v.videoHeight ? 'landscape' : 'portrait').catch(() => {})
  }
}

// shows only the short label; the native picker (full width on phones) lists the bit rates
function QualitySelect({ value, onChange, levels, canDirect, bitRate, className = '' }) {
  const current = value === ORIGINAL ? '原始' : levels.find((l) => l.key === value)?.label || value
  return (
    <label title="畫質（只套用這部影片；預設畫質在「設定」頁）"
      className={`relative inline-flex shrink-0 cursor-pointer items-center gap-1 whitespace-nowrap rounded bg-white/10 px-2 py-1 text-xs text-neutral-200 hover:bg-white/20 ${className}`}>
      {current}
      <span className="text-[10px] opacity-60">▼</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="畫質"
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0">
        {canDirect && (
          <option value={ORIGINAL}>原始{bitRate ? ` · ${fmtBitrate(bitRate)}` : ''}</option>
        )}
        {levels.map((l) => (
          <option key={l.key} value={l.key}>{l.label} · ≤{kbpsText(l.kbps)}</option>
        ))}
      </select>
    </label>
  )
}

const Icon = {
  play: <path d="M8 5.5v13l11-6.5z" fill="currentColor" />,
  pause: <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" />,
  enter: <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" fill="none" stroke="currentColor" strokeWidth="2" />,
  exit: <path d="M9 4v5H4M20 9h-5V4M15 20v-5h5M4 15h5v5" fill="none" stroke="currentColor" strokeWidth="2" />,
}

const svg = (name, cls = 'h-5 w-5') => (
  <svg viewBox="0 0 24 24" className={cls} aria-hidden="true">{Icon[name]}</svg>
)

const BUTTON = 'flex h-8 shrink-0 items-center justify-center rounded bg-white/10 px-2 hover:bg-white/20'

// Plays the original file when the browser can and 原始 is chosen. Otherwise the server transcodes live at
// the chosen level (ffmpeg -> fragmented MP4 from `offset` seconds, bit rate capped), which can't be seeked
// by the browser itself, so seeking restarts the stream at the new position and the controls show
// offset + currentTime. Both use the same controls. The 畫質 starts at the 設定 page's default (per
// browser); a choice made in the player only applies to this video.
// Controls hide while playing after 3 s (mouse: move to show, click toggles play; touch: tap shows / hides
// them, the round button in the middle plays / pauses). Fullscreen fills the whole screen (also under the
// notch, 填滿 crops to the screen's shape, 完整 shows the whole picture) and turns phones to the video's
// orientation. `container` (the page's wrapper) is what goes fullscreen, so it stays fullscreen when the
// page swaps in the next video.
// Touch: swiping sideways switches to `nav.prev` / `nav.next` (like Telegram: the picture follows the
// finger, the neighbor's screenshot from `posterOf(dir)` slides in), then calls onSwipe(dir).
export default function Player({ video, startAt = 0, onTime, container, nav = {}, onSwipe, posterOf }) {
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
  const fsTarget = () => container?.current || box.current
  const [fs, setFs] = useState(() => Boolean(document.fullscreenElement) && document.fullscreenElement === container?.current)
  const [fill, setFill] = useState(fillScreen)
  const [active, setActive] = useState(true)
  const hideTimer = useRef(null)
  const pointer = useRef('mouse')
  const swipe = useRef(null) // touch in progress: { x, y, t, dx, dir }
  const swipedAt = useRef(0)
  const [dragX, setDragX] = useState(0)
  const [gliding, setGliding] = useState(false) // animate the picture back / out

  const src = mode === 'direct' ? `${MEDIA}/${video.id}/file` : `${MEDIA}/${video.id}/stream?t=${offset.toFixed(2)}&q=${quality}`
  const now = () => (mode === 'direct' ? ref.current?.currentTime || 0 : offset + (ref.current?.currentTime || 0))
  const showControls = dragX === 0 && (!playing || active || dragging !== null)

  function poke() {
    setActive(true)
    clearTimeout(hideTimer.current)
    hideTimer.current = setTimeout(() => setActive(false), HIDE_AFTER)
  }

  useEffect(() => () => clearTimeout(hideTimer.current), [])

  function changeQuality(q) {
    const t = now()
    setOffset(t)
    setTime(t)
    setWaiting(true)
    setQuality(q) // this video only; the default is set on the 設定 page
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

  function commitDrag() {
    if (dragging !== null) seek(dragging)
    setDragging(null)
  }

  function toggle() {
    const v = ref.current
    if (!v) return
    v.paused ? v.play().catch(() => {}) : v.pause()
  }

  async function fullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {})
      return
    }
    const target = fsTarget()
    if (target?.requestFullscreen) {
      setViewportFit(true)
      try {
        await target.requestFullscreen({ navigationUI: 'hide' })
        lockOrientation(ref.current)
      } catch {
        setViewportFit(false)
      }
    } else {
      ref.current?.webkitEnterFullscreen?.() // iPhone: only the video element itself can go fullscreen
    }
  }

  useEffect(() => {
    const onChange = () => {
      const on = Boolean(document.fullscreenElement) && document.fullscreenElement === fsTarget()
      setFs((was) => {
        // the page under it may have scrolled (other videos swapped in): bring the player back into view
        if (was && !on) requestAnimationFrame(() => box.current?.scrollIntoView({ block: 'nearest' }))
        return on
      })
    }
    document.addEventListener('fullscreenchange', onChange)
    return () => {
      document.removeEventListener('fullscreenchange', onChange)
      if (!document.fullscreenElement) setViewportFit(false)
    }
  }, [])

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
      else return
      poke()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  useEffect(() => {
    if (ref.current) ref.current.volume = volume
  }, [volume, src])

  // ── swipe to the previous / next video (touch) ──

  const canSwipe = Boolean(onSwipe && (nav.prev || nav.next))

  function onTouchStart(e) {
    // anywhere on the picture (also the round play button), not on the control bar
    if (!canSwipe || e.touches.length !== 1 || e.target.closest('[data-controls]')) {
      if (swipe.current) settle()
      swipe.current = null
      return
    }
    const t = e.touches[0]
    swipe.current = { x: t.clientX, y: t.clientY, t: Date.now(), dx: 0, dir: null }
    setGliding(false)
  }

  function onTouchMove(e) {
    const s = swipe.current
    if (!s || e.touches.length !== 1) return
    const dx = e.touches[0].clientX - s.x
    const dy = e.touches[0].clientY - s.y
    if (!s.dir && Math.max(Math.abs(dx), Math.abs(dy)) > 8) s.dir = Math.abs(dx) > Math.abs(dy) ? 'h' : 'v'
    if (s.dir !== 'h') return
    s.dx = dx
    const edge = (dx > 0 && !nav.prev) || (dx < 0 && !nav.next)
    setDragX(edge ? dx / 4 : dx) // resist at the first / last video
  }

  function settle() {
    setGliding(true)
    setDragX(0)
  }

  function onTouchEnd() {
    const s = swipe.current
    swipe.current = null
    if (!s || s.dir !== 'h') return
    swipedAt.current = Date.now()
    const flick = Math.abs(s.dx) >= SWIPE_MIN / 2 && Math.abs(s.dx) / Math.max(1, Date.now() - s.t) > 0.5
    const far = Math.abs(s.dx) >= SWIPE_MIN || flick
    const dir = s.dx < 0 ? 'next' : 'prev'
    if (!far || !nav[dir]) return settle()
    const width = box.current?.clientWidth || window.innerWidth
    setGliding(true)
    setDragX(dir === 'next' ? -width : width) // slide out, the neighbor's screenshot slides in
    ref.current?.pause()
    setTimeout(() => onSwipe(dir), 200)
  }

  const events = {
    onPlay: () => {
      setPlaying(true)
      poke()
    },
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
      lockOrientation(ref.current) // swiped to a video of the other orientation while fullscreen
    },
    onError: () => {
      if (mode === 'direct') {
        // the browser could not decode the original after all: fall back to live transcoding
        setOffset(time)
        setQuality(levelAtMost(levels, '720h'))
      }
    },
  }

  function onVideoClick() {
    if (Date.now() - swipedAt.current < 400) return
    if (pointer.current === 'mouse') {
      toggle()
      poke()
    } else if (showControls && playing) {
      clearTimeout(hideTimer.current)
      setActive(false)
    } else poke()
  }

  const fit = fs ? `h-full w-full ${fill ? 'object-cover' : 'object-contain'}` : 'aspect-video w-full object-contain'
  const neighbor = (dir) => {
    const url = dragX !== 0 && nav[dir] ? posterOf?.(dir) : null
    return (
      <div className={`absolute inset-y-0 w-full bg-black ${dir === 'prev' ? 'right-full' : 'left-full'}`}>
        {url && <img src={url} alt="" draggable={false} className={`h-full w-full ${fs && fill ? 'object-cover' : 'object-contain'}`} />}
      </div>
    )
  }

  const shown = dragging ?? time
  return (
    <div
      ref={box}
      onPointerMove={(e) => e.pointerType === 'mouse' && poke()}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      onTouchCancel={() => {
        if (swipe.current?.dir === 'h') settle()
        swipe.current = null
      }}
      style={canSwipe ? { touchAction: 'pan-y pinch-zoom' } : undefined}
      className={`relative overflow-hidden bg-black ${fs ? 'h-full w-full' : 'rounded-xl'} ${showControls ? '' : 'cursor-none'}`}
    >
      <div
        style={{ transform: dragX ? `translateX(${dragX}px)` : undefined }}
        className={`relative ${fs ? 'h-full' : ''} ${gliding ? 'transition-transform duration-200 ease-out' : ''}`}
      >
        {neighbor('prev')}
        <video
          ref={ref}
          key={src}
          src={src}
          poster={offset === 0 ? video.shots?.[0] : undefined}
          autoPlay
          playsInline
          onPointerDown={(e) => (pointer.current = e.pointerType)}
          onClick={onVideoClick}
          className={`block bg-black ${fit}`}
          {...events}
        />
        {neighbor('next')}
      </div>
      {waiting && dragX === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/30 border-t-white" />
        </div>
      )}
      {nav.total > 1 && showControls && (
        <span className="pointer-events-none absolute right-[max(0.5rem,env(safe-area-inset-right))] top-[max(0.5rem,env(safe-area-inset-top))] rounded bg-black/60 px-2 py-0.5 text-xs tabular-nums text-neutral-200">
          {nav.index} / {nav.total}
          <span className="hidden pointer-coarse:inline"> · 左右滑動切換</span>
        </span>
      )}
      {/* touch: tapping the video only shows / hides the controls, so play / pause sits in the middle.
          Hidden, not removed: a swipe that starts on it must keep its touch target in the page. */}
      <button
        onClick={() => {
          if (Date.now() - swipedAt.current < 400) return
          toggle()
          poke()
        }}
        aria-label={playing ? '暫停' : '播放'}
        aria-hidden={!showControls || waiting}
        tabIndex={showControls && !waiting ? 0 : -1}
        className={`absolute left-1/2 top-1/2 flex h-14 w-14 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 transition-opacity pointer-fine:hidden ${
          showControls && !waiting ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      >
        {svg(playing ? 'pause' : 'play', 'h-7 w-7')}
      </button>
      <div
        data-controls
        onPointerDown={poke}
        className={`absolute inset-x-0 bottom-0 space-y-1.5 bg-gradient-to-t from-black/90 via-black/50 to-transparent pt-10 text-sm transition-opacity duration-300
          pb-[max(0.5rem,env(safe-area-inset-bottom))] pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))]
          ${showControls ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
      >
        <div className="flex items-center gap-2 text-xs tabular-nums text-neutral-300">
          <span className="shrink-0">{fmtDuration(shown)}</span>
          <input
            type="range"
            className="seek min-w-0 flex-1"
            min={0}
            max={duration || 1}
            step={0.5}
            value={Math.min(shown, duration || shown)}
            onChange={(e) => setDragging(Number(e.target.value))}
            onPointerUp={commitDrag}
            onPointerCancel={commitDrag}
            onTouchEnd={commitDrag}
            onKeyUp={commitDrag}
            aria-label="進度"
          />
          <span className="shrink-0">{fmtDuration(duration)}</span>
        </div>
        <div className="flex min-w-0 items-center gap-1.5 sm:gap-2">
          <button onClick={toggle} className={`${BUTTON} w-10`} aria-label={playing ? '暫停' : '播放'} title={playing ? '暫停（空白鍵）' : '播放（空白鍵）'}>
            {svg(playing ? 'pause' : 'play')}
          </button>
          <button onClick={() => seek(now() - 10)} className={`${BUTTON} text-xs`} title="倒退 10 秒（←）">-10s</button>
          <button onClick={() => seek(now() + 10)} className={`${BUTTON} text-xs`} title="快轉 10 秒（→）">+10s</button>
          <input
            type="range"
            className="seek !w-20 pointer-coarse:hidden"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onChange={(e) => setVolume(Number(e.target.value))}
            title="音量"
            aria-label="音量"
          />
          <span className={`ml-auto hidden text-xs sm:inline ${mode === 'stream' ? 'text-amber-300' : 'text-neutral-400'}`}>
            {mode === 'stream' ? '即時轉檔' : '原始檔'}
          </span>
          <QualitySelect value={quality} onChange={changeQuality} levels={levels} canDirect={canDirect}
            bitRate={video.info?.bit_rate} className="ml-auto sm:ml-0" />
          {fs && (
            <button
              onClick={() => {
                setFill(!fill)
                setFillScreen(!fill)
              }}
              className={`${BUTTON} text-xs`}
              title={fill ? '目前填滿螢幕（可能裁掉邊緣），按一下顯示完整畫面' : '目前顯示完整畫面，按一下填滿螢幕'}
            >
              {fill ? '完整' : '填滿'}
            </button>
          )}
          <button onClick={fullscreen} className={`${BUTTON} w-10`} aria-label={fs ? '離開全螢幕' : '全螢幕'} title={fs ? '離開全螢幕（F）' : '全螢幕（F）'}>
            {svg(fs ? 'exit' : 'enter')}
          </button>
        </div>
      </div>
    </div>
  )
}
