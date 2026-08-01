import { useCallback, useState } from "react"

interface YearRangeSliderProps {
  min: number
  max: number
  value: [number, number]
  onChange: (value: [number, number]) => void
  disabled?: boolean
}

/**
 * Dual-thumb year range slider built from two stacked native <input type="range">.
 * The lower input sits on top (higher z-index) so its thumb stays reachable even
 * when both thumbs are at the same position. Thumb styling lives in App.css
 * under `.yr-slider` (WebKit + Mozilla pseudo-elements can't be set inline).
 */
export function YearRangeSlider({ min, max, value, onChange, disabled }: YearRangeSliderProps) {
  const [activeThumb, setActiveThumb] = useState<"lo" | "hi" | null>(null)

  const safeMin = Math.min(min, max)
  const safeMax = Math.max(min, max)

  const lo = Math.min(value[0], value[1])
  const hi = Math.max(value[0], value[1])

  const handleLo = useCallback(
    (raw: number) => {
      const next = Math.min(safeMax, Math.max(safeMin, raw))
      onChange([Math.min(next, hi), hi])
    },
    [onChange, safeMin, safeMax, hi]
  )

  const handleHi = useCallback(
    (raw: number) => {
      const next = Math.min(safeMax, Math.max(safeMin, raw))
      onChange([lo, Math.max(next, lo)])
    },
    [onChange, safeMin, safeMax, lo]
  )

  if (safeMin === safeMax) {
    // Only one year available — nothing to slide.
    return (
      <div className="text-xs text-muted-foreground">
        Hanya tersedia tahun {safeMin}.
      </div>
    )
  }

  const span = safeMax - safeMin
  const loPct = ((lo - safeMin) / span) * 100
  const hiPct = ((hi - safeMin) / span) * 100

  // Dynamic z-index so overlapping thumbs don't trap each other
  const loZ = activeThumb === "lo" ? 10 : lo === safeMax ? 3 : lo === hi ? 1 : 2
  const hiZ = activeThumb === "hi" ? 10 : hi === safeMin ? 3 : lo === hi ? 2 : 1

  return (
    <div className="yr-slider min-w-[170px] max-w-[220px]">
      <div className="relative h-4">
        <div className="absolute top-1/2 h-1 w-full -translate-y-1/2 rounded-full bg-muted" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-primary transition-all duration-75"
          style={{ left: `${loPct}%`, width: `${Math.max(hiPct - loPct, 0)}%` }}
        />
        <input
          type="range"
          min={safeMin}
          max={safeMax}
          step={1}
          value={lo}
          disabled={disabled}
          aria-label="Tahun awal"
          onChange={(e) => handleLo(Number(e.target.value))}
          onMouseDown={() => setActiveThumb("lo")}
          onTouchStart={() => setActiveThumb("lo")}
          onFocus={() => setActiveThumb("lo")}
          onBlur={() => setActiveThumb(null)}
          className="cursor-pointer"
          style={{ zIndex: loZ }}
        />
        <input
          type="range"
          min={safeMin}
          max={safeMax}
          step={1}
          value={hi}
          disabled={disabled}
          aria-label="Tahun akhir"
          onChange={(e) => handleHi(Number(e.target.value))}
          onMouseDown={() => setActiveThumb("hi")}
          onTouchStart={() => setActiveThumb("hi")}
          onFocus={() => setActiveThumb("hi")}
          onBlur={() => setActiveThumb(null)}
          className="cursor-pointer"
          style={{ zIndex: hiZ }}
        />
      </div>
      <div className="mt-0.5 flex items-center justify-between text-[10px] font-medium text-muted-foreground leading-none">
        <span>{lo}</span>
        <span className="text-muted-foreground/60">—</span>
        <span>{hi}</span>
      </div>
    </div>
  )
}

