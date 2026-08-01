/**
 * Professional PDF export with BPS Kabupaten Tasikmalaya branding.
 *
 * Uses jsPDF + jspdf-autotable for native vector tables (no html2canvas).
 * Includes:
 *  - BPS logo header
 *  - Title, subtitle
 *  - Styled data table with alternating row colors
 *  - Footer: page numbers, generation timestamp, source attribution
 *  - Optional chart image (rendered from Recharts canvas)
 */
import jsPDF from "jspdf"
import autoTable from "jspdf-autotable"

// ─── BPS Brand Colors ───────────────────────────────────────────────
const BPS_BLUE = [0, 147, 221] as const   // #0093dd
const BPS_ORANGE = [235, 137, 27] as const // #eb891b
const WHITE = [255, 255, 255] as const
const DARK = [33, 37, 41] as const         // body text
const GRAY_LIGHT = [248, 249, 250] as const // alternating rows
const GRAY_MED = [108, 117, 125] as const   // secondary text
const BORDER = [222, 226, 230] as const     // light rule

// ─── Logo (loaded once, cached) ─────────────────────────────────────
let cachedLogoDataUrl: string | null = null

async function loadBpsLogo(): Promise<string> {
  if (cachedLogoDataUrl) return cachedLogoDataUrl

  try {
    const res = await fetch("/Lambang_Badan_Pusat_Statistik_(BPS)_Indonesia.svg")
    const svgText = await res.text()

    const img = new Image()
    const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" })
    const url = URL.createObjectURL(blob)

    return new Promise<string>((resolve) => {
      img.onload = () => {
        const canvas = document.createElement("canvas")
        // Render at 2x for crisp logo
        const size = 128
        canvas.width = size
        canvas.height = size
        const ctx = canvas.getContext("2d")!
        // SVG has non-square viewBox (1381×1070), draw centered & fit
        const scale = Math.min(size / img.naturalWidth, size / img.naturalHeight)
        const w = img.naturalWidth * scale
        const h = img.naturalHeight * scale
        ctx.drawImage(img, (size - w) / 2, (size - h) / 2, w, h)
        cachedLogoDataUrl = canvas.toDataURL("image/png")
        URL.revokeObjectURL(url)
        resolve(cachedLogoDataUrl)
      }
      img.onerror = () => {
        URL.revokeObjectURL(url)
        resolve("")
      }
      img.src = url
    })
  } catch {
    return ""
  }
}

// ─── Helpers ────────────────────────────────────────────────────────
function isYearLike(n: number): boolean {
  return Number.isInteger(n) && n >= 1900 && n <= 2099
}

function formatIdNumber(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "-"
  const n = Number(value)
  if (Number.isNaN(n)) return String(value)
  // Don't apply thousand separators to year values (2017 → "2017", not "2.017")
  if (isYearLike(n)) return String(n)
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(n)
}

function timestamp(): string {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date())
}

// ─── Public API ─────────────────────────────────────────────────────
export interface PdfExportTable {
  /** Section/table title shown above the table (e.g. "4.1.7 — Jumlah Sekolah, Guru, dan Murid SMA") */
  title?: string
  /** Column headers */
  columns: string[]
  /** Data rows — values aligned to columns */
  rows: (string | number | null | undefined)[][]
}

export interface PdfExportChartSection {
  /** Section title (table number + full title) */
  title?: string
  /** Optional indicator label shown under the title */
  subtitle?: string
  /** Chart image for THIS section (PNG data URL) */
  chartImageDataUrl?: string
  /** Data table columns */
  columns: string[]
  /** Data table rows */
  rows: (string | number | null | undefined)[][]
}

