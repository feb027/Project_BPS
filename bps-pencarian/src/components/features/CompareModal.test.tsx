import { describe, it, expect } from 'vitest'
import { pickMetricByHint } from './CompareModal'

const METRICS = [
  'Guru Jumlah',
  'Guru Negeri',
  'Guru Swasta',
  'Murid Jumlah',
  'Murid Negeri',
  'Murid Swasta',
  'Rasio Murid-Guru (%)',
  'Sekolah Jumlah',
  'Sekolah Negeri',
  'Sekolah Swasta',
]

describe('pickMetricByHint', () => {
  it('matches reordered words: "Jumlah Murid (SMA)" -> "Murid Jumlah"', () => {
    expect(pickMetricByHint(METRICS, 'Jumlah Murid (SMA)')).toBe('Murid Jumlah')
  })

  it('matches "Jumlah Guru (SMA)" -> "Guru Jumlah"', () => {
    expect(pickMetricByHint(METRICS, 'Jumlah Guru (SMA)')).toBe('Guru Jumlah')
  })

  it('matches "Jumlah Sekolah" -> "Sekolah Jumlah"', () => {
    expect(pickMetricByHint(METRICS, 'Jumlah Sekolah (SMA)')).toBe('Sekolah Jumlah')
  })

  it('does not pick a metric missing a hint word ("Murid (SMA)" must not match "Guru Jumlah")', () => {
    expect(pickMetricByHint(METRICS, 'Murid (SMA)')).toBe('Murid Jumlah')
  })

  it('returns undefined when no metric contains all hint words', () => {
    expect(pickMetricByHint(METRICS, 'Produksi Alpukat')).toBeUndefined()
  })

  it('returns undefined for empty hint', () => {
    expect(pickMetricByHint(METRICS, '')).toBeUndefined()
    expect(pickMetricByHint(METRICS, undefined)).toBeUndefined()
  })

  it('treats non-alphanumerics as word separators', () => {
    // "Rasio Murid-Guru (%)" normalizes to "rasio murid guru" — a hint with
    // words {rasio, murid} should match it, not "Murid Jumlah" (no "rasio").
    expect(pickMetricByHint(METRICS, 'Rasio Murid-Guru')).toBe('Rasio Murid-Guru (%)')
  })
})
