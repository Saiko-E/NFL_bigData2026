import { useEffect, useMemo, useRef, useState } from 'react'
import { asArray, number, pick, type JsonRecord } from './api'

export type TrackingFrame = {
  id: number
  time: string
  event: string
  entities: TrackingEntity[]
}

export type TrackingEntity = {
  id: string
  name: string
  jersey: string
  team: string
  position: string
  x: number
  y: number
  speed: number
  direction: number
  orientation: number
  isBall: boolean
}

const COLORS = ['#38bdf8', '#fb7185']

export function normalizeTracking(payload: unknown): TrackingFrame[] {
  const source = payload && typeof payload === 'object' ? payload as JsonRecord : {}
  const candidates = asArray(payload, ['frames', 'tracking', 'data'])
  const rows = candidates.length ? candidates : asArray(source.data)
  if (!rows.length) return []

  const nestedFrames = rows.some(row => Array.isArray(row.players) || Array.isArray(row.entities) || Array.isArray(row.tracking))
  if (nestedFrames) {
    return rows.map((frame, index) => ({
      id: number(frame, ['frameId', 'frame_id', 'frame'], index + 1),
      time: pick(frame, ['time', 'timestamp', 'frameTime'], ''),
      event: pick(frame, ['event', 'eventName'], ''),
      entities: asArray(frame, ['players', 'entities', 'tracking', 'data']).map(normalizeEntity),
    })).sort((a, b) => a.id - b.id)
  }

  const grouped = new Map<number, TrackingFrame>()
  rows.forEach((row, index) => {
    const id = number(row, ['frameId', 'frame_id', 'frame'], index + 1)
    const current = grouped.get(id) ?? { id, time: pick(row, ['time', 'timestamp'], ''), event: '', entities: [] }
    current.event ||= pick(row, ['event', 'eventName'], '')
    current.entities.push(normalizeEntity(row))
    grouped.set(id, current)
  })
  return [...grouped.values()].sort((a, b) => a.id - b.id)
}

function normalizeEntity(row: JsonRecord): TrackingEntity {
  const display = pick(row, ['displayName', 'display_name', 'playerName', 'name'], 'Unknown')
  const team = pick(row, ['club', 'teamAbbr', 'team', 'team_abbr'], 'UNK')
  const id = pick(row, ['nflId', 'nfl_id', 'playerId', 'id'], `${team}-${display}`)
  const isBall = display.toLowerCase().includes('football') || team.toLowerCase() === 'football' || id.toLowerCase() === 'ball'
  return {
    id, name: isBall ? 'Football' : display, team, isBall,
    jersey: pick(row, ['jerseyNumber', 'jersey_number', 'jersey', 'number'], ''),
    position: pick(row, ['officialPosition', 'position', 'positionAbbr', 'pos'], ''),
    x: number(row, ['x_std', 'xStd', 'x', 'x_coord']), y: number(row, ['y_std', 'yStd', 'y', 'y_coord']),
    speed: number(row, ['s', 'speed']), direction: number(row, ['dir_std', 'dirStd', 'dir', 'direction']),
    orientation: number(row, ['o_std', 'oStd', 'o', 'orientation']),
  }
}

type Props = {
  frames: TrackingFrame[]
  loading: boolean
  onSelection?: (entity: TrackingEntity | null) => void
}

