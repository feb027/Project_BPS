import { useState, useDeferredValue } from "react"
import { Sidebar } from "./Sidebar"
import { MainArea } from "./MainArea"
import { CatalogBrowser, type CatalogSelection } from "../features/CatalogBrowser"

type SelectedItem = {
  id: number
  type: "tabel" | "indikator"
  title: string
  initialFilter?: string
  initialFilters?: string[]
}

export function SplitPaneLayout() {
  const [query, setQuery] = useState("")
  // Vercel Best Practice: useDeferredValue for input responsiveness during heavy renders
  const deferredQuery = useDeferredValue(query)

  const [selectedItem, setSelectedItem] = useState<SelectedItem | null>(null)

  const openTabel = (selection: CatalogSelection) =>
    setSelectedItem({
      id: selection.id,
      type: selection.type,
      title: selection.title,
    })

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden text-foreground">
      <Sidebar query={query} setQuery={setQuery} />
      <CatalogBrowser onOpenTabel={openTabel} />
      <div className="flex-1 overflow-hidden relative flex flex-col">
        <MainArea query={deferredQuery} selectedItem={selectedItem} setSelectedItem={setSelectedItem} />
      </div>
    </div>
  )
}
