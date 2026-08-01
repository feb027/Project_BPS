import { useRef } from "react"
import { BarChart3, Download, ExternalLink, FileText } from "lucide-react"
import {
  ResponsiveContainer,
  LineChart,
  BarChart,
  Bar,
  LabelList,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Line,
  Legend,
} from "recharts"
import * as XLSX from "xlsx"
import html2canvas from "html2canvas-pro"
import { exportProfessionalPdf } from "../../lib/pdfExport"

type Observation = {
  id: number
  tahun: number | null
  nilai: number
  nilai_teks: string
  wilayah_nama: string
  rincian_nama?: string
  subject_name?: string
  subject_kind?: string
  satuan?: string
  tabel?: {
    id: number
    nomor_tabel: string
    judul: string
  }
}

type QuickMatch = {
  indicator_id: number
  indicator_name: string
  wilayah?: { id: number; nama: string; jenis: string }
  subject_name?: string
  age_label?: string | null
  summary_kind?: string
  observations: Observation[]
}

interface InlineTimeSeriesAnswerProps {
  match: QuickMatch
  subjectName: string
  onOpenChart: () => void
}

const chartColors = ["#2563eb", "#ea580c", "#16a34a", "#ca8a04", "#9333ea"]

function formatIndonesianNumber(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") return "-"
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(numeric)
}

// Compact form for axis/tooltip labels so multi-trillion Rupiah values
// don't overflow the narrow Y-axis gutter. 1.234.567.890 -> "1,23 M".
const COMPACT_UNITS: [number, string][] = [
  [1e12, "T"],
  [1e9, "M"],
  [1e6, "Jt"],
  [1e3, "Rb"],
]
// Units written BEFORE the number (Indonesian currency convention: "Rp 3,43 T").
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
  // Currency (Rp) LEADS the value; every other unit (km, jiwa, %) FOLLOWS it.
  const u = displayUnit(unit)
  if (!u) return body
  return isPrefixUnit(u) ? `${u} ${body}` : `${body} ${u}`
}

function getRowSubject(row: Observation) {
  if (row.subject_name && row.subject_name !== "-") return row.subject_name
  if (row.wilayah_nama && row.wilayah_nama !== "-") return row.wilayah_nama
  if (row.rincian_nama && row.rincian_nama !== "-") return row.rincian_nama
  return "Indonesia"
}

function safeFileName(name: string) {
  return name.replace(/[^a-z0-9-_]+/gi, "_").replace(/^_+|_+$/g, "").slice(0, 60) || "data"
}

