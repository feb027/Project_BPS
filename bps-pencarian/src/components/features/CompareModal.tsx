import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { X, Loader2, AlertTriangle, BarChart3, Plus, Check, FileSpreadsheet, FileText, ChevronDown } from "lucide-react"
import { ResponsiveContainer, LineChart, CartesianGrid, XAxis, YAxis, Tooltip, Legend, Line } from "recharts"
import * as XLSX from "xlsx"
import html2canvas from "html2canvas-pro"
import { exportProfessionalPdf } from "../../lib/pdfExport"
import { useCatalogSeries, type CatalogSeriesRow } from "../../lib/api"
import { shortTitleForExport } from "../../lib/utils"
import { YearRangeSlider } from "./YearRangeSlider"
import { canonRincian, chartColors, formatCompactNumber, metricKey } from "./ChartModal"

export interface CompareItem {
  nomor_tabel: string
  title: string
  /** Concept hint from multi-concept search (e.g. "Jumlah Guru (SMA)") so a
      section can default to the matching metric when several concepts point
      to the same table (guru + murid SMA live in table 4.1.7). */
  metricHint?: string
}

interface CompareModalProps {
  items: CompareItem[]
  onClose: () => void
  onRemove: (nomorTabel: string) => void
}

const TRIVIAL_RINCIAN = new Set(["jumlah", "total"])

/**
 * Pick the metric whose words all appear in the hint, order-insensitively.
 * BPS names reorder words ("Jumlah Murid (SMA)" vs metric "Murid Jumlah"),
 * so matching is by word-set, not substring. Returns undefined when no metric
 * matches (caller falls back to the most-common metric).
 */
