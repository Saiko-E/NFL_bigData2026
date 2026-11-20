import { useEffect, useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, asArray, number, pick, query, shortNumber, STATIC_DEMO, type JsonRecord } from './api'
import FootballField, { normalizeTracking, type TrackingFrame } from './FootballField'
import { ComparisonView, MatchupsView, TacticsView } from './AnalyticsViews'

type Tab = 'overview' | 'matchups' | 'compare' | 'tactics'
const tabs: { id: Tab; label: string; icon: string }[] = [
  { id: 'overview', label: 'Overview', icon: '⌂' }, { id: 'matchups', label: 'QB Pressure', icon: '◈' },
  { id: 'compare', label: 'Player Compare', icon: '⇄' }, { id: 'tactics', label: 'Play Explorer', icon: '⌘' },
]

function useList(path: string | null, preferred: string[]) {
  const [data, setData] = useState<JsonRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!path) { setData([]); setLoading(false); return }
    const controller = new AbortController()
    setLoading(true); setError('')
    api(path, controller.signal).then(payload => setData(asArray(payload, preferred))).catch(err => {
      if (err instanceof Error && err.name !== 'AbortError') setError(err.message)
    }).finally(() => setLoading(false))
    return () => controller.abort()
  }, [path])
  return { data, loading, error }
}