export default function FootballField({ frames, loading, onSelection }: Props) {
  const [frameIndex, setFrameIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [selectedId, setSelectedId] = useState('')
  const [labels, setLabels] = useState(true)
  const [trails, setTrails] = useState(true)
  const [vectors, setVectors] = useState(true)
  const lastRef = useRef(0)
  const accumulatorRef = useRef(0)

  useEffect(() => { setFrameIndex(0); setPlaying(false); setSelectedId('') }, [frames])
  useEffect(() => {
    if (!playing || frames.length < 2) return
    let animation = 0
    const tick = (now: number) => {
      if (!lastRef.current) lastRef.current = now
      accumulatorRef.current += now - lastRef.current
      lastRef.current = now
      const interval = 100 / speed
      if (accumulatorRef.current >= interval) {
        const steps = Math.floor(accumulatorRef.current / interval)
        accumulatorRef.current %= interval
        setFrameIndex(previous => {
          const next = previous + steps
          if (next >= frames.length - 1) { setPlaying(false); return frames.length - 1 }
          return next
        })
      }
      animation = requestAnimationFrame(tick)
    }
    animation = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(animation); lastRef.current = 0; accumulatorRef.current = 0 }
  }, [playing, speed, frames.length])

  const frame = frames[frameIndex]
  const teams = useMemo(() => [...new Set(frames.flatMap(item => item.entities.filter(e => !e.isBall).map(e => e.team)))], [frames])
  const selected = frame?.entities.find(entity => entity.id === selectedId) ?? null
  const history = useMemo(() => {
    if (!selectedId) return []
    return frames.slice(Math.max(0, frameIndex - 18), frameIndex + 1).flatMap(item => item.entities.filter(entity => entity.id === selectedId))
  }, [frames, frameIndex, selectedId])
  const distances = useMemo(() => {
    if (!selected) return []
    return frame.entities.filter(entity => !entity.isBall && entity.id !== selected.id).map(entity => ({
      entity, distance: Math.hypot(entity.x - selected.x, entity.y - selected.y),
    })).sort((a, b) => a.distance - b.distance).slice(0, 3)
  }, [frame, selected])

  const select = (entity: TrackingEntity) => {
    if (entity.isBall) return
    const next = selectedId === entity.id ? '' : entity.id
    setSelectedId(next)
    onSelection?.(next ? entity : null)
  }

  const teamColor = (entity: TrackingEntity) => entity.isBall ? '#7c3aed' : COLORS[Math.max(0, teams.indexOf(entity.team)) % COLORS.length]
  const sx = (x: number) => (x / 120) * 1200
  const sy = (y: number) => (y / 53.3) * 533

  return <section className="panel overflow-hidden">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 px-4 py-3">
      <div>
        <div className="flex items-center gap-2"><span className={`status-dot ${playing ? 'animate-pulse' : ''}`} /> <h2 className="font-semibold text-white">Live play tracking</h2></div>
        <p className="mt-0.5 text-xs text-slate-500">10 Hz player positioning · frame {frames.length ? frameIndex + 1 : 0}/{frames.length}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Toggle active={labels} onClick={() => setLabels(!labels)} label="Labels" />
        <Toggle active={trails} onClick={() => setTrails(!trails)} label="Trails" />
        <Toggle active={vectors} onClick={() => setVectors(!vectors)} label="Vectors" />
      </div>
    </div>

    <div className="grid xl:grid-cols-[minmax(0,1fr)_220px]">
      <div className="p-3 sm:p-5">
        <div className="field-wrap">
          {loading && <div className="absolute inset-0 z-10 grid place-items-center bg-slate-950/65 backdrop-blur-sm"><div className="loader" /><span className="mt-14 text-xs text-slate-300">Loading tracking data</span></div>}
          {!loading && !frames.length && <div className="absolute inset-0 z-10 grid place-items-center bg-slate-950/45"><div className="text-center"><div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-full bg-white/5 text-2xl">⌁</div><p className="font-medium text-slate-200">Select a play to load tracking</p><p className="mt-1 text-xs text-slate-500">Player positions will render here at 10 frames per second.</p></div></div>}
          <svg viewBox="0 0 1200 533" className="block w-full" aria-label="Animated football tracking field">
            <defs><pattern id="grass" width="40" height="40" patternUnits="userSpaceOnUse"><rect width="40" height="40" fill="#153b2b"/><path d="M0 40L40 0M-10 10L10-10M30 50L50 30" stroke="#fff" strokeOpacity=".018" strokeWidth="7"/></pattern><filter id="glow"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#cbd5e1" opacity=".8"/></marker></defs>
            <rect width="1200" height="533" fill="url(#grass)" />
            <rect x="100" y="0" width="1000" height="533" fill="none" stroke="#d7e8dc" strokeOpacity=".65" strokeWidth="3" />
            <g stroke="#e8f4ec" strokeOpacity=".35" fill="none">
              {Array.from({ length: 21 }, (_, i) => <line key={i} x1={100 + i * 50} x2={100 + i * 50} y1="0" y2="533" strokeWidth={i % 2 === 0 ? 2 : 1} />)}
              <line x1="100" x2="1100" y1="177" y2="177" strokeDasharray="6 15" /><line x1="100" x2="1100" y1="356" y2="356" strokeDasharray="6 15" />
            </g>
            <g fill="#fff" fillOpacity=".3" fontSize="28" fontWeight="700" textAnchor="middle">
              {[10,20,30,40,50,40,30,20,10].map((yard, i) => <g key={i}><text x={200 + i * 100} y="53">{yard}</text><text x={200 + i * 100} y="500" transform={`rotate(180 ${200 + i * 100} 488)`}>{yard}</text></g>)}
            </g>
            <text x="50" y="278" textAnchor="middle" fill="#fff" fillOpacity=".17" fontSize="20" fontWeight="800" transform="rotate(-90 50 266)">END ZONE</text><text x="1150" y="278" textAnchor="middle" fill="#fff" fillOpacity=".17" fontSize="20" fontWeight="800" transform="rotate(90 1150 266)">END ZONE</text>
            {trails && selected && history.length > 1 && <polyline points={history.map(e => `${sx(e.x)},${sy(e.y)}`).join(' ')} fill="none" stroke="#facc15" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" opacity=".65" />}
            {frame?.entities.map(entity => {
              const x = sx(entity.x), y = sy(entity.y), active = selectedId === entity.id, color = teamColor(entity)
              const radians = (entity.direction - 90) * Math.PI / 180
              const vectorLength = Math.min(55, 12 + entity.speed * 5)
              return <g key={entity.id} onClick={() => select(entity)} className={entity.isBall ? '' : 'cursor-pointer'}>
                {vectors && !entity.isBall && entity.speed > 0 && <line x1={x} y1={y} x2={x + Math.cos(radians) * vectorLength} y2={y + Math.sin(radians) * vectorLength} stroke={color} strokeWidth="3" strokeOpacity=".7" markerEnd="url(#arrow)" />}
                {active && <circle cx={x} cy={y} r="22" fill="none" stroke="#facc15" strokeWidth="3" filter="url(#glow)" />}
                {entity.isBall ? <ellipse cx={x} cy={y} rx="8" ry="5" fill="#9a5b27" stroke="#fff" strokeWidth="1.5" transform={`rotate(${entity.orientation} ${x} ${y})`} /> : <><circle cx={x} cy={y} r="14" fill={color} stroke="#07111f" strokeWidth="3" /><text x={x} y={y + 4} textAnchor="middle" fill="#fff" fontSize="10" fontWeight="800">{entity.jersey || entity.position}</text>{labels && <text x={x} y={y - 21} textAnchor="middle" fill="#fff" fontSize="11" fontWeight="600" paintOrder="stroke" stroke="#07111f" strokeWidth="4">{entity.name.split(' ').slice(-1)[0]}</text>}</>}
              </g>
            })}
          </svg>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button className="control primary" onClick={() => { if (frameIndex >= frames.length - 1) setFrameIndex(0); setPlaying(!playing) }} disabled={!frames.length}>{playing ? 'Ⅱ' : '▶'} <span>{playing ? 'Pause' : 'Play'}</span></button>
          <button className="control" onClick={() => { setPlaying(false); setFrameIndex(0) }} disabled={!frames.length}>↺ <span>Restart</span></button>
          <select className="control select-control" value={speed} onChange={event => setSpeed(Number(event.target.value))} aria-label="Playback speed"><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={1.5}>1.5×</option><option value={2}>2×</option></select>
          <input className="min-w-36 flex-1 accent-sky-400" type="range" min="0" max={Math.max(0, frames.length - 1)} value={frameIndex} onChange={event => { setPlaying(false); setFrameIndex(Number(event.target.value)) }} disabled={!frames.length} aria-label="Tracking timeline" />
          <span className="w-16 text-right font-mono text-xs text-slate-400">{((frameIndex / 10)).toFixed(1)}s</span>
        </div>
        {frame?.event && <div className="mt-3 inline-flex items-center gap-2 rounded-lg border border-amber-300/15 bg-amber-300/5 px-3 py-1.5 text-xs text-amber-200"><span className="h-1.5 w-1.5 rounded-full bg-amber-300" /> Event: {frame.event.replace(/_/g, ' ')}</div>}
      </div>
      <aside className="border-t border-white/5 bg-slate-950/30 p-4 xl:border-l xl:border-t-0">
        <p className="eyebrow">Player focus</p>
        {selected ? <div className="mt-4">
          <div className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl text-sm font-bold text-slate-950" style={{ background: teamColor(selected) }}>{selected.jersey || selected.position}</span><div><p className="font-semibold text-white">{selected.name}</p><p className="text-xs text-slate-500">{selected.team} · {selected.position || 'Player'}</p></div></div>
          <div className="mt-5 grid grid-cols-2 gap-2"><MiniStat label="Speed" value={`${selected.speed.toFixed(1)} yd/s`} /><MiniStat label="Direction" value={`${Math.round(selected.direction)}°`} /><MiniStat label="X position" value={`${selected.x.toFixed(1)} yd`} /><MiniStat label="Y position" value={`${selected.y.toFixed(1)} yd`} /></div>
          <p className="mb-2 mt-5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">Nearest players</p>
          <div className="space-y-2">{distances.map(({ entity, distance }) => <button key={entity.id} className="flex w-full items-center justify-between rounded-lg bg-white/[.035] px-3 py-2 text-left text-xs hover:bg-white/[.07]" onClick={() => select(entity)}><span className="truncate text-slate-300">#{entity.jersey} {entity.name}</span><span className="ml-2 font-mono text-sky-300">{distance.toFixed(1)} yd</span></button>)}</div>
        </div> : <div className="mt-16 text-center text-xs leading-5 text-slate-500"><div className="mb-2 text-2xl text-slate-600">◎</div>Click any player marker to inspect speed, direction, and nearest-player distances.</div>}
      </aside>
    </div>
  </section>
}

function Toggle({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return <button onClick={onClick} className={`rounded-lg border px-2.5 py-1.5 transition ${active ? 'border-sky-400/25 bg-sky-400/10 text-sky-300' : 'border-white/5 text-slate-500 hover:text-slate-300'}`}><span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${active ? 'bg-sky-300' : 'bg-slate-600'}`} />{label}</button>
}
function MiniStat({ label, value }: { label: string; value: string }) { return <div className="rounded-lg bg-white/[.035] p-2.5"><p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-1 font-mono text-xs font-semibold text-slate-200">{value}</p></div> }
