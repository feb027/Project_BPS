import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Strip a trailing year (e.g. ", 2017" or " (2017)") from a BPS table
// title so panels show a clean, general title instead of a year-scoped one.
export function cleanTitle(title: string) {
  if (!title) return title
  return title
    .replace(/,?\s*\d{4}\s*$/, "")
    .replace(/\s*[\(\[]\s*\d{4}\s*[\)\]]\s*$/, "")
    .replace(/\s{2,}/g, " ")
    .trim()
}
