import { Suspense, lazy } from "react"
import { Search, FileText, BarChart3, Loader2 } from "lucide-react"
import { useSearch } from "../../lib/api"
import { InlineTimeSeriesAnswer } from "../features/InlineTimeSeriesAnswer"

const ChartModal = lazy(() => import("../features/ChartModal").then(module => ({ default: module.ChartModal })))

type SelectedItem = {id: number, type: 'tabel' | 'indikator', title: string, initialFilter?: string}

interface MainAreaProps {
  query: string
  selectedItem: SelectedItem | null
  setSelectedItem: (item: SelectedItem | null) => void
}

export function MainArea({ query, selectedItem, setSelectedItem }: MainAreaProps) {
  const { data, isLoading, error } = useSearch(query)

  const detectedWilayah = data?.detected_wilayah?.nama as string | undefined
  const quickMatches = data?.quick_matches ?? []
  const primaryQuickMatch = quickMatches[0]
  const directAnswerSubject = primaryQuickMatch?.subject_name || detectedWilayah
  const directAnswerFilter = detectedWilayah
  const hasDirectAnswer = Boolean(primaryQuickMatch && directAnswerSubject)
  const hasData = data && (data.tabel?.length > 0 || data.indikator?.length > 0 || quickMatches.length > 0)

  return (
    <main className="flex-1 bg-muted/20 overflow-y-auto w-full relative">
      {/* Header */}
      <header className="h-16 border-b border-border bg-card flex items-center justify-between px-8 sticky top-0 z-10 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="h-8 w-8 rounded bg-primary/10 flex items-center justify-center text-primary">
            <Search className="h-4 w-4" />
          </div>
          <h2 className="text-lg font-semibold text-foreground tracking-tight">Hasil Pencarian</h2>
        </div>
      </header>

      {/* Content Body */}
      <div className="p-8 max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
        
        {query.length < 2 ? (
          <div className="text-center p-12 border border-dashed border-border rounded-lg bg-card/50">
            <Search className="h-8 w-8 text-muted-foreground mx-auto mb-4 opacity-50" />
            <p className="text-muted-foreground">Ketik minimal 2 karakter untuk mulai mencari data publikasi BPS.</p>
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center p-12 text-primary">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        ) : error ? (
          <div className="text-center p-12 text-destructive border border-destructive/20 bg-destructive/5 rounded-lg">
            Terjadi kesalahan saat memuat data.
          </div>
        ) : !hasData ? (
          <div className="text-center p-12 border border-border rounded-lg bg-card">
            <p className="text-muted-foreground">Tidak ditemukan hasil untuk "{query}"</p>
          </div>
        ) : (
          <div className="space-y-8">
            {hasDirectAnswer && primaryQuickMatch && directAnswerSubject && (
              <InlineTimeSeriesAnswer
                match={primaryQuickMatch}
                subjectName={directAnswerSubject}
                onOpenChart={() => setSelectedItem({
                  id: primaryQuickMatch.indicator_id,
                  type: 'indikator',
                  title: primaryQuickMatch.indicator_name,
                  initialFilter: directAnswerFilter,
                })}
              />
            )}

            <div className={hasDirectAnswer ? "rounded-lg border border-border bg-card p-4" : "space-y-4"}>
              {hasDirectAnswer ? (
                <details>
                  <summary className="cursor-pointer text-sm font-semibold text-foreground">
                    Hasil lain dari database ({data.tabel.length + data.indikator.length})
                  </summary>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Ini adalah kandidat indikator/tabel mentah dari publikasi: varian laki-laki/perempuan, total, kemiskinan, atau tabel terkait lain. Dibuka hanya kalau jawaban utama belum sesuai.
                  </p>
                  <div className="mt-4 grid grid-cols-1 gap-4">
                    {data.indikator?.map((ind: any) => (
                      <div key={`ind-${ind.id}`}
                           onClick={() => setSelectedItem({id: ind.id, type: 'indikator', title: ind.nama, initialFilter: detectedWilayah})}
                           className="group bg-background border border-border rounded-lg p-5 hover:border-primary/50 hover:shadow-md transition-all duration-200 cursor-pointer flex flex-col gap-4 relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-1 h-full bg-primary/80 scale-y-0 group-hover:scale-y-100 transition-transform origin-bottom"></div>
                        <div className="flex items-start justify-between">
                          <div className="flex gap-4">
                            <div className="mt-1 h-10 w-10 rounded-md bg-secondary/10 flex items-center justify-center text-secondary shrink-0">
                              <BarChart3 className="h-5 w-5" />
                            </div>
                            <div>
                              <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">{ind.nama}</h3>
                              <div className="flex items-center gap-3 mt-1.5">
                                <span className="inline-flex items-center rounded-full bg-secondary/10 px-2.5 py-0.5 text-xs font-semibold text-secondary">Indikator Strategis</span>
                                <span className="text-xs text-muted-foreground">Satu Data BPS</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}

                    {data.tabel?.map((tab: any) => (
                      <div key={`tab-${tab.id}`}
                           onClick={() => setSelectedItem({id: tab.id, type: 'tabel', title: tab.judul, initialFilter: detectedWilayah})}
                           className="group bg-background border border-border rounded-lg p-5 hover:border-primary/50 hover:shadow-md transition-all duration-200 cursor-pointer flex flex-col gap-4 relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-1 h-full bg-accent/80 scale-y-0 group-hover:scale-y-100 transition-transform origin-bottom"></div>
                        <div className="flex items-start justify-between">
                          <div className="flex gap-4">
                            <div className="mt-1 h-10 w-10 rounded-md bg-accent/10 flex items-center justify-center text-accent shrink-0">
                              <FileText className="h-5 w-5" />
                            </div>
                            <div>
                              <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">{tab.judul}</h3>
                              <div className="flex items-center gap-3 mt-1.5">
                                <span className="inline-flex items-center rounded-full bg-accent/10 px-2.5 py-0.5 text-xs font-semibold text-accent">Tabel Data</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">
                    Menampilkan <span className="font-semibold text-foreground">{data.tabel.length + data.indikator.length}</span> hasil untuk <span className="font-semibold text-foreground">"{query}"</span>
                  </p>
                  <div className="grid grid-cols-1 gap-4">
                    {data.indikator?.map((ind: any) => (
                      <div key={`ind-${ind.id}`}
                           onClick={() => setSelectedItem({id: ind.id, type: 'indikator', title: ind.nama, initialFilter: detectedWilayah})}
                           className="group bg-card border border-border rounded-lg p-5 hover:border-primary/50 hover:shadow-md transition-all duration-200 cursor-pointer flex flex-col gap-4 relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-1 h-full bg-primary/80 scale-y-0 group-hover:scale-y-100 transition-transform origin-bottom"></div>
                        <div className="flex items-start justify-between">
                          <div className="flex gap-4">
                            <div className="mt-1 h-10 w-10 rounded-md bg-secondary/10 flex items-center justify-center text-secondary shrink-0">
                              <BarChart3 className="h-5 w-5" />
                            </div>
                            <div>
                              <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">{ind.nama}</h3>
                              <div className="flex items-center gap-3 mt-1.5">
                                <span className="inline-flex items-center rounded-full bg-secondary/10 px-2.5 py-0.5 text-xs font-semibold text-secondary">Indikator Strategis</span>
                                <span className="text-xs text-muted-foreground">Satu Data BPS</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}

                    {data.tabel?.map((tab: any) => (
                      <div key={`tab-${tab.id}`}
                           onClick={() => setSelectedItem({id: tab.id, type: 'tabel', title: tab.judul, initialFilter: detectedWilayah})}
                           className="group bg-card border border-border rounded-lg p-5 hover:border-primary/50 hover:shadow-md transition-all duration-200 cursor-pointer flex flex-col gap-4 relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-1 h-full bg-accent/80 scale-y-0 group-hover:scale-y-100 transition-transform origin-bottom"></div>
                        <div className="flex items-start justify-between">
                          <div className="flex gap-4">
                            <div className="mt-1 h-10 w-10 rounded-md bg-accent/10 flex items-center justify-center text-accent shrink-0">
                              <FileText className="h-5 w-5" />
                            </div>
                            <div>
                              <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">{tab.judul}</h3>
                              <div className="flex items-center gap-3 mt-1.5">
                                <span className="inline-flex items-center rounded-full bg-accent/10 px-2.5 py-0.5 text-xs font-semibold text-accent">Tabel Data</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Chart Modal (Lazy Loaded) */}
      {selectedItem && (
        <Suspense fallback={<div className="absolute inset-0 bg-background/50 flex items-center justify-center"><Loader2 className="animate-spin" /></div>}>
          <ChartModal item={selectedItem} onClose={() => setSelectedItem(null)} />
        </Suspense>
      )}
    </main>
  )
}
