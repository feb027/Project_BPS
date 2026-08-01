import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Strip a trailing year or year-range (e.g. ", 2017", "(2017)", ", 2013-2017",
// ", 2014–2018", ", 2013-", "Tahun 2025", "2021-2025") from a BPS table title
// so panels show a clean, general title instead of a year-scoped one.
export function cleanTitle(title: string) {
  if (!title) return title
  return title
    .replace(/\bTahun\s+\d{4}(?:\s*[-–—]\s*\d{4})?\s*$/i, "")
    .replace(/,?\s*[-–—]?\s*\d{4}(?:[-–—]\s*\d{4})?\s*(?:\s*[a-zA-Zμ²]+\d*)?\s*[-–—]?\s*$/, "")
    .replace(/\s*[\(\[)]*\s*\d{4}(?:\s*[-–—]\s*\d{4})?\s*[\)\]]?\s*$/, "")
    .replace(/,?\s*-\s*$/, "")
    .replace(/\s{2,}/g, " ")
    .trim()
}

// Shorten a BPS table title for respondent-facing exports (PDF/Excel).
// DB judul can be truncated at 400 chars mid-sentence (e.g. "... dan 2019/"),
// so keep everything up to "di Kabupaten Tasikmalaya" and drop the trailing
// year-range part (", 2018/2019 dan 2019/2020").
export function shortTitleForExport(title: string) {
  if (!title) return title
  const t = title.trim()
  const marker = "di Kabupaten Tasikmalaya"
  const idx = t.indexOf(marker)
  if (idx > 10) return t.slice(0, idx + marker.length).trim()
  // Fallback: drop trailing slash-year ranges then clean the tail
  const withoutYearRange = t.replace(/,\s*\d{4}\/\d{0,4}(?:\s*dan\s*\d{4}\/\d{0,4})*\s*$/g, "")
  return cleanTitle(withoutYearRange)
}
