import { Search, FileText, BarChart3, Loader2, Table2, PanelLeft } from "lucide-react"
import { useSearch } from "../../lib/api"
import { InlineTimeSeriesAnswer } from "../features/InlineTimeSeriesAnswer"

type SelectedItem = {id?: number, nomor_tabel?: string, type: 'tabel' | 'indikator', title: string, initialFilter?: string, initialFilters?: string[]}

interface MainAreaProps {
  query: string
  setSelectedItem: (item: SelectedItem | null) => void
  showBrowseToggle?: boolean
  onToggleBrowse?: () => void
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

function RawResultCard({ children, icon, accent = "primary", onClick }: { children: React.ReactNode, icon: React.ReactNode, accent?: "primary" | "accent", onClick: () => void }) {
  const accentClass = accent === "primary" ? "bg-primary/80" : "bg-accent/80"
  const iconClass = accent === "primary" ? "bg-secondary/10 text-secondary" : "bg-accent/10 text-accent"

  return (
    <div
      onClick={onClick}
      className="group bg-background border border-border rounded-lg p-5 hover:border-primary/50 hover:shadow-md transition-all duration-200 cursor-pointer flex flex-col gap-4 relative overflow-hidden"
    >
      <div className={`absolute top-0 left-0 w-1 h-full ${accentClass} scale-y-0 group-hover:scale-y-100 transition-transform origin-bottom`}></div>
      <div className="flex items-start gap-4">
        <div className={`mt-1 h-10 w-10 rounded-md flex items-center justify-center shrink-0 ${iconClass}`}>
          {icon}
        </div>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  )
}

export function MainArea({ query, setSelectedItem, showBrowseToggle, onToggleBrowse }: MainAreaProps) {
  const { data, isLoading, error } = useSearch(query)

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
        {showBrowseToggle && (
          <button
            type="button"
            onClick={onToggleBrowse}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted transition-colors"
          >
            <PanelLeft className="h-4 w-4" />
            Jelajahi Publikasi
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
            {hasDirectAnswer && primaryQuickMatch && directAnswerSubject ? (
              <InlineTimeSeriesAnswer
                match={primaryQuickMatch}
                subjectName={directAnswerSubject}
                onOpenChart={() => setSelectedItem({
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
                        onClick={() => openTabel(tab.id, tab.judul)}
                      >
                        <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">{tab.judul}</h3>
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