export function InlineTimeSeriesAnswer({ match, subjectName, onOpenChart }: InlineTimeSeriesAnswerProps) {
  const sectionRef = useRef<HTMLElement>(null)
  const rows = [...(match.observations ?? [])]
    .filter((row) => row.tahun !== null && row.tahun !== undefined)
    .sort((a, b) => {
      const yearDiff = Number(a.tahun) - Number(b.tahun)
      return yearDiff !== 0 ? yearDiff : getRowSubject(a).localeCompare(getRowSubject(b))
    })

  const subjects = Array.from(new Set(rows.map(getRowSubject)))
  const isComparison = subjects.length > 1
  const first = rows[0]
  const latest = rows.at(-1)
  const unit = displayUnit(latest?.satuan || first?.satuan)
  const hasRows = rows.length > 0

  const latestBySubject = subjects.map((subject) => {
    const subjectRows = rows.filter((row) => getRowSubject(row) === subject)
    return { subject, row: subjectRows.at(-1) }
  })

  const chartData = Object.values(
    rows.reduce((acc: Record<string, Record<string, number | null>>, row) => {
      const year = String(row.tahun)
      if (!acc[year]) acc[year] = { tahun: Number(row.tahun) }
      acc[year][getRowSubject(row)] = Number(row.nilai)
      return acc
    }, {})
  ).sort((a, b) => Number(a.tahun) - Number(b.tahun))

  const yearRange = first && latest ? `${first.tahun}–${latest.tahun}` : ""

  // Kalau cuma 1 tahun unik, pakai bar chart dengan nilai tercetak di atas
  // bar (line chart 1 titik hampir tak terlihat dan hilang di export PDF).
  const uniqueYears = new Set(rows.map((row) => String(row.tahun)))
  const isSingleYear = uniqueYears.size === 1

  const handleExportExcel = () => {
    if (!hasRows) return
    const exportRows = rows.map((row) => ({
      Tahun: row.tahun,
      Seri: getRowSubject(row),
      Nilai: row.nilai,
      Satuan: unit,
      Rincian: row.rincian_nama && row.rincian_nama !== "-" ? row.rincian_nama : "",
      Wilayah: row.wilayah_nama && row.wilayah_nama !== "-" ? row.wilayah_nama : "",
      Nomor_Tabel: row.tabel?.nomor_tabel ?? "",
      Judul_Tabel: row.tabel?.judul ?? "",
    }))
    const worksheet = XLSX.utils.json_to_sheet(exportRows)
    const workbook = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(workbook, worksheet, "Data")
    XLSX.writeFile(workbook, `${safeFileName(match.indicator_name)}_${safeFileName(subjectName)}.xlsx`)
  }

  const handleExportPDF = async () => {
    if (!hasRows) return

    // Capture the chart/table section as image for the PDF
    let chartImageDataUrl: string | undefined
    if (sectionRef.current) {
      try {
        const canvas = await html2canvas(sectionRef.current, {
          scale: 2,
          backgroundColor: "#ffffff",
          useCORS: true,
        })
        chartImageDataUrl = canvas.toDataURL("image/png")
      } catch {
        // Capture failed — export table-only PDF
      }
    }

    // Build a pivot table: rows = subjects, columns = years
    const years = Array.from(new Set(rows.map((r) => String(r.tahun)))).sort()

    // Build lookup: { "Bantarkalong" => { "2017" => 273, ... } }
    const lookup: Record<string, Record<string, number>> = {}
    for (const row of rows) {
      const subj = getRowSubject(row)
      const year = String(row.tahun)
      if (!lookup[subj]) lookup[subj] = {}
      lookup[subj][year] = row.nilai
    }

    // Columns: [Seri, year1, year2, ...]
    const columns = [isComparison ? "Wilayah" : "Seri", ...years]
    const pdfRows = subjects.map((subj) => [
      subj,
      ...years.map((y) => lookup[subj]?.[y] ?? "-"),
    ])

    const satuanText = unit ? ` • Satuan: ${unit}` : ""
    const tabelInfo = latest?.tabel ? ` • Sumber: Tabel ${latest.tabel.nomor_tabel}` : ""

    await exportProfessionalPdf({
      title: `${match.indicator_name} — ${subjectName}`,
      subtitle: match.age_label
        ? `Kelompok Umur: ${match.age_label} • ${subjects.length} seri • ${rows.length} titik data${yearRange ? ` • ${yearRange}` : ""}${satuanText}${tabelInfo}`
        : `${subjects.length} seri • ${rows.length} titik data${yearRange ? ` • ${yearRange}` : ""}${satuanText}${tabelInfo}`,
      columns,
      rows: pdfRows,
      fileName: `${safeFileName(match.indicator_name)}_${safeFileName(subjectName)}`,
      chartImageDataUrl,
    })
  }

  return (
    <section ref={sectionRef} className="rounded-lg border border-primary/25 bg-card p-5 shadow-sm space-y-5 min-h-[calc(100vh-10rem)] flex flex-col">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 h-10 w-10 rounded-md bg-primary/10 flex items-center justify-center text-primary shrink-0">
            <BarChart3 className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">Jawaban langsung</p>
            <h3 className="mt-1 text-xl font-semibold text-foreground">
              {match.indicator_name} — {subjectName}
            </h3>
            {match.age_label ? (
              <span className="mt-1 inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                {match.age_label}
              </span>
            ) : null}
            <p className="mt-1 text-sm text-muted-foreground">
              {hasRows
                ? isComparison
                  ? `Grafik ringkas langsung membandingkan ${subjects.join(" dan ")}${match.age_label ? ` untuk ${match.age_label}` : ""}. Buka tabel detail kalau ingin melihat baris database.`
                  : match.summary_kind === "aggregate"
                    ? "Ringkasan otomatis dari tabel paling relevan per tahun. Hasil mentah tetap disimpan di bagian detail."
                    : `Time series otomatis dari hasil pencarian. Hanya menampilkan ${subjectName}${match.age_label ? `, ${match.age_label}` : ""}, bukan semua kecamatan/rincian.`
                : "Tidak ada observasi yang dapat ditampilkan untuk hasil ini."}
            </p>
          </div>
        </div>

        {hasRows && latestBySubject.length > 0 && (
          <div className="rounded-md border border-border bg-muted/30 px-4 py-3 min-w-48 max-w-72">
            <p className="text-xs text-muted-foreground">Data terbaru</p>
            {isComparison ? (
              <div className="mt-2 space-y-2">
                {latestBySubject.map(({ subject, row }) => row && (
                  <div key={subject} className="flex items-baseline justify-between gap-4">
                    <span className="text-xs font-medium text-muted-foreground truncate">{subject}</span>
                    <span className="text-sm font-semibold text-foreground whitespace-nowrap text-right">
                      {formatCompactNumber(row.nilai, unit)}
                    </span>
                  </div>
                ))}
              </div>
            ) : latest ? (
              <div>
                <p className="mt-1 text-2xl font-semibold text-foreground">{formatCompactNumber(latest.nilai, unit)}</p>
                <p className="text-xs text-muted-foreground">{isPrefixUnit(unit) ? `${unit} • ${latest.tahun}` : `${latest.tahun}${unit ? ` • ${unit}` : ""}`}</p>
              </div>
            ) : null}
          </div>
        )}
      </div>

      {!hasRows ? (
        <div className="flex-1 min-h-[420px] rounded-md border border-dashed border-border bg-background flex flex-col items-center justify-center text-center p-8">
          <BarChart3 className="h-9 w-9 text-muted-foreground mb-3" />
          <p className="text-base font-semibold text-foreground">Tidak ada data</p>
          <p className="mt-1 text-sm text-muted-foreground">Hasil pencarian ditemukan, tetapi tidak ada nilai numerik untuk divisualkan.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5 flex-1 min-h-0">
          <div className="min-h-[420px] rounded-md border border-border bg-background p-4">
            <ResponsiveContainer width="100%" height="100%">
              {isSingleYear ? (
                <BarChart data={chartData} margin={{ top: 24, right: 16, left: 0, bottom: isComparison ? 28 : 8 }}>
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
                    formatter={(value, name) => [`${formatCompactNumber(value as number, unit)}`, String(name)]}
                    labelFormatter={(label) => `Tahun ${label}`}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      borderColor: "hsl(var(--border))",
                      color: "hsl(var(--foreground))",
                      borderRadius: "0.375rem",
                    }}
                  />
                  {isComparison && <Legend wrapperStyle={{ paddingTop: 12 }} />}
                  {subjects.map((subject, index) => (
                    <Bar
                      key={subject}
                      dataKey={subject}
                      name={subject}
                      fill={chartColors[index % chartColors.length]}
                      radius={[4, 4, 0, 0]}
                      maxBarSize={72}
                    >
                      <LabelList
                        dataKey={subject}
                        position="top"
                        formatter={(value) => formatCompactNumber(value as number, unit)}
                        style={{ fill: "hsl(var(--muted-foreground))", fontSize: 12, fontWeight: 600 }}
                      />
                    </Bar>
                  ))}
                </BarChart>
              ) : (
                <LineChart data={chartData} margin={{ top: 12, right: 16, left: 0, bottom: isComparison ? 28 : 8 }}>
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
                    formatter={(value, name) => [`${formatCompactNumber(value as number, unit)}`, String(name)]}
                    labelFormatter={(label) => `Tahun ${label}`}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      borderColor: "hsl(var(--border))",
                      color: "hsl(var(--foreground))",
                      borderRadius: "0.375rem",
                    }}
                  />
                  {isComparison && <Legend wrapperStyle={{ paddingTop: 12 }} />}
                  {subjects.map((subject, index) => (
                    <Line
                      key={subject}
                      type="monotone"
                      dataKey={subject}
                      name={subject}
                      stroke={chartColors[index % chartColors.length]}
                      strokeWidth={isComparison ? 2.5 : 3}
                      activeDot={{ r: 6, strokeWidth: 0 }}
                      dot={{ r: 4, strokeWidth: 0 }}
                      connectNulls
                    />
                  ))}
                </LineChart>
              )}
            </ResponsiveContainer>
          </div>

          <div className="rounded-md border border-border bg-background overflow-hidden">
            <div className="px-3 py-2 border-b border-border text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {isComparison ? "Perbandingan per tahun" : "Tahun dan nilai"}
            </div>
            <div className="max-h-[420px] overflow-auto">
              {isComparison ? (
                <table className="w-full min-w-[280px] text-sm">
                  <thead className="sticky top-0 bg-background">
                    <tr className="border-b border-border">
                      <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground">Tahun</th>
                      {subjects.map((subject) => (
                        <th key={subject} className="px-3 py-2 text-right text-xs font-semibold text-muted-foreground">
                          {subject}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {chartData.map((point) => (
                      <tr key={String(point.tahun)} className="border-b border-border last:border-0">
                        <td className="px-3 py-2 text-muted-foreground">{String(point.tahun)}</td>
                        {subjects.map((subject) => (
                          <td key={subject} className="px-3 py-2 text-right font-medium text-foreground whitespace-nowrap">
                            {formatCompactNumber(point[subject] as number | null | undefined, unit)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <table className="w-full text-sm">
                  <thead className="sr-only">
                    <tr><th>Tahun</th><th>Nilai</th></tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id} className="border-b border-border last:border-0">
                        <td className="px-3 py-2 text-muted-foreground">{row.tahun}</td>
                        <td className="px-3 py-2 text-right font-medium text-foreground">
                          {isPrefixUnit(unit) ? `${unit} ${formatIndonesianNumber(row.nilai)}` : `${formatIndonesianNumber(row.nilai)}${unit ? ` ${unit}` : ""}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-3 border-t border-border pt-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <div>
          {hasRows ? (
            <>
              {subjects.length} seri • {rows.length} titik data{yearRange ? ` • ${yearRange}` : ""}
              {latest?.tabel ? ` • sumber tabel ${latest.tabel.nomor_tabel}` : ""}
            </>
          ) : "Tidak ada data untuk divisualkan"}
        </div>
        {hasRows && (
          <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
            <button
              onClick={handleExportExcel}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-secondary/10 px-3 text-xs font-semibold text-secondary hover:bg-secondary/20"
            >
              <FileText className="h-4 w-4" />
              Unduh Excel
            </button>
            <button
              onClick={handleExportPDF}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-xs font-semibold text-primary-foreground hover:bg-primary/90"
            >
              <Download className="h-4 w-4" />
              Cetak PDF
            </button>
            <button
              onClick={onOpenChart}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-xs font-semibold text-primary hover:bg-muted"
            >
              Buka tabel detail
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
