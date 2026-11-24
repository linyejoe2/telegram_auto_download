import { useState } from 'react'
import AppMenu from '../components/AppMenu.jsx'
import {
  defaultQuality, fillScreen, kbpsText, LEVELS, ORIGINAL, perHourText, setDefaultQuality, setFillScreen,
} from '../settings.js'

// 設定: playback preferences of this browser (stored in localStorage, so every device keeps its own)

function Option({ name, checked, onChange, title, detail }) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-lg px-3 py-2.5 ring-1 transition ${
        checked ? 'bg-accent/15 ring-accent/70' : 'bg-neutral-900 ring-white/10 hover:ring-white/25'
      }`}
    >
      <input type="radio" name={name} checked={checked} onChange={onChange} className="mt-1 accent-[var(--color-accent)]" />
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        {detail && <span className="block text-xs text-neutral-400">{detail}</span>}
      </span>
    </label>
  )
}

export default function Settings({ onLogout }) {
  const [quality, setQuality] = useState(defaultQuality)
  const [fill, setFill] = useState(fillScreen)
  const [saved, setSaved] = useState(false)

  function done() {
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }

  function pickQuality(q) {
    setQuality(q)
    setDefaultQuality(q)
    done()
  }

  function pickFill(value) {
    setFill(value)
    setFillScreen(value)
    done()
  }

  return (
    <div className="mx-auto max-w-2xl px-4 pb-16">
      <header className="sticky top-0 z-10 -mx-4 mb-4 flex items-center gap-3 bg-neutral-950/90 px-4 py-3 backdrop-blur">
        <h1 className="text-lg font-semibold">設定</h1>
        <span className={`ml-auto text-sm text-emerald-400 transition-opacity ${saved ? 'opacity-100' : 'opacity-0'}`} aria-live="polite">
          已儲存
        </span>
        <AppMenu onLogout={onLogout} />
      </header>

      <p className="mb-6 rounded-lg bg-neutral-900 px-3 py-2 text-xs text-neutral-400 ring-1 ring-white/10">
        這些設定只存在這個瀏覽器，手機和電腦可以各自設定（例如手機用 720p 低省流量，電腦用原始）。
      </p>

      <section className="mb-8 space-y-3">
        <div>
          <h2 className="font-semibold">預設播放畫質</h2>
          <p className="text-xs text-neutral-400">
            打開影片時用的畫質。播放器右下的畫質選單可以臨時切換，只套用在那部影片。
            影片解析度比選的畫質低時，用它能用的最高畫質。
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Option
              name="quality"
              checked={quality === ORIGINAL}
              onChange={() => pickQuality(ORIGINAL)}
              title="原始"
              detail="直接播放原始檔，畫質最好、跳轉最快，流量也最大；瀏覽器無法播放的格式會用最高的轉檔畫質"
            />
          </div>
          {LEVELS.map((l) => (
            <Option
              key={l.key}
              name="quality"
              checked={quality === l.key}
              onChange={() => pickQuality(l.key)}
              title={`${l.label}（即時轉檔）`}
              detail={`最高 ${kbpsText(l.kbps)} · 每小時約 ${perHourText(l.kbps)}`}
            />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="font-semibold">轉檔播放器全螢幕</h2>
          <p className="text-xs text-neutral-400">全螢幕時也可以用「填滿 / 完整」按鈕切換，切換後會記住。</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Option name="fill" checked={fill} onChange={() => pickFill(true)} title="填滿"
            detail="畫面填滿螢幕（含瀏海區域），沒有黑邊，邊緣可能被裁掉一點" />
          <Option name="fill" checked={!fill} onChange={() => pickFill(false)} title="完整"
            detail="顯示完整畫面，螢幕比例不同時兩側或上下會有黑邊" />
        </div>
      </section>
    </div>
  )
}
