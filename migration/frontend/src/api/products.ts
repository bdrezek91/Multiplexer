import { apiRequest } from './client'
import type { Product, ProductInput } from '../types'

export interface ProductFilters {
  status?: string
  grupa?: string
  search?: string
  limit?: number
  offset?: number
}

export function listProducts(filters: ProductFilters = {}): Promise<Product[]> {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.grupa) params.set('grupa', filters.grupa)
  if (filters.search) params.set('search', filters.search)
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))
  if (filters.offset !== undefined) params.set('offset', String(filters.offset))
  const query = params.toString()
  return apiRequest<Product[]>(`/products${query ? `?${query}` : ''}`)
}

export function getProduct(kod: string): Promise<Product> {
  return apiRequest<Product>(`/products/${encodeURIComponent(kod)}`)
}

export function createProduct(data: ProductInput & { kod: string }): Promise<Product> {
  return apiRequest<Product>('/products', { method: 'POST', body: data })
}

export function updateProduct(kod: string, data: ProductInput): Promise<Product> {
  return apiRequest<Product>(`/products/${encodeURIComponent(kod)}`, { method: 'PUT', body: data })
}

export function deleteProduct(kod: string): Promise<void> {
  return apiRequest<void>(`/products/${encodeURIComponent(kod)}`, { method: 'DELETE' })
}
