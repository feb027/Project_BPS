import { useState, useDeferredValue, Suspense, lazy, useCallback, useEffect } from "react"
import { Sidebar } from "./Sidebar"
import { MainArea } from "./MainArea"
import { CatalogBrowser, type CatalogSelection } from "../features/CatalogBrowser"
import { SearchInput } from "../features/SearchInput"
import { JenisDataChips } from "../features/JenisDataChips"
import { Loader2, Columns2, Trash2, PanelLeft } from "lucide-react"
import type { CompareItem } from "../features/CompareModal"

const ChartModal = lazy(() => import("../features/ChartModal").then((module) => ({ default: module.ChartModal })))
const CompareModal = lazy(() => import("../features/CompareModal").then((module) => ({ default: module.CompareModal })))

type SelectedItem = {
  nomor_tabel?: string
  id?: number
  type: "tabel" | "indikator" | "series"
  title: string
  initialFilter?: string
  initialFilters?: string[]
  seriesObservations?: any[]
  subjectName?: string
}

const COMPARE_KEY = "bps_compare_basket"
const MAX_COMPARE = 6

function loadCompareBasket(): CompareItem[] {
  try {
    const raw = localStorage.getItem(COMPARE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return parsed
        .filter((c) => c && typeof c.nomor_tabel === "string" && typeof c.title === "string")
        .slice(0, MAX_COMPARE)
    }
  } catch {
    /* ignore corrupt storage */
  }
  return []
}

