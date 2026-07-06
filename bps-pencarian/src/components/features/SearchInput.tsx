
import { Search } from "lucide-react"

interface SearchInputProps {
  query: string
  setQuery: (q: string) => void
}

export function SearchInput({ query, setQuery }: SearchInputProps) {
  return (
    <div className="relative group">
      <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none">
        <Search className="h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
      </div>
      <input
        type="text"
        className="w-full h-10 pl-10 pr-4 rounded-md border border-input bg-background text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-shadow duration-200"
        placeholder="Contoh: jumlah penduduk cisayong"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
    </div>
  )
}
