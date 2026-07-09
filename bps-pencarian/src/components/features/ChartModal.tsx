import { useMemo, useState, useCallback } from "react"
import { X, Loader2, Table2, LineChart as LineIcon, BarChart3, ChevronDown, Check, ListTree } from "lucide-react"
import { ResponsiveContainer, LineChart, CartesianGrid, XAxis, YAxis, Tooltip, Legend, Line } from "recharts"
import { useTimeSeries, useCatalogSeries, type CatalogSeriesRow } from "../../lib/api"

interface ChartModalProps {
  item: {
    id?: number
    nomor_tabel?: string
    type: "tabel" | "indikator"
    title: string
    initialFilter?: string
    initialFilters?: string[]
  }
  onClose: () => void
}

function formatIndonesianNumber(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") return "-"
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(numeric)
}

function getValue(row: any) {
  return row.nilai ?? row.nilai_num
}

const chartColors = [
  "#2563eb", "#ea580c", "#16a34a", "#ca8a04", "#9333ea",
  "#0891b2", "#db2777", "#0d9488", "#c2410c", "#7c3aed",
  "#0369a1", "#b91c1c", "#15803d", "#a16207", "#6d28d9",
  "#0e7490", "#be185d", "#047857", "#b45309", "#4f46e5",
]

// Normalize unit case so "Jiwa" and "jiwa" merge into one indicator.
function normUnit(unit: string | undefined) {
  const u = (unit || "").trim().toLowerCase()
  return u === "none" ? "" : u
}

function metricKey(row: CatalogSeriesRow) {
  const unit = normUnit(row.unit)
  return `${row.subject_name}${unit ? ` (${unit})` : ""}`
}

// The dimension along which rows are split into separate lines.
type Dimension = "wilayah" | "rincian"

function dimensionValue(row: CatalogSeriesRow, dim: Dimension) {
  return dim === "wilayah" ? row.wilayah_nama : row.rincian_nama
}

const TRIVIAL_RINCIAN = new Set(["jumlah", "total"])

function isTrivial(dim: Dimension, value: string) {
  if (!value || value === "-") return true
  if (dim === "rincian" && TRIVIAL_RINCIAN.has(value.toLowerCase())) return true
  return false
}

const DIM_LABEL: Record<Dimension, string> = { wilayah: "Wilayah", rincian: "Rincian" }

// Persist chart selection per table (nomor_tabel) so the user's last choice
// (indicator + dimension + selected members) is remembered next time.
function storageKeyFor(item: ChartModalProps["item"]) {
  return item.nomor_tabel ? `bps_chart_sel_${item.nomor_tabel}` : `bps_chart_sel_id_${item.id ?? "x"}`
}

interface SavedSelection {
  dimension?: Dimension
  metric?: string
  sel?: { wilayah?: string[]; rincian?: string[] }
}

function loadSavedSelection(item: ChartModalProps["item"]): SavedSelection | null {
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(storageKeyFor(item)) : null
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === "object") return parsed
  } catch {
    /* ignore corrupt storage */
  }
  return null
}

function saveSelection(item: ChartModalProps["item"], sel: SavedSelection) {
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(storageKeyFor(item), JSON.stringify(sel))
    }
  } catch {
    /* ignore quota / private mode errors */
  }
}

