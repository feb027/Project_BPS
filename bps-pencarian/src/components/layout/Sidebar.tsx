
import { SearchInput } from "../features/SearchInput"

interface SidebarProps {
  query: string
  setQuery: (q: string) => void
}

export function Sidebar({ query, setQuery }: SidebarProps) {
  return (
    <aside className="w-80 shrink-0 border-r border-border bg-card/50 backdrop-blur-sm flex flex-col h-full shadow-sm z-10 transition-all duration-300">
      <div className="p-6 border-b border-border flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight text-primary">Data Publikasi BPS</h1>
        <p className="text-xs text-muted-foreground">Sistem Pencarian & Ekstraksi Time-Series</p>
      </div>
      
      <div className="p-6 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-foreground tracking-wide">PENCARIAN</h2>
          <SearchInput query={query} setQuery={setQuery} />
        </div>
      </div>
      
      <div className="p-4 border-t border-border mt-auto">
        <div className="text-[10px] text-muted-foreground uppercase tracking-widest text-center">
          Internal BPS Use Only
        </div>
      </div>
    </aside>
  )
}
