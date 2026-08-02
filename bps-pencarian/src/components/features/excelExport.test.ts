import { describe, expect, it } from "vitest"
import ExcelJS from "exceljs"
import { buildStyledSheet } from "../../lib/excelExport"

describe("excelExport.buildStyledSheet", () => {
  it("menulis nilai angka asli (bukan string berformat) + styling header", async () => {
    const wb = new ExcelJS.Workbook()
    buildStyledSheet(wb, {
      title: "Tabel Uji",
      meta: ["Indikator: X", "Satuan: kg"],
      header: ["Wilayah", "2019", "2020"],
      rows: [
        ["Bantarkalong", 273, 300],
        ["Singaparna", 150, 175],
      ],
    })

    // Verifikasi cell angka: number, bukan string "273"
    const ws = wb.getWorksheet("Data")
    expect(ws).toBeDefined()
    const wsSafe = ws! // TS strict: worksheet pasti ada karena buildStyledSheet menambahkannya
    expect(wsSafe.getCell(4, 2).value).toBe(273) // angka asli
    expect(typeof wsSafe.getCell(4, 2).value).toBe("number")

    // Header berisi teks + bold
    expect(wsSafe.getCell(3, 1).value).toBe("Wilayah")
    expect(wsSafe.getCell(3, 1).font?.bold).toBe(true)

    // Judul + meta di baris 1-2
    expect(wsSafe.getCell(1, 1).value).toBe("Tabel Uji")
    expect(String(wsSafe.getCell(2, 1).value)).toContain("Satuan: kg")

    // Freeze pane
    expect(wsSafe.views[0]?.state).toBe("frozen")

    // Workbook bisa di-serialize ke buffer xlsx (valid)
    const buffer = await wb.xlsx.writeBuffer()
    expect(buffer.byteLength).toBeGreaterThan(1000)
  })
})
