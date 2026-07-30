import { useMemo, useState, useCallback } from "react"
import { X, Loader2, Table2, LineChart as LineIcon, BarChart3, ChevronDown, Check, ListTree, FileSpreadsheet, FileText } from "lucide-react"
import { ResponsiveContainer, LineChart, CartesianGrid, XAxis, YAxis, Tooltip, Legend, Line } from "recharts"
import * as XLSX from "xlsx"
import html2canvas from "html2canvas"
import jsPDF from "jspdf"
import { useTimeSeries, useCatalogSeries, type CatalogSeriesRow } from "../../lib/api"

function safeFileName(name: string) {
  return (name || "data")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-zA-Z0-9 _.-]/g, "")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .slice(0, 80) || "data"
}

interface ChartModalProps {
  item: {
    id?: number
    nomor_tabel?: string
    type: "tabel" | "indikator" | "series"
    title: string
    initialFilter?: string
    initialFilters?: string[]
    seriesObservations?: any[]
    subjectName?: string
  }
  onClose: () => void
}

const COMPACT_UNITS: [number, string][] = [
  [1e12, "T"],
  [1e9, "M"],
  [1e6, "Jt"],
  [1e3, "Rb"],
]
function formatCompactNumber(value: number | string | null | undefined, unit?: string) {
  if (value === null || value === undefined || value === "") return "-"
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  const abs = Math.abs(numeric)
  let body = ""
  let matched = false
  for (const [threshold, suffix] of COMPACT_UNITS) {
    if (abs >= threshold) {
      const scaled = numeric / threshold
      body = `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(scaled)} ${suffix}`
      matched = true
      break
    }
  }
  if (!matched) {
    body = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(numeric)
  }
  // Currency (Rp) LEADS the value: "Rp 3,43 T". Every other unit (km, jiwa,
  // %, ha, ...) FOLLOWS it: "169,29 km". Decide placement from the unit.
  const u = displayUnit(unit)
  if (!u) return body
  return isPrefixUnit(u) ? `${u} ${body}` : `${body} ${u}`
}

