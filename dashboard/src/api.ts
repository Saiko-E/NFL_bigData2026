export type JsonRecord = Record<string, unknown>

const ARRAY_KEYS = ['data', 'results', 'items', 'teams', 'games', 'plays', 'players', 'matchups', 'tactics', 'tracking', 'frames']

export const pick = (item: unknown, keys: string[], fallback = ''): string => {
  if (!item || typeof item !== 'object') return fallback
  const record = item as JsonRecord
  for (const key of keys) {
    const value = record[key]
    if (value !== undefined && value !== null && value !== '') return String(value)
  }
  return fallback
}

export const number = (item: unknown, keys: string[], fallback = 0): number => {
  if (!item || typeof item !== 'object') return fallback
  const record = item as JsonRecord
  for (const key of keys) {
    const raw = record[key]
    if (raw === undefined || raw === null || raw === '') continue
    if (typeof raw === 'boolean') return raw ? 1 : 0
    const value = Number(raw)
    if (Number.isFinite(value)) return value
  }
  return fallback
}

export const asArray = (payload: unknown, preferred: string[] = []): JsonRecord[] => {
  if (Array.isArray(payload)) return payload.filter((value): value is JsonRecord => !!value && typeof value === 'object')
  if (!payload || typeof payload !== 'object') return []
  const record = payload as JsonRecord
  for (const key of [...preferred, ...ARRAY_KEYS]) {
    const value = record[key]
    if (Array.isArray(value)) return value.filter((entry): entry is JsonRecord => !!entry && typeof entry === 'object')
  }
  return []
}

export async function api<T = unknown>(path: string, signal?: AbortSignal): Promise<T> {
  const normalized = path.replace(/^\//, '')
  const response = await fetch(normalized, { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

export const query = (path: string, params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value))
  })
  const suffix = search.toString()
  return suffix ? `${path}?${suffix}` : path
}

export const shortNumber = (value: number) => new Intl.NumberFormat('en-US', {
  notation: value >= 1000 ? 'compact' : 'standard', maximumFractionDigits: 1,
}).format(value)