export function SplitPaneLayout() {
  const [query, setQuery] = useState("")
  // Vercel Best Practice: useDeferredValue for input responsiveness during heavy renders
  const deferredQuery = useDeferredValue(query)

  // Jenis Data filter (sidebar) — applied to the catalog browser and to table
  // candidates in search results.
  const [filterTipe, setFilterTipe] = useState("all")

  // Modal lives at the layout level so it opens whether the user clicked a
  // browse card (no query) or a search result (has query).
  const [selectedItem, setSelectedItem] = useState<SelectedItem | null>(null)

  // When the user is searching, the browse panel slides out to the left (it is
  // kept mounted and animated, not unmounted) so the results get the full
  // width. They can slide it back with the header toggle or the panel's X.
  const [showBrowse, setShowBrowse] = useState(false)

  // Multi-table comparison basket (persisted across visits).
  const [compareItems, setCompareItems] = useState<CompareItem[]>(loadCompareBasket)
  const [compareOpen, setCompareOpen] = useState(false)

  useEffect(() => {
    try {
      localStorage.setItem(COMPARE_KEY, JSON.stringify(compareItems))
    } catch {
      /* ignore quota / private mode errors */
    }
  }, [compareItems])

  const toggleCompare = useCallback((item: CompareItem) => {
    setCompareItems((prev) => {
      const exists = prev.some((c) => c.nomor_tabel === item.nomor_tabel)
      if (exists) return prev.filter((c) => c.nomor_tabel !== item.nomor_tabel)
      if (prev.length >= MAX_COMPARE) return prev
      return [...prev, item]
    })
  }, [])

  const removeCompare = useCallback((nomorTabel: string) => {
    setCompareItems((prev) => prev.filter((c) => c.nomor_tabel !== nomorTabel))
  }, [])

  const clearCompare = useCallback(() => {
    setCompareItems([])
    setCompareOpen(false)
  }, [])

  // Phase 2: multi-concept search ("murid sma + guru sma") replaces the basket
  // with the detected tables and opens the comparison automatically.
  const autoCompare = useCallback((items: CompareItem[]) => {
    if (items.length < 2) return
    setCompareItems(items)
    setCompareOpen(true)
  }, [])

  const inCompare = useCallback(
    (nomorTabel: string) => compareItems.some((c) => c.nomor_tabel === nomorTabel),
    [compareItems]
  )

  const openTabel = (selection: CatalogSelection) =>
    setSelectedItem({
      nomor_tabel: selection.nomor_tabel,
      type: "tabel",
      title: selection.title,
    })

  const hasQuery = deferredQuery.trim().length >= 2
  const browseOpen = hasQuery ? showBrowse : true

  // No query: browse fills the whole main view. Querying: the panel is a
  // fixed-width rail that animates width + slide. On mobile (<md) the rail is
  // full width and the Sidebar is replaced by the mobile header.
  const wrapperClass = hasQuery
    ? `shrink-0 overflow-hidden transition-[width] duration-300 ease-in-out motion-reduce:transition-none ${browseOpen ? "w-full md:w-96" : "w-0"}`
    : "flex-1 min-w-0"
  const innerClass = hasQuery
    ? `h-full w-full md:w-96 transition-transform duration-300 ease-in-out motion-reduce:transition-none ${browseOpen ? "translate-x-0" : "-translate-x-full"}`
    : "h-full"

  return (
    <div className="flex h-screen w-full flex-col bg-background overflow-hidden text-foreground">
      {/* Mobile header (hidden on md+) — replaces the Sidebar on small screens */}
      <div className="md:hidden border-b border-border bg-card px-4 py-2.5 flex flex-col gap-2 z-20 shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-semibold tracking-tight text-primary whitespace-nowrap">
            Data BPS
          </h1>
          <div className="flex-1 min-w-0">
            <SearchInput query={query} setQuery={setQuery} />
          </div>
          {hasQuery && (
            <button
              type="button"
              onClick={() => setShowBrowse((v) => !v)}
              aria-pressed={showBrowse}
              className="shrink-0 inline-flex items-center gap-1 rounded-md border border-border bg-background px-2.5 py-2 text-xs font-semibold text-foreground hover:bg-muted transition-colors"
            >
              <PanelLeft className="h-3.5 w-3.5" />
              {showBrowse ? "Hasil" : "Jelajahi"}
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 overflow-x-auto pb-0.5">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground shrink-0">
            Jenis Data:
          </span>
          <JenisDataChips filterTipe={filterTipe} onFilterTipe={setFilterTipe} />
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <Sidebar query={query} setQuery={setQuery} filterTipe={filterTipe} onFilterTipe={setFilterTipe} />
        <div className={wrapperClass}>
          <div className={innerClass}>
            <CatalogBrowser
              onOpenTabel={openTabel}
              fill={!hasQuery}
              onClose={hasQuery ? () => setShowBrowse(false) : undefined}
              compareItems={compareItems}
              inCompare={inCompare}
              onToggleCompare={toggleCompare}
              filterTipe={filterTipe}
            />
          </div>
        </div>
        {hasQuery && (
          <div className="flex-1 overflow-hidden relative flex flex-col">
            <MainArea
              query={deferredQuery}
              setSelectedItem={setSelectedItem}
              browseOpen={showBrowse}
              onToggleBrowse={() => setShowBrowse((v) => !v)}
              inCompare={inCompare}
              onToggleCompare={toggleCompare}
              onAutoCompare={autoCompare}
              filterTipe={filterTipe}
            />
          </div>
        )}
      </div>

      {compareItems.length > 0 && !compareOpen && (
        <div className="fixed bottom-6 left-1/2 z-40 -translate-x-1/2 max-w-[calc(100vw-1.5rem)]">
          <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 shadow-lg animate-in slide-in-from-bottom-4 duration-200">
            <Columns2 className="h-4 w-4 shrink-0 text-accent" />
            <span className="text-xs font-semibold text-foreground whitespace-nowrap">
              {compareItems.length} tabel dipilih
            </span>
            <div className="mx-1 h-5 w-px bg-border" />
            <button
              type="button"
              onClick={() => setCompareOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3.5 py-1.5 text-xs font-semibold text-white hover:opacity-90 transition-opacity"
            >
              Lihat
            </button>
            <button
              type="button"
              onClick={clearCompare}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
              aria-label="Bersihkan pilihan"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {selectedItem && (
        <Suspense
          fallback={
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          }
        >
          <ChartModal item={selectedItem} onClose={() => setSelectedItem(null)} />
        </Suspense>
      )}

      {compareOpen && (
        <Suspense
          fallback={
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          }
        >
          <CompareModal
            items={compareItems}
            onClose={() => setCompareOpen(false)}
            onRemove={(nomorTabel) => {
              removeCompare(nomorTabel)
              if (compareItems.length <= 1) setCompareOpen(false)
            }}
          />
        </Suspense>
      )}
    </div>
  )
}
