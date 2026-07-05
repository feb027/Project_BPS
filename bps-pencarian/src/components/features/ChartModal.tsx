import { useMemo, useRef } from "react"
import { X, Download, FileText, Loader2 } from "lucide-react"
import { 
  ResponsiveContainer, LineChart, CartesianGrid, XAxis, YAxis, Tooltip, Line, Legend
} from "recharts"
import { useTimeSeries } from "../../lib/api"
import * as XLSX from "xlsx"
import html2canvas from "html2canvas"
import jsPDF from "jspdf"

interface ChartModalProps {
  item: {id: number, type: 'tabel' | 'indikator', title: string}
  onClose: () => void
}

export function ChartModal({ item, onClose }: ChartModalProps) {
  const { data, isLoading, error } = useTimeSeries(item.id, item.type)
  const chartRef = useRef<HTMLDivElement>(null)

  // Vercel Best Practice: useMemo for expensive data transformations before rendering charts
  const chartData = useMemo(() => {
    if (!data) return []
    // Group data by year
    const grouped = data.reduce((acc: any, row: any) => {
      const year = row.tahun
      if (!acc[year]) acc[year] = { tahun: year }
      
      const region = row.wilayah?.nama || 'Indonesia'
      acc[year][region] = row.nilai_num
      return acc
    }, {})

    return Object.values(grouped).sort((a: any, b: any) => a.tahun - b.tahun)
  }, [data])

  // Get unique regions to plot multiple lines
  const regions = useMemo(() => {
    if (!data) return []
    const r = new Set<string>()
    data.forEach((row: any) => {
      r.add(row.wilayah?.nama || 'Indonesia')
    })
    return Array.from(r)
  }, [data])

  const colors = ["#2563eb", "#ea580c", "#16a34a", "#ca8a04", "#9333ea"] // BPS & nice colors

  const handleExportExcel = () => {
    if (!data) return
    const worksheet = XLSX.utils.json_to_sheet(data)
    const workbook = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(workbook, worksheet, "Data")
    XLSX.writeFile(workbook, `Data_${item.title.substring(0, 30)}.xlsx`)
  }

  const handleExportPDF = async () => {
    if (!chartRef.current) return
    const canvas = await html2canvas(chartRef.current, { scale: 2 })
    const imgData = canvas.toDataURL("image/png")
    const pdf = new jsPDF("landscape", "mm", "a4")
    const pdfWidth = pdf.internal.pageSize.getWidth()
    const pdfHeight = (canvas.height * pdfWidth) / canvas.width
    
    pdf.setFontSize(16)
    pdf.text(item.title, 15, 15)
    pdf.addImage(imgData, "PNG", 15, 25, pdfWidth - 30, pdfHeight - 20)
    pdf.save(`Grafik_${item.title.substring(0, 30)}.pdf`)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose}></div>
      <div className="relative bg-card border border-border shadow-lg rounded-xl w-full max-w-5xl h-[85vh] flex flex-col animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-xl font-semibold text-foreground pr-8 truncate" title={item.title}>
            {item.title}
          </h2>
          <button 
            onClick={onClose}
            className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors absolute right-4"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-6 flex flex-col gap-6">
          {isLoading ? (
            <div className="flex-1 flex flex-col items-center justify-center text-primary">
              <Loader2 className="h-10 w-10 animate-spin mb-4" />
              <p className="text-sm font-medium animate-pulse">Memuat data time-series…</p>
            </div>
          ) : error ? (
            <div className="flex-1 flex items-center justify-center text-destructive">
              Gagal memuat data.
            </div>
          ) : data?.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground">
              Tidak ada data observasi untuk {item.type} ini.
            </div>
          ) : (
            <>
              {/* Toolbar */}
              <div className="flex items-center justify-end gap-3">
                <button 
                  onClick={handleExportExcel}
                  className="h-9 px-4 inline-flex items-center justify-center gap-2 rounded-md bg-secondary/10 text-secondary text-sm font-medium hover:bg-secondary/20 transition-colors"
                >
                  <FileText className="h-4 w-4" />
                  Unduh Excel
                </button>
                <button 
                  onClick={handleExportPDF}
                  className="h-9 px-4 inline-flex items-center justify-center gap-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                  <Download className="h-4 w-4" />
                  Cetak PDF
                </button>
              </div>

              {/* Chart */}
              <div className="flex-1 min-h-[400px] border border-border rounded-lg p-4 bg-background" ref={chartRef}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                    <XAxis 
                      dataKey="tahun" 
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
                      dy={10}
                    />
                    <YAxis 
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
                      dx={-10}
                    />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: "hsl(var(--card))",
                        borderColor: "hsl(var(--border))",
                        color: "hsl(var(--foreground))",
                        borderRadius: "0.5rem",
                        boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)"
                      }}
                    />
                    <Legend wrapperStyle={{ paddingTop: "20px" }} />
                    {regions.map((region, idx) => (
                      <Line 
                        key={region}
                        type="monotone" 
                        dataKey={region} 
                        stroke={colors[idx % colors.length]} 
                        strokeWidth={3}
                        activeDot={{ r: 6, strokeWidth: 0 }}
                        dot={{ r: 4, strokeWidth: 0 }}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
