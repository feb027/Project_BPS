/**
 * Excel export helper (ExcelJS) — styling BPS, angka asli (bukan string),
 * meta judul/indikator, freeze pane, column width otomatis.
 *
 * Dipakai oleh ChartModal & CompareModal. ExcelJS versi browser:
 * `wb.xlsx.writeBuffer()` -> Blob -> download.
 */
import ExcelJS from "exceljs"

// ─── BPS Brand Colors ───────────────────────────────────────────────
const BPS_BLUE = "FF0093DD" // header bg
const BPS_NAVY = "FF1E3A8A" // judul teks
const WHITE = "FFFFFFFF"
const LIGHT_BLUE = "FFE8F4FB" // alternating rows
const BORDER = "FFD0D7DE"
const MUTED = "FF64748B"

export interface StyledSheetOptions {
  title: string
  meta: string[] // baris keterangan (indikator, satuan, sumber, tanggal)
  header: string[]
  rows: (string | number)[][]
  sheetName?: string
}

/** Nomor format Excel: integer tanpa desimal, selain itu 2 desimal. */
function numFmtFor(v: number): string {
  return Number.isInteger(v) ? "#,##0" : "#,##0.00"
}

export function buildStyledSheet(wb: ExcelJS.Workbook, opts: StyledSheetOptions): ExcelJS.Worksheet {
  const ws = wb.addWorksheet(opts.sheetName ?? "Data")
  const nCols = Math.max(opts.header.length, ...opts.rows.map((r) => r.length))

  // Baris 1: judul (merged)
  ws.mergeCells(1, 1, 1, nCols)
  const titleCell = ws.getCell(1, 1)
  titleCell.value = opts.title
  titleCell.font = { bold: true, size: 14, color: { argb: BPS_NAVY } }
  titleCell.alignment = { vertical: "middle" }
  ws.getRow(1).height = 26

  // Baris 2: meta (merged, italic muted)
  ws.mergeCells(2, 1, 2, nCols)
  const metaCell = ws.getCell(2, 1)
  metaCell.value = opts.meta.join("  •  ")
  metaCell.font = { size: 10, italic: true, color: { argb: MUTED } }
  ws.getRow(2).height = 18

  // Baris 3: header (bold putih di atas biru BPS)
  const headerRow = ws.getRow(3)
  headerRow.height = 22
  opts.header.forEach((h, i) => {
    const cell = headerRow.getCell(i + 1)
    cell.value = h
    cell.font = { bold: true, color: { argb: WHITE }, size: 11 }
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: BPS_BLUE } }
    cell.alignment = { vertical: "middle", horizontal: "center", wrapText: true }
    cell.border = { bottom: { style: "medium", color: { argb: BPS_BLUE } } }
  })

  // Baris data: angka ASLI (bukan string), satuan hanya di meta
  opts.rows.forEach((row, ri) => {
    const excelRow = ws.getRow(4 + ri)
    excelRow.height = 20
    row.forEach((v, ci) => {
      const cell = excelRow.getCell(ci + 1)
      if (typeof v === "number") {
        cell.value = v
        cell.numFmt = numFmtFor(v)
        cell.alignment = { horizontal: "right", vertical: "middle" }
      } else {
        cell.value = v
        cell.alignment = { vertical: "middle", horizontal: ci === 0 ? "left" : "center" }
      }
      cell.border = { bottom: { style: "thin", color: { argb: BORDER } } }
      if (ri % 2 === 1) {
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: LIGHT_BLUE } }
      }
    })
  })

  // Column width: 1st col lebar (nama wilayah/rincian), sisanya cukup utk tahun
  ws.columns = opts.header.map((h, i) => ({
    width: i === 0 ? Math.min(Math.max(24, h.length + 4), 42) : Math.min(Math.max(12, h.length + 4), 16),
  }))

  // Freeze pane: judul + meta + header tetap terlihat saat scroll
  ws.views = [{ state: "frozen", ySplit: 3 }]
  return ws
}

export async function downloadWorkbook(wb: ExcelJS.Workbook, fileName: string): Promise<void> {
  const buffer = await wb.xlsx.writeBuffer()
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = fileName.endsWith(".xlsx") ? fileName : `${fileName}.xlsx`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export function timestampLabel(): string {
  return `Dibuat ${new Date().toLocaleString("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })}`
}
