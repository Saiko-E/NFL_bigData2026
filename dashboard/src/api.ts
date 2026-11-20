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

export const STATIC_DEMO = window.location.hostname.endsWith('github.io') || new URLSearchParams(window.location.search).has('demo')
let demoPromise: Promise<JsonRecord> | null = null

async function demoApi(path: string, signal?: AbortSignal): Promise<unknown> {
  demoPromise ??= fetch('demo.json', { signal }).then(response => {
    if (!response.ok) throw new Error('Static demo data is unavailable')
    return response.json() as Promise<JsonRecord>
  })
  const demo = await demoPromise
  const route = path.split('?')[0]
  if (route === 'api/overview') return demo.overview
  if (route === 'api/teams') return { items: demo.teams, total: asArray(demo.teams).length, limit: 100, offset: 0 }
  if (route === 'api/games') return { items: demo.games, total: asArray(demo.games).length, limit: 100, offset: 0 }
  if (route === 'api/players') return { items: demo.players, total: asArray(demo.players).length, limit: 100, offset: 0 }
  if (route === 'api/plays') return { items: demo.plays, total: asArray(demo.plays).length, limit: 100, offset: 0 }
  if (route.endsWith('/tracking')) return demo.tracking
  if (route.endsWith('/matchups')) return demo.matchups
  if (route === 'api/analytics/tactics') return demo.tactics
  const player = route.match(/^api\/players\/(\d+)\/stats$/)
  if (player) return (demo.playerStats as JsonRecord)?.[player[1]] ?? {}
  throw new Error(`Route unavailable in static demo: ${route}`)
}

export async function api<T = unknown>(path: string, signal?: AbortSignal): Promise<T> {
  const normalized = path.replace(/^\//, '')
  if (STATIC_DEMO) return demoApi(normalized, signal) as Promise<T>
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
