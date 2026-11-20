import { useId, useState } from 'react'

// Multi-value input (e.g. 主演): Enter / comma adds a tag, × removes it, suggestions from existing tags.
export default function TagInput({ value, onChange, suggestions = [], placeholder }) {
  const [text, setText] = useState('')
  const listId = useId()

  function add(raw) {
    const names = raw.split(/[,，、]/).map((s) => s.trim()).filter(Boolean)
    const next = [...value]
    for (const n of names) if (!next.some((v) => v.toLowerCase() === n.toLowerCase())) next.push(n)
    onChange(next)
    setText('')
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-lg bg-neutral-800 px-2 py-1.5 ring-1 ring-white/10 focus-within:ring-accent">
      {value.map((tag) => (
        <span key={tag} className="flex items-center gap-1 rounded-md bg-accent/20 px-2 py-0.5 text-sm text-red-100">
          {tag}
          <button type="button" onClick={() => onChange(value.filter((v) => v !== tag))} className="text-red-200/70 hover:text-white" aria-label={`移除 ${tag}`}>
            ×
          </button>
        </span>
      ))}
      <input
        list={listId}
        value={text}
        onChange={(e) => {
          const v = e.target.value
          // picking a datalist suggestion fills the whole value at once
          if (suggestions.includes(v)) add(v)
          else setText(v)
        }}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ',') && text.trim()) {
            e.preventDefault()
            add(text)
          } else if (e.key === 'Backspace' && !text && value.length) {
            onChange(value.slice(0, -1))
          }
        }}
        onBlur={() => text.trim() && add(text)}
        placeholder={value.length ? '' : placeholder}
        className="min-w-24 flex-1 bg-transparent py-0.5 text-sm outline-none"
      />
      <datalist id={listId}>
        {suggestions.filter((s) => !value.includes(s)).map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
    </div>
  )
}
