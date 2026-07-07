import { BarChart3, ExternalLink } from "lucide-react"
import {
  ResponsiveContainer,
  LineChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Line,
  Legend,
} from "recharts"

type Observation = {
  id: number
  tahun: number | null
  nilai: number
  nilai_teks: string
  wilayah_nama: string
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

function cleanUnit(unit?: string) {
  return unit && unit !== "-" ? unit : ""
}

function getRowSubject(row: Observation) {
  return row.wilayah_nama && row.wilayah_nama !== "-" ? row.wilayah_nama : "Indonesia"
}

export function InlineTimeSeriesAnswer({ match, subjectName, onOpenChart }: InlineTimeSeriesAnswerProps) {
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
  const unit = cleanUnit(latest?.satuan || first?.satuan)

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

  return (
    <section className="rounded-lg border border-primary/25 bg-card p-5 shadow-sm space-y-5">
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
            <p className="mt-1 text-sm text-muted-foreground">
              {isComparison
                ? `Grafik ringkas langsung membandingkan ${subjects.join(" dan ")}. Buka detail hanya kalau ingin tambah seri, unduh Excel, atau cetak PDF.`
                : match.summary_kind === "aggregate"
                  ? "Ringkasan otomatis dari tabel paling relevan per tahun. Hasil mentah tetap disimpan di bagian detail."
                  : `Time series otomatis dari hasil pencarian. Hanya menampilkan ${subjectName}, bukan semua kecamatan.`}
            </p>
          </div>
        </div>

        {latestBySubject.length > 0 && (
          <div className="rounded-md border border-border bg-muted/30 px-4 py-3 min-w-48">
            <p className="text-xs text-muted-foreground">Data terbaru</p>
            {isComparison ? (
              <div className="mt-2 space-y-2">
                {latestBySubject.map(({ subject, row }) => row && (
                  <div key={subject} className="flex items-baseline justify-between gap-4">
                    <span className="text-xs font-medium text-muted-foreground">{subject}</span>
                    <span className="text-sm font-semibold text-foreground whitespace-nowrap">
                      {formatIndonesianNumber(row.nilai)}{unit ? ` ${unit}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            ) : latest ? (
              <>
                <p className="mt-1 text-2xl font-semibold text-foreground">{formatIndonesianNumber(latest.nilai)}</p>
                <p className="text-xs text-muted-foreground">{latest.tahun}{unit ? ` • ${unit}` : ""}</p>
              </>
            ) : null}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-5">
        <div className="h-[320px] rounded-md border border-border bg-background p-4">
          <ResponsiveContainer width="100%" height="100%">
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
                width={68}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
                tickFormatter={(value) => formatIndonesianNumber(value)}
              />
              <Tooltip
                formatter={(value, name) => [`${formatIndonesianNumber(value as number)}${unit ? ` ${unit}` : ""}`, String(name)]}
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
          </ResponsiveContainer>
        </div>

        <div className="rounded-md border border-border bg-background overflow-hidden">
          <div className="px-3 py-2 border-b border-border text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Tahun dan nilai
          </div>
          <div className="max-h-[280px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sr-only">
                <tr>
                  {isComparison && <th>Wilayah</th>}
                  <th>Tahun</th>
                  <th>Nilai</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-border last:border-0">
                    {isComparison && <td className="px-3 py-2 text-muted-foreground">{getRowSubject(row)}</td>}
                    <td className="px-3 py-2 text-muted-foreground">{row.tahun}</td>
                    <td className="px-3 py-2 text-right font-medium text-foreground">
                      {formatIndonesianNumber(row.nilai)}{unit ? ` ${unit}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2 border-t border-border pt-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <div>
          {subjects.length} seri • {rows.length} titik data{yearRange ? ` • ${yearRange}` : ""}
          {latest?.tabel ? ` • sumber tabel ${latest.tabel.nomor_tabel}` : ""}
        </div>
        <button
          onClick={onOpenChart}
          className="inline-flex items-center gap-2 text-primary font-semibold hover:underline self-start sm:self-auto"
        >
          Buka grafik detail
          <ExternalLink className="h-3.5 w-3.5" />
        </button>
      </div>
    </section>
  )
}
