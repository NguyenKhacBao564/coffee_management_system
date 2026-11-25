import { useEffect, useRef, useState } from 'react'
import { Activity, ChevronLeft, ChevronRight, Clock3, RefreshCw, Scale } from 'lucide-react'
import { Button } from '@/components/ui/button'

type Facility = { id: number; code: string; name: string }
type Signal = { event_id: string; agent_id: string; sequence: string; weight_kg: string; source: string; observed_at_utc: string; received_at_utc: string; is_acceptance_test: boolean; gap_before?: boolean; series_key?: string; segment_started_at_utc?: string; segment_ended_at_utc?: string; segment_sample_count?: number }
type Agent = { agent_id: string; display_name: string; scale_code: string; facility_id: number; facility_name: string; is_active: boolean; latest: Signal | null }
type Page<T> = { items: T[]; total: number; page: number; page_size: number }
type ChartView = 'auto' | 'overview' | 'raw'
type Chart = { chart_view: 'raw' | 'overview'; total_segments: number | null; items: Signal[]; total: number; returned: number; downsampled: boolean; max_points: number; gap_threshold_seconds: number }
type Summary = { timezone: string; range_sample_count: number; today_observed_sample_count: number; month_observed_sample_count: number; delayed_over_60s_sample_count: number; max_receive_delay_seconds: number | null; daily_counts_truncated: boolean; daily_observed_sample_counts: { date: string; sample_count: number }[]; observed_weighings: null; confirmed_weighings: null; needs_review_weighings: null; weighing_status: string; weight_totals: null }
type ScaleAgentState = { agent_id: string; received_at_utc: string | null; state: string; reader_status: string | null; signal_delivery_state: 'paused' | 'pending' | 'no_pending' | 'unknown'; pending_signal_count: number | null }
type Snapshot = { key: string; latest: Signal | null; history: Page<Signal>; agentState: ScaleAgentState | null; checkedAt: Date }
type ChartSnapshot = { key: string; chart: Chart; summary: Summary; range: { from: string; to: string }; checkedAt: Date }
type RangePreset = '1h' | '24h' | '7d' | 'month' | 'all' | 'custom'
type ZoomBookmark = { range: { from: string; to: string }; preset: RangePreset; view: ChartView }
const apiRoot = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const base = `${apiRoot}/scale-monitoring`
const time = (value: string | Date) => new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(value))
const weight = (value: number | string) => {
  const n = Number(value)
  return Math.abs(n) >= 1000 ? `${(n / 1000).toLocaleString('vi-VN', { maximumFractionDigits: 3 })} t` : `${n.toLocaleString('vi-VN', { maximumFractionDigits: 3 })} kg`
}
const delayLabel = (seconds: number | null) => {
  if (seconds === null) return '—'
  const value = Math.max(0, Math.round(seconds))
  if (value < 60) return `${value} giây`
  if (value < 3600) return `${Math.floor(value / 60)} phút ${value % 60} giây`
  return `${Math.floor(value / 3600)} giờ ${Math.floor((value % 3600) / 60)} phút`
}
const localInput = (date: Date) => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(date)
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]))
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`
}
const rangeQuery = (range: { from: string; to: string }) => {
  const query = new URLSearchParams()
  if (range.from) query.set('observed_from', new Date(`${range.from}+07:00`).toISOString())
  if (range.to) query.set('observed_to', new Date(`${range.to}+07:00`).toISOString())
  return query
}

class ReadError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}
async function read<T>(path: string, signal: AbortSignal, root = base): Promise<T> {
  const response = await fetch(`${root}${path}`, { signal, credentials: 'same-origin', cache: 'no-store' })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event('nhu-tung-session-expired'))
    throw new ReadError(response.status, typeof data?.detail === 'string' ? data.detail : 'Không tải được dữ liệu cân. Hãy thử lại.')
  }
  return data as T
}

function elapsed(timestamp: string, now: number): string {
  const seconds = Math.floor((now - Date.parse(timestamp)) / 1000)
  if (seconds < 0) return 'Thời gian quan sát nằm sau giờ hiện tại của trình duyệt'
  if (seconds < 60) return `${seconds} giây từ mẫu quan sát`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} phút ${seconds % 60} giây từ mẫu quan sát`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ ${Math.floor((seconds % 3600) / 60)} phút từ mẫu quan sát`
  return `${Math.floor(seconds / 86400)} ngày ${Math.floor((seconds % 86400) / 3600)} giờ từ mẫu quan sát`
}

function presetRange(preset: RangePreset): { from: string; to: string } {
  const to = new Date(), from = new Date(to)
  if (preset === 'all') return { from: '', to: '' }
  if (preset === '1h') from.setTime(to.getTime() - 3_600_000)
  if (preset === '24h') from.setTime(to.getTime() - 86_400_000)
  if (preset === '7d') from.setTime(to.getTime() - 7 * 86_400_000)
  if (preset === 'month') return { from: `${localInput(to).slice(0, 7)}-01T00:00:00`, to: localInput(to) }
  return { from: localInput(from), to: localInput(to) }
}

function WeightChart({ chart, range, onZoom }: { chart: Chart; range: { from: string; to: string }; onZoom: (from: number, to: number, detail?: boolean) => void }) {
  const dragStart = useRef<number | null>(null)
  const [selection, setSelection] = useState<[number, number] | null>(null)
  const [hovered, setHover] = useState<Signal | null>(null)
  // Hooks must also run for an empty series, which can become nonempty on polling.
  const sorted = chart.items
  const overview = chart.chart_view === 'overview'
  const hover = sorted.find(s => s.event_id === hovered?.event_id) ?? null
  if (!sorted.length) return <div className="scale-empty">Chưa có điểm ghi nhận trong khoảng thời gian này.</div>
  const stamps = sorted.map(s => Date.parse(s.observed_at_utc)), weights = sorted.map(s => Number(s.weight_kg))
  const minTime = range.from ? new Date(`${range.from}+07:00`).getTime() : Math.min(...stamps)
  const maxTime = range.to ? new Date(`${range.to}+07:00`).getTime() : Math.max(...stamps)
  const plot = { left: 96, right: 930, top: 20, bottom: 232 }
  const minWeight = Math.min(...weights), maxWeight = Math.max(...weights)
  const padding = Math.max(100, (maxWeight - minWeight) * 0.08)
  const roughStep = Math.max(1, (maxWeight - minWeight + 2 * padding) / 5)
  const magnitude = 10 ** Math.floor(Math.log10(roughStep))
  const step = ([1, 2, 5, 10].find(n => n * magnitude >= roughStep) ?? 10) * magnitude
  const low = Math.max(0, Math.floor((minWeight - padding) / step) * step)
  const high = Math.max(low + step, Math.ceil((maxWeight + padding) / step) * step)
  const ticks = Array.from({ length: Math.round((high - low) / step) + 1 }, (_, i) => low + i * step)
  const unit = high >= 1000 ? 'tấn' : 'kg', divisor = high >= 1000 ? 1000 : 1
  const x = (stamp: number) => maxTime === minTime ? (plot.left + plot.right) / 2 : plot.left + (stamp - minTime) / (maxTime - minTime) * (plot.right - plot.left)
  const y = (value: number) => plot.bottom - (value - low) / (high - low) * (plot.bottom - plot.top)
  const indexById = new Map(sorted.map((s, i) => [s.event_id, i]))
  const pointX = (s: Signal) => overview ? sorted.length === 1 ? (plot.left + plot.right) / 2 : plot.left + (indexById.get(s.event_id) ?? 0) / (sorted.length - 1) * (plot.right - plot.left) : x(Date.parse(s.observed_at_utc))
  const grouped = new Map<string, Signal[]>()
  for (const s of sorted) {
    const key = overview ? s.agent_id : s.series_key ?? s.agent_id
    const segment = grouped.get(key) ?? []
    segment.push(s); grouped.set(key, segment)
  }
  const pointAt = (event: { clientX: number; clientY: number; currentTarget: SVGSVGElement }) => {
    const rect = event.currentTarget.getBoundingClientRect()
    return { x: Math.max(plot.left, Math.min(plot.right, (event.clientX - rect.left) / rect.width * 960)), y: (event.clientY - rect.top) / rect.height * 300 }
  }
  const stampAt = (px: number) => minTime + (px - plot.left) / (plot.right - plot.left) * (maxTime - minTime)
  const nearest = (point: { x: number; y: number }) => {
    let closest: Signal | null = null, distance = Infinity
    for (const s of sorted) {
      const dx = pointX(s) - point.x, dy = y(Number(s.weight_kg)) - point.y
      const score = dx * dx + dy * dy * 0.15
      if (Math.abs(dx) <= 20 && score < distance) { closest = s; distance = score }
    }
    return closest
  }
  const last = sorted[sorted.length - 1]
  const lastSegment = overview ? [last] : grouped.get(last.series_key ?? last.agent_id) ?? []
  const openSegment = (s: Signal) => onZoom(Date.parse(s.segment_started_at_utc ?? s.observed_at_utc) - 30_000, Date.parse(s.segment_ended_at_utc ?? s.observed_at_utc) + 30_000, true)
  const axisPoints = overview ? Array.from(new Set(Array.from({ length: 5 }, (_, i) => Math.round((sorted.length - 1) * i / 4)))).map(index => ({ stamp: Date.parse(sorted[index].observed_at_utc), px: pointX(sorted[index]) })) : Array.from({ length: 5 }, (_, i) => ({ stamp: minTime + (maxTime - minTime) * i / 4, px: x(minTime + (maxTime - minTime) * i / 4) }))
  const axisTime = (stamp: number) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', ...(maxTime - minTime < 3_600_000 ? { second: '2-digit' } : {}) }).format(stamp)
  const axisDate = (stamp: number) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit' }).format(stamp)
  return <div className="scale-chart">
    <div className="scale-chart-tools"><button type="button" onClick={() => {
      if (overview) openSegment(last)
      else { const stamps = lastSegment.map(s => Date.parse(s.observed_at_utc)); onZoom(Math.min(...stamps) - 30_000, Math.max(...stamps) + 30_000, true) }
    }}>Xem rõ đoạn tín hiệu cuối</button><span>{overview ? 'Nhấp đúp một điểm để mở tín hiệu gốc của đoạn đó.' : 'Kéo ngang để chọn và phóng to một khoảng trên trục thời gian.'}</span></div>
    <div className="scale-plot-scroll"><svg viewBox="0 0 960 300" style={overview ? { minWidth: Math.max(720, sorted.length * 14) } : undefined} role="img" aria-label={overview ? `${chart.returned} điểm đại diện theo thứ tự đoạn tín hiệu từ ${chart.total} mẫu gốc` : `Đường trọng lượng theo toàn khoảng lọc, ${chart.returned} trong ${chart.total} mẫu${chart.downsampled ? ', đã giảm mẫu' : ''}`}
      onDoubleClick={event => { const s = nearest(pointAt(event)); if (overview && s) openSegment(s) }}
      onPointerDown={event => { dragStart.current = pointAt(event).x; setSelection([dragStart.current, dragStart.current]); event.currentTarget.setPointerCapture(event.pointerId) }}
      onPointerMove={event => {
        const point = pointAt(event)
        if (dragStart.current !== null) { setSelection([dragStart.current, point.x]); return }
        setHover(nearest(point))
      }}
      onPointerLeave={() => { if (dragStart.current === null) setHover(null) }}
      onPointerCancel={() => { dragStart.current = null; setSelection(null) }}
      onPointerUp={event => {
        if (dragStart.current !== null) {
          const end = pointAt(event).x, start = dragStart.current
          dragStart.current = null; setSelection(null)
          if (Math.abs(end - start) >= 8 && Math.abs(stampAt(end) - stampAt(start)) >= 1000) {
            setHover(null)
            if (overview) {
              const a = Math.max(0, Math.floor((Math.min(start, end) - plot.left) / (plot.right - plot.left) * (sorted.length - 1)))
              const b = Math.min(sorted.length - 1, Math.ceil((Math.max(start, end) - plot.left) / (plot.right - plot.left) * (sorted.length - 1)))
              onZoom(Date.parse(sorted[a].segment_started_at_utc ?? sorted[a].observed_at_utc) - 30_000, Date.parse(sorted[b].segment_ended_at_utc ?? sorted[b].observed_at_utc) + 30_000, a === b)
            } else onZoom(stampAt(Math.min(start, end)), stampAt(Math.max(start, end)))
          } else setHover(nearest(pointAt(event)))
        }
      }}>
      <text x={plot.left} y="12">Trọng lượng ({unit})</text>
      {ticks.map(value => <g key={value}><line x1={plot.left} x2={plot.right} y1={y(value)} y2={y(value)} stroke="#e3ebe6" strokeDasharray="4 4" /><text x={plot.left - 14} y={y(value) + 4} textAnchor="end">{(value / divisor).toLocaleString('vi-VN', { maximumFractionDigits: 3 })}</text></g>)}
      {axisPoints.map(({ stamp, px }, i) => <g key={i}><line x1={px} x2={px} y1={plot.top} y2={plot.bottom} stroke="#edf2ee" /><text x={px} y="254" textAnchor={i === 0 ? 'start' : i === axisPoints.length - 1 ? 'end' : 'middle'}>{axisTime(stamp)}</text><text x={px} y="272" textAnchor={i === 0 ? 'start' : i === axisPoints.length - 1 ? 'end' : 'middle'}>{axisDate(stamp)}</text></g>)}
      {[...grouped.values()].map((segment, i) => segment.length === 1
        ? <circle key={`isolated-${i}`} cx={pointX(segment[0])} cy={y(Number(segment[0].weight_kg))} r="2.5" fill={segment[0].is_acceptance_test ? '#b07824' : '#32805a'} />
        : <polyline key={`segment-${i}`} points={segment.map(s => `${pointX(s)},${y(Number(s.weight_kg))}`).join(' ')} fill="none" stroke="#32805a" strokeWidth="1.5" strokeDasharray={overview ? '5 3' : undefined} strokeLinejoin="miter" strokeLinecap="butt" />)}
      {overview && sorted.map(s => <circle key={s.event_id} cx={pointX(s)} cy={y(Number(s.weight_kg))} r="3" fill={s.is_acceptance_test ? '#b07824' : '#32805a'} />)}
      {hover && <g><line x1={pointX(hover)} x2={pointX(hover)} y1={plot.top} y2={plot.bottom} stroke="#92ac9e" strokeDasharray="3 3" /><circle cx={pointX(hover)} cy={y(Number(hover.weight_kg))} r="4" fill={hover.is_acceptance_test ? '#b07824' : '#32805a'} stroke="white" strokeWidth="1.5" /></g>}
      {selection && <rect x={Math.min(...selection)} y={plot.top} width={Math.abs(selection[1] - selection[0])} height={plot.bottom - plot.top} fill="#32805a" opacity="0.12" />}
    </svg></div>
    <div className={`scale-chart-tooltip ${hover ? 'active' : ''}`} role="status">{hover ? <><strong>{weight(hover.weight_kg)}</strong><span>PC quan sát {time(hover.observed_at_utc)} · Server nhận {time(hover.received_at_utc)}</span><span>Trễ {delayLabel((Date.parse(hover.received_at_utc) - Date.parse(hover.observed_at_utc)) / 1000)} · #{hover.sequence}{overview && ` · ${hover.segment_sample_count?.toLocaleString('vi-VN')} mẫu trong đoạn ${time(hover.segment_started_at_utc!)} – ${time(hover.segment_ended_at_utc!)}`}{hover.is_acceptance_test ? ' · Kiểm thử S03a' : ''}</span></> : <span>Rê chuột hoặc chạm vào đường để xem mẫu; kéo ngang để chọn khoảng phóng to.</span>}</div>
    {overview ? <p className="scale-muted">{chart.total_segments?.toLocaleString('vi-VN')} đoạn có tín hiệu · {chart.total.toLocaleString('vi-VN')} mẫu gốc. Mỗi điểm là mẫu thật có trọng lượng xuất hiện nhiều nhất trong đoạn; chưa phải số cân đã chốt. Các điểm cách đều theo thứ tự; khoảng cách ngang không thể hiện thời lượng. Đường nối giúp so sánh điểm, không thể hiện trọng lượng giữa các đoạn.{chart.downsampled && ` Đã giảm ${chart.total_segments?.toLocaleString('vi-VN')} → ${chart.returned.toLocaleString('vi-VN')} điểm đại diện do giới hạn.`}</p> : <p className="scale-muted">{chart.downsampled ? `Đã giảm mẫu ${chart.total.toLocaleString('vi-VN')} → ${chart.returned.toLocaleString('vi-VN')} điểm, giữ đầu/cuối và cực trị từng khoảng thời gian.` : `${chart.total.toLocaleString('vi-VN')} mẫu trong toàn khoảng lọc.`} Đường thẳng; ngắt khi chuỗi gốc thiếu mẫu trên {chart.gap_threshold_seconds} giây. Khoảng trống không được điền thành 0. Chọn bộ lọc nhanh để trở về khoảng rộng hơn.</p>}
  </div>
}

export default function ScaleMonitoring({ facilities, initialFacilityId }: { facilities: Facility[]; initialFacilityId: number | null }) {
  const [facilityId, setFacilityId] = useState(String(initialFacilityId ?? facilities[0]?.id ?? ''))
  const [agentId, setAgentId] = useState(''), [agentPage, setAgentPage] = useState(1), [page, setPage] = useState(1)
  const [preset, setPreset] = useState<RangePreset>('24h')
  const [viewPreference, setViewPreference] = useState<ChartView>('auto')
  const [zoomHistory, setZoomHistory] = useState<ZoomBookmark[]>([])
  const [draft, setDraft] = useState(() => presetRange('24h')), [range, setRange] = useState(() => presetRange('24h'))
  const [filterError, setFilterError] = useState(''), [failure, setFailure] = useState<{ key: string; message: string } | null>(null), [busy, setBusy] = useState(false)
  const [chartFailure, setChartFailure] = useState<{ key: string; message: string } | null>(null)
  const [catalog, setCatalog] = useState<{ key: string; page: Page<Agent> } | null>(null), [snapshot, setSnapshot] = useState<Snapshot | null>(null), [chartSnapshot, setChartSnapshot] = useState<ChartSnapshot | null>(null)
  const [refresh, setRefresh] = useState(0), [now, setNow] = useState(Date.now()), [visible, setVisible] = useState(!document.hidden)
  const catalogKey = `${facilityId}:${agentPage}`
  const rangeKey = preset === 'custom' ? `custom:${range.from}:${range.to}` : preset
  const key = `${catalogKey}:${agentId}:${page}:${rangeKey}`
  const chartKey = `${facilityId}:${agentId}:${rangeKey}:${viewPreference}`
  const error = failure?.key === key ? failure.message : ''
  const agents = catalog?.key === catalogKey ? catalog.page : null
  const data = snapshot?.key === key ? snapshot : null
  const chartData = chartSnapshot?.key === chartKey ? chartSnapshot : null
  const chartError = chartFailure?.key === chartKey ? chartFailure.message : ''
  const selected = agents?.items.find(a => a.agent_id === agentId)
  useEffect(() => { setZoomHistory([]) }, [facilityId, agentId])

  useEffect(() => {
    let alive = true, running = false
    let timer: number | undefined, deadline: number | undefined, controller: AbortController | undefined
    setSnapshot(previous => previous?.key === key ? previous : null)
    const run = async () => {
      if (!alive || running || document.hidden || !facilityId) return
      running = true; setBusy(true)
      controller = new AbortController()
      const current = controller
      let timedOut = false
      deadline = window.setTimeout(() => { timedOut = true; current.abort() }, 8000)
      try {
        const list = await read<Page<Agent>>(`/agents?facility_id=${facilityId}&page=${agentPage}&page_size=50`, current.signal)
        if (!alive || current.signal.aborted) return
        const chosen = list.items.find(a => a.agent_id === agentId) ?? list.items[0]
        if ((chosen?.agent_id ?? '') !== agentId) {
          setCatalog({ key: catalogKey, page: list }); setAgentId(chosen?.agent_id ?? ''); setPage(1)
          return
        }
        const params = new URLSearchParams({ facility_id: facilityId, agent_id: agentId })
        const effectiveRange = preset === 'custom' ? range : presetRange(preset)
        rangeQuery(effectiveRange).forEach((value, k) => params.set(k, value))
        params.set('page', String(page)); params.set('page_size', '30')
        const [history, states] = await Promise.all([
          chosen ? read<Page<Signal>>(`/signals?${params}`, current.signal) : Promise.resolve({ items: [], total: 0, page: 1, page_size: 30 }),
          read<{ items: ScaleAgentState[] }>(`/heartbeat/scale-agents?facility_id=${facilityId}`, current.signal, `${apiRoot}/vehicle-pilot`),
        ])
        if (!alive || current.signal.aborted) return
        setCatalog({ key: catalogKey, page: list })
        setSnapshot({ key, latest: chosen?.latest ?? null, history, agentState: states.items.find(s => s.agent_id === agentId) ?? null, checkedAt: new Date() }); setFailure(null)
      } catch (reason) {
        if (!alive || (current.signal.aborted && !timedOut)) return
        if (reason instanceof ReadError && [401, 403, 404].includes(reason.status)) { setSnapshot(null); setCatalog(null) }
        setFailure({ key, message: timedOut ? 'API phản hồi quá lâu. Dữ liệu chưa cập nhật.' : reason instanceof Error ? reason.message : 'Không kết nối được API.' })
      } finally {
        window.clearTimeout(deadline); running = false
        if (alive) { setBusy(false); if (!document.hidden) timer = window.setTimeout(() => void run(), 5000) }
      }
    }
    const visibility = () => {
      setVisible(!document.hidden); window.clearTimeout(timer)
      if (document.hidden) controller?.abort()
      else void run()
    }
    document.addEventListener('visibilitychange', visibility)
    void run()
    return () => { alive = false; controller?.abort(); window.clearTimeout(timer); window.clearTimeout(deadline); document.removeEventListener('visibilitychange', visibility) }
  }, [facilityId, agentId, agentPage, page, range.from, range.to, preset, refresh, key, catalogKey])

  useEffect(() => {
    let alive = true, running = false
    let timer: number | undefined, deadline: number | undefined, controller: AbortController | undefined
    setChartSnapshot(previous => previous?.key === chartKey ? previous : null)
    const run = async () => {
      if (!alive || running || document.hidden || !facilityId || !agentId) return
      running = true; controller = new AbortController()
      const current = controller; let timedOut = false
      deadline = window.setTimeout(() => { timedOut = true; current.abort() }, 8000)
      try {
        const params = new URLSearchParams({ facility_id: facilityId, agent_id: agentId })
        const effectiveRange = preset === 'custom' ? range : presetRange(preset)
        rangeQuery(effectiveRange).forEach((value, k) => params.set(k, value))
        const [chart, summary] = await Promise.all([
          read<Chart>(`/signals/chart?${params}&max_points=1200&view=${viewPreference}`, current.signal),
          read<Summary>(`/summary?${params}`, current.signal),
        ])
        if (!alive || current.signal.aborted) return
        setChartSnapshot({ key: chartKey, chart, summary, range: effectiveRange, checkedAt: new Date() }); setChartFailure(null)
        if (preset !== 'custom') setDraft(effectiveRange)
      } catch (reason) {
        if (!alive || (current.signal.aborted && !timedOut)) return
        setChartFailure({ key: chartKey, message: timedOut ? 'Đồ thị/tổng hợp phản hồi quá lâu; dữ liệu chưa cập nhật.' : reason instanceof Error ? reason.message : 'Không tải được chuỗi đồ thị.' })
      } finally {
        window.clearTimeout(deadline); running = false
        if (alive && !document.hidden) timer = window.setTimeout(() => void run(), 5000)
      }
    }
    const visibility = () => { window.clearTimeout(timer); if (document.hidden) controller?.abort(); else void run() }
    document.addEventListener('visibilitychange', visibility); void run()
    return () => { alive = false; controller?.abort(); window.clearTimeout(timer); window.clearTimeout(deadline); document.removeEventListener('visibilitychange', visibility) }
  }, [facilityId, agentId, range.from, range.to, preset, viewPreference, refresh, chartKey])

  useEffect(() => {
    if (!visible) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    setNow(Date.now())
    return () => window.clearInterval(timer)
  }, [visible])

  const latest = data?.latest
  const agentState = data?.agentState
  const contactLabel = agentState ? ({ communicating: 'PC đang liên lạc', delayed: 'PC liên lạc chậm', lost: 'PC mất liên lạc', never_received: 'Chưa có heartbeat', disabled: 'Agent đã vô hiệu hóa', legacy_snapshot: 'Heartbeat phiên bản cũ' } as Record<string, string>)[agentState.state] : 'Chưa có trạng thái PC'
  const readerLabel = agentState?.reader_status ? ({ starting: 'Đang khởi động', ok: 'Đọc được nguồn', empty: 'Nguồn đang trống', error: 'Lỗi đọc nguồn', unavailable: 'Nguồn không khả dụng' } as Record<string, string>)[agentState.reader_status] : 'Chưa có trạng thái nguồn'
  const setQuickRange = (value: RangePreset) => {
    const next = presetRange(value)
    setZoomHistory([]); setPreset(value); setRange(next); setDraft(next); setPage(1); setFilterError('')
  }
  const editRange = (field: 'from' | 'to', value: string) => {
    const current = preset === 'custom' ? draft : chartData?.range ?? draft
    if (preset !== 'custom') setRange(current)
    setPreset('custom'); setDraft({ ...current, [field]: value })
  }
  const zoomTo = (from: number, to: number, detail = false) => {
    if (to - from < 1000) return
    setZoomHistory(previous => [...previous, { range: chartData?.range ?? range, preset, view: viewPreference }].slice(-20))
    const value = { from: localInput(new Date(from)), to: localInput(new Date(to)) }
    setViewPreference(detail ? 'raw' : 'auto')
    setPreset('custom'); setDraft(value); setRange(value); setPage(1); setFilterError('')
  }
  const restoreZoom = (index: number) => {
    const saved = zoomHistory[index]
    if (!saved) return
    setRange(saved.range); setDraft(saved.range); setPreset(saved.preset); setViewPreference(saved.view)
    setZoomHistory(previous => previous.slice(0, index)); setPage(1); setFilterError('')
  }
  const zoomBounds = () => {
    if (!chartData) return null
    const items = chartData.chart.items
    const from = chartData.range.from ? new Date(`${chartData.range.from}+07:00`).getTime() : items.length ? Date.parse(items[0].segment_started_at_utc ?? items[0].observed_at_utc) - 30_000 : null
    const to = chartData.range.to ? new Date(`${chartData.range.to}+07:00`).getTime() : items.length ? Date.parse(items[items.length - 1].segment_ended_at_utc ?? items[items.length - 1].observed_at_utc) + 30_000 : null
    return from !== null && to !== null ? { from, to } : null
  }
  const zoomBy = (factor: number) => {
    const bounds = zoomBounds()
    if (!bounds) return
    const center = (bounds.from + bounds.to) / 2, half = Math.max(1000, (bounds.to - bounds.from) * factor / 2)
    zoomTo(center - half, center + half)
  }
  return <div className="page-content scale-page">
    <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-line" /> TÍN HIỆU CÂN THÔ</div><h1>Tín hiệu cân</h1><p className="page-subtitle">Xem các mẫu PC đã gửi, thời gian quan sát và thời gian server nhận.</p></div><Button variant="outline" size="sm" onClick={() => setRefresh(v => v + 1)} disabled={busy || !facilityId}><RefreshCw size={15} className={busy ? 'spin' : ''} />{error ? 'Thử lại' : 'Làm mới'}</Button></section>
    <div className="scale-note"><Activity size={18} /><p>Agent chỉ tạo mẫu khi đọc thành công <strong>≥ 1.000 kg</strong>. Không có mẫu mới không đồng nghĩa PC offline hoặc cân về 0. Mẫu ghi nhận chưa xác nhận cân ổn định hay số cân đã chốt.</p></div>
    <section className="panel scale-filters"><label>Cơ sở<select aria-label="Cơ sở theo dõi" value={facilityId} onChange={e => { setFacilityId(e.target.value); setAgentId(''); setAgentPage(1); setPage(1) }}>{!facilities.length && <option value="">Chưa được gán cơ sở</option>}{facilities.map(f => <option key={f.id} value={f.id}>{f.name} · {f.code}</option>)}</select></label><label>Cân / agent<select aria-label="Cân theo dõi" value={agentId} onChange={e => { setAgentId(e.target.value); setPage(1) }} disabled={!agents?.items.length}>{!agents?.items.length && <option value="">{busy ? 'Đang tải danh sách cân…' : error ? 'Chưa tải được danh sách cân' : 'Chưa có cân'}</option>}{agents?.items.map(a => <option key={a.agent_id} value={a.agent_id}>{a.scale_code} · {a.display_name}{!a.is_active ? ' (Đã vô hiệu hóa)' : ''}</option>)}</select></label>{agents && agents.total > 50 && <div className="scale-agent-paging"><button className="icon-button" aria-label="Danh sách cân trước" disabled={agentPage === 1} onClick={() => { setAgentPage(v => v - 1); setAgentId(''); setPage(1) }}><ChevronLeft size={16} /></button><span>Cân: trang {agentPage}/{Math.ceil(agents.total / 50)}</span><button className="icon-button" aria-label="Danh sách cân sau" disabled={agentPage * 50 >= agents.total} onClick={() => { setAgentPage(v => v + 1); setAgentId(''); setPage(1) }}><ChevronRight size={16} /></button></div>}</section>
    {error && <div className="scale-error" role="alert"><strong>Dữ liệu chưa cập nhật.</strong> {error}{data && <span> Đang giữ dữ liệu của lần tải thành công lúc {time(data.checkedAt)}.</span>}</div>}
    {!facilityId ? <div className="panel scale-empty">Chưa có cơ sở đang hoạt động được phép xem.</div> : <>
      {busy && !data && <p className="scale-muted" role="status">Đang tải dữ liệu tín hiệu…</p>}
      <section className={`scale-agent-status ${agentState?.signal_delivery_state === 'paused' ? 'paused' : ''}`} aria-label="Trạng thái PC và gửi cân">
        <div><strong>{error ? 'Trạng thái PC chưa cập nhật' : contactLabel}</strong><span>Nguồn cân: {readerLabel}</span><small>{agentState?.received_at_utc ? `Heartbeat server nhận ${time(agentState.received_at_utc)}` : 'Chưa có thời điểm server nhận heartbeat'}</small></div>
        <div><strong>{agentState?.signal_delivery_state === 'paused' ? 'PC đang tạm dừng gửi cân' : agentState?.signal_delivery_state === 'pending' ? 'PC còn mẫu cân chờ gửi' : agentState?.signal_delivery_state === 'no_pending' ? 'PC báo không có mẫu chờ gửi' : 'Chưa biết trạng thái gửi cân'}</strong><span>{agentState?.pending_signal_count != null ? `${agentState.pending_signal_count.toLocaleString('vi-VN')} mẫu chờ gửi/ACK tại PC` : 'Chưa có số mẫu chờ gửi'}</span>{agentState?.signal_delivery_state === 'paused' && <small>Cần kiểm tra sender trên PC cân. Làm mới web không giải phóng hàng đợi này.</small>}{error && <small>Đang giữ snapshot cũ; không dùng để kết luận trạng thái hiện tại.</small>}</div>
      </section>
      <section className="scale-summary">
        <div className="panel scale-reading"><div className="scale-summary-heading"><span className="section-kicker">TRỌNG LƯỢNG GHI NHẬN GẦN NHẤT</span><Scale size={19} /></div><div className="scale-weight">{latest ? weight(latest.weight_kg) : '—'}</div><div className="scale-summary-tags"><span className="scale-state">{latest ? 'Mẫu lịch sử' : busy && !data ? 'Đang tải mẫu' : error && !data ? 'Chưa tải được mẫu' : 'Chưa có mẫu'}</span>{latest?.is_acceptance_test && <span className="scale-test-tag">Kiểm thử nguồn giả S03a</span>}</div><p className="scale-muted">{selected ? `${selected.facility_name} · ${selected.scale_code}` : 'Chọn cơ sở và cân để theo dõi.'} · Giá trị mới nhất theo thời gian quan sát; không đại diện trọng lượng hiện tại khi reader trống.</p></div>
        <div className="panel scale-timing"><div className="scale-summary-heading"><span className="section-kicker">THỜI GIAN CỦA MẪU</span><Clock3 size={18} /></div><dl><div><dt>PC quan sát</dt><dd title={latest?.observed_at_utc}>{latest ? time(latest.observed_at_utc) : '—'}</dd></div><div><dt>Server nhận</dt><dd title={latest?.received_at_utc}>{latest ? time(latest.received_at_utc) : '—'}</dd></div></dl><p className="scale-age">{latest ? elapsed(latest.observed_at_utc, now) : 'Chưa có thời gian quan sát để tính khoảng cách.'}</p><p className="scale-muted">Giờ Việt Nam (Asia/Ho_Chi_Minh) · Không suy ra trạng thái kết nối PC.</p></div>
      </section>
      <section className="scale-manager-summary" aria-label="Tổng hợp quan sát cho quản lý"><div className="scale-manager-heading"><div><span className="section-kicker">TỔNG HỢP TỪ DỮ LIỆU THẬT</span><h2>Đối chiếu theo thời gian quan sát</h2></div><span className="scale-muted">Không cộng trọng lượng các mẫu</span></div>{chartData ? <><div className="scale-manager-cards"><div><strong>{chartData.summary.today_observed_sample_count.toLocaleString('vi-VN')}</strong><span>Mẫu tín hiệu hôm nay</span></div><div><strong>{chartData.summary.month_observed_sample_count.toLocaleString('vi-VN')}</strong><span>Mẫu tín hiệu tháng này</span></div><div><strong>{chartData.summary.delayed_over_60s_sample_count.toLocaleString('vi-VN')}</strong><span>Mẫu nhận trễ hơn 1 phút trong khoảng · trễ lớn nhất {delayLabel(chartData.summary.max_receive_delay_seconds)}</span></div><div><strong>Chưa đủ dữ liệu</strong><span>Lượt cân quan sát</span></div><div><strong>Chưa có workflow</strong><span>Đã xác nhận / cần xem lại</span></div></div><p className="scale-muted">Ngày và tháng theo Asia/Ho_Chi_Minh, đếm theo thời điểm PC quan sát. Chưa có lớp lượt cân quan sát; số mẫu không thay thế số lượt xe/cân và không tạo tổng khối lượng nhập/xuất.</p>{chartData.summary.daily_observed_sample_counts.length > 0 && <p className="scale-muted">Theo ngày trong khoảng lọc{chartData.summary.daily_counts_truncated ? ' (chỉ hiện 366 ngày đầu)' : ''}: {chartData.summary.daily_observed_sample_counts.map(d => `${d.date}: ${d.sample_count} mẫu`).join(' · ')}</p>}</> : <p className="scale-muted">{chartError || 'Đang tải số liệu tổng hợp…'}</p>}</section>
      <section className="panel scale-history"><div className="panel-heading"><div><span className="section-kicker">LỊCH SỬ QUAN SÁT</span><h2>Mẫu tín hiệu đã lưu</h2></div><span className="scale-muted">{data ? `${data.history.total.toLocaleString('vi-VN')} mẫu trong bộ lọc` : '—'}</span></div>
        <div className="scale-presets" aria-label="Khoảng thời gian nhanh">{[['1h','1 giờ'],['24h','24 giờ'],['7d','7 ngày'],['month','Tháng này'],['all','Mọi thời gian']].map(([key,label]) => <button type="button" key={key} aria-pressed={preset === key} onClick={() => setQuickRange(key as RangePreset)}>{label}</button>)}</div>
        <form className="scale-range" onSubmit={e => { e.preventDefault(); if (draft.from && draft.to && draft.from > draft.to) { setFilterError('Thời gian bắt đầu phải trước hoặc bằng thời gian kết thúc.'); return } setFilterError(''); setZoomHistory([]); setPreset('custom'); setRange(draft); setPage(1) }}><label>Từ (giờ Việt Nam)<input type="datetime-local" step="1" aria-label="Quan sát từ" value={draft.from} onChange={e => editRange('from', e.target.value)} /></label><label>Đến (giờ Việt Nam)<input type="datetime-local" step="1" aria-label="Quan sát đến" value={draft.to} onChange={e => editRange('to', e.target.value)} /></label><Button type="submit" variant="outline" size="sm">Áp dụng</Button></form>
        <p className="scale-range-mode">{preset === 'custom' ? 'Khoảng lịch sử cố định. Chọn 1 giờ/24 giờ/7 ngày/tháng này để cập nhật tới hiện tại.' : 'Bộ lọc đang theo thời điểm hiện tại và tự cập nhật khi có mẫu mới.'}</p>
        {filterError && <p className="scale-error" role="alert">{filterError}</p>}
        {chartError && <p className="scale-error" role="alert">Biểu đồ chưa cập nhật. {chartError}{chartData && ` Đang giữ lần tải lúc ${time(chartData.checkedAt)}.`}</p>}
        <div className="scale-view-controls" aria-label="Chế độ và phóng to biểu đồ">
          <div>{([['auto','Tự động'],['overview','Điểm đại diện'],['raw','Tín hiệu gốc']] as const).map(([value,label]) => <button type="button" key={value} aria-pressed={viewPreference === value} onClick={() => setViewPreference(value)}>{label}</button>)}</div>
          <div><button type="button" onClick={() => zoomBy(0.5)} disabled={!zoomBounds()} aria-label="Phóng to biểu đồ">＋ Phóng to</button><button type="button" onClick={() => zoomBy(2)} disabled={!zoomBounds()} aria-label="Thu nhỏ biểu đồ">− Thu nhỏ</button><button type="button" onClick={() => restoreZoom(zoomHistory.length - 1)} disabled={!zoomHistory.length}>Quay lại khoảng trước</button><button type="button" onClick={() => restoreZoom(0)} disabled={!zoomHistory.length}>Đặt lại zoom</button></div>
        </div>
        {chartData ? <WeightChart key={chartKey} chart={chartData.chart} range={chartData.range} onZoom={zoomTo} /> : <div className="scale-empty">{chartError || 'Đang tải chuỗi đồ thị…'}</div>}
        <div className="scale-table-wrap"><table className="scale-table"><thead><tr><th>Trọng lượng</th><th>PC quan sát</th><th>Server nhận</th><th>Chi tiết</th></tr></thead><tbody>{data?.history.items.map(s => <tr key={s.event_id}><td className="scale-table-weight">{weight(s.weight_kg)}{s.is_acceptance_test && <span className="scale-test-tag">Kiểm thử S03a</span>}</td><td title={s.observed_at_utc}>{time(s.observed_at_utc)}</td><td title={s.received_at_utc}>{time(s.received_at_utc)}</td><td><details><summary>Metadata</summary><small>Sequence #{s.sequence} · {s.source}</small><small className="scale-event-id">Event ID: {s.event_id}</small></details></td></tr>)}</tbody></table></div>
        {data && !data.history.items.length && <div className="scale-empty">{selected ? 'Chưa có mẫu trong khoảng thời gian đã chọn.' : 'Chưa có agent tại cơ sở này.'}</div>}
        <div className="table-footer"><span>{data ? `${data.history.items.length} mẫu trên trang · mới nhất theo thời gian quan sát trước` : 'Chưa tải lịch sử'}</span><div className="pagination"><button className="icon-button" aria-label="Lịch sử trước" disabled={page <= 1 || busy} onClick={() => setPage(v => v - 1)}><ChevronLeft size={16} /></button><span>Trang {page}/{Math.max(1, Math.ceil((data?.history.total ?? 0) / 30))}</span><button className="icon-button" aria-label="Lịch sử sau" disabled={busy || !data || page * 30 >= data.history.total} onClick={() => setPage(v => v + 1)}><ChevronRight size={16} /></button></div></div>
      </section>
      <p className="scale-poll-note">{!visible ? 'Tạm dừng cập nhật khi tab ẩn.' : 'Tự cập nhật sau khoảng 5 giây giữa các lượt tải.'}{data && ` Lần tải thành công: ${time(data.checkedAt)}.`} {error && 'Dữ liệu chưa cập nhật.'}</p>
    </>}
  </div>
}