export function pickMetricByHint(metrics: string[], hint?: string): string | undefined {
  if (!hint) return undefined
  const base = (s: string) =>
    (s || "")
      .toLowerCase()
      .replace(/\(.*\)/g, "")
      .replace(/[^a-z0-9 ]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
  const hintWords = base(hint).split(" ").filter(Boolean)
  if (hintWords.length === 0) return undefined
  return metrics.find((m) => {
    const mWords = new Set(base(m).split(" ").filter(Boolean))
    return hintWords.every((w) => mWords.has(w))
  })
}

interface SectionProps {
  item: CompareItem
  index: number
  onRemove: () => void
  yearRange: [number, number] | null
  onReportRange: (min: number, max: number) => void
  onRowsReady: (index: number, payload: { nomor: string; title: string; metric: string; rows: Record<string, unknown>[] }) => void
}

export interface SectionExportRows {
  nomor: string
  title: string
  metric: string
  rows: Record<string, unknown>[]
}

const fmtVal = (v: unknown) => {
  if (v === null || v === undefined || v === "") return "-"
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(n)
}

// Pivot export rows: one row per member (wilayah/rincian), one column per
// year — far easier to read than long-format rows that repeat the year for
// every member. The satuan is merged into each value cell.
function buildPivot(rows: Record<string, unknown>[]) {
  if (!rows.length) return { header: ["Wilayah / Rincian"], body: [] as string[][], unit: "" }
  const first = rows[0]
  const dimKey = first && first["Wilayah"] ? "Wilayah" : "Rincian"
  const unit = String((rows.find((r) => r.Satuan)?.Satuan) || "").trim()
  const years = Array.from(new Set(rows.map((r) => String(r.Tahun)))).sort()
  const members = Array.from(new Set(rows.map((r) => String(r[dimKey] ?? "-")))).sort()
  const lookup: Record<string, Record<string, unknown>> = {}
  for (const r of rows) {
    const m = String(r[dimKey] ?? "-")
    const y = String(r.Tahun)
    if (!lookup[m]) lookup[m] = {}
    lookup[m][y] = r.Nilai
  }
  const cell = (v: unknown) => `${fmtVal(v)}${unit ? ` ${unit}` : ""}`
  return {
    header: ["Wilayah / Rincian", ...years],
    body: members.map((m) => [m, ...years.map((y) => cell(lookup[m]?.[y] ?? "-"))]),
    unit,
  }
}

function CompareTableSection({ item, index, onRemove, yearRange, onReportRange, onRowsReady }: SectionProps) {
  const { data, isLoading, error } = useCatalogSeries(item.nomor_tabel)
  const rows = (data?.series ?? []) as CatalogSeriesRow[]

  // Report the section's own year span so the parent can union all bounds.
  useEffect(() => {
    const years = rows
      .map((r) => r.tahun)
      .filter((y): y is number => typeof y === "number" && Number.isFinite(y))
    if (years.length > 0) {
      onReportRange(Math.min(...years), Math.max(...years))
    }
  }, [rows, onReportRange])

  const metrics = useMemo(() => {
    const s = new Map<string, string>()
    rows.forEach((r) => {
      const k = metricKey(r)
      if (!s.has(k)) s.set(k, k)
    })
    return Array.from(s.values()).sort()
  }, [rows])

  // Default metric: prefer the concept hint (multi-concept search) when it
  // matches; otherwise the metric with the most rows (mirrors ChartModal).
  const [selectedMetric, setSelectedMetric] = useState<string>("")
  useEffect(() => {
    if (metrics.length === 0) return
    setSelectedMetric((cur) => {
      if (cur && metrics.includes(cur)) return cur
      if (item.metricHint) {
        const byHint = pickMetricByHint(metrics, item.metricHint)
        if (byHint) return byHint
      }
      return metrics.reduce((best, m) => {
        const countBest = rows.filter((r) => metricKey(r) === best).length
        const countM = rows.filter((r) => metricKey(r) === m).length
        return countM > countBest ? m : best
      }, metrics[0])
    })
  }, [metrics, rows, item.metricHint])

  const metricRows = useMemo(
    () => rows.filter((r) => metricKey(r) === selectedMetric),
    [rows, selectedMetric]
  )

  // Dimension: prefer rincian (per-kategori tables), else wilayah.
  const rincianVals = useMemo(
    () =>
      Array.from(
        new Set(metricRows.map((r) => canonRincian(r.rincian_nama)).filter((v) => v && v !== "-" && !TRIVIAL_RINCIAN.has(v.toLowerCase())))
      ).sort(),
    [metricRows]
  )
  const wilayahVals = useMemo(
    () =>
      Array.from(new Set(metricRows.map((r) => r.wilayah_nama).filter((v) => v && v !== "-"))).sort(),
    [metricRows]
  )
  // Dimension + member selection per section (mirrors ChartModal):
  // user can pick Wilayah vs Rincian and tick which members to show.
  const [dimension, setDimension] = useState<"wilayah" | "rincian">("wilayah")
  const [selectedDim, setSelectedDim] = useState<Set<string>>(new Set())
  const [dimDropdownOpen, setDimDropdownOpen] = useState(false)
  const initDimRef = useRef(false)

  useEffect(() => {
    if (initDimRef.current || metricRows.length === 0) return
    initDimRef.current = true
    const useR = rincianVals.length >= 2 && rincianVals.length >= wilayahVals.length
    setDimension(useR ? "rincian" : "wilayah")
    const vals = useR ? rincianVals : wilayahVals
    if (!useR && vals.includes("Kabupaten Tasikmalaya")) {
      setSelectedDim(new Set(["Kabupaten Tasikmalaya"]))
    } else {
      setSelectedDim(new Set(vals))
    }
  }, [metricRows, rincianVals, wilayahVals])

  const dimVals = useMemo(
    () => (dimension === "rincian" ? rincianVals : wilayahVals),
    [dimension, rincianVals, wilayahVals]
  )
  const isRincianDim = dimension === "rincian"
  const members = useMemo(() => Array.from(selectedDim), [selectedDim])

  const toggleDim = (v: string) =>
    setSelectedDim((prev) => {
      const next = new Set(prev)
      if (next.has(v)) next.delete(v)
      else next.add(v)
      return next
    })
  const selectAllDim = () => setSelectedDim(new Set(dimVals))
  const clearAllDim = () => setSelectedDim(new Set())

  const DIM_LABEL: Record<"wilayah" | "rincian", string> = { wilayah: "Wilayah", rincian: "Rincian" }
  const canSwitchDim = rincianVals.length >= 2 && wilayahVals.length >= 2

  // Pivot (year × member) within the shared year range.
  const chartData = useMemo(() => {
    const lo = yearRange ? yearRange[0] : null
    const hi = yearRange ? yearRange[1] : null
    const byYear: Record<string, Record<string, number | null>> = {}
    metricRows.forEach((row) => {
      const y = row.tahun
      if (typeof y !== "number") return
      if (lo !== null && y < lo) return
      if (hi !== null && y > hi) return
      const dim = isRincianDim ? canonRincian(row.rincian_nama) : row.wilayah_nama
      if (!dim || dim === "-") return
      if (!members.includes(dim)) return
      const key = String(y)
      if (!byYear[key]) byYear[key] = { tahun: y }
      byYear[key][dim] = Number(row.nilai ?? row.nilai_teks ?? 0)
    })
    const points = Object.values(byYear).sort((a, b) => Number(a.tahun) - Number(b.tahun))
    return { points, lines: members }
  }, [metricRows, isRincianDim, members, yearRange])

  const metricUnit = useMemo(() => {
    const r = metricRows.find((row) => row.unit)
    return (r?.unit || "").trim().toLowerCase()
  }, [metricRows])

  const colorMap = useMemo(() => {
    const m: Record<string, string> = {}
    chartData.lines.forEach((k, i) => {
      m[k] = chartColors[i % chartColors.length]
    })
    return m
  }, [chartData.lines])

  // Export rows: metric + year range + selected members (same scope as chart).
  const sectionExportRows = useMemo(() => {
    const lo = yearRange ? yearRange[0] : null
    const hi = yearRange ? yearRange[1] : null
    return metricRows
      .filter((row) => {
        const y = row.tahun
        if (typeof y !== "number") return false
        if (lo !== null && y < lo) return false
        if (hi !== null && y > hi) return false
        return true
      })
      .filter((row) => {
        const dim = isRincianDim ? canonRincian(row.rincian_nama) : row.wilayah_nama
        return !!dim && dim !== "-" && members.includes(dim)
      })
      .map((row) => ({
        Tahun: row.tahun ?? "-",
        [isRincianDim ? "Rincian" : "Wilayah"]: isRincianDim
          ? canonRincian(row.rincian_nama)
          : row.wilayah_nama,
        Nilai: row.nilai ?? row.nilai_teks ?? "-",
        Satuan: (row.unit || "").trim(),
      }))
  }, [metricRows, isRincianDim, members, yearRange])

  useEffect(() => {
    onRowsReady(index, {
      nomor: item.nomor_tabel,
      title: item.title,
      metric: selectedMetric,
      rows: sectionExportRows,
    })
  }, [index, item.nomor_tabel, item.title, selectedMetric, sectionExportRows, onRowsReady])

  const renderTooltip = (props: any) => {
    const { active, payload, label } = props
    if (!active || !payload || payload.length === 0) return null
    const ordered = [...chartData.lines]
      .map((k) => payload.find((p: any) => p.dataKey === k))
      .filter(Boolean)
    return (
      <div
        style={{
          backgroundColor: "hsl(var(--card))",
          border: "1px solid hsl(var(--border))",
          borderRadius: "0.375rem",
          padding: "8px 10px",
          fontSize: "0.75rem",
          color: "hsl(var(--foreground))",
          boxShadow: "0 4px 12px rgba(0,0,0,0.12)",
        }}
      >
        <p style={{ fontWeight: 600, marginBottom: 4 }}>Tahun {label}</p>
        {ordered.map((p: any) => (
          <div key={p.dataKey} style={{ display: "flex", alignItems: "center", gap: 6, lineHeight: 1.6 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 9999,
                background: colorMap[p.dataKey as string],
                flexShrink: 0,
              }}
            />
            <span style={{ color: colorMap[p.dataKey as string], fontWeight: 500 }}>
              {p.dataKey} : {formatCompactNumber(p.value, metricUnit)}
            </span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <section className="rounded-md border border-border bg-background">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <span className="font-mono text-xs font-semibold text-primary">{item.nomor_tabel}</span>
        <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground" title={item.title}>
          {shortTitleForExport(item.title)}
        </h3>
        {metrics.length > 1 && (
          <select
            value={selectedMetric}
            onChange={(e) => setSelectedMetric(e.target.value)}
            className="rounded-md border border-border bg-background px-2.5 py-1 text-xs font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            aria-label="Pilih indikator"
          >
            {metrics.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        )}

        {/* Dimension switch (only when both dims are meaningful) */}
        {canSwitchDim && (
          <div className="flex items-center gap-0.5 rounded-md border border-border bg-background p-0.5">
            {(["wilayah", "rincian"] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => {
                  setDimension(d)
                  const vals = d === "rincian" ? rincianVals : wilayahVals
                  setSelectedDim(
                    d === "wilayah" && vals.includes("Kabupaten Tasikmalaya")
                      ? new Set(["Kabupaten Tasikmalaya"])
                      : new Set(vals)
                  )
                }}
                className={`rounded px-2 py-1 text-[11px] font-semibold transition-colors ${
                  dimension === d ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
                }`}
              >
                {DIM_LABEL[d]}
              </button>
            ))}
          </div>
        )}

        {/* Member multi-select */}
        {dimVals.length > 1 && (
          <div className="relative">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setDimDropdownOpen(!dimDropdownOpen)
              }}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1 text-xs font-medium text-foreground hover:bg-muted transition-colors"
            >
              {DIM_LABEL[dimension]} ({selectedDim.size}/{dimVals.length})
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
                  className="absolute z-50 mt-1 w-64 max-h-72 rounded-md border border-border bg-card shadow-lg overflow-hidden"
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center justify-between border-b border-border px-3 py-2">
                    <span className="text-xs font-semibold text-foreground">
                      Pilih {DIM_LABEL[dimension]}
                    </span>
                    <div className="flex gap-2">
                      <button onClick={selectAllDim} className="text-[10px] font-semibold text-primary hover:underline">Semua</button>
                      <button onClick={clearAllDim} className="text-[10px] font-semibold text-muted-foreground hover:underline">Hapus</button>
                    </div>
                  </div>
                  <div className="overflow-auto max-h-[220px] p-2">
                    {dimVals.map((v) => {
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

        <button
          type="button"
          onClick={onRemove}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
          aria-label={`Hapus ${item.nomor_tabel} dari daftar`}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-4">
        {isLoading ? (
          <div className="flex h-52 flex-col items-center justify-center text-primary">
            <Loader2 className="h-8 w-8 animate-spin" />
            <p className="mt-2 text-xs">Memuat data…</p>
          </div>
        ) : error ? (
          <div className="flex h-52 items-center justify-center rounded-md border border-destructive/20 bg-destructive/5 text-sm text-destructive">
            Gagal memuat data tabel {item.nomor_tabel}.
          </div>
        ) : chartData.points.length === 0 || chartData.lines.length === 0 ? (
          <div className="flex h-52 flex-col items-center justify-center rounded-md border border-dashed border-border bg-muted/20 text-center">
            <BarChart3 className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm font-semibold text-foreground">Belum ada data</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Tidak ada observasi untuk rentang tahun yang dipilih.
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData.points} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
              <XAxis
                dataKey="tahun"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                width={64}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                tickFormatter={(value) => formatCompactNumber(value)}
              />
              <Tooltip content={renderTooltip} />
              <Legend wrapperStyle={{ paddingTop: 8, fontSize: 11 }} />
              {chartData.lines.map((key, index) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  name={key}
                  stroke={chartColors[index % chartColors.length]}
                  strokeWidth={2}
                  activeDot={{ r: 4, strokeWidth: 0 }}
                  dot={{ r: 2.5, strokeWidth: 0 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  )
}

export function CompareModal({ items, onClose, onRemove }: CompareModalProps) {
  const [dataBounds, setDataBounds] = useState<[number, number] | null>(null)
  const [sel, setSel] = useState<[number, number] | null>(null)
  const sectionsRef = useRef<HTMLDivElement>(null)
  const rowsRef = useRef<Record<number, SectionExportRows>>({})

  const reportRange = useCallback((min: number, max: number) => {
    setDataBounds((prev) => (prev ? [Math.min(prev[0], min), Math.max(prev[1], max)] : [min, max]))
  }, [])

  const onRowsReady = useCallback(
    (index: number, payload: SectionExportRows) => {
      rowsRef.current[index] = payload
    },
    []
  )

  // Default selection = full range; clamp an existing selection when bounds change.
  useEffect(() => {
    if (!dataBounds) return
    setSel((cur) => {
      if (!cur) return dataBounds
      const [a, b] = cur
      return [
        Math.min(Math.max(a, dataBounds[0]), dataBounds[1]),
        Math.max(Math.min(b, dataBounds[1]), dataBounds[0]),
      ]
    })
  }, [dataBounds])

  const effectiveRange = sel ?? dataBounds

  const presetSemua = useCallback(() => {
    if (dataBounds) setSel(dataBounds)
  }, [dataBounds])

  const presetLimaTahun = useCallback(() => {
    if (!dataBounds) return
    const [mn, mx] = dataBounds
    setSel([Math.max(mn, mx - 4), mx])
  }, [dataBounds])

  const rangeStr = effectiveRange ? `${effectiveRange[0]}-${effectiveRange[1]}` : "semua-tahun"

  const exportExcel = useCallback(() => {
    const entries = Object.values(rowsRef.current).filter((e) => e.rows.length > 0)
    if (entries.length === 0) return
    const wb = XLSX.utils.book_new()
    const summary = entries.map((e, i) => ({
      No: i + 1,
      Tabel: e.nomor,
      Judul: shortTitleForExport(e.title),
      Indikator: e.metric,
      "Baris Data": e.rows.length,
    }))
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(summary), "Ringkasan")
    entries.forEach((e, i) => {
      const sheetName = `T${i + 1}_${e.nomor.replace(/[\\/?*[\]:]/g, "_")}`.slice(0, 31)
      const pivot = buildPivot(e.rows)
      XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([pivot.header, ...pivot.body]), sheetName)
    })
    XLSX.writeFile(wb, `data_bps_tasikmalaya_${rangeStr}_${entries.length}tabel.xlsx`)
  }, [rangeStr])

  const exportPDF = useCallback(async () => {
    const entries = Object.values(rowsRef.current).filter((e) => e.rows.length > 0)
    if (entries.length === 0) return

    // Capture EVERY section's chart individually (html2canvas on the
    // scrollable container only renders the visible viewport). Each chart
    // stays its own image so the PDF can render them BIG, one per section —
    // not scaled down into a single composed thumbnail.
    const sectionEls = sectionsRef.current
      ? Array.from(sectionsRef.current.querySelectorAll("section"))
      : []
    const chartUrls: (string | undefined)[] = []
    for (const el of sectionEls) {
      try {
        const canvas = await html2canvas(el as HTMLElement, {
          scale: 2,
          backgroundColor: "#ffffff",
          useCORS: true,
        })
        chartUrls.push(canvas.toDataURL("image/png"))
      } catch {
        chartUrls.push(undefined)
      }
    }

    const totalRows = entries.reduce((s, e) => s + e.rows.length, 0)
    const tabelList = entries.map((e) => e.nomor).join(", ")
    await exportProfessionalPdf({
      title: "Data BPS Kabupaten Tasikmalaya",
      subtitle: `Rentang tahun ${rangeStr.replace("-", "–")} • ${entries.length} tabel (${tabelList}) • ${totalRows} baris data`,
      fileName: `data_bps_tasikmalaya_${rangeStr}_${entries.length}tabel`,
      orientation: "landscape",
      // One full section per table: real table title (no 'Tabel' prefix, cut
      // at 'di Kabupaten Tasikmalaya'), big chart, and a readable pivot
      // (member x year) with the satuan merged into the values.
      chartSections: entries.map((e, i) => {
        const pivot = buildPivot(e.rows)
        return {
          title: `${e.nomor} — ${shortTitleForExport(e.title)}`,
          subtitle: `Indikator: ${e.metric}${pivot.unit ? ` • Satuan: ${pivot.unit}` : ""}`,
          chartImageDataUrl: chartUrls[i],
          columns: pivot.header,
          rows: pivot.body,
        }
      }),
    })
  }, [rangeStr])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      <div className="absolute inset-0 bg-background/80" onClick={onClose}></div>
      <div className="relative bg-card border border-border shadow-lg rounded-md w-full max-w-6xl h-[88vh] flex flex-col animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="min-w-0 pr-12">
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">
              Lihat beberapa tabel (gabungan semua publikasi)
            </p>
            <h2 className="mt-1 text-xl font-semibold text-foreground truncate">
              Lihat {items.length} Tabel
            </h2>
          </div>
          <button
            onClick={onClose}
            className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors absolute right-4"
            aria-label="Tutup tampilan"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Shared year range */}
        {dataBounds && (
          <div className="flex flex-wrap items-center gap-3 border-b border-border bg-background/60 px-4 md:px-6 py-3">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-foreground whitespace-nowrap">
              <Plus className="h-3.5 w-3.5 text-primary" /> Rentang tahun
            </span>
            <YearRangeSlider
              min={dataBounds[0]}
              max={dataBounds[1]}
              value={effectiveRange ?? dataBounds}
              onChange={(v) => setSel(v)}
            />
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={presetSemua}
                className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] font-semibold text-muted-foreground hover:border-primary/40 hover:text-foreground transition-colors"
              >
                Semua
              </button>
              <button
                type="button"
                onClick={presetLimaTahun}
                className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] font-semibold text-muted-foreground hover:border-primary/40 hover:text-foreground transition-colors"
              >
                5 tahun terakhir
              </button>
            </div>
          </div>
        )}

        {/* Stacked sections */}
        <div ref={sectionsRef} className="flex-1 overflow-auto p-6 flex flex-col gap-5">
          {items.map((item, idx) => (
            <CompareTableSection
              key={`${idx}-${item.nomor_tabel}`}
              item={item}
              index={idx}
              onRemove={() => onRemove(item.nomor_tabel)}
              yearRange={effectiveRange}
              onReportRange={reportRange}
              onRowsReady={onRowsReady}
            />
          ))}
          {items.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
              <AlertTriangle className="h-8 w-8 mb-3" />
              <p className="text-sm">Tidak ada tabel untuk ditampilkan.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 border-t border-border px-4 md:px-6 py-3">
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">
            Setiap grafik punya skala sendiri; rentang tahun disinkronkan agar perbandingan adil.
          </p>
          <div className="flex shrink-0 items-center gap-1.5 flex-wrap">
            <button
              type="button"
              onClick={exportExcel}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-2 text-xs font-medium text-foreground hover:bg-primary/5 hover:border-primary/50 transition-colors"
              title="Unduh Excel (satu sheet per tabel)"
            >
              <FileSpreadsheet className="h-4 w-4" /> Excel
            </button>
            <button
              type="button"
              onClick={exportPDF}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-2 text-xs font-medium text-foreground hover:bg-primary/5 hover:border-primary/50 transition-colors"
              title="Unduh PDF (gambar grafik + ringkasan)"
            >
              <FileText className="h-4 w-4" /> PDF
            </button>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-4 py-2 text-xs font-semibold text-foreground hover:bg-muted transition-colors"
            >
              <Check className="h-3.5 w-3.5" /> Tutup
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
