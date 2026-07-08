import { useMemo, useState } from "react"
import { X, Loader2, Table2 } from "lucide-react"
import { useTimeSeries } from "../../lib/api"

interface ChartModalProps {
  item: {id: number, type: 'tabel' | 'indikator', title: string, initialFilter?: string, initialFilters?: string[]}
  onClose: () => void
}

function cleanSubjectLabel(value: string) {
  const withoutGroup = value.replace(/^\[[^\]]+\]\s*/, "").replace(/^[a-z]\.?\s+/i, "")
  const primary = withoutGroup.split("/")[0].trim()
  return primary.toLowerCase() === "diaspal" ? "Aspal" : (primary || value)
}

function getSubjectName(row: any) {
  const subject = row.subject_name
  const wilayah = row.wilayah_nama || row.wilayah?.nama
  const rincian = row.rincian_nama
  if (subject && subject !== "-") return cleanSubjectLabel(String(subject))
  if (rincian && rincian !== "-") return cleanSubjectLabel(String(rincian))
  if (wilayah && wilayah !== "-") return cleanSubjectLabel(String(wilayah))
  return row.subject?.name ? cleanSubjectLabel(String(row.subject.name)) : "Indonesia"
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

export function ChartModal({ item, onClose }: ChartModalProps) {
  const { data, isLoading, error } = useTimeSeries(item.id, item.type)
  const initialSubjects = item.initialFilters?.length ? item.initialFilters : (item.initialFilter ? [item.initialFilter] : [])
  const [subjectFilter, setSubjectFilter] = useState("")
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>(initialSubjects)

  const allRows = useMemo(() => {
    if (!data) return []
    return Array.isArray(data) ? data : data.observations ?? []
  }, [data])

  const allSubjects = useMemo(() => {
    const result = new Set<string>()
    allRows.forEach((row: any) => {
      result.add(getSubjectName(row))
    })
    return Array.from(result).sort((a, b) => a.localeCompare(b))
  }, [allRows])

  const matchingSubjects = useMemo(() => {
    const filter = subjectFilter.trim().toLowerCase()
    if (!filter) return allSubjects.slice(0, 40)
    return allSubjects.filter((subject) => subject.toLowerCase().includes(filter)).slice(0, 40)
  }, [allSubjects, subjectFilter])

  const rows = useMemo(() => {
    const selected = new Set(selectedSubjects.map((subject) => subject.toLowerCase()))
    const sortedRows = [...allRows].sort((a: any, b: any) => {
      const subjectDiff = getSubjectName(a).localeCompare(getSubjectName(b))
      if (subjectDiff !== 0) return subjectDiff
      return Number(a.tahun ?? 0) - Number(b.tahun ?? 0)
    })

    if (selected.size > 0) {
      return sortedRows.filter((row: any) => selected.has(String(getSubjectName(row)).toLowerCase()))
    }

    const filter = subjectFilter.trim().toLowerCase()
    if (filter) {
      return sortedRows.filter((row: any) => String(getSubjectName(row)).toLowerCase().includes(filter))
    }

    return sortedRows
  }, [allRows, selectedSubjects, subjectFilter])

  const toggleSubject = (subject: string) => {
    setSelectedSubjects((current) =>
      current.includes(subject)
        ? current.filter((item) => item !== subject)
        : [...current, subject]
    )
  }

  const addFirstMatchingSubject = () => {
    const subject = matchingSubjects[0]
    if (subject && !selectedSubjects.includes(subject)) {
      setSelectedSubjects((current) => [...current, subject])
      setSubjectFilter("")
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      <div className="absolute inset-0 bg-background/80" onClick={onClose}></div>
      <div className="relative bg-card border border-border shadow-lg rounded-md w-full max-w-6xl h-[88vh] flex flex-col animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="min-w-0 pr-12">
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">Tabel data dari database</p>
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

        <div className="flex-1 overflow-auto p-6 flex flex-col gap-5">
          {isLoading ? (
            <div className="flex-1 min-h-[420px] flex flex-col items-center justify-center text-primary rounded-md border border-dashed border-border bg-muted/20">
              <Loader2 className="h-10 w-10 animate-spin mb-4" />
              <p className="text-sm font-medium animate-pulse">Memuat tabel data…</p>
            </div>
          ) : error ? (
            <div className="flex-1 min-h-[420px] flex items-center justify-center text-destructive rounded-md border border-destructive/20 bg-destructive/5">
              Gagal memuat data dari database.
            </div>
          ) : allRows.length === 0 ? (
            <div className="flex-1 min-h-[420px] flex flex-col items-center justify-center rounded-md border border-dashed border-border bg-muted/20 text-center">
              <Table2 className="h-9 w-9 text-muted-foreground mb-3" />
              <p className="text-base font-semibold text-foreground">Tidak ada data</p>
              <p className="mt-1 text-sm text-muted-foreground">Database belum memiliki observasi untuk pilihan ini.</p>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div className="w-full lg:max-w-xl">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide" htmlFor="subject-filter">
                    Filter seri tabel
                  </label>
                  <div className="mt-2 flex gap-2">
                    <input
                      id="subject-filter"
                      list="subject-options"
                      value={subjectFilter}
                      onChange={(event) => setSubjectFilter(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault()
                          addFirstMatchingSubject()
                        }
                      }}
                      placeholder="Cari seri: Aspal, Kerikil, Cisayong"
                      className="min-w-0 flex-1 h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                    <button
                      type="button"
                      onClick={addFirstMatchingSubject}
                      disabled={!matchingSubjects[0] || selectedSubjects.includes(matchingSubjects[0])}
                      className="h-9 px-3 rounded-md border border-border bg-background text-sm font-medium text-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Tambah
                    </button>
                  </div>
                  <datalist id="subject-options">
                    {allSubjects.map((subject) => <option key={subject} value={subject} />)}
                  </datalist>

                  {selectedSubjects.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selectedSubjects.map((subject) => (
                        <button
                          key={subject}
                          type="button"
                          onClick={() => toggleSubject(subject)}
                          className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary hover:bg-primary/15"
                          title="Klik untuk hapus dari tabel"
                        >
                          {subject}
                          <span aria-hidden="true">×</span>
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={() => setSelectedSubjects([])}
                        className="rounded-full border border-border px-3 py-1 text-xs font-medium text-muted-foreground hover:bg-muted"
                      >
                        Tampilkan semua
                      </button>
                    </div>
                  )}

                  {subjectFilter && matchingSubjects.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {matchingSubjects.slice(0, 8).map((subject) => (
                        <button
                          key={subject}
                          type="button"
                          onClick={() => toggleSubject(subject)}
                          className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${selectedSubjects.includes(subject) ? "border-primary bg-primary/10 text-primary" : "border-border bg-background text-muted-foreground hover:bg-muted"}`}
                        >
                          {selectedSubjects.includes(subject) ? "✓ " : "+ "}{subject}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-md border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
                  <span className="font-semibold text-foreground">{rows.length}</span> baris ditampilkan dari <span className="font-semibold text-foreground">{allRows.length}</span> baris database
                </div>
              </div>

              {rows.length === 0 ? (
                <div className="flex-1 min-h-[360px] flex flex-col items-center justify-center rounded-md border border-dashed border-border bg-muted/20 text-center">
                  <Table2 className="h-9 w-9 text-muted-foreground mb-3" />
                  <p className="text-base font-semibold text-foreground">Tidak ada data</p>
                  <p className="mt-1 text-sm text-muted-foreground">Tidak ada baris yang cocok dengan filter seri saat ini.</p>
                </div>
              ) : (
                <div className="rounded-md border border-border bg-background overflow-hidden">
                  <div className="max-h-[58vh] overflow-auto">
                    <table className="w-full min-w-[760px] text-sm">
                      <thead className="sticky top-0 bg-background z-10 shadow-[0_1px_0_hsl(var(--border))]">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Tahun</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Seri</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Nilai</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Rincian</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Wilayah</th>
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row: any) => (
                          <tr key={row.id} className="border-b border-border last:border-0 hover:bg-muted/30">
                            <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.tahun ?? "-"}</td>
                            <td className="px-4 py-3 font-medium text-foreground whitespace-nowrap">{getSubjectName(row)}</td>
                            <td className="px-4 py-3 text-right font-semibold text-foreground whitespace-nowrap">{formatIndonesianNumber(getValue(row))}</td>
                            <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.rincian_nama && row.rincian_nama !== "-" ? row.rincian_nama : "-"}</td>
                            <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{row.wilayah_nama && row.wilayah_nama !== "-" ? row.wilayah_nama : "-"}</td>
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
