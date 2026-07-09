import { useState, useDeferredValue, Suspense, lazy } from "react"
import { Sidebar } from "./Sidebar"
import { MainArea } from "./MainArea"
import { CatalogBrowser, type CatalogSelection } from "../features/CatalogBrowser"
import { Loader2 } from "lucide-react"

const ChartModal = lazy(() => import("../features/ChartModal").then((module) => ({ default: module.ChartModal })))

type SelectedItem = {
  nomor_tabel?: string
  id?: number
  type: "tabel" | "indikator"
  title: string
  initialFilter?: string
  initialFilters?: string[]
}

export function SplitPaneLayout() {
  const [query, setQuery] = useState("")
  // Vercel Best Practice: useDeferredValue for input responsiveness during heavy renders
  const deferredQuery = useDeferredValue(query)

  // Modal lives at the layout level so it opens whether the user clicked a
  // browse card (no query) or a search result (has query).
  const [selectedItem, setSelectedItem] = useState<SelectedItem | null>(null)

  // When the user is searching, the browse panel slides out to the left (it is
  // kept mounted and animated, not unmounted) so the results get the full
  // width. They can slide it back with the header toggle or the panel's X.
  const [showBrowse, setShowBrowse] = useState(false)

  const openTabel = (selection: CatalogSelection) =>
    setSelectedItem({
      nomor_tabel: selection.nomor_tabel,
      type: "tabel",
      title: selection.title,
    })

  const hasQuery = deferredQuery.trim().length >= 2
  // When searching, the browse panel slides out to the left (kept mounted
  // + animated) and the results get the full width. When there is NO
  // query, show BOTH the browse panel (left) and the landing hint
  // (right) side by side so the user sees example queries that map
  // to the published table titles.
  const browseOpen = hasQuery ? showBrowse : true
  const showLanding = !hasQuery

  // No query: browse fills the whole main view. Querying: the panel is a
  // fixed-width rail that animates width + slide.
  const wrapperClass = hasQuery
    ? `shrink-0 overflow-hidden transition-[width] duration-300 ease-in-out motion-reduce:transition-none ${browseOpen ? "w-96" : "w-0"}`
    : "flex-1"
  const innerClass = hasQuery
    ? `h-full w-96 transition-transform duration-300 ease-in-out motion-reduce:transition-none ${browseOpen ? "translate-x-0" : "-translate-x-full"}`
    : "h-full"

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden text-foreground">
      <Sidebar query={query} setQuery={setQuery} />
      <div className={wrapperClass}>
        <div className={innerClass}>
          <CatalogBrowser
            onOpenTabel={openTabel}
            fill={showLanding ? false : !hasQuery}
            onClose={hasQuery ? () => setShowBrowse(false) : undefined}
          />
        </div>
      </div>
      {showLanding ? (
        <div className="flex-1 overflow-hidden relative flex flex-col">
          <MainArea
            query={deferredQuery}
            setQuery={setQuery}
            setSelectedItem={setSelectedItem}
            browseOpen={showBrowse}
            onToggleBrowse={() => setShowBrowse((v) => !v)}
          />
        </div>
      ) : hasQuery && (
        <div className="flex-1 overflow-hidden relative flex flex-col">
          <MainArea
            query={deferredQuery}
            setQuery={setQuery}
            setSelectedItem={setSelectedItem}
            browseOpen={showBrowse}
            onToggleBrowse={() => setShowBrowse((v) => !v)}
          />
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
    </div>
  )
}
