import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, asArray, number, pick, query, type JsonRecord } from './api'

const tooltipStyle = { background: '#0b1628', border: '1px solid rgba(148,163,184,.16)', borderRadius: 10, fontSize: 12 }

function useEndpoint(path: string | null, preferred: string[] = [], acceptObject = false) {
  const [data, setData] = useState<JsonRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!path) { setData([]); return }
    const controller = new AbortController()
    setLoading(true); setError('')
    api(path, controller.signal).then(payload => {
      const records = asArray(payload, preferred)
      if (records.length || !acceptObject || !payload || typeof payload !== 'object') { setData(records); return }
      const record = payload as JsonRecord
      const nested = preferred.map(key => record[key]).find(value => value && typeof value === 'object' && !Array.isArray(value))
      setData([nested ? nested as JsonRecord : record])
    }).catch(err => {
      if (err instanceof Error && err.name !== 'AbortError') setError(err.message)
    }).finally(() => setLoading(false))
    return () => controller.abort()
  }, [path, acceptObject])
  return { data, loading, error }
}

export function MatchupsView({ gameId, playId }: { gameId: string; playId: string }) {
  const path = gameId && playId ? `api/plays/${encodeURIComponent(gameId)}/${encodeURIComponent(playId)}/matchups` : null
  const { data, loading, error } = useEndpoint(path, ['matchups', 'pressure'])
  const rows = data.map((item, index) => ({
    name: pick(item, ['defenderName', 'rusherName', 'defender', 'playerName', 'name'], `Rusher ${index + 1}`),
    target: pick(item, ['offenderName', 'blockerName', 'matchup', 'target'], 'QB'),
    blockType: pick(item, ['blockType', 'block_type'], 'Pass block'),
    impact: ['beaten', 'hitAllowed', 'hurryAllowed', 'sackAllowed', 'hit', 'hurry', 'sack'].reduce((sum, key) => sum + number(item, [key]), 0),
    pressure: Math.max(...['hit', 'hurry', 'sack', 'hitAllowed', 'hurryAllowed', 'sackAllowed'].map(key => number(item, [key]))),
  }))
  return <ViewShell title="QB pressure & matchups" subtitle="Pass-rush proximity, protection assignments, and pressure timing" loading={loading} error={error} empty={!rows.length}>
    <div className="grid gap-4 lg:grid-cols-3">
      <Metric label="Pass-rush matchups" value={String(rows.length)} note="Protection assignments" tone="rose" />
      <Metric label="Pressure rate" value={rows.length ? `${(rows.reduce((sum, row) => sum + row.pressure, 0) / rows.length * 100).toFixed(1)}%` : '—'} note="Matchups producing pressure" tone="amber" />
      <Metric label="Protection losses" value={String(rows.filter(row => row.impact > 0).length)} note="Beaten, hurry, hit, or sack" tone="sky" />
    </div>
    <div className="mt-4 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
      <ChartCard title="Pressure impact" detail="Charted protection losses by pass rusher">
        <ResponsiveContainer width="100%" height={280}><BarChart data={rows.slice(0, 10)} layout="vertical" margin={{ left: 12, right: 16 }}><CartesianGrid stroke="#94a3b8" strokeOpacity={0.08} horizontal={false}/><XAxis type="number" tick={axisTick}/><YAxis type="category" dataKey="name" width={90} tick={axisTick}/><Tooltip contentStyle={tooltipStyle} formatter={(v) => [Number(v).toFixed(0), 'Impact score']}/><Bar dataKey="impact" radius={[0, 5, 5, 0]}>{rows.map((_, i) => <Cell key={i} fill={i < 3 ? '#fb7185' : '#38bdf8'} />)}</Bar></BarChart></ResponsiveContainer>
      </ChartCard>
      <div className="panel p-4"><p className="eyebrow">Matchup board</p><div className="mt-3 space-y-2">{rows.slice(0, 8).map((row, index) => <div key={`${row.name}-${index}`} className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[.025] p-3"><div><p className="text-sm font-medium text-slate-200">{row.name}</p><p className="text-xs text-slate-500">vs {row.target} · {row.blockType}</p></div><div className="text-right"><p className="font-mono text-sm text-rose-300">{row.impact.toFixed(0)}</p><p className="text-[10px] uppercase text-slate-600">impact</p></div></div>)}</div></div>
    </div>
  </ViewShell>
}

export function ComparisonView({ players }: { players: JsonRecord[] }) {
  const [first, setFirst] = useState('')
  const [second, setSecond] = useState('')
  useEffect(() => { if (!players.some(player => pick(player, ['nflId', 'playerId', 'id']) === first)) setFirst(players[0] ? pick(players[0], ['nflId', 'playerId', 'id']) : '') }, [players, first])
  const firstPlayer = players.find(player => pick(player, ['nflId', 'playerId', 'id']) === first)
  const firstPosition = pick(firstPlayer, ['officialPosition', 'positionGroup', 'position', 'pos'])
  const samePosition = players.filter(player => pick(player, ['nflId', 'playerId', 'id']) !== first
    && (!firstPosition || pick(player, ['officialPosition', 'positionGroup', 'position', 'pos']) === firstPosition))
  const comparisonCandidates = useMemo(() => samePosition.length ? samePosition : players.filter(player => pick(player, ['nflId', 'playerId', 'id']) !== first), [players, first, firstPosition])
  useEffect(() => { if (!comparisonCandidates.some(player => pick(player, ['nflId', 'playerId', 'id']) === second)) setSecond(comparisonCandidates[0] ? pick(comparisonCandidates[0], ['nflId', 'playerId', 'id']) : '') }, [comparisonCandidates, second])
  const firstStats = useEndpoint(first ? `api/players/${encodeURIComponent(first)}/stats` : null, ['stats', 'data'], true)
  const secondStats = useEndpoint(second ? `api/players/${encodeURIComponent(second)}/stats` : null, ['stats', 'data'], true)
  const a = firstStats.data[0] ?? {}, b = secondStats.data[0] ?? {}
  const playerName = (id: string) => pick(players.find(player => pick(player, ['nflId', 'playerId', 'id']) === id), ['displayName', 'playerName', 'name'], id || 'Player')
  const metrics = [
    ['Speed', ['avgSpeed', 'averageSpeed', 'avg_speed_window_yps', 'speed', 's']], ['Max speed', ['maxSpeed', 'topSpeed', 'top_speed_yps']], ['Routes', ['n_routes', 'routes']],
    ['Distance', ['distance', 'totalDistance', 'avg_dist_window_yds']], ['Acceleration', ['avgAcceleration', 'avg_max_abs_accel_ypss', 'acceleration', 'a']], ['Plays', ['n_plays', 'plays']],
  ] as const
  const chart = metrics.map(([metric, keys]) => ({ metric, [playerName(first)]: number(a, [...keys]), [playerName(second)]: number(b, [...keys]) }))
  return <ViewShell title="Player comparison" subtitle="Compare tracking-derived production and athletic profiles" loading={firstStats.loading || secondStats.loading} error={firstStats.error || secondStats.error} empty={!players.length}>
    <div className="panel mb-4 grid gap-3 p-4 md:grid-cols-[1fr_auto_1fr] md:items-end">
      <PlayerSelect label="Player A" value={first} onChange={setFirst} players={players}/><span className="hidden pb-3 text-xs text-slate-600 md:block">VERSUS</span><PlayerSelect label={`Player B${firstPosition ? ` · ${firstPosition}` : ''}`} value={second} onChange={setSecond} players={comparisonCandidates}/>
    </div>
    <div className="grid gap-4 xl:grid-cols-[1fr_1.4fr]">
      <ChartCard title="Observed profile" detail="Tracking-derived values; axes use different units"><ResponsiveContainer width="100%" height={330}><RadarChart data={chart}><PolarGrid stroke="#94a3b8" strokeOpacity={.15}/><PolarAngleAxis dataKey="metric" tick={{ fill: '#94a3b8', fontSize: 11 }}/><Radar name={playerName(first)} dataKey={playerName(first)} stroke="#38bdf8" fill="#38bdf8" fillOpacity={.18}/><Radar name={playerName(second)} dataKey={playerName(second)} stroke="#fb7185" fill="#fb7185" fillOpacity={.16}/><Legend wrapperStyle={{ fontSize: 11 }}/><Tooltip contentStyle={tooltipStyle}/></RadarChart></ResponsiveContainer></ChartCard>
      <div className="panel overflow-hidden"><div className="grid grid-cols-[1fr_100px_1fr] border-b border-white/5 bg-white/[.02] px-4 py-3 text-center text-xs"><span className="font-medium text-sky-300">{playerName(first)}</span><span className="text-slate-600">METRIC</span><span className="font-medium text-rose-300">{playerName(second)}</span></div>{chart.map(row => <div key={row.metric} className="grid grid-cols-[1fr_100px_1fr] border-b border-white/5 px-4 py-4 text-center last:border-0"><span className="font-mono font-semibold text-slate-200">{Number(row[playerName(first)]).toFixed(2)}</span><span className="text-xs text-slate-500">{row.metric}</span><span className="font-mono font-semibold text-slate-200">{Number(row[playerName(second)]).toFixed(2)}</span></div>)}</div>
    </div>
  </ViewShell>
}

export function TacticsView() {
  const { data, loading, error } = useEndpoint(query('api/analytics/tactics', { dimension: 'formation', minPlays: 10 }), ['tactics', 'plays'])
  const rows = data.map((item, index) => ({
    label: pick(item, ['tactic', 'concept', 'playType', 'formation', 'name'], `Tactic ${index + 1}`),
    formation: pick(item, ['dimension', 'formation', 'offenseFormation', 'offense_formation'], 'Formation'),
    coverage: pick(item, ['coverage', 'coverageType', 'defensiveCoverage'], 'Unclassified'),
    usage: number(item, ['nPlays', 'usage', 'count', 'frequency', 'plays']), success: number(item, ['completionRate', 'successRate', 'success_rate', 'rate']) * 100,
    pressure: number(item, ['pressureRate', 'pressure_rate']) * 100, yards: number(item, ['avgPlayResult', 'yards', 'yardsGained', 'avgYards']),
    time: number(item, ['avgTimeToThrowSeconds', 'timeToThrow']),
  }))
  return <ViewShell title="Tactics & play explorer" subtitle="Formation tendencies, concepts, coverages, and outcomes" loading={loading} error={error} empty={!rows.length}>
    <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
      <ChartCard title="Tactical frequency" detail="Play volume by formation or concept"><ResponsiveContainer width="100%" height={300}><BarChart data={rows.slice(0, 12)}><CartesianGrid stroke="#94a3b8" strokeOpacity={.08} vertical={false}/><XAxis dataKey="label" tick={axisTick} interval={0} angle={-18} textAnchor="end" height={65}/><YAxis tick={axisTick}/><Tooltip contentStyle={tooltipStyle}/><Bar dataKey="usage" fill="#a78bfa" radius={[5,5,0,0]}/></BarChart></ResponsiveContainer></ChartCard>
      <ChartCard title="Outcome rates" detail="Completion and pressure rate by tactic"><ResponsiveContainer width="100%" height={300}><LineChart data={rows.slice(0, 12)}><CartesianGrid stroke="#94a3b8" strokeOpacity={.08}/><XAxis dataKey="label" tick={axisTick} hide/><YAxis tick={axisTick}/><Tooltip contentStyle={tooltipStyle}/><Line type="monotone" dataKey="success" stroke="#34d399" strokeWidth={2} dot={{ fill: '#34d399', r: 3 }}/><Line type="monotone" dataKey="pressure" stroke="#38bdf8" strokeWidth={2} dot={false}/></LineChart></ResponsiveContainer></ChartCard>
    </div>
    <div className="panel mt-4 overflow-x-auto"><table className="data-table"><thead><tr><th>Tactic</th><th>Dimension</th><th>Coverage</th><th>Plays</th><th>Completion</th><th>Avg result</th><th>Time to throw</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.label}-${index}`}><td className="font-medium text-slate-200">{row.label}</td><td>{row.formation}</td><td>{row.coverage}</td><td>{row.usage.toFixed(0)}</td><td>{row.success.toFixed(1)}%</td><td>{row.yards.toFixed(1)} yd</td><td>{row.time.toFixed(2)}s</td></tr>)}</tbody></table></div>
  </ViewShell>
}

function PlayerSelect({ label, value, onChange, players }: { label: string; value: string; onChange: (value: string) => void; players: JsonRecord[] }) { return <label><span className="mb-2 block text-[10px] font-semibold uppercase tracking-widest text-slate-500">{label}</span><select className="select-field" value={value} onChange={event => onChange(event.target.value)}>{players.map(player => { const id = pick(player, ['nflId', 'playerId', 'id']); return <option key={id} value={id}>{pick(player, ['displayName', 'playerName', 'name'], id)} · {pick(player, ['officialPosition', 'positionGroup', 'position', 'pos', 'teamAbbr', 'club'])}</option> })}</select></label> }
function ViewShell({ title, subtitle, loading, error, empty, children }: { title: string; subtitle: string; loading: boolean; error: string; empty: boolean; children: React.ReactNode }) { return <div><div className="mb-5"><p className="eyebrow">Analytics workspace</p><h2 className="mt-1 text-xl font-semibold text-white">{title}</h2><p className="mt-1 text-sm text-slate-500">{subtitle}</p></div>{error && <Notice text={`API unavailable: ${error}`} />}{loading ? <div className="panel grid h-72 place-items-center"><div className="loader"/></div> : empty ? <div className="panel grid h-72 place-items-center px-5 text-center text-sm text-slate-500">No records returned for the current selection.<br/>Choose another game or play, or verify the API service.</div> : children}</div> }
function Notice({ text }: { text: string }) { return <div className="mb-4 rounded-xl border border-amber-300/15 bg-amber-300/5 px-4 py-3 text-xs text-amber-200">{text}</div> }
function ChartCard({ title, detail, children }: { title: string; detail: string; children: React.ReactNode }) { return <div className="panel p-4"><p className="font-medium text-slate-200">{title}</p><p className="mb-4 mt-0.5 text-xs text-slate-500">{detail}</p>{children}</div> }
function Metric({ label, value, note, tone }: { label: string; value: string; note: string; tone: 'rose'|'amber'|'sky' }) { const color = { rose: 'bg-rose-400', amber: 'bg-amber-400', sky: 'bg-sky-400' }[tone]; return <div className="metric-card"><div className={`mb-3 h-1 w-8 rounded-full ${color}`}/><p className="text-xs text-slate-500">{label}</p><p className="mt-1 font-mono text-2xl font-semibold text-white">{value}</p><p className="mt-2 text-[11px] text-slate-600">{note}</p></div> }
const axisTick = { fill: '#64748b', fontSize: 10 }
