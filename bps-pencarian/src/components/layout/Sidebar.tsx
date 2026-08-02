
import { SearchInput } from "../features/SearchInput"
import { JenisDataChips } from "../features/JenisDataChips"

interface SidebarProps {
  query: string
  setQuery: (q: string) => void
  filterTipe: string
  onFilterTipe: (tipe: string) => void
}

export function Sidebar({ query, setQuery, filterTipe, onFilterTipe }: SidebarProps) {
  return (
    <aside className="hidden md:flex md:w-80 shrink-0 border-r border-border bg-card/50 backdrop-blur-sm flex-col h-full shadow-sm z-10 transition-all duration-300">
      <div className="p-6 border-b border-border flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight text-primary">Data Publikasi BPS</h1>
        <p className="text-xs text-muted-foreground">Sistem Pencarian & Ekstraksi Time-Series</p>
      </div>
      
      <div className="p-6 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-foreground tracking-wide">PENCARIAN</h2>
            <SearchInput query={query} setQuery={setQuery} />
          </div>

          <div className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-foreground tracking-wide">JENIS DATA</h2>
            <p className="text-xs text-muted-foreground -mt-1">
              Saring tabel di katalog dan hasil pencarian.
            </p>
            <JenisDataChips filterTipe={filterTipe} onFilterTipe={onFilterTipe} />
          </div>
        </div>
      </div>
      
      <div className="p-4 border-t border-border mt-auto">
        <div className="text-[10px] text-muted-foreground uppercase tracking-widest text-center">
          Data BPS Kab. Tasikmalaya
        </div>
      </div>
    </aside>
  )
}
