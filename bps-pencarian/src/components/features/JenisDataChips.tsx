interface JenisDataChipsProps {
  filterTipe: string
  onFilterTipe: (tipe: string) => void
}

const TIPE_OPTIONS = [
  { value: "all", label: "Semua" },
  { value: "kecamatan", label: "Per Kecamatan" },
  { value: "kabupaten", label: "Per Kabupaten" },
  { value: "kategori", label: "Per Kategori" },
]

export function JenisDataChips({ filterTipe, onFilterTipe }: JenisDataChipsProps) {
  return (
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
  )
}
