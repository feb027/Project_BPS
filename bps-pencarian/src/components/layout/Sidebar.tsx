
import { SearchInput } from "../features/SearchInput"

interface SidebarProps {
  query: string
  setQuery: (q: string) => void
  filterTipe: string
  onFilterTipe: (tipe: string) => void
}

const TIPE_OPTIONS = [
  { value: "all", label: "Semua" },
  { value: "kecamatan", label: "Per Kecamatan" },
  { value: "kabupaten", label: "Per Kabupaten" },
  { value: "kategori", label: "Per Kategori" },
]

export function Sidebar({ query, setQuery, filterTipe, onFilterTipe }: SidebarProps) {
  return (
    <aside className="w-80 shrink-0 border-r border-border bg-card/50 backdrop-blur-sm flex flex-col h-full shadow-sm z-10 transition-all duration-300">
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
            <div className="flex flex-wrap gap-1.5">
              {TIPE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => onFilterTipe(opt.value)}
                  aria-pressed={filterTipe === opt.value}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors border ${
                    filterTipe === opt.value
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-background text-muted-foreground border-border hover:border-primary/40 hover:text-foreground"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
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
