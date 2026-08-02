import { describe, expect, it } from "vitest"
import jsPDF from "jspdf"
import { registerFiraFonts } from "./pdfExport"

describe("pdfExport", () => {
  it("registerFiraFonts memanggil method INSTANCE (bukan static API) — tidak throw", () => {
    const pdf = new jsPDF("portrait", "mm", "a4")
    // Base64 dummy (bukan font valid — cukup untuk memastikan jalur
    // addFileToVFS/addFont instance dipanggil tanpa error TypeError).
    expect(() =>
      registerFiraFonts(pdf, { regular: "AA==", bold: "AA==" })
    ).not.toThrow()
  })
})
