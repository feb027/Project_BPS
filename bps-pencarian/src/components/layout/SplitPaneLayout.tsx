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

  // When the user is searching, hide the browse panel by default so the
  // results get the full width (important on small screens). They can toggle
  // it back with the "Jelajahi" button.
  const [showBrowse, setShowBrowse] = useState(false)

  const openTabel = (selection: CatalogSelection) =>
    setSelectedItem({
      nomor_tabel: selection.nomor_tabel,
      type: "tabel",
      title: selection.title,
    })

  const hasQuery = deferredQuery.trim().length >= 2
  const browseVisible = hasQuery ? showBrowse : true

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden text-foreground">
      <Sidebar query={query} setQuery={setQuery} />
      {browseVisible && <CatalogBrowser onOpenTabel={openTabel} fill={!hasQuery} />}
      {hasQuery && (
        <div className="flex-1 overflow-hidden relative flex flex-col">
          <MainArea
            query={deferredQuery}
            setSelectedItem={setSelectedItem}
            showBrowseToggle={!browseVisible}
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