export interface PdfExportOptions {
  /** Main report title */
  title: string
  /** Optional subtitle (e.g. selected indicator) */
  subtitle?: string
  /** Main summary columns (optional when detailTables/chartSections are used) */
  columns?: string[]
  /** Main summary rows (optional when detailTables/chartSections are used) */
  rows?: (string | number | null | undefined)[][]
  /** File name (without .pdf) */
  fileName: string
  /** Optional chart image as data URL (PNG) */
  chartImageDataUrl?: string
  /** Orientation override */
  orientation?: "portrait" | "landscape"
  /** One data table per section (e.g. per compared table), rendered after the chart image */
  detailTables?: PdfExportTable[]
  /** Full per-section pages: each with its own (big) chart image + data table */
  chartSections?: PdfExportChartSection[]
}

export async function exportProfessionalPdf(opts: PdfExportOptions) {
  const {
    title,
    subtitle,
    columns,
    rows,
    fileName,
    chartImageDataUrl,
    orientation,
    detailTables,
    chartSections,
  } = opts

  // Auto-detect orientation: ≥5 columns → landscape
  const orient = orientation ?? ((columns?.length ?? 0) >= 5 ? "landscape" : "portrait")
  const pdf = new jsPDF(orient, "mm", "a4")
  const pageW = pdf.internal.pageSize.getWidth()
  const pageH = pdf.internal.pageSize.getHeight()
  const marginX = 14
  const contentW = pageW - marginX * 2

  // ── Load logo ──
  const logoDataUrl = await loadBpsLogo()

  // ── Header function (drawn on every page via didDrawPage) ──
  const headerHeight = 28
  const drawHeader = () => {
    // Blue accent bar at the very top
    pdf.setFillColor(...BPS_BLUE)
    pdf.rect(0, 0, pageW, 3, "F")

    // Logo
    const logoSize = 16
    const logoY = 6
    if (logoDataUrl) {
      pdf.addImage(logoDataUrl, "PNG", marginX, logoY, logoSize, logoSize)
    }

    // Institution name
    const textX = marginX + logoSize + 4
    pdf.setFont("helvetica", "bold")
    pdf.setFontSize(11)
    pdf.setTextColor(...DARK)
    pdf.text("BADAN PUSAT STATISTIK", textX, logoY + 6)
    pdf.setFont("helvetica", "normal")
    pdf.setFontSize(9)
    pdf.setTextColor(...GRAY_MED)
    pdf.text("KABUPATEN TASIKMALAYA", textX, logoY + 12)

    // Thin separator line
    pdf.setDrawColor(...BORDER)
    pdf.setLineWidth(0.3)
    pdf.line(marginX, headerHeight, pageW - marginX, headerHeight)
  }

  // ── Footer function ──
  const footerHeight = 12
  const drawFooter = (pageNumber: number, totalPages: number) => {
    const footerY = pageH - footerHeight + 4

    // Thin separator
    pdf.setDrawColor(...BORDER)
    pdf.setLineWidth(0.3)
    pdf.line(marginX, footerY - 4, pageW - marginX, footerY - 4)

    // Left: source
    pdf.setFont("helvetica", "normal")
    pdf.setFontSize(7)
    pdf.setTextColor(...GRAY_MED)
    pdf.text(`Sumber: Basis Data BPS Kab. Tasikmalaya — Diekspor ${timestamp()}`, marginX, footerY)

    // Right: page number
    const pageText = `Halaman ${pageNumber} dari ${totalPages}`
    const pageTextWidth = pdf.getTextWidth(pageText)
    pdf.text(pageText, pageW - marginX - pageTextWidth, footerY)
  }

  // ── Draw first page header ──
  drawHeader()

  // ── Title block ──
  let cursorY = headerHeight + 8

  pdf.setFont("helvetica", "bold")
  pdf.setFontSize(13)
  pdf.setTextColor(...DARK)
  // Wrap long titles
  const titleLines = pdf.splitTextToSize(title, contentW)
  pdf.text(titleLines, marginX, cursorY)
  cursorY += titleLines.length * 6

  if (subtitle) {
    pdf.setFont("helvetica", "normal")
    pdf.setFontSize(9)
    pdf.setTextColor(...GRAY_MED)
    const subLines = pdf.splitTextToSize(subtitle, contentW)
    pdf.text(subLines, marginX, cursorY + 2)
    cursorY += subLines.length * 4 + 4
  }

  // ── Orange accent underline below title ──
  pdf.setDrawColor(...BPS_ORANGE)
  pdf.setLineWidth(0.6)
  pdf.line(marginX, cursorY + 1, marginX + Math.min(contentW * 0.4, 70), cursorY + 1)
  cursorY += 6

  // ── Chart image (if provided) ──
  const drawChartImage = async (dataUrl: string, maxH: number) => {
    const img = new Image()
    img.src = dataUrl
    await new Promise<void>((resolve) => {
      img.onload = () => resolve()
      img.onerror = () => resolve()
    })
    if (!img.naturalWidth || !img.naturalHeight) return cursorY
    const aspect = img.naturalWidth / img.naturalHeight
    let chartW = contentW
    let chartH = chartW / aspect
    if (chartH > maxH) {
      chartH = maxH
      chartW = chartH * aspect
    }
    if (cursorY + chartH + 10 > pageH - footerHeight) {
      pdf.addPage()
      drawHeader()
      cursorY = headerHeight + 8
    }
    pdf.addImage(dataUrl, "PNG", marginX + (contentW - chartW) / 2, cursorY, chartW, chartH)
    return cursorY + chartH + 6
  }

  if (chartImageDataUrl) {
    cursorY = await drawChartImage(chartImageDataUrl, orient === "landscape" ? 80 : 100)
  }

  // ── Data tables ──
  // Format numeric values with Indonesian locale
  const fmtRow = (row: (string | number | null | undefined)[]) =>
    row.map((cell) => {
      if (cell === null || cell === undefined) return "-"
      if (typeof cell === "number") return formatIdNumber(cell)
      return String(cell)
    })

  const columnAlignment = (cols: string[]) =>
    cols.reduce((acc, col, i) => {
      const isYear = /^\d{4}$/.test(col.trim())
      const isValue = /nilai|value|jumlah/i.test(col)
      if (isYear || isValue) {
        acc[i] = { halign: "right" as const, fontStyle: isValue ? "bold" as const : "normal" as const }
      }
      return acc
    }, {} as Record<number, { halign: "right"; fontStyle: "bold" | "normal" }>)

  let lastTableY = cursorY

  // Main summary table (when columns/rows provided)
  if (columns && columns.length && rows) {
    autoTable(pdf, {
      startY: cursorY,
      head: [columns],
      body: rows.map(fmtRow),
      styles: {
        font: "helvetica",
        fontSize: 8,
        cellPadding: { top: 2.5, right: 3, bottom: 2.5, left: 3 },
        textColor: [...DARK],
        lineColor: [...BORDER],
        lineWidth: 0.2,
        overflow: "linebreak",
      },
      headStyles: {
        fillColor: [...BPS_BLUE],
        textColor: [...WHITE],
        fontStyle: "bold",
        fontSize: 8,
        halign: "left",
      },
      alternateRowStyles: {
        fillColor: [...GRAY_LIGHT],
      },
      columnStyles: columnAlignment(columns),
      didDrawPage: (data) => {
        if (data.pageNumber > 1) {
          drawHeader()
        }
      },
      margin: { top: headerHeight + 6, left: marginX, right: marginX, bottom: footerHeight + 4 },
    })
    // jspdf-autotable exposes the last-drawn table (incl. finalY) on the doc
    // object — its return value is void.
    lastTableY = (pdf as unknown as { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? lastTableY
  }

  // Detail data tables — one per section (e.g. per compared table)
  if (detailTables && detailTables.length) {
    for (const t of detailTables) {
      if (!t.columns.length) continue
      let startY = lastTableY + 10
      if (startY > pageH - footerHeight - 40) {
        pdf.addPage()
        drawHeader()
        startY = headerHeight + 10
      }
      if (t.title) {
        pdf.setFont("helvetica", "bold")
        pdf.setFontSize(10)
        pdf.setTextColor(...DARK)
        const titleLines = pdf.splitTextToSize(t.title, contentW)
        pdf.text(titleLines, marginX, startY + 4)
        startY += titleLines.length * 5 + 4
      }
      autoTable(pdf, {
        startY,
        head: [t.columns],
        body: t.rows.map(fmtRow),
        styles: {
          font: "helvetica",
          fontSize: 7.5,
          cellPadding: { top: 2, right: 3, bottom: 2, left: 3 },
          textColor: [...DARK],
          lineColor: [...BORDER],
          lineWidth: 0.2,
          overflow: "linebreak",
        },
        headStyles: {
          fillColor: [...BPS_BLUE],
          textColor: [...WHITE],
          fontStyle: "bold",
          fontSize: 7.5,
          halign: "left",
        },
        alternateRowStyles: {
          fillColor: [...GRAY_LIGHT],
        },
        columnStyles: columnAlignment(t.columns),
        didDrawPage: (data) => {
          if (data.pageNumber > 1) {
            drawHeader()
          }
        },
        margin: { top: headerHeight + 6, left: marginX, right: marginX, bottom: footerHeight + 4 },
      })
      lastTableY = (pdf as unknown as { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? lastTableY
    }
  }

  // ── Full per-section pages: big chart + data table each ──
  if (chartSections && chartSections.length) {
    for (const sec of chartSections) {
      // Section title (start on a fresh page if not enough room left)
      if (cursorY > pageH - footerHeight - 45) {
        pdf.addPage()
        drawHeader()
        cursorY = headerHeight + 8
      }
      if (sec.title) {
        pdf.setFont("helvetica", "bold")
        pdf.setFontSize(12)
        pdf.setTextColor(...DARK)
        const titleLines = pdf.splitTextToSize(sec.title, contentW)
        pdf.text(titleLines, marginX, cursorY + 4)
        cursorY += titleLines.length * 6 + 4
      }
      if (sec.subtitle) {
        pdf.setFont("helvetica", "normal")
        pdf.setFontSize(9)
        pdf.setTextColor(...GRAY_MED)
        const subLines = pdf.splitTextToSize(sec.subtitle, contentW)
        pdf.text(subLines, marginX, cursorY + 2)
        cursorY += subLines.length * 4 + 3
      }

      // Big chart for this section (up to ~120mm tall — far larger than the
      // old single composed image that shrank every chart)
      if (sec.chartImageDataUrl) {
        cursorY = await drawChartImage(sec.chartImageDataUrl, 120)
      }

      // Data table for this section (auto-paginates to following pages)
      if (sec.columns.length) {
        autoTable(pdf, {
          startY: cursorY,
          head: [sec.columns],
          body: sec.rows.map(fmtRow),
          styles: {
            font: "helvetica",
            fontSize: 8,
            cellPadding: { top: 2, right: 3, bottom: 2, left: 3 },
            textColor: [...DARK],
            lineColor: [...BORDER],
            lineWidth: 0.2,
            overflow: "linebreak",
          },
          headStyles: {
            fillColor: [...BPS_BLUE],
            textColor: [...WHITE],
            fontStyle: "bold",
            fontSize: 8,
            halign: "left",
          },
          alternateRowStyles: {
            fillColor: [...GRAY_LIGHT],
          },
          columnStyles: columnAlignment(sec.columns),
          didDrawPage: (data) => {
            if (data.pageNumber > 1) {
              drawHeader()
            }
          },
          margin: { top: headerHeight + 6, left: marginX, right: marginX, bottom: footerHeight + 4 },
        })
        cursorY = (pdf as unknown as { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? cursorY
      }
      cursorY += 10
    }
  }

  // ── Draw footer on all pages ──
  const totalPages = pdf.getNumberOfPages()
  for (let i = 1; i <= totalPages; i++) {
    pdf.setPage(i)
    drawFooter(i, totalPages)
  }

  // ── Save ──
  pdf.save(`${fileName}.pdf`)
}
