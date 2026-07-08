import useSWR from "swr"

export const fetcher = (url: string) => fetch(url).then((res) => {
  if (!res.ok) throw new Error("Gagal mengambil data")
  return res.json()
})

// Vercel Best Practice: SWR for dedup
export function useSearch(query: string) {
  const { data, error, isLoading } = useSWR(
    query.length >= 2 ? `/pencarian/api/search/?q=${encodeURIComponent(query)}` : null,
    fetcher
  )

  return { data, error, isLoading }
}

export function useTimeSeries(id: number | null, type: 'tabel' | 'indikator' | null) {
  const queryParam = type === 'tabel' ? `tabel_id=${id}` : `indikator_id=${id}`
  const { data, error, isLoading } = useSWR(
    id && type ? `/pencarian/api/timeseries/?${queryParam}` : null,
    fetcher
  )

  return { data, error, isLoading }
}

export interface CatalogTable {
  nomor_tabel: string
  nama_ringkas: string
  judul: string
  tipe_baris: string
  jumlah_publikasi: number
  jumlah_baris: number
  rentang_tahun: [number, number] | null
}

export interface CatalogBab {
  id: number
  nomor: number
  nama: string
  jumlah_tabel: number
  tabel: CatalogTable[]
}

export interface CatalogResponse {
  babs: CatalogBab[]
}

// The browse panel always shows the merged tree across all publications —
// there is no per-publication selector. The `publikasiId` arg is accepted for
// call-site compatibility but ignored.
export function useCatalog(_publikasiId: number | null) {
  const { data, error, isLoading } = useSWR<CatalogResponse>(
    `/pencarian/api/catalog/`,
    fetcher
  )
  return { data, error, isLoading }
}

export interface CatalogSeriesRow {
  id: number
  tahun: number
  nilai: number
  nilai_teks: string
  unit: string
  wilayah_nama: string
  rincian_nama: string
  subject_name: string
  flag: string
}

export interface CatalogSeriesResponse {
  nomor_tabel: string
  judul: string
  nama_ringkas: string
  series: CatalogSeriesRow[]
}

// Merged multi-year time-series for a single table number (all publications).
export function useCatalogSeries(nomorTabel: string | null) {
  const { data, error, isLoading } = useSWR<CatalogSeriesResponse>(
    nomorTabel ? `/pencarian/api/catalog/?nomor_tabel=${encodeURIComponent(nomorTabel)}` : null,
    fetcher
  )
  return { data, error, isLoading }
}
