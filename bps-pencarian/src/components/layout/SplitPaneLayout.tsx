import { useState, useDeferredValue } from "react"
import { Sidebar } from "./Sidebar"
import { MainArea } from "./MainArea"

export function SplitPaneLayout() {
  const [query, setQuery] = useState("")
  // Vercel Best Practice: useDeferredValue for input responsiveness during heavy renders
  const deferredQuery = useDeferredValue(query)
  
  const [selectedItem, setSelectedItem] = useState<{id: number, type: 'tabel' | 'indikator', title: string, initialFilter?: string} | null>(null)

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden text-foreground">
      <Sidebar query={query} setQuery={setQuery} />
      <div className="flex-1 overflow-hidden relative flex flex-col">
        <MainArea query={deferredQuery} selectedItem={selectedItem} setSelectedItem={setSelectedItem} />
      </div>
    </div>
  )
}
