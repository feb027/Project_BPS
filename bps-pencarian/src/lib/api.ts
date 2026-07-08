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
  id: number
  nomor_tabel: string
  nama_ringkas: string
  judul: string
  tipe_baris: string
  tahun_data: number | null
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
  publikasi: { id: number; judul: string; tahun_terbit: number } | null
  publikasi_list: { id: number; judul: string; tahun_terbit: number }[]
  babs: CatalogBab[]
}

export function useCatalog(publikasiId: number | null) {
  const key = publikasiId
    ? `/pencarian/api/catalog/?publikasi_id=${publikasiId}`
    : `/pencarian/api/catalog/`
  const { data, error, isLoading } = useSWR<CatalogResponse>(key, fetcher)
  return { data, error, isLoading }
}
