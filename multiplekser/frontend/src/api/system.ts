import { apiRequest } from './client'
import type { SystemStatus } from '../types'

export function getSystemStatus(): Promise<SystemStatus> {
  return apiRequest<SystemStatus>('/system/status')
}
