import { Search, FileText, BarChart3, Loader2, Table2, PanelLeft, Plus, Check, Columns2 } from "lucide-react"
import { useEffect, useRef } from "react"
import type { Dispatch, SetStateAction } from "react"
import { useSearch } from "../../lib/api"
import { InlineTimeSeriesAnswer } from "../features/InlineTimeSeriesAnswer"
import { cleanTitle } from "../../lib/utils"
import type { CompareItem } from "../features/CompareModal"

type SelectedItem = {id?: number, nomor_tabel?: string, type: 'tabel' | 'indikator' | 'series', title: string, initialFilter?: string, initialFilters?: string[], seriesObservations?: any[], subjectName?: string}

interface MainAreaProps {
  query: string
  setSelectedItem: Dispatch<SetStateAction<SelectedItem | null>>
  browseOpen?: boolean
  onToggleBrowse?: () => void
  inCompare: (nomorTabel: string) => boolean
  onToggleCompare: (item: CompareItem) => void
  onAutoCompare: (items: CompareItem[]) => void
}

type EmptyPanelProps = {
  title: string
  description: string
  icon?: "search" | "table" | "loading" | "error"
}

function EmptyPanel({ title, description, icon = "table" }: EmptyPanelProps) {
  const Icon = icon === "search" ? Search : icon === "loading" ? Loader2 : Table2
  const isLoading = icon === "loading"
  const tone = icon === "error" ? "text-destructive" : "text-muted-foreground"

  return (
    <section className="rounded-lg border border-border bg-card min-h-[calc(100vh-10rem)] shadow-sm flex flex-col">
      <div className="border-b border-border px-5 py-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">Jawaban langsung</p>
        <h3 className="mt-1 text-xl font-semibold text-foreground">Hasil pencarian</h3>
      </div>
      <div className="flex-1 rounded-b-lg bg-background/50 p-6">
        <div className="h-full min-h-[420px] rounded-md border border-dashed border-border bg-muted/20 flex flex-col items-center justify-center text-center px-6">
          <Icon className={`h-10 w-10 mb-4 ${tone} ${isLoading ? "animate-spin" : ""}`} />
          <p className="text-lg font-semibold text-foreground">{title}</p>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>
        </div>
      </div>
    </section>
  )
}

function RawResultCard({ children, icon, accent = "primary", onClick, action }: { children: React.ReactNode, icon: React.ReactNode, accent?: "primary" | "accent", onClick: () => void, action?: React.ReactNode }) {
  const accentClass = accent === "primary" ? "bg-primary/80" : "bg-accent/80"
  const iconClass = accent === "primary" ? "bg-secondary/10 text-secondary" : "bg-accent/10 text-accent"

  return (
    <div
      onClick={onClick}
      className="group bg-background border border-border rounded-lg p-5 hover:border-primary/50 hover:shadow-md transition-all duration-200 cursor-pointer flex flex-col gap-4 relative overflow-hidden"
    >
      <div className={`absolute top-0 left-0 w-1 h-full ${accentClass} scale-y-0 group-hover:scale-y-100 transition-transform origin-bottom`}></div>
      {action && <div className="absolute right-3 top-3 z-10">{action}</div>}
      <div className="flex items-start gap-4">
        <div className={`mt-1 h-10 w-10 rounded-md flex items-center justify-center shrink-0 ${iconClass}`}>
          {icon}
        </div>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  )
}

