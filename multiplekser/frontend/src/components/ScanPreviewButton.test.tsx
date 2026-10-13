import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ScanPreviewButton } from './ScanPreviewButton'
import { getDocumentFile } from '../api/documents'
import { ApiError } from '../api/client'

vi.mock('../api/documents', () => ({ getDocumentFile: vi.fn() }))

describe('ScanPreviewButton — podgląd bez about:blank', () => {
  beforeEach(() => {
    vi.mocked(getDocumentFile).mockReset()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:scan-ok') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  })

  it('otwiera podgląd obrazu w dialogu zamiast pustej karty i zwalnia blob po zamknięciu', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.mocked(getDocumentFile).mockResolvedValue({
      blob: new Blob(['obraz'], { type: 'image/jpeg' }), filename: 'wydawka.jpg',
    })
    const user = userEvent.setup()
    render(<ScanPreviewButton documentId="doc1" />)
    await user.click(screen.getByRole('button', { name: 'Zobacz skan' }))
    expect(await screen.findByRole('img', { name: 'Wydawka — strona 1' })).toHaveAttribute('src', 'blob:scan-ok')
    expect(getDocumentFile).toHaveBeenCalledWith('doc1', 1)
    expect(openSpy).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Zamknij' }))
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:scan-ok'))
    openSpy.mockRestore()
  })

  it('pokazuje drugą stronę osobnych zdjęć bez otwierania nowej karty', async () => {
    vi.mocked(getDocumentFile).mockResolvedValue({
      blob: new Blob(['obraz'], { type: 'image/png' }), filename: 'strona.jpg',
    })
    const user = userEvent.setup()
    render(<ScanPreviewButton documentId="doc2" pageCount={2} />)
    await user.click(screen.getByRole('button', { name: 'Zobacz skan' }))
    await screen.findByRole('img', { name: 'Wydawka — strona 1' })
    await user.click(screen.getByRole('button', { name: 'Następna' }))
    expect(await screen.findByRole('img', { name: 'Wydawka — strona 2' })).toBeInTheDocument()
    expect(getDocumentFile).toHaveBeenNthCalledWith(2, 'doc2', 2)
    expect(screen.getByRole('link', { name: 'Pobierz oryginał' })).toHaveAttribute('href', 'blob:scan-ok')
  })

  it('wyświetla błąd API wewnątrz panelu zamiast pustej karty', async () => {
    vi.mocked(getDocumentFile).mockRejectedValue(new ApiError(404, 'Brak pliku w storage'))
    const user = userEvent.setup()
    render(<ScanPreviewButton documentId="missing" />)
    await user.click(screen.getByRole('button', { name: 'Zobacz skan' }))
    expect(await screen.findByText('Brak pliku w storage')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('wyświetla PDF w ramce wewnątrz dialogu', async () => {
    vi.mocked(getDocumentFile).mockResolvedValue({
      blob: new Blob(['%PDF-test'], { type: 'application/pdf' }), filename: 'wydawka.pdf',
    })
    const user = userEvent.setup()
    render(<ScanPreviewButton documentId="pdf" />)
    await user.click(screen.getByRole('button', { name: 'Zobacz skan' }))
    expect(await screen.findByTitle('Podgląd skanu PDF')).toHaveAttribute('src', 'blob:scan-ok')
  })
})
