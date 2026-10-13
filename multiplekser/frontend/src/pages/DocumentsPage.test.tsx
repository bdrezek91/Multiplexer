import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentsPage } from './DocumentsPage'
import * as documentsApi from '../api/documents'
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'admin@test.local', rola: 'admin', active: true, magazyny_dostepne: [] },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))
import * as compression from '../utils/compressImage'

vi.mock('../api/documents', async () => {
  const actual = await vi.importActual<typeof import('../api/documents')>('../api/documents')
  return { ...actual, listDocuments: vi.fn(), uploadDocument: vi.fn(), getClaudeUsage: vi.fn() }
})

vi.mock('../utils/compressImage', () => ({
  compressImageForUpload: vi.fn(),
}))

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
    vi.mocked(documentsApi.getClaudeUsage).mockResolvedValue({
      daemon_online: true, plan: 'Claude Pro', model: 'Sonnet', effort: 'Low',
      documents_done: 3, documents_error: 0, documents_waiting: 0,
      total_jobs: 0, jobs_24h: 0, pages_24h: 0, jobs_7d: 0, pages_7d: 0,
      avg_seconds: null, last_status: null, last_error_kind: null,
      last_error_at: null, subscription_remaining: null,
    })
    vi.mocked(documentsApi.uploadDocument).mockReset()
    vi.mocked(compression.compressImageForUpload).mockReset()
    vi.mocked(compression.compressImageForUpload).mockImplementation(async (file) => file)
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

  it('pozwala wybrac Claude + JEV z dzialem hydraulicznym przy uploadzie', async () => {
    const user = userEvent.setup()
    vi.mocked(documentsApi.uploadDocument).mockResolvedValue({ id: 'doc3', status: 'queued' })
    renderPage()
    const [cameraInput] = document.querySelectorAll('input[type="file"]')
    await user.upload(cameraInput as HTMLInputElement, fakeFile('hydraulika.jpg'))
    await user.click(screen.getByRole('button', { name: /claude \+ jev \(pro/i }))
    await user.click(screen.getByRole('button', { name: 'Hydraulika' }))
    await user.click(screen.getByRole('button', { name: /zatwierdź i wyślij/i }))
    await waitFor(() => expect(documentsApi.uploadDocument).toHaveBeenCalledTimes(1))
    expect(vi.mocked(documentsApi.uploadDocument).mock.calls[0][2]).toBe('claude_jev_test')
    expect(vi.mocked(documentsApi.uploadDocument).mock.calls[0][3]).toBe('hydraulika')
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

  it('zachowuje kolejnosc osobnych wyborow nawet gdy kompresja pierwszego trwa dluzej', async () => {
    const user = userEvent.setup()
    vi.mocked(documentsApi.uploadDocument).mockResolvedValue({ id: 'doc1', status: 'queued' })
    const resolvers = new Map<string, (file: File) => void>()
    vi.mocked(compression.compressImageForUpload).mockImplementation(
      (file) => new Promise<File>((resolve) => resolvers.set(file.name, resolve)),
    )
    renderPage()

    const [cameraInput] = document.querySelectorAll('input[type="file"]')
    const first = fakeFile('strona1-duza.jpg')
    const second = fakeFile('strona2-mala.jpg')
    await user.upload(cameraInput as HTMLInputElement, first)
    await waitFor(() => expect(compression.compressImageForUpload).toHaveBeenCalledTimes(1))

    await user.upload(cameraInput as HTMLInputElement, second)
    expect(compression.compressImageForUpload).toHaveBeenCalledTimes(1)

    resolvers.get(first.name)?.(first)
    await waitFor(() => expect(compression.compressImageForUpload).toHaveBeenCalledTimes(2))
    resolvers.get(second.name)?.(second)

    await waitFor(() => expect(screen.getByText(second.name)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /zatwierdź i wyślij/i }))
    await waitFor(() => expect(documentsApi.uploadDocument).toHaveBeenCalledTimes(1))
    const [sentFiles] = vi.mocked(documentsApi.uploadDocument).mock.calls[0]
    expect(sentFiles.map((file) => file.name)).toEqual([first.name, second.name])
  })

  it('wysyla oryginal i pokazuje ostrzezenie gdy kompresja sie nie powiedzie', async () => {
    const user = userEvent.setup()
    vi.mocked(compression.compressImageForUpload).mockImplementation(
      async (file, _maxSide, _quality, onFallback) => {
        onFallback?.(new Error('canvas error'))
        return file
      },
    )
    renderPage()

    const [cameraInput] = document.querySelectorAll('input[type="file"]')
    await user.upload(cameraInput as HTMLInputElement, fakeFile('oryginal.jpg'))

    expect(await screen.findByText(/nie udało się skompresować: oryginal.jpg/i)).toBeInTheDocument()
    expect(screen.getByText('oryginal.jpg')).toBeInTheDocument()
  })
})
