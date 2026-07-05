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