export function ChartModal({ item, onClose }: ChartModalProps) {
  const merged = useCatalogSeries(item.nomor_tabel ?? null)
  const single = useTimeSeries(item.id ?? null, item.nomor_tabel ? null : item.type)
  const isMerged = Boolean(item.nomor_tabel)
  const { data, isLoading, error } = isMerged ? merged : single

  const [view, setView] = useState<"chart" | "table">("chart")

  const allRows: CatalogSeriesRow[] = useMemo(() => {
    if (!data) return []
    if (isMerged) return (data as any).series as CatalogSeriesRow[]
    return Array.isArray(data) ? data : (data as any).observations ?? []
  }, [data, isMerged])

  // --- Derived facets ---
  const metrics = useMemo(() => {
    const s = new Map<string, string>()
    allRows.forEach((r) => {
      const k = metricKey(r)
      if (!s.has(k)) s.set(k, k)
    })
    return Array.from(s.values()).sort()
  }, [allRows])

  const wilayahValues = useMemo(
    () => Array.from(new Set(allRows.map((r) => r.wilayah_nama).filter((v) => v && v !== "-"))).sort(),
    [allRows]
  )
  const rincianValues = useMemo(
    () =>
      Array.from(
        new Set(
          allRows
            .map((r) => r.rincian_nama)
            .filter((v) => v && v !== "-" && !TRIVIAL_RINCIAN.has(v.toLowerCase()))
        )
      ).sort(),
    [allRows]
  )

  const availableDims: Dimension[] = useMemo(() => {
    const dims: Dimension[] = []
    if (wilayahValues.length > 1) dims.push("wilayah")
    if (rincianValues.length > 1) dims.push("rincian")
    return dims
  }, [wilayahValues, rincianValues])

  // --- Selection state (initialized from saved localStorage if present) ---
  const savedRef = useMemo(() => loadSavedSelection(item), [item])
  const [selectedMetric, setSelectedMetric] = useState<string>(() => {
    const saved = savedRef?.metric
    return saved && metrics.includes(saved) ? saved : metrics[0] ?? ""
  })
  const [dimension, setDimension] = useState<Dimension>(() => {
    const saved = savedRef?.dimension
    if (saved && availableDims.includes(saved)) return saved
    // default to the richer dimension
    if (rincianValues.length >= wilayahValues.length && availableDims.includes("rincian")) return "rincian"
    return availableDims[0] ?? "wilayah"
  })
  const dimValues = dimension === "wilayah" ? wilayahValues : rincianValues

  const [selectedDim, setSelectedDim] = useState<Set<string>>(() => {
    const savedSel = savedRef?.sel?.[dimension]
    if (Array.isArray(savedSel) && savedSel.length > 0) {
      return new Set(savedSel.filter((v) => dimValues.includes(v)))
    }
    // legacy: old wilayah-only save (pre-dimension refactor)
    if (dimension === "wilayah" && Array.isArray((savedRef as any)?.wilayah)) {
      return new Set((savedRef as any).wilayah.filter((v: string) => dimValues.includes(v)))
    }
    return new Set()
  })
  const [dimDropdownOpen, setDimDropdownOpen] = useState(false)
  const [hasSaved] = useState<boolean>(() =>
    Boolean(savedRef && (savedRef.metric || (savedRef.sel && (savedRef.sel.wilayah?.length || savedRef.sel.rincian?.length))))
  )

  // Auto-select defaults only when there is NO saved selection. This runs once
  // data has loaded (allRows populated), so the chosen dimension/members are
  // computed from the real facets — not from the mount-time empty state that
  // caused the "first open shows Wilayah, second open shows Rincian" bug.
  const [hasAutoSelected, setHasAutoSelected] = useState(false)
  useMemo(() => {
    if (hasAutoSelected || hasSaved || metrics.length === 0 || dimValues.length === 0) return
    // Prefer the Rincian dimension when the table has one (richer breakdown),
    // otherwise fall back to the first available dimension.
    const richDim: Dimension = availableDims.includes("rincian")
      ? "rincian"
      : availableDims[0] ?? "wilayah"
    setDimension(richDim)
    const best = metrics.reduce((a, b) => {
      const countA = allRows.filter((r) => metricKey(r) === a).length
      const countB = allRows.filter((r) => metricKey(r) === b).length
      return countA >= countB ? a : b
    }, metrics[0])
    setSelectedMetric(best)
    const metricRows = allRows.filter(
      (r) => metricKey(r) === best && !isTrivial(richDim, dimensionValue(r, richDim)),
    )
    const counts = new Map<string, number>()
    metricRows.forEach((r) => {
      const v = dimensionValue(r, richDim)
      if (v && v !== "-") counts.set(v, (counts.get(v) ?? 0) + 1)
    })
    const top = Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([v]) => v)
    if (richDim === "wilayah" && counts.has("Kabupaten Tasikmalaya") && !top.includes("Kabupaten Tasikmalaya")) {
      top.push("Kabupaten Tasikmalaya")
    }
    setSelectedDim(new Set(top))
    setHasAutoSelected(true)
  }, [metrics, allRows, hasAutoSelected, hasSaved, dimension, dimValues, availableDims, wilayahValues, rincianValues])

  const persist = useCallback(
    (nextMetric: string, nextDim: Dimension, nextSel: Set<string>) => {
      saveSelection(item, {
        dimension: nextDim,
        metric: nextMetric,
        sel: { ...(savedRef?.sel ?? {}), [nextDim]: Array.from(nextSel).sort() },
      })
    },
    [item, savedRef]
  )

  const metricChanged = useCallback(
    (newMetric: string) => {
      setSelectedMetric(newMetric)
      setDimDropdownOpen(false)
      persist(newMetric, dimension, selectedDim)
    },
    [persist, dimension, selectedDim]
  )

  const dimensionChanged = useCallback(
    (newDim: Dimension) => {
      setDimension(newDim)
      const newValues = newDim === "wilayah" ? wilayahValues : rincianValues
      const savedSel = savedRef?.sel?.[newDim]
      const initial =
        Array.isArray(savedSel) && savedSel.length > 0
          ? new Set(savedSel.filter((v) => newValues.includes(v)))
          : new Set<string>()
      setSelectedDim(initial)
      persist(selectedMetric, newDim, initial)
    },
    [persist, savedRef, selectedMetric, wilayahValues, rincianValues]
  )

  const toggleDim = useCallback(
    (v: string) => {
      setSelectedDim((prev) => {
        const next = new Set(prev)
        if (next.has(v)) next.delete(v)
        else next.add(v)
        persist(selectedMetric, dimension, next)
        return next
      })
    },
    [persist, selectedMetric, dimension]
  )

  const selectAllDim = useCallback(() => {
    setSelectedDim(new Set(dimValues))
    persist(selectedMetric, dimension, new Set(dimValues))
  }, [persist, selectedMetric, dimension, dimValues])

  const clearAllDim = useCallback(() => {
    setSelectedDim(new Set())
    persist(selectedMetric, dimension, new Set())
  }, [persist, selectedMetric, dimension])

  // --- Chart data: pivot by (year × dimension value) ---
  const chartData = useMemo(() => {
    const metricRows = allRows.filter((r) => metricKey(r) === selectedMetric)
    const byYear: Record<string, Record<string, number | null>> = {}
    const selected = selectedDim

    metricRows.forEach((row) => {
      const dim = dimensionValue(row, dimension)
      if (isTrivial(dimension, dim)) return
      if (selected.size > 0 && !selected.has(dim)) return
      const year = String(row.tahun ?? "")
      if (!byYear[year]) byYear[year] = { tahun: Number(row.tahun) }
      byYear[year][dim] = Number(getValue(row))
    })

    const lines =
      selected.size > 0
        ? Array.from(selected).sort()
        : // fallback: all dimension values in this metric (limit to 8 for readability)
          Array.from(
            new Set(
              metricRows
                .map((r) => dimensionValue(r, dimension))
                .filter((v) => !isTrivial(dimension, v))
            )
          ).sort().slice(0, 8)

    return {
      points: Object.values(byYear).sort((a, b) => Number(a.tahun) - Number(b.tahun)),
      lines,
    }
  }, [allRows, selectedMetric, selectedDim, dimension])

  const hasRows = allRows.length > 0
  const metricUnit = normUnit(allRows.find((r) => metricKey(r) === selectedMetric)?.unit)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      <div className="absolute inset-0 bg-background/80" onClick={onClose}></div>
      <div className="relative bg-card border border-border shadow-lg rounded-md w-full max-w-6xl h-[88vh] flex flex-col animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="min-w-0 pr-12">
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">
              {isMerged ? "Grafik time-series (gabungan semua publikasi)" : "Tabel data dari database"}
            </p>
            <h2 className="mt-1 text-xl font-semibold text-foreground truncate" title={item.title}>
              {item.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors absolute right-4"
            aria-label="Tutup detail"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6 flex flex-col gap-5">
          {isLoading ? (
            <div className="flex-1 min-h-[420px] flex flex-col items-center justify-center text-primary rounded-md border border-dashed border-border bg-muted/20">
              <Loader2 className="h-10 w-10 animate-spin mb-4" />
              <p className="text-sm font-medium animate-pulse">Memuat data…</p>
            </div>
          ) : error ? (
            <div className="flex-1 min-h-[420px] flex items-center justify-center text-destructive rounded-md border border-destructive/20 bg-destructive/5">
              Gagal memuat data dari database.
            </div>
          ) : !hasRows ? (
            <div className="flex-1 min-h-[420px] flex flex-col items-center justify-center rounded-md border border-dashed border-border bg-muted/20 text-center">
              <Table2 className="h-9 w-9 text-muted-foreground mb-3" />
              <p className="text-base font-semibold text-foreground">Tidak ada data</p>
              <p className="mt-1 text-sm text-muted-foreground">Database belum memiliki observasi untuk pilihan ini.</p>
            </div>
          ) : (
            <>
              {/* Controls row */}
              <div className="flex flex-wrap items-center gap-3">
                {/* View toggle */}
                <div className="flex items-center gap-1 rounded-md border border-border bg-background p-1">
                  <button
                    type="button"
                    onClick={() => setView("chart")}
                    className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold transition-colors ${view === "chart" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
                  >
                    <LineIcon className="h-4 w-4" /> Grafik
                  </button>
                  <button
                    type="button"
                    onClick={() => setView("table")}
                    className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold transition-colors ${view === "table" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
                  >
                    <BarChart3 className="h-4 w-4" /> Tabel
                  </button>
                </div>

                {/* Metric selector */}
                {metrics.length > 1 && (
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-semibold text-muted-foreground whitespace-nowrap">Indikator:</label>
                    <select
                      value={selectedMetric}
                      onChange={(e) => metricChanged(e.target.value)}
                      className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                    >
                      {metrics.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Dimension selector (Wilayah / Rincian) */}
                {availableDims.length > 1 && (
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-semibold text-muted-foreground whitespace-nowrap">Dimensi:</label>
                    <div className="flex items-center gap-1 rounded-md border border-border bg-background p-1">
                      {availableDims.map((dim) => (
                        <button
                          key={dim}
                          type="button"
                          onClick={() => dimensionChanged(dim)}
                          className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-semibold transition-colors ${dimension === dim ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
                        >
                          {dim === "rincian" && <ListTree className="h-3.5 w-3.5" />}
                          {DIM_LABEL[dim]}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Dimension member multi-select */}
                {dimValues.length > 0 && (
                  <div className="relative">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setDimDropdownOpen(!dimDropdownOpen)
                      }}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors"
                    >
                      {DIM_LABEL[dimension]} ({selectedDim.size}/{dimValues.length})
                      <ChevronDown className={`h-3.5 w-3.5 transition-transform ${dimDropdownOpen ? "rotate-180" : ""}`} />
                    </button>
                    {dimDropdownOpen && (
                      <>
                        <div
                          className="fixed inset-0 z-40"
                          onClick={(e) => {
                            e.stopPropagation()
                            setDimDropdownOpen(false)
                          }}
                        />
                        <div
                          className="absolute z-50 mt-1 w-72 max-h-80 rounded-md border border-border bg-card shadow-lg overflow-hidden"
                          onClick={(e) => e.stopPropagation()}
                          onMouseDown={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center justify-between border-b border-border px-3 py-2">
                            <span className="text-xs font-semibold text-foreground">Pilih {DIM_LABEL[dimension]}</span>
                            <div className="flex gap-2">
                              <button onClick={selectAllDim} className="text-[10px] font-semibold text-primary hover:underline">Semua</button>
                              <button onClick={clearAllDim} className="text-[10px] font-semibold text-muted-foreground hover:underline">Hapus</button>
                            </div>
                          </div>
                          <div className="overflow-auto max-h-[240px] p-2">
                            {dimValues.map((v) => {
                              const checked = selectedDim.has(v)
                              return (
                                <div
                                  key={v}
                                  role="button"
                                  tabIndex={0}
                                  aria-pressed={checked}
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    toggleDim(v)
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter" || e.key === " ") {
                                      e.preventDefault()
                                      e.stopPropagation()
                                      toggleDim(v)
                                    }
                                  }}
                                  className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50 cursor-pointer text-xs select-none"
                                >
                                  <span className={`h-4 w-4 rounded border flex items-center justify-center shrink-0 transition-colors ${checked ? "bg-primary border-primary" : "border-border bg-background"}`}>
                                    {checked && <Check className="h-3 w-3 text-primary-foreground" />}
                                  </span>
                                  <span className="text-foreground">{v}</span>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Chart / Table */}
              {view === "chart" ? (
                <div className="rounded-md border border-border bg-background p-4 min-h-[440px] flex-1">
                  {chartData.lines.length === 0 ? (
                    <div className="h-full min-h-[400px] flex items-center justify-center text-muted-foreground text-sm">
                      Pilih minimal satu {DIM_LABEL[dimension].toLowerCase()} untuk menampilkan grafik.
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData.points} margin={{ top: 12, right: 16, left: 0, bottom: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                        <XAxis
                          dataKey="tahun"
                          axisLine={false}
                          tickLine={false}
                          tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
                        />
                        <YAxis
                          axisLine={false}
                          tickLine={false}
                          width={72}
                          tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
                          tickFormatter={(value) => formatIndonesianNumber(value)}
                        />
                        <Tooltip
                          formatter={(value, name) => [`${formatIndonesianNumber(value as number)}${metricUnit ? ` ${metricUnit}` : ""}`, String(name)]}
                          labelFormatter={(label) => `Tahun ${label}`}
                          contentStyle={{
                            backgroundColor: "hsl(var(--card))",
                            borderColor: "hsl(var(--border))",
                            color: "hsl(var(--foreground))",
                            borderRadius: "0.375rem",
                            fontSize: "0.75rem",
                          }}
                        />
                        <Legend wrapperStyle={{ paddingTop: 12 }} />
                        {chartData.lines.map((key, index) => (
                          <Line
                            key={key}
                            type="monotone"
                            dataKey={key}
                            name={key}
                            stroke={chartColors[index % chartColors.length]}
                            strokeWidth={2}
                            activeDot={{ r: 5, strokeWidth: 0 }}
                            dot={{ r: 3, strokeWidth: 0 }}
                            connectNulls
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </div>
              ) : (
                <div className="rounded-md border border-border bg-background overflow-hidden flex-1">
                  <div className="max-h-[58vh] overflow-auto">
                    <table className="w-full min-w-[760px] text-sm">
                      <thead className="sticky top-0 bg-background z-10 shadow-[0_1px_0_hsl(var(--border))]">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Tahun</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{DIM_LABEL[dimension]}</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Nilai</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Rincian</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {allRows
                          .filter((row: any) => metricKey(row) === selectedMetric)
                          .filter((row: any) => {
                            if (selectedDim.size === 0) return true
                            return selectedDim.has(dimensionValue(row, dimension))
                          })
                          .map((row: any) => (
                            <tr key={row.id} className="border-b border-border last:border-0 hover:bg-muted/30">
                              <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.tahun ?? "-"}</td>
                              <td className="px-4 py-3 font-medium text-foreground whitespace-nowrap">{dimensionValue(row, dimension) || "-"}</td>
                              <td className="px-4 py-3 text-right font-semibold text-foreground whitespace-nowrap">
                                {formatIndonesianNumber(getValue(row))}{row.unit && normUnit(row.unit) ? ` ${normUnit(row.unit)}` : ""}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.rincian_nama && row.rincian_nama !== "-" ? row.rincian_nama : "-"}</td>
                              <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.flag || "ada"}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