export default function App() {
  const [tab, setTab] = useState<Tab>('overview')
  const [mobileNav, setMobileNav] = useState(false)
  const [teamId, setTeamId] = useState('')
  const [gameId, setGameId] = useState('')
  const [playId, setPlayId] = useState('')
  const [tracking, setTracking] = useState<TrackingFrame[]>([])
  const [trackingLoading, setTrackingLoading] = useState(false)
  const [trackingError, setTrackingError] = useState('')
  const [overview, setOverview] = useState<JsonRecord>({})
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)

  const teams = useList('api/teams', ['teams'])
  const games = useList(teamId ? query('api/games', { team: teamId, teamAbbr: teamId }) : null, ['games'])
  const plays = useList(gameId ? query('api/plays', { gameId, game_id: gameId }) : null, ['plays'])
  const players = useList(query('api/players', { team: teamId || undefined }), ['players'])

  useEffect(() => {
    const controller = new AbortController()
    api('api/overview', controller.signal).then(payload => {
      const record = payload && typeof payload === 'object' ? payload as JsonRecord : {}
      setOverview(record.data && !Array.isArray(record.data) && typeof record.data === 'object' ? record.data as JsonRecord : record)
      setApiOnline(true)
    }).catch(err => { if (err instanceof Error && err.name !== 'AbortError') setApiOnline(false) })
    return () => controller.abort()
  }, [])
  useEffect(() => { if (!teamId && teams.data[0]) setTeamId(teamKey(teams.data[0])) }, [teams.data, teamId])
  useEffect(() => { setGameId(games.data[0] ? gameKey(games.data[0]) : '') }, [teamId, games.data])
  useEffect(() => { setPlayId(plays.data[0] ? playKey(plays.data[0]) : '') }, [gameId, plays.data])
  useEffect(() => {
    if (!gameId || !playId) { setTracking([]); return }
    const controller = new AbortController()
    setTrackingLoading(true); setTrackingError('')
    api(`api/plays/${encodeURIComponent(gameId)}/${encodeURIComponent(playId)}/tracking`, controller.signal)
      .then(payload => setTracking(normalizeTracking(payload)))
      .catch(err => { if (err instanceof Error && err.name !== 'AbortError') { setTrackingError(err.message); setTracking([]) } })
      .finally(() => setTrackingLoading(false))
    return () => controller.abort()
  }, [gameId, playId])

  const currentTeam = teams.data.find(team => teamKey(team) === teamId)
  const currentGame = games.data.find(game => gameKey(game) === gameId)
  const currentPlay = plays.data.find(play => playKey(play) === playId)
  const errors = teams.error || games.error || plays.error || trackingError

  return <div className="min-h-screen bg-[#07101d] text-slate-300">
    <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(circle_at_80%_-20%,rgba(56,189,248,.09),transparent_34%),radial-gradient(circle_at_10%_90%,rgba(124,58,237,.06),transparent_34%)]"/>
    <aside className={`sidebar ${mobileNav ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0`}>
      <div className="flex h-16 items-center gap-3 border-b border-white/5 px-5">
        <div className="logo-mark"><span>N</span></div><div><p className="font-semibold leading-none text-white">NEXT<span className="text-sky-400">DOWN</span></p><p className="mt-1 text-[9px] font-medium tracking-[.24em] text-slate-600">NFL INTELLIGENCE</p></div>
        <button className="ml-auto text-slate-500 lg:hidden" onClick={() => setMobileNav(false)}>✕</button>
      </div>
      <nav className="px-3 py-5">
        <p className="px-3 pb-2 text-[9px] font-bold uppercase tracking-[.22em] text-slate-700">Workspace</p>
        {tabs.map(item => <button key={item.id} onClick={() => { setTab(item.id); setMobileNav(false) }} className={`nav-item ${tab === item.id ? 'active' : ''}`}><span className="w-5 text-center text-base">{item.icon}</span>{item.label}{tab === item.id && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-sky-300"/>}</button>)}
      </nav>
      <div className="mx-3 mt-auto rounded-xl border border-white/5 bg-white/[.025] p-3">
        <div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${apiOnline ? 'bg-emerald-400' : apiOnline === false ? 'bg-rose-400' : 'bg-amber-300'} ${apiOnline ? 'shadow-[0_0_8px_#34d399]' : ''}`}/><p className="text-xs font-medium text-slate-300">{apiOnline ? (STATIC_DEMO ? 'Static data demo' : 'Data service online') : apiOnline === false ? 'Data service offline' : 'Checking service'}</p></div><p className="mt-1 pl-4 text-[10px] text-slate-600">{STATIC_DEMO ? '32 teams · real curated plays' : 'Relative /api connection'}</p>
      </div>
      <div className="px-5 py-5 text-[10px] text-slate-700">UNAM · NFL Analytics Lab</div>
    </aside>
    {mobileNav && <button className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setMobileNav(false)} aria-label="Close navigation"/>}

    <main className="relative min-h-screen lg:pl-60">
      <header className="sticky top-0 z-20 flex h-16 items-center border-b border-white/5 bg-[#07101d]/85 px-4 backdrop-blur-xl sm:px-6">
        <button className="mr-3 text-xl text-slate-400 lg:hidden" onClick={() => setMobileNav(true)}>☰</button>
        <div><p className="text-sm font-medium capitalize text-white">{tabs.find(item => item.id === tab)?.label}</p><p className="hidden text-[10px] text-slate-600 sm:block">NFL player tracking & tactical analysis</p></div>
        <div className="ml-auto flex items-center gap-3"><span className="hidden rounded-full border border-white/5 bg-white/[.025] px-3 py-1 text-[10px] text-slate-500 sm:block">2021 · WEEKS 1–8</span><div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-violet-500 text-[10px] font-bold text-white">NX</div></div>
      </header>

      <div className="mx-auto max-w-[1580px] p-4 sm:p-6">
        <section className="mb-5">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow">Tracking command center</p><h1 className="mt-1 text-2xl font-semibold tracking-tight text-white sm:text-3xl">Read the field. <span className="text-slate-500">Own the next play.</span></h1></div><div className="text-right text-[10px] uppercase tracking-widest text-slate-600">Big Data Bowl<br/><span className="text-slate-400">Analytics Console</span></div></div>
          <div className="panel grid gap-px overflow-hidden bg-white/5 md:grid-cols-3">
            <Selector step="01" label="Team" value={teamId} onChange={setTeamId} loading={teams.loading} disabled={false} options={teams.data.map(team => ({ value: teamKey(team), label: teamLabel(team) }))}/>
            <Selector step="02" label="Game" value={gameId} onChange={setGameId} loading={games.loading} disabled={!teamId} options={games.data.map(game => ({ value: gameKey(game), label: gameLabel(game) }))}/>
            <Selector step="03" label="Play" value={playId} onChange={setPlayId} loading={plays.loading} disabled={!gameId} options={plays.data.map(play => ({ value: playKey(play), label: playLabel(play) }))}/>
          </div>
          {errors && <div className="mt-3 rounded-xl border border-rose-400/15 bg-rose-400/5 px-4 py-2.5 text-xs text-rose-200">Some live data could not be loaded ({errors}). The dashboard remains available.</div>}
        </section>

        {tab === 'overview' && <Overview overview={overview} team={currentTeam} game={currentGame} play={currentPlay} tracking={tracking} loading={trackingLoading}/>}
        {tab === 'matchups' && <MatchupsView gameId={gameId} playId={playId}/>}
        {tab === 'compare' && <ComparisonView players={players.data}/>}
        {tab === 'tactics' && <TacticsView/>}
      </div>
    </main>
  </div>
}

function Overview({ overview, team, game, play, tracking, loading }: { overview: JsonRecord; team?: JsonRecord; game?: JsonRecord; play?: JsonRecord; tracking: TrackingFrame[]; loading: boolean }) {
  const athletes = number(overview, ['players', 'playerCount', 'athletes'], new Set(tracking.flatMap(frame => frame.entities.filter(e => !e.isBall).map(e => e.id))).size)
  const games = number(overview, ['games', 'gameCount', 'totalGames'])
  const plays = number(overview, ['plays', 'playCount', 'totalPlays'])
  const trend = useMemo(() => tracking.filter((_, i) => i % Math.max(1, Math.floor(tracking.length / 30)) === 0).map((frame, i) => {
    const players = frame.entities.filter(entity => !entity.isBall)
    return { frame: frame.id || i, speed: players.length ? players.reduce((sum, entity) => sum + entity.speed, 0) / players.length : 0 }
  }), [tracking])
  return <div>
    <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
      <Stat icon="◉" label="Tracking rows" value={shortNumber(number(overview, ['trackingRows'], 0))} detail={tracking.length ? `${tracking.length} frames in active play` : 'Select a play to load frames'} color="sky"/>
      <Stat icon="♙" label="Active athletes" value={shortNumber(athletes)} detail={pick(team, ['displayName', 'teamName', 'name', 'teamAbbr'], 'Across dataset')} color="violet"/>
      <Stat icon="◇" label="Games indexed" value={shortNumber(games)} detail={pick(game, ['week', 'gameDate', 'date'], 'Searchable film')} color="emerald"/>
      <Stat icon="↗" label="Plays analyzed" value={shortNumber(plays)} detail="Tracking-ready snaps" color="amber"/>
    </div>
    <FootballField frames={tracking} loading={loading}/>
    <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_340px]">
      <div className="panel p-4"><div className="flex items-center justify-between"><div><p className="font-medium text-slate-200">Play velocity profile</p><p className="mt-0.5 text-xs text-slate-500">Average on-field speed by tracking frame</p></div><span className="rounded-lg bg-sky-400/10 px-2 py-1 text-[10px] text-sky-300">LIVE SAMPLE</span></div><div className="mt-3 h-40"><ResponsiveContainer width="100%" height="100%"><AreaChart data={trend}><defs><linearGradient id="speedFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" stopOpacity={.3}/><stop offset="100%" stopColor="#38bdf8" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#94a3b8" strokeOpacity={.06}/><XAxis dataKey="frame" tick={{ fill: '#64748b', fontSize: 9 }}/><YAxis tick={{ fill: '#64748b', fontSize: 9 }} width={28}/><Tooltip contentStyle={{ background: '#0b1628', border: '1px solid rgba(148,163,184,.16)', borderRadius: 8, fontSize: 11 }}/><Area type="monotone" dataKey="speed" stroke="#38bdf8" fill="url(#speedFill)" strokeWidth={2}/></AreaChart></ResponsiveContainer></div></div>
      <div className="panel p-4"><p className="eyebrow">Current play</p><p className="mt-3 text-sm font-medium leading-6 text-slate-200">{pick(play, ['playDescription', 'description', 'play'], 'Select a team, game, and play to begin film analysis.')}</p><div className="mt-4 grid grid-cols-3 gap-2"><Small label="Down" value={pick(play, ['down'], '—')}/><Small label="To go" value={pick(play, ['yardsToGo', 'yards_to_go'], '—')}/><Small label="Quarter" value={pick(play, ['quarter', 'qtr'], '—')}/></div></div>
    </div>
  </div>
}

function Selector({ step, label, value, onChange, options, loading, disabled }: { step: string; label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; loading: boolean; disabled: boolean }) { return <label className="bg-[#0b1626] p-4"><span className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-slate-500"><b className="text-sky-400">{step}</b>{label}{loading && <span className="ml-auto h-2 w-2 animate-pulse rounded-full bg-sky-400"/>}</span><select className="select-field" value={value} onChange={event => onChange(event.target.value)} disabled={disabled || loading}><option value="">{loading ? 'Loading…' : options.length ? `Select ${label.toLowerCase()}` : `No ${label.toLowerCase()} available`}</option>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label> }
function Stat({ icon, label, value, detail, color }: { icon: string; label: string; value: string; detail: string; color: string }) { const colors: Record<string,string> = { sky:'text-sky-300 bg-sky-400/10', violet:'text-violet-300 bg-violet-400/10', emerald:'text-emerald-300 bg-emerald-400/10', amber:'text-amber-300 bg-amber-400/10' }; return <div className="metric-card"><div className="flex items-start justify-between"><div><p className="text-xs text-slate-500">{label}</p><p className="mt-1 font-mono text-2xl font-semibold text-white">{value}</p></div><span className={`grid h-9 w-9 place-items-center rounded-lg ${colors[color]}`}>{icon}</span></div><p className="mt-3 truncate text-[10px] text-slate-600">{detail}</p></div> }
function Small({ label, value }: { label: string; value: string }) { return <div className="rounded-lg bg-white/[.03] p-2 text-center"><p className="text-[9px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-1 font-mono text-sm text-slate-300">{value}</p></div> }
const teamKey = (team: JsonRecord) => pick(team, ['teamAbbr', 'team_abbr', 'team', 'abbr', 'id', 'teamId'])
const gameKey = (game: JsonRecord) => pick(game, ['gameId', 'game_id', 'id'])
const playKey = (play: JsonRecord) => pick(play, ['playId', 'play_id', 'id'])
const teamLabel = (team: JsonRecord) => pick(team, ['displayName', 'teamName', 'name', 'teamAbbr', 'team', 'abbr'], teamKey(team))
const gameLabel = (game: JsonRecord) => pick(game, ['label', 'matchup', 'name'], `${pick(game, ['week'], 'Game')} · ${pick(game, ['homeTeamAbbr', 'homeTeam'], '')} vs ${pick(game, ['visitorTeamAbbr', 'awayTeam'], '')}`)
const playLabel = (play: JsonRecord) => { const id = playKey(play); const desc = pick(play, ['playDescription', 'description', 'label'], 'Play'); return `#${id} · ${desc.length > 68 ? `${desc.slice(0, 68)}…` : desc}` }
