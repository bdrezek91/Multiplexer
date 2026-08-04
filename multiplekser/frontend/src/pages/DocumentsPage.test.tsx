import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentsPage } from './DocumentsPage'
import * as documentsApi from '../api/documents'

vi.mock('../api/documents', async () => {
  const actual = await vi.importActual<typeof import('../api/documents')>('../api/documents')
  return { ...actual, listDocuments: vi.fn(), uploadDocument: vi.fn() }
})

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function fakeFile(name: string) {
  return new File(['dane'], name, { type: 'image/jpeg' })
}

describe('DocumentsPage - robienie kilku zdjec aparatem przed zatwierdzeniem', () => {
  beforeEach(() => {
    vi.mocked(documentsApi.listDocuments).mockResolvedValue([])
    vi.mocked(documentsApi.uploadDocument).mockReset()
  })

  it('kazde uzycie "Zrob zdjecie" dokada plik do listy zamiast go zastepowac, wysylka dopiero po zatwierdzeniu', async () => {
    const user = userEvent.setup()
    vi.mocked(documentsApi.uploadDocument).mockResolvedValue({ id: 'doc1', status: 'queued' })
    renderPage()

    const [cameraInput] = document.querySelectorAll('input[type="file"]')

    await user.upload(cameraInput as HTMLInputElement, fakeFile('strona1.jpg'))
    await user.upload(cameraInput as HTMLInputElement, fakeFile('strona2.jpg'))
    await user.upload(cameraInput as HTMLInputElement, fakeFile('strona3.jpg'))

    // Trzy zdjecia z aparatu widoczne na liscie - wysylka jeszcze NIE nastapila.
    expect(screen.getByText('strona1.jpg')).toBeInTheDocument()
    expect(screen.getByText('strona2.jpg')).toBeInTheDocument()
    expect(screen.getByText('strona3.jpg')).toBeInTheDocument()
    expect(documentsApi.uploadDocument).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /zatwierdź i wyślij/i }))

    await waitFor(() => expect(documentsApi.uploadDocument).toHaveBeenCalledTimes(1))
    const [sentFiles] = vi.mocked(documentsApi.uploadDocument).mock.calls[0]
    expect(sentFiles.map((f) => f.name)).toEqual(['strona1.jpg', 'strona2.jpg', 'strona3.jpg'])
  })

  it('pozwala usunac pojedyncze zdjecie z listy przed zatwierdzeniem', async () => {
    const user = userEvent.setup()
    vi.mocked(documentsApi.uploadDocument).mockResolvedValue({ id: 'doc1', status: 'queued' })
    renderPage()

    const [cameraInput] = document.querySelectorAll('input[type="file"]')
    await user.upload(cameraInput as HTMLInputElement, fakeFile('zla-strona.jpg'))
    await user.upload(cameraInput as HTMLInputElement, fakeFile('dobra-strona.jpg'))

    await user.click(screen.getByLabelText('Usuń zla-strona.jpg'))
    expect(screen.queryByText('zla-strona.jpg')).not.toBeInTheDocument()
    expect(screen.getByText('dobra-strona.jpg')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /zatwierdź i wyślij/i }))

    await waitFor(() => expect(documentsApi.uploadDocument).toHaveBeenCalledTimes(1))
    const [sentFiles] = vi.mocked(documentsApi.uploadDocument).mock.calls[0]
    expect(sentFiles.map((f) => f.name)).toEqual(['dobra-strona.jpg'])
  })
})
