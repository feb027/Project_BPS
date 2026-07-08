import { useState } from "react"
import {
  ChevronDown,
  Table2,
  Layers,
  BookOpen,
  Loader2,
  AlertTriangle,
  FileBarChart,
  Eye,
} from "lucide-react"
import { useCatalog, type CatalogTable } from "../../lib/api"

export interface CatalogSelection {
  id: number
  type: "tabel"
  title: string
}

interface CatalogBrowserProps {
  onOpenTabel: (selection: CatalogSelection) => void
}

function tipeLabel(tipe: string) {
  if (tipe === "kecamatan") return "Per Kecamatan"
  if (tipe === "kabupaten") return "Per Kabupaten"
  if (tipe === "kategori") return "Per Kategori"
  return tipe
}

function TableCard({
  tabel,
  onOpen,
}: {
  tabel: CatalogTable
  onOpen: (selection: CatalogSelection) => void
}) {
  const punyaData = tabel.jumlah_baris > 0
  const rentang =
    tabel.rentang_tahun && tabel.rentang_tahun[0] === tabel.rentang_tahun[1]
      ? `${tabel.rentang_tahun[0]}`
      : tabel.rentang_tahun
      ? `${tabel.rentang_tahun[0]}–${tabel.rentang_tahun[1]}`
      : null

  return (
    <button
      type="button"
      onClick={() =>
        onOpen({
          id: tabel.id,
          type: "tabel",
          title: tabel.nama_ringkas || tabel.judul,
        })
      }
      className="group w-full text-left rounded-md border border-border bg-background p-3 hover:border-primary/50 hover:bg-primary/[0.03] transition-colors duration-150 flex items-start gap-3"
    >
      <div className="mt-0.5 h-8 w-8 shrink-0 rounded-md bg-accent/10 text-accent flex items-center justify-center">
        <FileBarChart className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-xs font-semibold text-primary">
            {tabel.nomor_tabel}
          </span>
          {tabel.nama_ringkas && (
            <span className="text-sm font-semibold text-foreground truncate group-hover:text-primary transition-colors">
              {tabel.nama_ringkas}
            </span>
          )}
        </div>
        {!tabel.nama_ringkas && (
          <p className="text-sm font-semibold text-foreground truncate group-hover:text-primary transition-colors">
            {tabel.judul}
          </p>
        )}
        <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">
          {tabel.nama_ringkas ? tabel.judul : ""}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5">
            {tipeLabel(tabel.tipe_baris)}
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 font-semibold text-primary">
            Publikasi {tabel.publikasi_tahun}
          </span>
          {rentang && (
            <span className="inline-flex items-center gap-1">
              <Eye className="h-3 w-3" /> {rentang}
            </span>
          )}
          <span className="inline-flex items-center gap-1">
            <Table2 className="h-3 w-3" /> {tabel.jumlah_baris} baris
          </span>
        </div>
      </div>
      {punyaData && (
        <span className="mt-1 shrink-0 text-[11px] font-semibold text-accent whitespace-nowrap">
          Lihat grafik →
        </span>
      )}
    </button>
  )
}

export function CatalogBrowser({ onOpenTabel }: CatalogBrowserProps) {
  const { data, error, isLoading } = useCatalog(null)
  const [openBabs, setOpenBabs] = useState<Record<number, boolean>>({})

  const toggleBab = (id: number) =>
    setOpenBabs((current) => ({ ...current, [id]: !current[id] }))

  const babs = data?.babs ?? []

  return (
    <aside className="w-96 shrink-0 border-r border-border bg-card/40 flex flex-col h-full overflow-hidden">
      <div className="border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold tracking-wide text-foreground">
            Jelajahi Publikasi
          </h2>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Pilih bab lalu tabel untuk langsung melihat grafik time-series (gabungan semua tahun terbit).
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isLoading ? (
          <div className="flex h-full flex-col items-center justify-center text-primary">
            <Loader2 className="h-8 w-8 animate-spin" />
            <p className="mt-3 text-sm">Memuat katalog…</p>
          </div>
        ) : error ? (
          <div className="flex h-full flex-col items-center justify-center text-destructive text-center px-6">
            <AlertTriangle className="h-8 w-8 mb-3" />
            <p className="text-sm font-medium">Gagal memuat katalog.</p>
          </div>
        ) : babs.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground px-6">
            <Layers className="h-8 w-8 mb-3" />
            <p className="text-sm">Katalog belum tersedia.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {babs.map((bab) => {
              const isOpen = openBabs[bab.id] ?? bab.nomor === 1
              return (
                <section
                  key={bab.id}
                  className="rounded-lg border border-border bg-background/60 overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => toggleBab(bab.id)}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left hover:bg-muted/50 transition-colors"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="font-mono text-xs font-semibold text-primary">
                        {bab.nomor}.
                      </span>
                      <span className="truncate text-sm font-semibold text-foreground">
                        {bab.nama}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
                      <span>{bab.jumlah_tabel} tabel</span>
                      <ChevronDown
                        className={`h-4 w-4 transition-transform duration-200 ${
                          isOpen ? "rotate-180" : ""
                        }`}
                      />
                    </span>
                  </button>
                  {isOpen && (
                    <div className="space-y-2 border-t border-border px-3 py-3">
                      {bab.tabel.length === 0 ? (
                        <p className="px-1 text-xs text-muted-foreground">
                          Belum ada tabel.
                        </p>
                      ) : (
                        bab.tabel.map((tabel) => (
                          <TableCard
                            key={tabel.id}
                            tabel={tabel}
                            onOpen={onOpenTabel}
                          />
                        ))
                      )}
                    </div>
                  )}
                </section>
              )
            })}
          </div>
        )}
      </div>

      <div className="border-t border-border px-4 py-3">
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground text-center">
          Hanya baca • Tidak ada aksi edit
        </p>
      </div>
    </aside>
  )
}
