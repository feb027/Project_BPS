import { useMemo, useState, useCallback } from "react"
import { X, Loader2, Table2, LineChart as LineIcon, BarChart3, ChevronDown, Check } from "lucide-react"
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

function metricKey(row: CatalogSeriesRow) {
  const unit = row.unit && row.unit !== "-" ? row.unit : ""
  return `${row.subject_name}${unit ? ` (${unit})` : ""}`
}

// Persist chart selection per table (nomor_tabel) so the user's last choice
// (indicator + kecamatan) is remembered next time they open the same table.
function storageKeyFor(item: ChartModalProps["item"]) {
  return item.nomor_tabel ? `bps_chart_sel_${item.nomor_tabel}` : `bps_chart_sel_id_${item.id ?? "x"}`
}

function loadSavedSelection(item: ChartModalProps["item"]): { metric?: string; wilayah?: string[] } | null {
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

function saveSelection(item: ChartModalProps["item"], metric: string, wilayah: string[]) {
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(storageKeyFor(item), JSON.stringify({ metric, wilayah }))
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
    const s = new Map<string, string>() // key -> display label
    allRows.forEach((r) => {
      const k = metricKey(r)
      if (!s.has(k)) s.set(k, k)
    })
    return Array.from(s.values()).sort()
  }, [allRows])

  const allWilayah = useMemo(() => {
    const s = new Set<string>()
    allRows.forEach((r) => {
      const w = r.wilayah_nama
      if (w && w !== "-") s.add(w)
    })
    return Array.from(s).sort()
  }, [allRows])

  // --- Selection state (initialized from saved localStorage if present) ---
  const savedRef = useMemo(() => loadSavedSelection(item), [item])
  const [selectedMetric, setSelectedMetric] = useState<string>(() => savedRef?.metric && metrics.includes(savedRef.metric) ? savedRef.metric : (metrics[0] ?? ""))
  const [selectedWilayah, setSelectedWilayah] = useState<Set<string>>(() => {
    const saved = savedRef?.wilayah
    if (Array.isArray(saved) && saved.length > 0) {
      return new Set(saved.filter((w) => allWilayah.includes(w)))
    }
    return new Set()
  })
  const [wilayahDropdownOpen, setWilayahDropdownOpen] = useState(false)
  // Tracks whether a real saved selection existed, so we don't auto-overwrite it.
  const [hasSaved] = useState<boolean>(() => Boolean(savedRef && (savedRef.metric || (Array.isArray(savedRef.wilayah) && savedRef.wilayah.length > 0))))

  // Auto-select defaults only when there is NO saved selection.
  const [hasAutoSelected, setHasAutoSelected] = useState(false)
  useMemo(() => {
    if (hasAutoSelected || hasSaved || metrics.length === 0) return
    const best = metrics.reduce((a, b) => {
      const countA = allRows.filter((r) => metricKey(r) === a).length
      const countB = allRows.filter((r) => metricKey(r) === b).length
      return countA >= countB ? a : b
    }, metrics[0])
    setSelectedMetric(best)
    const metricRows = allRows.filter((r) => metricKey(r) === best)
    const wilCounts = new Map<string, number>()
    metricRows.forEach((r) => {
      const w = r.wilayah_nama
      if (w && w !== "-") wilCounts.set(w, (wilCounts.get(w) ?? 0) + 1)
    })
    const top = Array.from(wilCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([w]) => w)
    if (wilCounts.has("Kabupaten Tasikmalaya") && !top.includes("Kabupaten Tasikmalaya")) {
      top.push("Kabupaten Tasikmalaya")
    }
    setSelectedWilayah(new Set(top))
    setHasAutoSelected(true)
  }, [metrics, allRows, hasAutoSelected, hasSaved])

  const persist = useCallback((metric: string, wilayah: Set<string>) => {
    saveSelection(item, metric, Array.from(wilayah).sort())
  }, [item])

  const metricChanged = useCallback((newMetric: string) => {
    setSelectedMetric(newMetric)
    setWilayahDropdownOpen(false)
    persist(newMetric, selectedWilayah)
  }, [persist, selectedWilayah])

  const toggleWilayah = useCallback((w: string) => {
    setSelectedWilayah((prev) => {
      const next = new Set(prev)
      if (next.has(w)) next.delete(w)
      else next.add(w)
      persist(selectedMetric, next)
      return next
    })
  }, [persist, selectedMetric])

  const selectAllWilayah = useCallback(() => {
    setSelectedWilayah(new Set(allWilayah))
    persist(selectedMetric, new Set(allWilayah))
  }, [persist, selectedMetric, allWilayah])

  const clearAllWilayah = useCallback(() => {
    setSelectedWilayah(new Set())
    persist(selectedMetric, new Set())
  }, [persist, selectedMetric])

  // --- Chart data: pivot by (year × kecamatan) ---
  const chartData = useMemo(() => {
    const metricRows = allRows.filter((r) => metricKey(r) === selectedMetric)
    const byYear: Record<string, Record<string, number | null>> = {}
    const selected = selectedWilayah

    metricRows.forEach((row) => {
      const wil = row.wilayah_nama || "-"
      if (selected.size > 0 && !selected.has(wil)) return
      const year = String(row.tahun ?? "")
      if (!byYear[year]) byYear[year] = { tahun: Number(row.tahun) }
      byYear[year][wil] = Number(getValue(row))
    })

    const lines = selected.size > 0
      ? Array.from(selected).sort()
      : // fallback: all wilayah in this metric (limit to 8 for readability)
        Array.from(new Set(metricRows.map((r) => r.wilayah_nama || "-"))).sort().slice(0, 8)

    return {
      points: Object.values(byYear).sort((a, b) => Number(a.tahun) - Number(b.tahun)),
      lines,
    }
  }, [allRows, selectedMetric, selectedWilayah])

  const hasRows = allRows.length > 0
  const metricUnit = allRows.find((r) => metricKey(r) === selectedMetric)?.unit

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

                {/* Kecamatan multi-select */}
                {allWilayah.length > 0 && (
                  <div className="relative">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setWilayahDropdownOpen(!wilayahDropdownOpen)
                      }}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors"
                    >
                      Kecamatan ({selectedWilayah.size}/{allWilayah.length})
                      <ChevronDown className={`h-3.5 w-3.5 transition-transform ${wilayahDropdownOpen ? "rotate-180" : ""}`} />
                    </button>
                    {wilayahDropdownOpen && (
                      <>
                        {/* Backdrop closes the dropdown when clicking outside the panel.
                            It sits first so a click on the panel never reaches it. */}
                        <div
                          className="fixed inset-0 z-40"
                          onClick={(e) => {
                            e.stopPropagation()
                            setWilayahDropdownOpen(false)
                          }}
                        />
                        <div
                          className="absolute z-50 mt-1 w-72 max-h-80 rounded-md border border-border bg-card shadow-lg overflow-hidden"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center justify-between border-b border-border px-3 py-2">
                            <span className="text-xs font-semibold text-foreground">Pilih Kecamatan</span>
                            <div className="flex gap-2">
                              <button onClick={selectAllWilayah} className="text-[10px] font-semibold text-primary hover:underline">Semua</button>
                              <button onClick={clearAllWilayah} className="text-[10px] font-semibold text-muted-foreground hover:underline">Hapus</button>
                            </div>
                          </div>
                          <div className="overflow-auto max-h-[240px] p-2">
                            {allWilayah.map((w) => {
                              const checked = selectedWilayah.has(w)
                              return (
                                <label
                                  key={w}
                                  className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50 cursor-pointer text-xs"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <span className={`h-4 w-4 rounded border flex items-center justify-center shrink-0 transition-colors ${checked ? "bg-primary border-primary" : "border-border bg-background"}`}>
                                    {checked && <Check className="h-3 w-3 text-primary-foreground" />}
                                  </span>
                                  <input
                                    type="checkbox"
                                    className="sr-only"
                                    checked={checked}
                                    onChange={() => toggleWilayah(w)}
                                  />
                                  <span className="text-foreground">{w}</span>
                                </label>
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
                      Pilih minimal satu kecamatan untuk menampilkan grafik.
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
                          formatter={(value, name) => [`${formatIndonesianNumber(value as number)}${metricUnit && metricUnit !== "-" ? ` ${metricUnit}` : ""}`, String(name)]}
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
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Wilayah</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Nilai</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Rincian</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {allRows
                          .filter((row: any) => metricKey(row) === selectedMetric)
                          .filter((row: any) => {
                            if (selectedWilayah.size === 0) return true
                            return selectedWilayah.has(row.wilayah_nama)
                          })
                          .map((row: any) => (
                            <tr key={row.id} className="border-b border-border last:border-0 hover:bg-muted/30">
                              <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.tahun ?? "-"}</td>
                              <td className="px-4 py-3 font-medium text-foreground whitespace-nowrap">{row.wilayah_nama || "-"}</td>
                              <td className="px-4 py-3 text-right font-semibold text-foreground whitespace-nowrap">
                                {formatIndonesianNumber(getValue(row))}{row.unit && row.unit !== "-" ? ` ${row.unit}` : ""}
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
