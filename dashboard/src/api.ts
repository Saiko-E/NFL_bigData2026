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
  demoPromise ??= fetch('demo/index.json').then(response => {
    if (!response.ok) throw new Error('Static demo data is unavailable')
    return response.json() as Promise<JsonRecord>
  })
  const demo = await demoPromise
  const [route, search = ''] = path.split('?')
  const params = new URLSearchParams(search)
  const paged = (items: JsonRecord[]) => ({ items, total: items.length, limit: 500, offset: 0 })
  if (route === 'api/overview') return demo.overview
  if (route === 'api/teams') return paged(asArray(demo.teams))
  if (route === 'api/games') {
    const team = params.get('team') || params.get('teamAbbr')
    const items = asArray(demo.games).filter(game => !team || [pick(game, ['homeTeamAbbr']), pick(game, ['visitorTeamAbbr'])].includes(team))
    return paged(items)
  }
  if (route === 'api/players') {
    const team = params.get('team')
    const items = asArray(demo.players).filter(player => !team || pick(player, ['teams']).split(',').includes(team))
    return paged(items)
  }
  if (route === 'api/plays') {
    const gameId = params.get('gameId') || params.get('game_id')
    const items = asArray(demo.plays).filter(play => !gameId || pick(play, ['gameId']) === gameId)
    return paged(items)
  }
  const playRoute = route.match(/^api\/plays\/(\d+)\/(\d+)\/(tracking|matchups)$/)
  if (playRoute) {
    const key = `${playRoute[1]}-${playRoute[2]}`
    if (playRoute[3] === 'tracking') {
      const response = await fetch(`demo/tracking/${key}.json`, { signal })
      if (!response.ok) throw new Error('Tracking is unavailable for this curated play')
      return response.json()
    }
    return (demo.matchups as JsonRecord)?.[key] ?? { matchups: [], total: 0 }
  }
  if (route === 'api/analytics/tactics') return demo.tactics
  const player = route.match(/^api\/players\/(\d+)\/stats$/)
  if (player) return (demo.playerStats as JsonRecord)?.[player[1]] ?? {}
  throw new Error(`Route unavailable in static demo: ${route}`)
}

export async function api<T = unknown>(path: string, signal?: AbortSignal): Promise<T> {
  const normalized = path.replace(/^\//, '')
  if (STATIC_DEMO) return demoApi(normalized, signal) as Promise<T>
  let response: Response
  try {
    response = await fetch(normalized, { signal, headers: { Accept: 'application/json' } })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return demoApi(normalized) as Promise<T>
  }
  if (response.ok) return response.json() as Promise<T>
  if (response.status === 503) return demoApi(normalized) as Promise<T>
  throw new Error(`${response.status} ${response.statusText}`)
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
