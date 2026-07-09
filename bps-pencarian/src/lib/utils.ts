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
    .replace(/\s*[\(\[]\s*\d{4}(?:\s*[-–—]\s*\d{4})?\s*[\)\]]\s*$/, "")
    .replace(/,?\s*-\s*$/, "")
    .replace(/\s{2,}/g, " ")
    .trim()
}
