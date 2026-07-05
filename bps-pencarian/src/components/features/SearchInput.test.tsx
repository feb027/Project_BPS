import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { SearchInput } from './SearchInput'

describe('SearchInput Component', () => {
  it('renders correctly with initial query', () => {
    const setQuery = vi.fn()
    render(<SearchInput query="inflasi" setQuery={setQuery} />)
    
    const input = screen.getByPlaceholderText(/Ketik kata kunci/i) as HTMLInputElement
    expect(input).toBeInTheDocument()
    expect(input.value).toBe('inflasi')
  })

  it('calls setQuery when input changes', () => {
    const setQuery = vi.fn()
    render(<SearchInput query="" setQuery={setQuery} />)
    
    const input = screen.getByPlaceholderText(/Ketik kata kunci/i)
    fireEvent.change(input, { target: { value: 'kemiskinan' } })
    
    expect(setQuery).toHaveBeenCalledWith('kemiskinan')
    expect(setQuery).toHaveBeenCalledTimes(1)
  })
})