// Units that must be written BEFORE the number (Indonesian currency convention).
const PREFIX_UNITS = new Set(["rp", "rp.", "idr", "us$", "$"])
function isPrefixUnit(unit?: string) {
  return PREFIX_UNITS.has((unit || "").trim().toLowerCase())
}
// Canonical display form: "rp" -> "Rp"; everything else kept as-is.
function displayUnit(unit?: string) {
  const u = (unit || "").trim()
  if (!u || u === "-") return ""
  return isPrefixUnit(u) ? "Rp" : u
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

// Rincian labels must be uniform: entries that differ ONLY by letter case
// (e.g. "KOPERASI X" vs "Koperasi X" vs "koperasi x") refer to the same
// category and must not appear as separate, near-duplicate options in the
// dropdown / chart legend / table. We canonicalize to Title Case so every
// variant collapses to one consistent label.
export function toTitleCase(s: string): string {
  return s
    .toLowerCase()
    .replace(/(^|[^a-z])[a-z]/g, (c) => c.toUpperCase())
}
export function canonRincian(name: string | undefined): string {
  const n = (name ?? "").trim()
  return n && n !== "-" ? toTitleCase(n) : n
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
  const isSeries = item.type === "series"
  const merged = useCatalogSeries(item.nomor_tabel ?? null)
  const single = useTimeSeries(item.id ?? null, isSeries ? null : (item.nomor_tabel ? null : (item.type as "tabel" | "indikator")))
  const isMerged = Boolean(item.nomor_tabel)
  const { data, isLoading, error } = isMerged ? merged : isSeries ? { data: null, isLoading: false, error: null } : single

  const [view, setView] = useState<"chart" | "table">("chart")

  const allRows: CatalogSeriesRow[] = useMemo(() => {
    if (isSeries) {
      // Drill into a pre-aggregated "series" answer (e.g. the Jumlah Guru
      // kabupaten total). Use the same observations so the detail view is
      // identical to the inline summary — one row per year, no scattered
      // per-level rows. Force a uniform subject so the single series is not
      // split by leftover per-level rincian labels carried from the source
      // tables.
      const subject = item.subjectName ?? "Kabupaten Tasikmalaya"
      // Use a uniform (empty) unit for the whole series so metricKey() is
      // identical across all years. Source observations may carry differing
      // satuan ("Orang" / "Jiwa" / "") per year, which would otherwise split
      // 2020/2021 into a different metric and drop them from the table.
      const mapped = (item.seriesObservations ?? []).map((r) => ({
        id: r.id,
        tahun: r.tahun,
        nilai: r.nilai,
        nilai_teks: r.nilai_teks ?? String(r.nilai),
        unit: "",
        wilayah_nama: r.wilayah_nama ?? "-",
        rincian_nama: subject,
        subject_name: subject,
        flag: r.flag || "ada",
      }))
      return mapped
    }
    if (!data) return []
    const raw: CatalogSeriesRow[] = isMerged
      ? ((data as any).series as CatalogSeriesRow[])
      : Array.isArray(data)
        ? data
        : (data as any).observations ?? []
    // Canonicalize rincian labels to a single Title Case form so variants
    // like "KOPERASI X" / "Koperasi X" collapse into one consistent option
    // across the dropdown, chart legend, and table.
    return raw.map((r) => ({ ...r, rincian_nama: canonRincian(r.rincian_nama) }))
  }, [data, isMerged, isSeries, item])

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
  // For the "rincian" dimension we only want the per-category totals, not the
  // gender sub-splits (Anggota PNS - Laki-Laki / Perempuan) which would otherwise
  // explode the dropdown and the chart into near-duplicate series. Keep rows whose
  // subject is a Jumlah/wilayah total (i.e. NOT a gender split).
  const rincianRows = useMemo(
    () => allRows.filter((r) => !/(laki-laki|perempuan)/i.test(r.subject_name || "")),
    [allRows]
  )
  const rincianValues = useMemo(
    () =>
      Array.from(
        new Set(
          rincianRows
            .map((r) => r.rincian_nama)
            .filter((v) => v && v !== "-" && !TRIVIAL_RINCIAN.has(v.toLowerCase()))
        )
      ).sort(),
    [rincianRows]
  )

  const availableDims: Dimension[] = useMemo(() => {
    const dims: Dimension[] = []
    if (wilayahValues.length > 1) dims.push("wilayah")
    if (rincianValues.length > 1) dims.push("rincian")
    return dims
  }, [wilayahValues, rincianValues])

  // For a pre-aggregated "series" drill (e.g. Jumlah Guru kabupaten total)
  // there is exactly ONE row per year with a single subject, so there is no
  // dimension to pick. Treat it as a single rincian series and auto-select
  // it so the chart/table render immediately instead of prompting the user
  // to "pilih minimal satu wilayah".
  const effectiveDims: Dimension[] = isSeries ? ["rincian"] : availableDims

  // --- Selection state (initialized from saved localStorage if present) ---
  const savedRef = useMemo(() => loadSavedSelection(item), [item])
  const [selectedMetric, setSelectedMetric] = useState<string>(() => {
    const saved = savedRef?.metric
    return saved && metrics.includes(saved) ? saved : metrics[0] ?? ""
  })
  const [dimension, setDimension] = useState<Dimension>(() => {
    if (isSeries) return "rincian"
    const saved = savedRef?.dimension
    if (saved && availableDims.includes(saved)) return saved
    // default to the richer dimension
    if (rincianValues.length >= wilayahValues.length && availableDims.includes("rincian")) return "rincian"
    return availableDims[0] ?? "wilayah"
  })
  const dimValues = dimension === "wilayah" ? wilayahValues : rincianValues

  const [selectedDim, setSelectedDim] = useState<Set<string>>(() => {
    if (isSeries) return new Set(rincianValues)
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
  // Auto-select smart defaults whenever the fetched rows change (always runs
  // after data has loaded, so the chosen dimension/members come from the real
  // facets — not from a mount-time empty state, and not from a stale
  // Wilayah save left by the old buggy version).
  //
  // NOTE: we deliberately do NOT skip when a saved selection exists. The old
  // code guarded on `hasSaved`, which froze stale "wilayah" localStorage
  // entries written by the previous bug (tables with 1 wilayah + many
  // rincian, e.g. 9.1 / 2.2.1), so they kept opening on Wilayah
  // until manually switched. The user's explicit choices still persist via
  // `persist()` on every toggle/dimension/metric change, so re-defaulting
  // here only corrects once on load and never fights a live user edit.
  const [hasAutoSelected, setHasAutoSelected] = useState(false)
  // Initialize dimension + metric defaults once data has loaded, but DO NOT
  // auto-pick any dimension members. The user must choose which
  // kecamatan/rincian to show — an empty selection yields an empty
  // chart/table with a "pilih minimal satu ..." prompt, instead of
  // silently showing all (or a pre-picked subset).
  useMemo(() => {
    if (hasAutoSelected || metrics.length === 0 || dimValues.length === 0) return
    if (isSeries) {
      // Single pre-aggregated series: keep the rincian member selected so the
      // chart/table render immediately (no "pilih minimal satu" prompt).
      setDimension("rincian")
      setSelectedMetric(metrics[0] ?? "")
      setSelectedDim(new Set(rincianValues))
      setHasAutoSelected(true)
      return
    }
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
    // Restore the user's previously saved members for this dimension if any;
    // otherwise leave it empty so they pick explicitly (no silent "show all").
    const savedSel = savedRef?.sel?.[richDim]
    const restored =
      Array.isArray(savedSel) && savedSel.length > 0
        ? new Set(savedSel.filter((v) => (richDim === "wilayah" ? wilayahValues : rincianValues).includes(v)))
        : new Set<string>()
    setSelectedDim(restored)
    setHasAutoSelected(true)
  }, [metrics, allRows, hasAutoSelected, dimension, dimValues, availableDims, wilayahValues, rincianValues, isSeries])

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

  // --- Export only the selected dimension members (e.g. chosen kecamatan) ---
  // If nothing is selected, the export is empty (matches the empty chart/table).
  const exportRows = useMemo(() => {
    if (selectedDim.size === 0) return []
    return allRows
      .filter((row) => metricKey(row) === selectedMetric)
      .filter((row) => selectedDim.has(dimensionValue(row, dimension)))
      .map((row) => ({
        Tahun: row.tahun ?? "-",
        [dimension === "wilayah" ? "Wilayah" : "Rincian"]: dimensionValue(row, dimension) || "-",
        Nilai: getValue(row),
        Satuan: normUnit(row.unit) || "",
        Rincian: row.rincian_nama && row.rincian_nama !== "-" ? row.rincian_nama : "",
        Status: row.flag || "ada",
      }))
  }, [allRows, selectedMetric, selectedDim, dimension])

  const handleExportExcel = useCallback(() => {
    if (exportRows.length === 0) return
    const worksheet = XLSX.utils.json_to_sheet(exportRows)
    const workbook = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(workbook, worksheet, "Data")
    const sel = selectedDim.size > 0 ? `_${Array.from(selectedDim).join("-")}` : ""
    XLSX.writeFile(workbook, `${safeFileName(item.title)}${sel}.xlsx`)
  }, [exportRows, item.title, selectedDim])

  const handleExportPDF = useCallback(async () => {
    if (exportRows.length === 0) return
    const worksheet = XLSX.utils.json_to_sheet(exportRows)
    const workbook = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(workbook, worksheet, "Data")
    // Render the sheet to an HTML table, then to canvas -> PDF.
    const html = XLSX.utils.sheet_to_html(worksheet, { id: "bps-export-table", editable: false })
    const container = document.createElement("div")
    container.innerHTML = html
    Object.assign(container.style, {
      position: "fixed",
      left: "-99999px",
      top: "0",
      background: "#ffffff",
      padding: "12px",
    } as CSSStyleDeclaration)
    document.body.appendChild(container)
    try {
      const canvas = await html2canvas(container, { scale: 2, backgroundColor: "#ffffff" })
      const imgData = canvas.toDataURL("image/png")
      const pdf = new jsPDF("landscape", "mm", "a4")
      const pdfWidth = pdf.internal.pageSize.getWidth()
      const pdfHeight = (canvas.height * pdfWidth) / canvas.width
      pdf.addImage(imgData, "PNG", 0, 0, pdfWidth, Math.min(pdfHeight, pdf.internal.pageSize.getHeight()))
      const sel = selectedDim.size > 0 ? `_${Array.from(selectedDim).join("-")}` : ""
      pdf.save(`${safeFileName(item.title)}${sel}.pdf`)
    } finally {
      document.body.removeChild(container)
    }
  }, [exportRows, item.title, selectedDim])

  // --- Chart data: pivot by (year × dimension value) ---
  const chartData = useMemo(() => {
    // When splitting by rincian, use only the Jumlah/wilayah-total rows (not the
    // Laki-Laki / Perempuan gender splits) so each category is one clean series.
    const sourceRows = dimension === "rincian" ? rincianRows : allRows
    const metricRows = sourceRows.filter((r) => metricKey(r) === selectedMetric)
    const byYear: Record<string, Record<string, number | null>> = {}
    const selected = selectedDim

    metricRows.forEach((row) => {
      const dim = dimensionValue(row, dimension)
      if (isTrivial(dimension, dim)) return
      if (selected.size > 0 && !selected.has(dim)) return
      const year = String(row.tahun ?? "")
      if (!byYear[year]) byYear[year] = { tahun: Number(row.tahun) }
      // Backend already aggregates aliased rincian (e.g. Eselon III.a+III.b ->
      // "Administrator") and collapses duplicate publications, so each
      // (year, dim) pair carries exactly one value here.
      byYear[year][dim] = Number(getValue(row))
    })

    // Order the series by their value in the LATEST year (descending) so the
    // legend, tooltip, AND the drawn line positions all match. (Recharts
    // stacks lines by data value, so a purely alphabetical order would make
    // the tooltip/legend disagree with where each colored line actually sits.)
    const years = Object.values(byYear)
    const latestYear = years.length ? Math.max(...years.map((y) => Number(y.tahun))) : null
    const valueOf = (dim: string) => {
      if (latestYear == null) return 0
      const row = years.find((y) => Number(y.tahun) === latestYear)
      return row ? Number((row as any)[dim]) || 0 : 0
    }
    const lines =
      selected.size > 0
        ? Array.from(selected).sort((a, b) => valueOf(b) - valueOf(a))
        : [] // no selection -> empty chart/table, prompt user to pick

    return {
      points: Object.values(byYear).sort((a, b) => Number(a.tahun) - Number(b.tahun)),
      lines,
    }
  }, [allRows, selectedMetric, selectedDim, dimension])

  const hasRows = allRows.length > 0
  const metricUnit = normUnit(allRows.find((r) => metricKey(r) === selectedMetric)?.unit)

  // Stable color lookup so the tooltip, legend, and lines stay in the same
  // order/colors. chartData.lines is sorted by latest-year value (descending)
  // and the <Line> stroke uses chartColors[index]; mirror that here so the
  // hover tooltip lists series in the exact same sequence as the drawn lines.
  const colorMap = useMemo(() => {
    const m: Record<string, string> = {}
    chartData.lines.forEach((k, i) => {
      m[k] = chartColors[i % chartColors.length]
    })
    return m
  }, [chartData.lines])

  const renderTooltip = (props: any) => {
    const { active, payload, label } = props
    if (!active || !payload || payload.length === 0) return null
    // Sort the tooltip by each series' value IN THE HOVERED YEAR so the row
    // order always mirrors where each colored line sits at that year. (Legend
    // stays locked to the latest year for stability.)
    const point = chartData.points.find(
      (p: any) => Number(p.tahun) === Number(label),
    )
    const ordered = point
      ? [...chartData.lines]
          .sort(
            (a: string, b: string) =>
              (Number((point as any)[b]) || 0) - (Number((point as any)[a]) || 0),
          )
          .map((k: string) => payload.find((p: any) => p.dataKey === k))
          .filter(Boolean)
      : chartData.lines
          .map((k: string) => payload.find((p: any) => p.dataKey === k))
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

                {/* Export (selected dimension members only, e.g. chosen kecamatan) */}
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={handleExportExcel}
                    className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-primary/5 hover:border-primary/50 transition-colors"
                    title="Unduh Excel (kecamatan/rincian terpilih)"
                  >
                    <FileSpreadsheet className="h-4 w-4" /> Excel
                  </button>
                  <button
                    type="button"
                    onClick={handleExportPDF}
                    className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-primary/5 hover:border-primary/50 transition-colors"
                    title="Unduh PDF (kecamatan/rincian terpilih)"
                  >
                    <FileText className="h-4 w-4" /> PDF
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
                {effectiveDims.length > 1 && (
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
                {dimValues.length > 0 && !isSeries && (
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
                          tickFormatter={(value) => formatCompactNumber(value)}
                        />
                        <Tooltip
                          content={renderTooltip}
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
                          .filter((row: any) => selectedDim.has(dimensionValue(row, dimension)))
                          .map((row: any) => (
                            <tr key={row.id} className="border-b border-border last:border-0 hover:bg-muted/30">
                              <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.tahun ?? "-"}</td>
                              <td className="px-4 py-3 font-medium text-foreground whitespace-nowrap">{dimensionValue(row, dimension) || "-"}</td>
                              <td className="px-4 py-3 text-right font-semibold text-foreground whitespace-nowrap">
                                {formatCompactNumber(getValue(row), row.unit && normUnit(row.unit) ? normUnit(row.unit) : undefined)}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.rincian_nama && row.rincian_nama !== "-" ? row.rincian_nama : "-"}</td>
                              <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.flag || "ada"}</td>
                            </tr>
                          ))}
                        {selectedDim.size === 0 && (
                          <tr>
                            <td colSpan={5} className="px-4 py-8 text-center text-sm text-muted-foreground">
                              Pilih minimal satu {DIM_LABEL[dimension].toLowerCase()} untuk menampilkan tabel.
                            </td>
                          </tr>
                        )}
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
