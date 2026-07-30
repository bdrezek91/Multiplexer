import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProductFormDialog } from './ProductFormDialog'
import * as productsApi from '../api/products'
import type { Product } from '../types'

vi.mock('../api/products', async () => {
  const actual = await vi.importActual<typeof import('../api/products')>('../api/products')
  return { ...actual, createProduct: vi.fn(), updateProduct: vi.fn() }
})

function renderDialog(product: Product | null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ProductFormDialog open onClose={vi.fn()} product={product} dzial="elektryka" />
    </QueryClientProvider>,
  )
}

describe('ProductFormDialog', () => {
  beforeEach(() => {
    vi.mocked(productsApi.createProduct).mockReset()
    vi.mocked(productsApi.updateProduct).mockReset()
  })

  it('przy tworzeniu rozbija aliasy po przecinku i wysyla wraz z kodem', async () => {
    const user = userEvent.setup()
    vi.mocked(productsApi.createProduct).mockResolvedValue({} as Product)

    renderDialog(null)

    await user.type(screen.getByLabelText(/^kod/i), 'NOWY KOD')
    await user.type(screen.getByLabelText(/nazwa/i), 'Nowy produkt')
    await user.type(screen.getByLabelText(/aliasy/i), 'alias jeden, alias dwa ,  alias trzy')
    await user.click(screen.getByRole('button', { name: /zapisz/i }))

    await waitFor(() => expect(productsApi.createProduct).toHaveBeenCalledTimes(1))
    expect(productsApi.createProduct).toHaveBeenCalledWith(
      expect.objectContaining({
        kod: 'NOWY KOD',
        nazwa: 'Nowy produkt',
        aliasy: ['alias jeden', 'alias dwa', 'alias trzy'],
      }),
      'elektryka',
    )
  })

  it('pole kodu jest zablokowane przy edycji, a warianty_magazynowe przechodza niezmienione', async () => {
    const user = userEvent.setup()
    vi.mocked(productsApi.updateProduct).mockResolvedValue({} as Product)
    const existing: Product = {
      kod: 'ISTNIEJACY',
      nazwa: 'Stara nazwa',
      jm: 'SZT',
      grupa: 'Grupa A',
      status: 'generyczny',
      atrybuty: {},
      kolor_domniemany: false,
      aliasy: ['istniejacy alias'],
      warianty_magazynowe: { Zabrze: 'ISTNIEJACY ZABRZE' },
      dzial: 'elektryka',
    }

    renderDialog(existing)

    expect(screen.getByLabelText(/^kod/i)).toBeDisabled()

    await user.clear(screen.getByLabelText(/nazwa/i))
    await user.type(screen.getByLabelText(/nazwa/i), 'Zmieniona nazwa')
    await user.click(screen.getByRole('button', { name: /zapisz/i }))

    await waitFor(() => expect(productsApi.updateProduct).toHaveBeenCalledTimes(1))
    expect(productsApi.updateProduct).toHaveBeenCalledWith(
      'ISTNIEJACY',
      expect.objectContaining({
        nazwa: 'Zmieniona nazwa',
        warianty_magazynowe: { Zabrze: 'ISTNIEJACY ZABRZE' },
      }),
      'elektryka',
    )
  })
})
