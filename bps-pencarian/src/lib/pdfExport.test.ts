import { describe, expect, it, beforeAll } from "vitest"
import jsPDF from "jspdf"
import { svg2pdf } from "svg2pdf.js"
import { extractChartSvg } from "./pdfExport"

// jsdom tidak implementasi SVG getBBox — polyfill seperti browser nyata,
// svg2pdf memakainya untuk mengukur teks.
beforeAll(() => {
  if (!(SVGElement.prototype as any).getBBox) {
    ;(SVGElement.prototype as any).getBBox = () => ({
      x: 0, y: 0, width: 100, height: 20,
    })
  }
})

describe("pdfExport.extractChartSvg + svg2pdf", () => {
  it("merender SVG ke PDF vector tanpa error", async () => {
    // Recharts-like SVG: garis + teks + style var() yang harus di-resolve
    const container = document.createElement("div")
    container.innerHTML = `
      <svg width="800" height="400" xmlns="http://www.w3.org/2000/svg">
        <g stroke="var(--color-border)" fill="var(--color-primary)">
          <line x1="10" y1="390" x2="790" y2="390" stroke-width="1"/>
          <rect x="50" y="200" width="60" height="190" fill="#3B82F6"/>
          <rect x="130" y="150" width="60" height="240" fill="#1E40AF"/>
          <text x="60" y="180" font-size="14" font-family="Fira Sans">2019</text>
        </g>
      </svg>
    `
    // Set CSS vars di document supaya resolveVars punya nilai
    document.documentElement.style.setProperty("--color-border", "#E2E8F0")
    document.documentElement.style.setProperty("--color-primary", "#1E3A8A")
    document.body.appendChild(container)

    const svgMarkup = extractChartSvg(container)
    expect(svgMarkup).toBeTruthy()
    // var() harus sudah di-resolve — tidak ada var( tersisa
    expect(svgMarkup).not.toContain("var(")

    const doc = new DOMParser().parseFromString(svgMarkup!, "image/svg+xml")
    const svg = doc.querySelector("svg")
    expect(svg).toBeTruthy()

    const pdf = new jsPDF("portrait", "mm", "a4")
    await svg2pdf(svg!, pdf, { x: 10, y: 10, width: 180, height: 90 })

    // PDF valid: ada halaman + ukuran file wajar
    expect(pdf.getNumberOfPages()).toBeGreaterThanOrEqual(1)
    const out = pdf.output("arraybuffer")
    expect(out.byteLength).toBeGreaterThan(500)
  })
})
