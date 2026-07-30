import { apiRequest } from './client'
import type { Dzial, Product, ProductInput } from '../types'

export interface ProductFilters {
  status?: string
  grupa?: string
  search?: string
  limit?: number
  offset?: number
  dzial?: Dzial
}

export function listProducts(filters: ProductFilters = {}): Promise<Product[]> {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.grupa) params.set('grupa', filters.grupa)
  if (filters.search) params.set('search', filters.search)
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))
  if (filters.offset !== undefined) params.set('offset', String(filters.offset))
  if (filters.dzial) params.set('dzial', filters.dzial)
  const query = params.toString()
  return apiRequest<Product[]>(`/products${query ? `?${query}` : ''}`)
}

export function getProduct(kod: string, dzial?: Dzial): Promise<Product> {
  const query = dzial ? `?dzial=${dzial}` : ''
  return apiRequest<Product>(`/products/${encodeURIComponent(kod)}${query}`)
}

export function createProduct(data: ProductInput & { kod: string }, dzial?: Dzial): Promise<Product> {
  const query = dzial ? `?dzial=${dzial}` : ''
  return apiRequest<Product>(`/products${query}`, { method: 'POST', body: data })
}

export function updateProduct(kod: string, data: ProductInput, dzial?: Dzial): Promise<Product> {
  const query = dzial ? `?dzial=${dzial}` : ''
  return apiRequest<Product>(`/products/${encodeURIComponent(kod)}${query}`, { method: 'PUT', body: data })
}

export function deleteProduct(kod: string, dzial?: Dzial): Promise<void> {
  const query = dzial ? `?dzial=${dzial}` : ''
  return apiRequest<void>(`/products/${encodeURIComponent(kod)}${query}`, { method: 'DELETE' })
}