export function MainArea({ query, setSelectedItem, browseOpen, onToggleBrowse, inCompare, onToggleCompare, onAutoCompare }: MainAreaProps) {
  const { data, isLoading, error } = useSearch(query)

  // Phase 2: multi-concept query ("murid sma + guru sma") — auto-fill the
  // comparison basket with the best table per concept and open it. Guarded by
  // a ref so we only auto-open ONCE per (query, tables) combination instead of
  // re-opening on every keystroke while the user keeps typing.
  const lastAutoCompareRef = useRef("")
  const multiConcepts = (data?.multi_concepts ?? []) as any[]
  const multiTables = multiConcepts
    .map((m) => ({ tabel: m?.observations?.[0]?.tabel, indicator_name: m?.indicator_name }))
    .filter((x: any) => x.tabel && x.tabel.nomor_tabel)
  const multiKey = query + "|" + multiTables.map((x: any) => x.tabel.nomor_tabel).join(",")
  useEffect(() => {
    if (multiTables.length < 2) return
    if (lastAutoCompareRef.current === multiKey) return
    lastAutoCompareRef.current = multiKey
    onAutoCompare(
      multiTables.map((x: any) => ({
        nomor_tabel: String(x.tabel.nomor_tabel),
        title: cleanTitle(x.tabel.judul || x.tabel.nomor_tabel),
        metricHint: String(x.indicator_name || ""),
      }))
    )
  }, [multiKey, multiTables, onAutoCompare])

  const detectedWilayah = data?.detected_wilayah?.nama as string | undefined
  const detectedWilayahs = (data?.detected_wilayahs ?? [])
    .map((wilayah: any) => wilayah?.nama)
    .filter(Boolean) as string[]
  const quickMatches = data?.quick_matches ?? []
  const primaryQuickMatch = quickMatches[0]
  const quickObservationSubjects = Array.from(new Set(
    ((primaryQuickMatch?.observations ?? []) as any[])
      .map((row: any) => row?.subject_name || (row?.wilayah_nama !== "-" ? row?.wilayah_nama : row?.rincian_nama))
      .filter(Boolean)
  )) as string[]
  const quickComparisonSubjects = ((primaryQuickMatch?.comparison_subjects ?? []) as any[])
    .map((subject: any) => subject?.nama)
    .filter(Boolean) as string[]
  const directAnswerSubject = primaryQuickMatch?.subject_name || detectedWilayah
  const directAnswerFilter = detectedWilayah || (quickObservationSubjects.length === 1 ? quickObservationSubjects[0] : undefined)
  const initialSubjectFilters = detectedWilayahs.length > 0
    ? detectedWilayahs
    : (quickObservationSubjects.length > 0 ? quickObservationSubjects : quickComparisonSubjects)
  const hasDirectAnswer = Boolean(primaryQuickMatch && directAnswerSubject)
  const resultCount = (data?.tabel?.length ?? 0) + (data?.indikator?.length ?? 0)
  const hasData = Boolean(data && (resultCount > 0 || quickMatches.length > 0))

  const openIndikator = (id: number, title: string) => setSelectedItem({
    id,
    type: 'indikator',
    title,
    initialFilter: directAnswerFilter,
    initialFilters: initialSubjectFilters,
  })

  const openTabel = (id: number, title: string) => setSelectedItem({
    id,
    type: 'tabel',
    title,
    initialFilter: directAnswerFilter,
    initialFilters: initialSubjectFilters,
  })

  return (
    <main className="flex-1 bg-muted/20 overflow-y-auto w-full relative">
      <header className="h-16 border-b border-border bg-card flex items-center justify-between px-8 sticky top-0 z-10 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="h-8 w-8 rounded bg-primary/10 flex items-center justify-center text-primary">
            <Search className="h-4 w-4" />
          </div>
          <h2 className="text-lg font-semibold text-foreground tracking-tight">Hasil Pencarian</h2>
        </div>
        {browseOpen !== undefined && onToggleBrowse && (
          <button
            type="button"
            onClick={onToggleBrowse}
            aria-pressed={browseOpen}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted transition-colors"
          >
            <PanelLeft className="h-4 w-4" />
            {browseOpen ? "Sembunyikan" : "Jelajahi Publikasi"}
          </button>
        )}
      </header>

      <div className="p-8 max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
        {query.length < 2 ? (
          <EmptyPanel
            icon="search"
            title="Belum ada pencarian"
            description="Ketik nama indikator, rincian, atau wilayah. Area hasil tetap penuh supaya grafik atau tabel berikutnya tidak mengubah tata letak halaman."
          />
        ) : isLoading ? (
          <EmptyPanel
            icon="loading"
            title="Memuat data"
            description="Sistem sedang mencari indikator, rincian, dan tabel yang cocok dari database publikasi."
          />
        ) : error ? (
          <EmptyPanel
            icon="error"
            title="Gagal memuat data"
            description="Terjadi kesalahan saat mengambil hasil dari API pencarian. Coba ulangi beberapa saat lagi."
          />
        ) : !hasData ? (
          <EmptyPanel
            icon="table"
            title="Tidak ada data"
            description={`Tidak ditemukan data untuk "${query}". Coba gunakan kata kunci lain seperti nama indikator, rincian, atau kecamatan.`}
          />
        ) : (
          <div className="space-y-8 min-h-[calc(100vh-10rem)]">
            {multiTables.length >= 2 && (
              <div className="flex flex-wrap items-center gap-3 rounded-md border border-accent/40 bg-accent/5 px-4 py-3">
                <Columns2 className="h-4 w-4 shrink-0 text-accent" />
                <p className="min-w-0 flex-1 text-sm text-foreground">
                  Terdeteksi <strong>{multiTables.length} konsep</strong> — grafik perbandingan dibuka otomatis.
                </p>
                <button
                  type="button"
                  onClick={() =>
                    onAutoCompare(
                      multiTables.map((x: any) => ({
                        nomor_tabel: String(x.tabel.nomor_tabel),
                        title: cleanTitle(x.tabel.judul || x.tabel.nomor_tabel),
                        metricHint: String(x.indicator_name || ""),
                      }))
                    )
                  }
                  className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 transition-opacity"
                >
                  <Columns2 className="h-3.5 w-3.5" /> Bandingkan
                </button>
              </div>
            )}
            {hasDirectAnswer && primaryQuickMatch && directAnswerSubject ? (
              <InlineTimeSeriesAnswer
                match={primaryQuickMatch}
                subjectName={directAnswerSubject}
                onOpenChart={() => setSelectedItem(primaryQuickMatch.drill_mode === "series"
                  ? {
                      type: 'series',
                      title: primaryQuickMatch.indicator_name,
                      seriesObservations: primaryQuickMatch.observations,
                      subjectName: directAnswerSubject,
                    }
                  : {
                      id: primaryQuickMatch.indicator_id,
                      type: 'indikator',
                      title: primaryQuickMatch.indicator_name,
                      initialFilter: directAnswerFilter,
                      initialFilters: initialSubjectFilters,
                    })}
              />
            ) : (
              <EmptyPanel
                icon="table"
                title="Tidak ada data"
                description="Hasil indikator atau tabel ditemukan, tetapi belum ada observasi numerik yang dapat langsung divisualkan. Buka kandidat di bawah untuk melihat tabel database."
              />
            )}

            <div className="rounded-lg border border-border bg-card p-4">
              <details open={!hasDirectAnswer}>
                <summary className="cursor-pointer text-sm font-semibold text-foreground">
                  Hasil lain dari database ({resultCount})
                </summary>
                <p className="mt-2 text-sm text-muted-foreground">
                  Kandidat indikator dan tabel mentah dari publikasi. Buka kalau ingin melihat data database selain jawaban utama.
                </p>

                {resultCount === 0 ? (
                  <div className="mt-4 rounded-md border border-dashed border-border bg-muted/20 p-8 text-center">
                    <p className="font-semibold text-foreground">Tidak ada data</p>
                    <p className="mt-1 text-sm text-muted-foreground">Tidak ada kandidat indikator atau tabel untuk query ini.</p>
                  </div>
                ) : (
                  <div className="mt-4 grid grid-cols-1 gap-4">
                    {data.indikator?.map((ind: any) => (
                      <RawResultCard
                        key={`ind-${ind.id}`}
                        icon={<BarChart3 className="h-5 w-5" />}
                        accent="primary"
                        onClick={() => openIndikator(ind.id, ind.nama)}
                      >
                        <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">{ind.nama}</h3>
                        <div className="flex items-center gap-3 mt-1.5">
                          <span className="inline-flex items-center rounded-full bg-secondary/10 px-2.5 py-0.5 text-xs font-semibold text-secondary">Indikator</span>
                          <span className="text-xs text-muted-foreground">Klik untuk tabel detail</span>
                        </div>
                      </RawResultCard>
                    ))}

                    {data.tabel?.map((tab: any) => (
                      <RawResultCard
                        key={`tab-${tab.id}`}
                        icon={<FileText className="h-5 w-5" />}
                        accent="accent"
                        onClick={() => openTabel(tab.id, cleanTitle(tab.judul))}
                        action={
                          tab.nomor_tabel ? (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                onToggleCompare({
                                  nomor_tabel: String(tab.nomor_tabel),
                                  title: cleanTitle(tab.judul),
                                })
                              }}
                              title={
                                inCompare(String(tab.nomor_tabel))
                                  ? "Hapus dari perbandingan"
                                  : "Tambah ke perbandingan"
                              }
                              aria-pressed={inCompare(String(tab.nomor_tabel))}
                              className={`inline-flex h-7 w-7 items-center justify-center rounded-md border transition-colors ${
                                inCompare(String(tab.nomor_tabel))
                                  ? "bg-accent border-accent text-white"
                                  : "border-border bg-background text-muted-foreground hover:border-accent hover:text-accent"
                              }`}
                            >
                              {inCompare(String(tab.nomor_tabel)) ? (
                                <Check className="h-4 w-4" />
                              ) : (
                                <Plus className="h-4 w-4" />
                              )}
                            </button>
                          ) : undefined
                        }
                      >
                        <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">{cleanTitle(tab.judul)}</h3>
                        <div className="flex items-center gap-3 mt-1.5">
                          <span className="inline-flex items-center rounded-full bg-accent/10 px-2.5 py-0.5 text-xs font-semibold text-accent">Tabel Data</span>
                          {tab.nomor_tabel && <span className="text-xs text-muted-foreground">Tabel {tab.nomor_tabel}</span>}
                        </div>
                      </RawResultCard>
                    ))}
                  </div>
                )}
              </details>
            </div>
          </div>
        )}
      </div>

    </main>
  )
}
