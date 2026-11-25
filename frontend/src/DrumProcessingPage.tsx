import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  Award,
  CheckCircle2,
  Clock,
  Droplets,
  Eye,
  Flame,
  Gauge,
  History,
  Info,
  Layers,
  Lightbulb,
  Plus,
  RefreshCw,
  Scale,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Thermometer,
  Timer,
  TrendingUp,
  Wind,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import './DrumProcessingPage.css'
import DrumRunRecords from './DrumRunRecords'

type UserProfile = {
  id: number
  username: string
  display_name: string
  role: 'admin' | 'manager' | 'staff' | 'drum_operator'
  facilities: { id: number; code: string; name: string }[]
  active_facility: { id: number; code: string; name: string } | null
}

type Drum = {
  id: number
  facility_id: number
  drum_code: string
  drum_name: string
  capacity_kg: string | number | null
  measurement_mode: 'center_only' | 'two_ends' | 'three_points'
  has_moisture_imbalance: boolean
  has_blade_issue: boolean
  characteristics_notes: string | null
  status: 'idle' | 'running' | 'maintenance'
  is_active: boolean
  active_run_id: number | null
  active_batch_code: string | null
}

type PeriodicLog = {
  id: number
  run_id: number
  operator_id: number | null
  operator_name: string
  sequence: number
  moisture_percent: string | number
  moisture_head_percent: string | number | null
  moisture_center_percent: string | number | null
  moisture_tail_percent: string | number | null
  moisture_diff_ends: string | number | null
  temperature_celsius: string | number
  temperature_location: string | null
  measured_at: string
  recorded_at: string
  scheduled_time: string | null
  delay_seconds: number | null
  compliance_status: 'on_time' | 'late' | 'anomalous'
  note: string | null
}

type Inspection = {
  id: number
  run_id: number
  inspector_name: string
  inspected_at: string
  recorded_at: string
  sample_moisture_percent: string | number
  sample_moisture_head_percent: string | number | null
  sample_moisture_center_percent: string | number | null
  sample_moisture_tail_percent: string | number | null
  sample_temperature_celsius: string | number
  nearest_log_id: number | null
  moisture_diff: string | number | null
  temperature_diff: string | number | null
  evaluation: 'passed' | 'warning' | 'failed'
  notes: string | null
}

type Adherence = {
  total_logs: number
  on_time_count: number
  late_count: number
  max_delay_seconds: number
  compliance_rate_percent: number
}

type CoffeeCategory = 'ca_qua' | 'ca_lua' | 'ca_tron' | 'khac'

type SourceBedBatchInfo = {
  batch_id: number
  batch_code: string
  bed_number: number
  bed_code: string
  entered_at: string
  water_drained_status: string
  raw_material_status: string
  estimated_spoiled_percent: string | number | null
  discharged_at: string | null
  discharge_drain_status: string | null
  dry_status: string | null
  discharge_note: string | null
  total_bed_duration_minutes: number | null
  stirring_count: number
}

type StaticDryingBed = {
  id: number
  facility_id: number
  bed_number: number
  bed_code: string
  bed_name: string
  location_type: string
  capacity_kg: string | number | null
  is_active: boolean
  created_at: string
  active_batch_id: number | null
  active_batch_code: string | null
  active_batch_status: string | null
}

type StaticBedStirring = {
  id: number
  batch_id: number
  stirring_number: number
  started_at: string
  ended_at: string | null
  duration_minutes: number | null
  stirring_method: string | null
  note: string | null
  operator_name: string
  recorded_at: string
}

type StaticBedBatchItem = {
  id: number
  facility_id: number
  bed_id: number
  bed_number: number
  bed_code: string
  bed_name: string
  batch_code: string
  coffee_type: string | null
  input_weight_kg: string | number | null
  entered_at: string
  water_drained_status: 'drained' | 'wet' | string
  raw_material_status: 'fresh' | 'spoiled' | string
  estimated_spoiled_percent: string | number | null
  status: 'on_bed' | 'discharged' | 'cancelled' | string
  discharged_at: string | null
  discharge_drain_status: 'even' | 'uneven' | string | null
  dry_status: 'not_dry' | 'dry' | string | null
  discharge_note: string | null
  total_bed_duration_minutes: number | null
  operator_name: string
  stirring_count: number
  created_at: string
}

type StaticBedBatchDetail = {
  id: number
  facility_id: number
  bed_id: number
  bed_number: number
  bed_code: string
  bed_name: string
  batch_code: string
  coffee_type: string | null
  input_weight_kg: string | number | null
  entered_at: string
  water_drained_status: string
  raw_material_status: string
  estimated_spoiled_percent: string | number | null
  status: string
  discharged_at: string | null
  discharge_drain_status: string | null
  dry_status: string | null
  discharge_note: string | null
  total_bed_duration_minutes: number | null
  operator_name: string
  stirrings: StaticBedStirring[]
  created_at: string
  updated_at: string
}

type DrumRunDetail = {
  id: number
  facility_id: number
  drum_id: number
  drum_code: string
  drum_name: string
  drum_measurement_mode: 'center_only' | 'two_ends' | 'three_points'
  drum_has_moisture_imbalance: boolean
  drum_has_blade_issue: boolean
  drum_characteristics_notes: string | null
  batch_code: string
  coffee_type: string | null
  initial_weight_kg: string | number | null
  initial_temperature_celsius: string | number | null
  initial_temperature_location: string | null
  blend_ratio_qua_percent: string | number | null
  blend_ratio_lua_percent: string | number | null
  cycle_minutes: number
  entry_time: string
  heat_off_at: string | null
  rotation_off_at: string | null
  moisture_at_heat_off: string | number | null
  incubation_minutes: number | null
  exit_time: string | null
  operator_name: string
  status: 'in_progress' | 'completed' | 'cancelled'
  quality_assessment: 'ca_dep' | 'dat_chuan' | 'ca_xau' | null
  quality_note: string | null
  final_moisture_percent: string | number | null
  final_moisture_head_percent: string | number | null
  final_moisture_tail_percent: string | number | null
  final_discharged_at: string | null
  discharge_note: string | null
  source_type: 'indoor' | 'outdoor' | null
  source_bed_id: number | null
  source_bed_number: number | null
  source_bed_batch_id: number | null
  source_bed_batch: SourceBedBatchInfo | null
  logs: PeriodicLog[]
  inspections: Inspection[]
  adherence: Adherence
}

type DrumKPI = {
  facility_id: number
  total_runs: number
  in_progress_runs: number
  completed_runs: number
  total_logs: number
  on_time_logs: number
  late_logs: number
  compliance_rate_percent: number
  total_inspections: number
  passed_inspections: number
  warning_inspections: number
  failed_inspections: number
}

type DrumRecommendedStrategy = {
  recommended_heat_temp_celsius: string | number | null
  recommended_stop_heat_moisture: string | number | null
  recommended_incubation_minutes: number | null
  expected_incubation_moisture_drop: string | number | null
  expected_final_moisture: string | number | null
  sample_size_ca_dep: number
  strategy_summary: string
}

type DrumRunItem = {
  id: number
  facility_id: number
  drum_id: number
  drum_code: string
  drum_name: string
  measurement_mode: 'center_only' | 'two_ends' | 'three_points'
  has_moisture_imbalance: boolean
  has_blade_issue: boolean
  batch_code: string
  coffee_type: string | null
  initial_weight_kg: string | number | null
  initial_temperature_celsius: string | number | null
  blend_ratio_qua_percent: string | number | null
  blend_ratio_lua_percent: string | number | null
  cycle_minutes: number
  entry_time: string
  heat_off_at: string | null
  incubation_minutes: number | null
  exit_time: string | null
  operator_name: string
  status: 'in_progress' | 'completed' | 'cancelled'
  log_count: number
  latest_moisture_percent: string | number | null
  latest_temperature_celsius: string | number | null
  moisture_at_heat_off: string | number | null
  final_moisture_percent: string | number | null
  final_moisture_head_percent: string | number | null
  final_moisture_tail_percent: string | number | null
  quality_assessment: 'ca_dep' | 'dat_chuan' | 'ca_xau' | null
  quality_note: string | null
  inspection_count: number
  source_type: 'indoor' | 'outdoor' | null
  source_bed_id: number | null
  source_bed_number: number | null
  source_bed_batch_id: number | null
  source_bed_batch: SourceBedBatchInfo | null
  created_at: string
}

type DrumRunSummaryItem = {
  id: number
  batch_code: string
  coffee_type: string | null
  initial_temperature_celsius: string | number | null
  blend_ratio_qua_percent: string | number | null
  blend_ratio_lua_percent: string | number | null
  entry_time: string
  heat_off_at: string | null
  exit_time: string | null
  heat_duration_minutes: number | null
  incubation_minutes: number | null
  moisture_at_heat_off: string | number | null
  final_moisture_percent: string | number | null
  final_moisture_head_percent: string | number | null
  final_moisture_tail_percent: string | number | null
  moisture_drop_in_incubation: string | number | null
  avg_temperature_celsius: string | number | null
  quality_assessment: 'ca_dep' | 'dat_chuan' | 'ca_xau' | null
  quality_note: string | null
  operator_name: string
  source_type: string | null
  source_bed_number: number | null
  source_bed_batch_code: string | null
  raw_material_status: string | null
  estimated_spoiled_percent: string | number | null
  discharge_drain_status: string | null
}

type DrumAnalytics = {
  drum_id: number
  drum_code: string
  drum_name: string
  capacity_kg: string | number | null
  total_runs: number
  ca_dep_count: number
  dat_chuan_count: number
  ca_xau_count: number
  ca_dep_rate_percent: number
  strategy: DrumRecommendedStrategy
  history: DrumRunSummaryItem[]
}

const api = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '') + '/drum-processing'

async function call<T>(path: string, csrf: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`${api}${path}`, {
    method,
    credentials: 'same-origin',
    headers: {
      ...(!['GET', 'HEAD', 'OPTIONS'].includes(method) ? { 'X-CSRF-Token': csrf } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Không thể hoàn tất yêu cầu.')
  }
  return data as T
}

const dt = (val: string) =>
  new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(new Date(val))

const localNowInput = () => {
  const d = new Date(Date.now() + 7 * 3600 * 1000)
  return d.toISOString().slice(0, 16)
}

function renderQualityBadge(q: string | null | undefined) {
  if (q === 'ca_dep') {
    return <span className="dp-quality-badge dp-quality-ca_dep"><Award size={13} /> Cà đẹp</span>
  }
  if (q === 'dat_chuan') {
    return <span className="dp-quality-badge dp-quality-dat_chuan"><CheckCircle2 size={13} /> Đạt chuẩn</span>
  }
  if (q === 'ca_xau') {
    return <span className="dp-quality-badge dp-quality-ca_xau">Cà xấu</span>
  }
  return <span style={{ color: '#94a3b8' }}>—</span>
}

export default function DrumProcessingPage({
  user,
  csrf,
}: {
  user: UserProfile
  csrf: string
}) {
  const [drums, setDrums] = useState<Drum[]>([])
  const [_kpi, setKpi] = useState<DrumKPI | null>(null)
  void _kpi
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [runDetail, setRunDetail] = useState<DrumRunDetail | null>(null)
  const [detailTab, setDetailTab] = useState<'logs' | 'inspections'>('logs')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  // Modals
  const [startRunDrum, setStartRunDrum] = useState<Drum | null>(null)
  const [logModalRun, setLogModalRun] = useState<DrumRunDetail | null>(null)
  const [stopHeatModalRun, setStopHeatModalRun] = useState<DrumRunDetail | null>(null)
  const [dischargeModalRun, setDischargeModalRun] = useState<DrumRunDetail | null>(null)
  const [inspectModalRun, setInspectModalRun] = useState<DrumRunDetail | null>(null)
  const [createDrumModal, setCreateDrumModal] = useState(false)
  const [editDrumModal, setEditDrumModal] = useState<Drum | null>(null)

  // Create Drum State
  const [createMeasurementMode, setCreateMeasurementMode] = useState<'center_only' | 'two_ends'>('center_only')
  const [createHasMoistureImbalance, setCreateHasMoistureImbalance] = useState(false)
  const [createHasBladeIssue, setCreateHasBladeIssue] = useState(false)
  const [createCharacteristicsNotes, setCreateCharacteristicsNotes] = useState('')

  // Edit Drum State
  const [editMeasurementMode, setEditMeasurementMode] = useState<'center_only' | 'two_ends'>('center_only')
  const [editHasMoistureImbalance, setEditHasMoistureImbalance] = useState(false)
  const [editHasBladeIssue, setEditHasBladeIssue] = useState(false)
  const [editCharacteristicsNotes, setEditCharacteristicsNotes] = useState('')

  // Periodic Log Measurement Inputs (Live Calculation)
  const [logHeadMoisture, setLogHeadMoisture] = useState('')
  const [logTailMoisture, setLogTailMoisture] = useState('')

  // Discharge Measurement Inputs
  const [dischargeHeadMoisture, setDischargeHeadMoisture] = useState('')
  const [dischargeTailMoisture, setDischargeTailMoisture] = useState('')

  // Start Run Modal State
  const [coffeeCategory, setCoffeeCategory] = useState<CoffeeCategory>('ca_qua')
  const [ratioQua, setRatioQua] = useState<number>(50)
  const [ratioLua, setRatioLua] = useState<number>(50)
  const [customCoffeeType, setCustomCoffeeType] = useState<string>('')
  const [initialTemp, setInitialTemp] = useState<string>('75.0')

  const handleRatioQuaChange = (val: number) => {
    const clamped = Math.min(100, Math.max(0, isNaN(val) ? 0 : val))
    setRatioQua(clamped)
    setRatioLua(100 - clamped)
  }

  const handleRatioLuaChange = (val: number) => {
    const clamped = Math.min(100, Math.max(0, isNaN(val) ? 0 : val))
    setRatioLua(clamped)
    setRatioQua(100 - clamped)
  }

  // Strategy & History view
  const [analyticsDrum, setAnalyticsDrum] = useState<Drum | null>(null)
  const [analyticsData, setAnalyticsData] = useState<DrumAnalytics | null>(null)

  // Single Drum Detail View State
  const [selectedDrumId, setSelectedDrumId] = useState<number | null>(null)
  const [selectedDrumDetail, setSelectedDrumDetail] = useState<Drum | null>(null)
  const [drumHistoryRuns, setDrumHistoryRuns] = useState<DrumRunItem[]>([])
  const [drumAnalytics, setDrumAnalytics] = useState<DrumAnalytics | null>(null)
  const [drumHistoryFilter, setDrumHistoryFilter] = useState<'all' | 'in_progress' | 'ca_dep' | 'dat_chuan' | 'ca_xau'>('all')
  const [drumHistorySourceFilter, setDrumHistorySourceFilter] = useState<'all' | 'indoor' | 'outdoor' | 'unrecorded'>('all')
  const [drumHistoryDrainFilter, setDrumHistoryDrainFilter] = useState<'all' | 'even' | 'uneven'>('all')
  const [drumHistorySearch, setDrumHistorySearch] = useState('')

  // Main view navigation: Trống sấy cà vs Trông sàn sấy tĩnh
  const [mainTab, setMainTab] = useState<'drums' | 'static_beds'>('drums')

  // Static Drying Beds & Batches State
  const [staticBeds, setStaticBeds] = useState<StaticDryingBed[]>([])
  const [staticBedBatches, setStaticBedBatches] = useState<StaticBedBatchItem[]>([])
  const [staticBatchesFilter, setStaticBatchesFilter] = useState<'all' | 'even' | 'uneven' | 'spoiled'>('all')
  const [staticBatchSearch, setStaticBatchSearch] = useState('')

  // Static Bed Modals
  const [createBedBatchModal, setCreateBedBatchModal] = useState(false)
  const [selectedBedForNewBatch, setSelectedBedForNewBatch] = useState<StaticDryingBed | null>(null)
  const [enterBedWaterStatus, setEnterBedWaterStatus] = useState<'drained' | 'wet'>('wet')
  const [enterBedRawMaterialStatus, setEnterBedRawMaterialStatus] = useState<'fresh' | 'spoiled'>('fresh')
  const [enterBedSpoiledPercent, setEnterBedSpoiledPercent] = useState('')

  const [stirringModalBatch, setStirringModalBatch] = useState<StaticBedBatchItem | null>(null)
  const [dischargeBedModalBatch, setDischargeBedModalBatch] = useState<StaticBedBatchItem | null>(null)
  const [dischargeDrainStatus, setDischargeDrainStatus] = useState<'even' | 'uneven'>('even')
  const [dischargeDryStatus, setDischargeDryStatus] = useState<'not_dry' | 'dry'>('not_dry')
  const [detailBedBatchModal, setDetailBedBatchModal] = useState<StaticBedBatchDetail | null>(null)
  const [createStaticBedModal, setCreateStaticBedModal] = useState(false)

  // Start Run Modal: Source Selection
  const [startRunSourceType, setStartRunSourceType] = useState<'indoor' | 'outdoor'>('indoor')
  const [startRunBedId, setStartRunBedId] = useState<number | null>(null)
  const [startRunBedBatches, setStartRunBedBatches] = useState<StaticBedBatchItem[]>([])
  const [startRunSelectedBatchId, setStartRunSelectedBatchId] = useState<number | null>(null)

  const isManagerOrAdmin = user.role === 'admin' || user.role === 'manager'

  const loadBedBatchesForStartRun = async (bedId: number) => {
    try {
      const list = await call<StaticBedBatchItem[]>(`/static-bed-batches?bed_id=${bedId}&status=discharged`, csrf)
      setStartRunBedBatches(list)
      setStartRunSelectedBatchId(list.length > 0 ? list[0].id : null)
    } catch {
      setStartRunBedBatches([])
      setStartRunSelectedBatchId(null)
    }
  }

  const loadData = useCallback(async () => {
    if (!user.active_facility) return
    setLoading(true)
    setError('')
    try {
      const [dList, kpiData, bedsList, allBatches] = await Promise.all([
        call<Drum[]>('/drums', csrf),
        call<DrumKPI>('/audit/kpi', csrf),
        call<StaticDryingBed[]>('/static-beds', csrf).catch(() => []),
        call<StaticBedBatchItem[]>('/static-bed-batches', csrf).catch(() => []),
      ])
      setDrums(dList)
      setKpi(kpiData)
      setStaticBeds(bedsList)
      setStaticBedBatches(allBatches)

      if (selectedRunId) {
        const detail = await call<DrumRunDetail>(`/runs/${selectedRunId}`, csrf)
        setRunDetail(detail)
      }

      if (selectedDrumId) {
        const [d, runs, an] = await Promise.all([
          call<Drum>(`/drums/${selectedDrumId}`, csrf),
          call<DrumRunItem[]>(`/runs?drum_id=${selectedDrumId}`, csrf),
          call<DrumAnalytics>(`/drums/${selectedDrumId}/analytics`, csrf),
        ])
        setSelectedDrumDetail(d)
        setDrumHistoryRuns(runs)
        setDrumAnalytics(an)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được dữ liệu sấy.')
    } finally {
      setLoading(false)
    }
  }, [csrf, selectedRunId, selectedDrumId, user.active_facility])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const openDrumDetail = async (drumId: number) => {
    setSelectedDrumId(drumId)
    setSelectedRunId(null)
    setRunDetail(null)
    setLoading(true)
    setError('')
    try {
      const [d, runs, an] = await Promise.all([
        call<Drum>(`/drums/${drumId}`, csrf),
        call<DrumRunItem[]>(`/runs?drum_id=${drumId}`, csrf),
        call<DrumAnalytics>(`/drums/${drumId}/analytics`, csrf),
      ])
      setSelectedDrumDetail(d)
      setDrumHistoryRuns(runs)
      setDrumAnalytics(an)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể tải thông tin chi tiết trống.')
    } finally {
      setLoading(false)
    }
  }

  const openRunDetail = async (runId: number) => {
    try {
      setLoading(true)
      const detail = await call<DrumRunDetail>(`/runs/${runId}`, csrf)
      setRunDetail(detail)
      setSelectedRunId(runId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được chi tiết mẻ sấy.')
    } finally {
      setLoading(false)
    }
  }

  const openStrategyForDrum = async (drum: Drum) => {
    try {
      setLoading(true)
      const data = await call<DrumAnalytics>(`/drums/${drum.id}/analytics`, csrf)
      setAnalyticsData(data)
      setAnalyticsDrum(drum)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được chiến lược sấy của trống.')
    } finally {
      setLoading(false)
    }
  }

  // Handle start run
  const handleStartRun = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!startRunDrum) return
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      const localTime = String(f.get('entry_time'))
      const entryUtc = new Date(`${localTime}:00+07:00`).toISOString()

      let computedCoffeeType = 'Cà quả sấy ráo'
      let computedRatioQua: number | null = 100
      let computedRatioLua: number | null = 0

      if (coffeeCategory === 'ca_qua') {
        computedCoffeeType = 'Cà quả sấy ráo'
        computedRatioQua = 100
        computedRatioLua = 0
      } else if (coffeeCategory === 'ca_lua') {
        computedCoffeeType = 'Cà lụa sấy ráo'
        computedRatioQua = 0
        computedRatioLua = 100
      } else if (coffeeCategory === 'ca_tron') {
        computedCoffeeType = `Cà quả trộn cà lụa đã sấy ráo (${ratioQua}% quả / ${ratioLua}% lụa)`
        computedRatioQua = ratioQua
        computedRatioLua = ratioLua
      } else {
        computedCoffeeType = customCoffeeType.trim() || 'Loại cà khác'
        computedRatioQua = null
        computedRatioLua = null
      }

      const tempVal = initialTemp ? Number(initialTemp) : null

      let sourcePayload: Record<string, unknown> = {}
      if (startRunSourceType === 'indoor') {
        const selectedBed = staticBeds.find((b) => b.id === startRunBedId)
        if (!selectedBed) {
          throw new Error('Vui lòng chọn sàn sấy tĩnh xưởng trong!')
        }
        sourcePayload = {
          source_type: 'indoor',
          source_bed_id: selectedBed.id,
          source_bed_number: selectedBed.bed_number,
          source_bed_batch_id: startRunSelectedBatchId || null,
        }
      } else {
        sourcePayload = {
          source_type: 'outdoor',
          source_bed_id: null,
          source_bed_number: null,
          source_bed_batch_id: null,
        }
      }

      const newRun = await call<DrumRunDetail>('/runs', csrf, 'POST', {
        drum_id: startRunDrum.id,
        batch_code: String(f.get('batch_code')),
        coffee_type: computedCoffeeType,
        initial_weight_kg: f.get('initial_weight') ? Number(f.get('initial_weight')) : null,
        initial_temperature_celsius: tempVal !== null && !isNaN(tempVal) ? tempVal : null,
        initial_temperature_location: f.get("initial_temperature_location") || null,
        blend_ratio_qua_percent: computedRatioQua,
        blend_ratio_lua_percent: computedRatioLua,
        cycle_minutes: Number(f.get('cycle_minutes') || 30),
        entry_time: entryUtc,
        ...sourcePayload,
      })
      setStartRunDrum(null)
      setNotice(`Đã nạp mẻ ${newRun.batch_code} (${computedCoffeeType}) vào ${startRunDrum.drum_code}!`)
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể bắt đầu mẻ sấy.')
    } finally {
      setLoading(false)
    }
  }

  // Handle Static Bed: Create batch on bed
  const handleCreateBedBatch = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      const bedId = Number(f.get('bed_id'))
      const localTime = String(f.get('entered_at'))
      const enteredUtc = new Date(`${localTime}:00+07:00`).toISOString()

      const spoiledVal = enterBedRawMaterialStatus === 'spoiled' && enterBedSpoiledPercent.trim() !== ''
        ? Number(enterBedSpoiledPercent)
        : null

      await call('/static-bed-batches', csrf, 'POST', {
        bed_id: bedId,
        batch_code: String(f.get('batch_code')),
        coffee_type: f.get('coffee_type') ? String(f.get('coffee_type')) : null,
        input_weight_kg: f.get('input_weight_kg') ? Number(f.get('input_weight_kg')) : null,
        entered_at: enteredUtc,
        water_drained_status: enterBedWaterStatus,
        raw_material_status: enterBedRawMaterialStatus,
        estimated_spoiled_percent: spoiledVal,
      })
      setCreateBedBatchModal(false)
      setSelectedBedForNewBatch(null)
      setNotice('Đã ghi nhận mẻ cà vào sàn sấy tĩnh!')
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể đưa cà vào sàn.')
    } finally {
      setLoading(false)
    }
  }

  // Handle Static Bed: Record stirring
  const handleRecordStirring = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!stirringModalBatch) return
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      const startTime = String(f.get('started_at'))
      const startedUtc = new Date(`${startTime}:00+07:00`).toISOString()
      const endTime = f.get('ended_at') ? String(f.get('ended_at')) : null
      const endedUtc = endTime ? new Date(`${endTime}:00+07:00`).toISOString() : null
      const durationVal = f.get('duration_minutes') ? Number(f.get('duration_minutes')) : null

      await call(`/static-bed-batches/${stirringModalBatch.id}/stirrings`, csrf, 'POST', {
        started_at: startedUtc,
        ended_at: endedUtc,
        duration_minutes: durationVal,
        stirring_method: f.get('stirring_method') ? String(f.get('stirring_method')) : null,
        note: f.get('note') ? String(f.get('note')) : null,
      })
      setStirringModalBatch(null)
      setNotice(`Đã ghi nhận lượt đảo cà cho mẻ ${stirringModalBatch.batch_code}!`)
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể lưu lượt đảo.')
    } finally {
      setLoading(false)
    }
  }

  // Handle Static Bed: Discharge batch
  const handleDischargeBed = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!dischargeBedModalBatch) return
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      const localTime = String(f.get('discharged_at'))
      const dischargedUtc = new Date(`${localTime}:00+07:00`).toISOString()

      await call(`/static-bed-batches/${dischargeBedModalBatch.id}/discharge`, csrf, 'POST', {
        discharged_at: dischargedUtc,
        discharge_drain_status: dischargeDrainStatus,
        dry_status: dischargeDryStatus,
        discharge_note: f.get('discharge_note') ? String(f.get('discharge_note')) : null,
      })
      setDischargeBedModalBatch(null)
      setNotice(
        `Đã hoàn tất đưa mẻ ${dischargeBedModalBatch.batch_code} ra sàn (Đánh giá: ${dischargeDrainStatus === 'even' ? 'Ráo đều' : 'Chưa ráo đều'} · ${dischargeDryStatus === 'dry' ? '⚠️ Bị khô' : '✅ Không bị khô'})!`
      )
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể xả mẻ sàn.')
    } finally {
      setLoading(false)
    }
  }

  // Handle Static Bed: View detail
  const openBedBatchDetail = async (batchId: number) => {
    try {
      setLoading(true)
      const detail = await call<StaticBedBatchDetail>(`/static-bed-batches/${batchId}`, csrf)
      setDetailBedBatchModal(detail)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được chi tiết mẻ sàn.')
    } finally {
      setLoading(false)
    }
  }

  // Handle Static Bed: Delete batch (Manager / Admin)
  const handleDeleteBedBatch = async (batchId: number, batchCode: string) => {
    const confirmed = window.confirm(
      `Bạn có chắc chắn muốn xóa mẻ sàn "${batchCode}" không?\n\nLưu ý: Mọi nhật ký đảo cà của mẻ này sẽ bị xóa.`
    )
    if (!confirmed) return
    try {
      setLoading(true)
      await call(`/static-bed-batches/${batchId}`, csrf, 'DELETE')
      setDetailBedBatchModal(null)
      setNotice(`Đã xóa mẻ sàn ${batchCode} thành công!`)
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể xóa mẻ sàn sấy tĩnh.')
    } finally {
      setLoading(false)
    }
  }

  // Handle Static Bed: Create new bed (Manager / Admin)
  const handleCreateStaticBed = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      await call('/static-beds', csrf, 'POST', {
        bed_number: Number(f.get('bed_number')),
        bed_code: String(f.get('bed_code')),
        bed_name: String(f.get('bed_name')),
        capacity_kg: f.get('capacity_kg') ? Number(f.get('capacity_kg')) : null,
      })
      setCreateStaticBedModal(false)
      setNotice('Đã thêm sàn sấy tĩnh mới vào cơ sở.')
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể thêm sàn sấy.')
    } finally {
      setLoading(false)
    }
  }

  const openEditDrum = (drum: Drum) => {
    setEditMeasurementMode(drum.measurement_mode === 'two_ends' ? 'two_ends' : 'center_only')
    setEditHasMoistureImbalance(drum.has_moisture_imbalance || false)
    setEditHasBladeIssue(drum.has_blade_issue || false)
    setEditCharacteristicsNotes(drum.characteristics_notes || '')
    setEditDrumModal(drum)
  }

  const _openLogModal = (run: DrumRunDetail) => {
    setLogHeadMoisture('')
    setLogTailMoisture('')
    setLogModalRun(run)
  }
  void _openLogModal

  const openDischargeModal = (run: DrumRunDetail) => {
    setDischargeHeadMoisture('')
    setDischargeTailMoisture('')
    setDischargeModalRun(run)
  }

  // Handle record periodic log
  const handleRecordLog = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!logModalRun) return
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      const localTime = String(f.get('measured_at'))
      const measuredUtc = new Date(`${localTime}:00+07:00`).toISOString()

      const body: Record<string, unknown> = {
        temperature_celsius: Number(f.get('temperature_celsius')),
        temperature_location: f.get('temperature_location') || null,
        measured_at: measuredUtc,
        note: String(f.get('note')) || null,
      }

      if (logModalRun.drum_measurement_mode === 'two_ends') {
        const h = f.get('moisture_head_percent') === '' ? null : Number(f.get('moisture_head_percent'))
        const t = f.get('moisture_tail_percent') === '' ? null : Number(f.get('moisture_tail_percent'))
        body.moisture_head_percent = h
        body.moisture_tail_percent = t
        body.moisture_percent = h !== null && t !== null ? Number(((h + t) / 2).toFixed(2)) : h ?? t
      } else {
        const m = Number(f.get('moisture_percent'))
        body.moisture_percent = m
        body.moisture_center_percent = m
      }

      await call(`/runs/${logModalRun.id}/logs`, csrf, 'POST', body)
      setLogModalRun(null)
      setNotice('Đã ghi nhận độ ẩm và nhiệt độ chu kỳ thành công.')
      await loadData()
      if (selectedRunId) await openRunDetail(selectedRunId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể lưu nhật ký chu kỳ.')
    } finally {
      setLoading(false)
    }
  }

  // Handle stop heat & start incubation
  const handleStopHeat = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!stopHeatModalRun) return
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      const heatOffTime = String(f.get('heat_off_at'))
      const heatOffUtc = new Date(`${heatOffTime}:00+07:00`).toISOString()
      const rotationOffTime = f.get('rotation_off_at') ? String(f.get('rotation_off_at')) : null
      const rotationOffUtc = rotationOffTime ? new Date(`${rotationOffTime}:00+07:00`).toISOString() : null
      const moistureAtStop = f.get('moisture_at_heat_off') ? Number(f.get('moisture_at_heat_off')) : null

      const updated = await call<DrumRunDetail>(`/runs/${stopHeatModalRun.id}/stop-heat`, csrf, 'POST', {
        heat_off_at: heatOffUtc,
        rotation_off_at: rotationOffUtc,
        moisture_at_heat_off: moistureAtStop,
      })
      setStopHeatModalRun(null)
      setNotice(`Đã ghi nhận tắt nhiệt cho mẻ ${stopHeatModalRun.batch_code}. Cà đang được ủ trong trống!`)
      setRunDetail(updated)
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể ghi nhận tắt nhiệt.')
    } finally {
      setLoading(false)
    }
  }

  // Handle discharge coffee
  const handleDischarge = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!dischargeModalRun) return
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      const localTime = String(f.get('exit_time'))
      const exitUtc = new Date(`${localTime}:00+07:00`).toISOString()

      const body: Record<string, unknown> = {
        exit_time: exitUtc,
        quality_assessment: String(f.get('quality_assessment')) || 'dat_chuan',
        quality_note: String(f.get('quality_note')) || null,
        discharge_note: String(f.get('discharge_note')) || null,
      }

      if (dischargeModalRun.drum_measurement_mode === 'two_ends') {
        const h = Number(f.get('final_moisture_head_percent'))
        const t = Number(f.get('final_moisture_tail_percent'))
        body.final_moisture_head_percent = h
        body.final_moisture_tail_percent = t
        body.final_moisture_percent = Number(((h + t) / 2).toFixed(2))
      } else {
        body.final_moisture_percent = Number(f.get('final_moisture_percent'))
      }

      const updated = await call<DrumRunDetail>(`/runs/${dischargeModalRun.id}/discharge`, csrf, 'POST', body)
      setDischargeModalRun(null)
      setNotice(`Đã hoàn tất xả mẻ ${dischargeModalRun.batch_code} ra khỏi trống!`)
      setRunDetail(updated)
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể xả mẻ trống.')
    } finally {
      setLoading(false)
    }
  }

  // Handle random inspection
  const handleInspection = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!inspectModalRun) return
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      const localTime = String(f.get('inspected_at'))
      const inspectedUtc = new Date(`${localTime}:00+07:00`).toISOString()
      const result = await call<Inspection>(`/runs/${inspectModalRun.id}/inspections`, csrf, 'POST', {
        sample_moisture_percent: Number(f.get('sample_moisture_percent')),
        sample_temperature_celsius: Number(f.get('sample_temperature_celsius')),
        inspected_at: inspectedUtc,
        notes: String(f.get('notes')) || null,
      })
      setInspectModalRun(null)
      setNotice(
        result.evaluation === 'passed'
          ? 'Thanh tra ngẫu nhiên: Khớp số liệu với thợ trông trống (Đạt chuẩn)!'
          : result.evaluation === 'warning'
          ? 'Thanh tra ngẫu nhiên: Có sai lệch nhỏ cần lưu ý!'
          : 'CẢNH BÁO: Sai lệch số liệu lớn so với thợ trống báo cáo! Đã gắn cờ kiểm tra!'
      )
      await loadData()
      if (selectedRunId) await openRunDetail(selectedRunId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể lưu biên bản thanh tra.')
    } finally {
      setLoading(false)
    }
  }

  // Handle create drum
  const handleCreateDrum = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      await call('/drums', csrf, 'POST', {
        drum_code: String(f.get('drum_code')),
        drum_name: String(f.get('drum_name')),
        capacity_kg: f.get('capacity_kg') ? Number(f.get('capacity_kg')) : null,
        measurement_mode: createMeasurementMode,
        has_moisture_imbalance: createHasMoistureImbalance,
        has_blade_issue: createHasBladeIssue,
        characteristics_notes: createCharacteristicsNotes.trim() || null,
      })
      setCreateDrumModal(false)
      setNotice('Đã thêm trống sấy mới vào cơ sở.')
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể tạo trống mới.')
    } finally {
      setLoading(false)
    }
  }

  // Handle update drum
  const handleUpdateDrum = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!editDrumModal) return
    const f = new FormData(event.currentTarget)
    try {
      setLoading(true)
      const updated = await call<Drum>(`/drums/${editDrumModal.id}`, csrf, 'PATCH', {
        drum_name: String(f.get('drum_name')),
        capacity_kg: f.get('capacity_kg') ? Number(f.get('capacity_kg')) : null,
        measurement_mode: editMeasurementMode,
        has_moisture_imbalance: editHasMoistureImbalance,
        has_blade_issue: editHasBladeIssue,
        characteristics_notes: editCharacteristicsNotes.trim() || null,
      })
      setEditDrumModal(null)
      setNotice(`Đã cập nhật đặc tính thiết bị cho ${editDrumModal.drum_code}!`)
      await loadData()
      if (selectedDrumId === editDrumModal.id) {
        setSelectedDrumDetail(updated)
        try {
          const an = await call<DrumAnalytics>(`/drums/${editDrumModal.id}/analytics`, csrf)
          setDrumAnalytics(an)
        } catch {
          // Ignore
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể cập nhật đặc tính trống.')
    } finally {
      setLoading(false)
    }
  }

  // Handle delete drum
  const handleDeleteDrum = async (drum: Drum) => {
    const confirmed = window.confirm(
      `Bạn có chắc chắn muốn xóa trống "${drum.drum_code} - ${drum.drum_name}" không?\n\nLưu ý: Mọi mẻ sấy và dữ liệu nhật ký liên quan đến trống này cũng sẽ bị xóa vĩnh viễn.`
    )
    if (!confirmed) return
    try {
      setLoading(true)
      await call(`/drums/${drum.id}`, csrf, 'DELETE')
      setEditDrumModal(null)
      setNotice(`Đã xóa trống ${drum.drum_code} thành công!`)
      if (selectedDrumId === drum.id) {
        setSelectedDrumId(null)
        setSelectedDrumDetail(null)
      }
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không thể xóa trống sấy.')
    } finally {
      setLoading(false)
    }
  }

  // VIEW 1: DETAIL OF A SINGLE RUN
  if (selectedRunId && runDetail) {
    const isRunning = runDetail.status === 'in_progress'
    const isIncubating = isRunning && Boolean(runDetail.heat_off_at)

    return (
      <>
        <div className="page-content dp-page">
        <button
          className="d02-back"
          onClick={() => {
            setSelectedRunId(null)
            setRunDetail(null)
          }}
        >
          <ArrowLeft size={16} /> {selectedDrumId ? `Quay lại chi tiết trống ${runDetail.drum_code}` : 'Quay lại danh sách trống sấy'}
        </button>

        <DrumRunRecords key={runDetail.id} runId={runDetail.id} completed={runDetail.status === 'completed'} role={user.role} csrf={csrf} />
        <div className="welcome-row">
          <div>
            <div className="eyebrow">
              <span className="eyebrow-line" /> CHI TIẾT MẺ SẤY · {runDetail.drum_code}
            </div>
            <h1>{runDetail.batch_code}</h1>
            <p className="page-subtitle">
              <strong>{runDetail.coffee_type || 'Cà phê nhân'}</strong>
              {runDetail.initial_temperature_celsius !== null && runDetail.initial_temperature_celsius !== undefined && (
                <span> · Nhiệt độ ban đầu: <strong style={{ color: '#ea580c' }}>{runDetail.initial_temperature_celsius}°C</strong> ({runDetail.initial_temperature_location || "chưa rõ vị trí đo"})</span>
              )}
              {runDetail.initial_weight_kg && (
                <span> · Khối lượng nạp: <strong>{Number(runDetail.initial_weight_kg).toLocaleString('vi-VN')} kg</strong></span>
              )}
              {' · '}Phụ trách: <strong>{runDetail.operator_name}</strong>
              {' · '}
              {isRunning ? (
                isIncubating ? (
                  <span style={{ color: '#059669', fontWeight: 700 }}>Đang ủ trong trống (Đã tắt nhiệt)</span>
                ) : (
                  <span style={{ color: '#ea580c', fontWeight: 700 }}>Đang cấp nhiệt sấy</span>
                )
              ) : (
                <span>Đã xả trống hoàn tất · Đánh giá: {renderQualityBadge(runDetail.quality_assessment)}</span>
              )}
            </p>
          </div>
          <div className="d02-actions">
            <Button variant="outline" onClick={() => void openRunDetail(runDetail.id)} disabled={loading}>
              <RefreshCw size={15} className={loading ? 'spin' : ''} /> Làm mới
            </Button>
            {isRunning && (
              <>
                {/* Tạm thời ẩn chức năng đo nhiệt định kỳ theo chu kỳ */}
                {!runDetail.heat_off_at && (
                  <Button variant="outline" onClick={() => setStopHeatModalRun(runDetail)} style={{ borderColor: '#ea580c', color: '#ea580c' }}>
                    <Flame size={15} /> Tắt nhiệt & Bắt đầu ủ
                  </Button>
                )}
                <Button variant="outline" onClick={() => openDischargeModal(runDetail)}>
                  <Clock size={15} /> Xả trống / Ra trống
                </Button>
              </>
            )}
            <Button
              variant="outline"
              onClick={() => void openDrumDetail(runDetail.drum_id)}
            >
              <Info size={15} /> Thông tin trống {runDetail.drum_code}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                const drumObj = drums.find((d) => d.id === runDetail.drum_id)
                if (drumObj) void openStrategyForDrum(drumObj)
              }}
            >
              <TrendingUp size={15} /> Chiến lược trống {runDetail.drum_code}
            </Button>
          </div>
        </div>

        {error && <div className="d02-error" role="alert">{error}</div>}
        {notice && <div className="accounts-alert alert-success" role="status">{notice}</div>}

        {/* Coffee Source Card (Nguồn cà vào trống) */}
        <div className="dp-source-card" style={{ margin: '12px 0 16px', padding: '14px 18px', background: '#ffffff', borderRadius: '10px', border: '1px solid #cbd5e1', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Droplets size={18} style={{ color: '#0284c7' }} />
              <strong style={{ fontSize: '14px', color: '#0f172a' }}>Nguồn cà vào trống:</strong>
              {runDetail.source_type === 'indoor' ? (
                <span className="dp-badge" style={{ background: '#ecfdf5', color: '#047857', border: '1px solid #a7f3d0' }}>
                  🏢 Sàn tĩnh xưởng trong · Sàn số {runDetail.source_bed_number}
                </span>
              ) : runDetail.source_type === 'outdoor' ? (
                <span className="dp-badge" style={{ background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe' }}>
                  ☀️ Sàn tĩnh xưởng ngoài
                </span>
              ) : (
                <span className="dp-badge" style={{ background: '#f1f5f9', color: '#64748b' }}>
                  Chưa ghi nhận nguồn
                </span>
              )}
            </div>
            {runDetail.source_bed_batch && (
              <span style={{ fontSize: '12px', color: '#64748b' }}>
                Mã mẻ sàn liên kết: <strong style={{ color: '#0f172a' }}>{runDetail.source_bed_batch.batch_code}</strong>
              </span>
            )}
          </div>

          {runDetail.source_type === 'indoor' ? (
            runDetail.source_bed_batch ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginTop: '10px', paddingTop: '10px', borderTop: '1px solid #e2e8f0', fontSize: '13px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Tình trạng ráo nước vào sàn:</span>
                  <div>
                    <strong style={{ color: runDetail.source_bed_batch.water_drained_status === 'wet' ? '#ea580c' : '#059669' }}>
                      {runDetail.source_bed_batch.water_drained_status === 'wet' ? '💧 Cà Ướt' : '✨ Cà Ráo'}
                    </strong>
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Tình trạng nguyên liệu lúc vào:</span>
                  <div>
                    <strong style={{ color: runDetail.source_bed_batch.raw_material_status === 'spoiled' ? '#dc2626' : '#059669' }}>
                      {runDetail.source_bed_batch.raw_material_status === 'spoiled'
                        ? `⚠️ Cà Úng (${runDetail.source_bed_batch.estimated_spoiled_percent !== null && runDetail.source_bed_batch.estimated_spoiled_percent !== undefined ? `${runDetail.source_bed_batch.estimated_spoiled_percent}%` : 'Chưa ước tính'})`
                        : '✅ Cà Tươi'}
                    </strong>
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Thời gian & Lượt đảo trên sàn:</span>
                  <div>
                    <strong>
                      {runDetail.source_bed_batch.total_bed_duration_minutes
                        ? `${Math.floor(runDetail.source_bed_batch.total_bed_duration_minutes / 60)}h ${runDetail.source_bed_batch.total_bed_duration_minutes % 60}p`
                        : '—'}
                    </strong>
                    {' · '}
                    <span>{runDetail.source_bed_batch.stirring_count} lượt đảo</span>
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Đánh giá kết quả ra sàn:</span>
                  <div>
                    <strong style={{ color: runDetail.source_bed_batch.discharge_drain_status === 'even' ? '#059669' : '#d97706' }}>
                      {runDetail.source_bed_batch.discharge_drain_status === 'even' ? '🌟 Ráo đều' : runDetail.source_bed_batch.discharge_drain_status === 'uneven' ? '⚠️ Chưa ráo đều' : 'Chưa ra sàn'}
                    </strong>
                    {runDetail.source_bed_batch.dry_status && (
                      <span
                        style={{
                          marginLeft: '6px',
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '1px 6px',
                          borderRadius: '4px',
                          background: runDetail.source_bed_batch.dry_status === 'dry' ? '#fef2f2' : '#ecfdf5',
                          color: runDetail.source_bed_batch.dry_status === 'dry' ? '#dc2626' : '#047857',
                          border: `1px solid ${runDetail.source_bed_batch.dry_status === 'dry' ? '#fecaca' : '#a7f3d0'}`,
                        }}
                      >
                        {runDetail.source_bed_batch.dry_status === 'dry' ? '⚠️ Bị khô' : '✅ Không bị khô'}
                      </span>
                    )}
                    {runDetail.source_bed_batch.discharge_note && (
                      <div style={{ fontSize: '11px', color: '#64748b', fontStyle: 'italic', marginTop: '2px' }}>
                        {runDetail.source_bed_batch.discharge_note}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: '13px', color: '#64748b', marginTop: '6px' }}>
                <em>Chưa có bản ghi mẻ sàn (Nạp trực tiếp từ Sàn số {runDetail.source_bed_number})</em>
              </div>
            )
          ) : runDetail.source_type === 'outdoor' ? (
            <div style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
              Nguồn cà được tiếp nhận từ sàn sấy tĩnh xưởng ngoài cơ sở.
            </div>
          ) : (
            <div style={{ fontSize: '13px', color: '#94a3b8', marginTop: '4px', fontStyle: 'italic' }}>
              Mẻ sấy này chưa ghi nhận thông tin nguồn cà vào trống.
            </div>
          )}
        </div>

        {/* Drum Characteristics Banner */}
        <div className="dp-drum-defects" style={{ margin: '12px 0 16px', padding: '10px 16px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>Cấu hình kỹ thuật trống {runDetail.drum_code}:</span>
          <span className="dp-badge-mode">
            {runDetail.drum_measurement_mode === 'two_ends' ? '📍 Chế độ đo 2 đầu (Đầu & Đuôi)' : '📍 Chế độ đo tâm giữa trống'}
          </span>
          {runDetail.drum_has_moisture_imbalance && (
            <span className="dp-tag-defect">⚠️ Lệch ẩm 2 đầu nặng</span>
          )}
          {runDetail.drum_has_blade_issue && (
            <span className="dp-tag-defect">⚠️ Lỗi cánh đảo cà</span>
          )}
          {runDetail.drum_characteristics_notes && (
            <span className="dp-defect-note">ℹ️ {runDetail.drum_characteristics_notes}</span>
          )}
        </div>

        {/* Incubation Notification Banner */}
        {isIncubating && (
          <div className="dp-incubation-banner">
            <strong>⏱ Giai đoạn ủ nhiệt trong trống</strong>
            <span>
              Đã tắt nhiệt lúc {runDetail.heat_off_at ? dt(runDetail.heat_off_at) : ''}
              {runDetail.moisture_at_heat_off ? ` (Độ ẩm khi tắt nhiệt: ${runDetail.moisture_at_heat_off}%)` : ''}.
              Hơi nóng tích lũy trong buồng sấy tiếp tục giúp hạt cà chín đều và thoát ẩm từ từ. Hãy kiểm tra định kỳ trước khi xả trống.
            </span>
          </div>
        )}

        <div className="dp-kpi-grid">
          <div className="dp-kpi-card">
            <div className="dp-kpi-icon dp-icon-flame"><Thermometer size={20} /></div>
            <div className="dp-kpi-copy">
              <span>Nhiệt độ ban đầu</span>
              <strong>
                {runDetail.initial_temperature_celsius !== null && runDetail.initial_temperature_celsius !== undefined
                  ? `${runDetail.initial_temperature_celsius}°C`
                  : '—'}
              </strong>
              <small>{runDetail.initial_temperature_location || 'Nhiệt buồng nạp cà'}</small>
            </div>
          </div>
          <div className="dp-kpi-card">
            <div className="dp-kpi-icon dp-icon-flame" style={{ background: '#eff6ff', color: '#2563eb' }}><Scale size={20} /></div>
            <div className="dp-kpi-copy">
              <span>Khối lượng nạp</span>
              <strong>
                {runDetail.initial_weight_kg ? `${Number(runDetail.initial_weight_kg).toLocaleString('vi-VN')} kg` : '—'}
              </strong>
              <small>Lượng nguyên liệu vào trống</small>
            </div>
          </div>
          <div className="dp-kpi-card">
            <div className="dp-kpi-icon dp-icon-check"><Timer size={20} /></div>
            <div className="dp-kpi-copy">
              <span>Thời gian vào trống</span>
              <strong>{dt(runDetail.entry_time)}</strong>
              <small>
                {runDetail.exit_time
                  ? `Ra trống: ${dt(runDetail.exit_time)}`
                  : runDetail.heat_off_at
                  ? `Tắt nhiệt: ${dt(runDetail.heat_off_at)}`
                  : 'Đang cấp nhiệt sấy'}
              </small>
            </div>
          </div>
          <div className="dp-kpi-card">
            <div className="dp-kpi-icon dp-icon-flame"><Droplets size={20} /></div>
            <div className="dp-kpi-copy">
              <span>Độ ẩm ra trống / Kết quả</span>
              <strong>
                {runDetail.final_moisture_percent !== null
                  ? `${runDetail.final_moisture_percent}%`
                  : isRunning
                  ? (isIncubating ? 'Đang ủ nhiệt' : 'Đang sấy nhiệt')
                  : 'Chưa ghi nhận'}
              </strong>
              <small>
                {runDetail.final_moisture_head_percent !== null && runDetail.final_moisture_tail_percent !== null
                  ? `Đầu: ${runDetail.final_moisture_head_percent}% / Đuôi: ${runDetail.final_moisture_tail_percent}%`
                  : 'Đánh giá độ ẩm thành phẩm'}
              </small>
            </div>
          </div>
        </div>

        {/* Tạm thời ẩn bảng nhật ký chu kỳ nếu chưa có dữ liệu đo định kỳ */}
        {runDetail.logs.length > 0 && (
          <div className="panel dp-run-detail">
          <div className="dp-tabs">
            <button
              className={`dp-tab-btn ${detailTab === 'logs' ? 'is-active' : ''}`}
              onClick={() => setDetailTab('logs')}
            >
              Nhật ký chu kỳ trong trống ({runDetail.logs.length})
            </button>
            <button
              className={`dp-tab-btn ${detailTab === 'inspections' ? 'is-active' : ''}`}
              onClick={() => setDetailTab('inspections')}
            >
              Lịch sử thanh tra ngẫu nhiên ({runDetail.inspections.length})
            </button>
          </div>

          {detailTab === 'logs' ? (
            <div className="dp-table-wrap">
              <table className="dp-timeline-table">
                <thead>
                  <tr>
                    <th>Lần đo</th>
                    <th>Độ ẩm cà (%)</th>
                    <th>Nhiệt độ luồng hơi (°C)</th>
                    <th>Thời điểm đo</th>
                    <th>Máy chủ ghi nhận</th>
                    <th>Trạng thái</th>
                    <th>Ghi chú</th>
                  </tr>
                </thead>
                <tbody>
                  {runDetail.logs.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', padding: '30px', color: '#94a3b8' }}>
                        Chưa có lượt đo nào. Hãy bấm "Ghi nhật ký chu kỳ" để nhập số liệu.
                      </td>
                    </tr>
                  ) : (
                    runDetail.logs.map((log) => (
                      <tr key={log.id}>
                        <td>
                          <strong>Lần #{log.sequence}</strong>
                        </td>
                        <td>
                          <span style={{ color: '#0284c7', fontWeight: 700, fontSize: '15px' }}>
                            {log.moisture_percent}%
                          </span>
                          {(log.moisture_head_percent !== null || log.moisture_tail_percent !== null) && (
                            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                              Đầu: <strong>{log.moisture_head_percent === null ? "Chưa đo" : `${log.moisture_head_percent}%`}</strong> · Đuôi: <strong>{log.moisture_tail_percent === null ? "Chưa đo" : `${log.moisture_tail_percent}%`}</strong>
                              {log.moisture_diff_ends !== null && (
                                <span style={{ marginLeft: '4px', color: Number(log.moisture_diff_ends) > 1.5 ? '#b91c1c' : '#059669', fontWeight: 600 }}>
                                  (Δ {log.moisture_diff_ends}%)
                                </span>
                              )}
                            </div>
                          )}
                        </td>
                        <td>
                          <span style={{ color: '#ea580c', fontWeight: 700, fontSize: '15px' }}>
                            {log.temperature_celsius}°C
                          </span><small> · {log.temperature_location || "Chưa xác định vị trí đo"}</small>
                        </td>
                        <td>{dt(log.measured_at)}</td>
                        <td>
                          <small style={{ color: '#64748b' }}>{dt(log.recorded_at)}</small>
                        </td>
                        <td>
                          {log.compliance_status === 'on_time' ? (
                            <span className="dp-tag-ontime">Đúng hạn</span>
                          ) : (
                            <span className="dp-tag-late">
                              Trễ {Math.round((log.delay_seconds || 0) / 60)} phút
                            </span>
                          )}
                        </td>
                        <td>{log.note || '—'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="dp-table-wrap">
              <table className="dp-timeline-table">
                <thead>
                  <tr>
                    <th>Thời điểm thanh tra</th>
                    <th>Cấp trên thực hiện</th>
                    <th>Mẫu độ ẩm (%)</th>
                    <th>Mẫu nhiệt độ (°C)</th>
                    <th>Chênh lệch (Δ)</th>
                    <th>Kết luận</th>
                    <th>Ghi chú kiểm tra</th>
                  </tr>
                </thead>
                <tbody>
                  {runDetail.inspections.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', padding: '30px', color: '#94a3b8' }}>
                        Chưa có đợt thanh tra đột xuất nào cho mẻ sấy này.
                      </td>
                    </tr>
                  ) : (
                    runDetail.inspections.map((insp) => (
                      <tr key={insp.id}>
                        <td>{dt(insp.inspected_at)}</td>
                        <td><strong>{insp.inspector_name}</strong></td>
                        <td style={{ fontWeight: 700, color: '#0284c7' }}>{insp.sample_moisture_percent}%</td>
                        <td style={{ fontWeight: 700, color: '#ea580c' }}>{insp.sample_temperature_celsius}°C</td>
                        <td>
                          <small>
                            Δ ẩm: {insp.moisture_diff !== null ? `${insp.moisture_diff}%` : '—'}
                            {' · '}
                            Δ nhiệt: {insp.temperature_diff !== null ? `${insp.temperature_diff}°C` : '—'}
                          </small>
                        </td>
                        <td>
                          {insp.evaluation === 'passed' ? (
                            <span className="dp-eval-passed">Khớp số liệu</span>
                          ) : insp.evaluation === 'warning' ? (
                            <span className="dp-eval-warning">Lệch nhỏ</span>
                          ) : (
                            <span className="dp-eval-failed">Bất thường / Cần đối chất</span>
                          )}
                        </td>
                        <td>{insp.notes || '—'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
        )}
      </div>
      {renderModals()}
    </>
  )
}

  // VIEW 2: DETAIL OF A SINGLE DRUM (Thông tin chi tiết từng trống & Lịch sử vào trống chi tiết)
  if (selectedDrumId && selectedDrumDetail) {
    const isRunning = selectedDrumDetail.status === 'running'
    const filteredRuns = drumHistoryRuns.filter((r) => {
      if (drumHistoryFilter === 'in_progress' && r.status !== 'in_progress') return false
      if (drumHistoryFilter === 'ca_dep' && r.quality_assessment !== 'ca_dep') return false
      if (drumHistoryFilter === 'dat_chuan' && r.quality_assessment !== 'dat_chuan') return false
      if (drumHistoryFilter === 'ca_xau' && r.quality_assessment !== 'ca_xau') return false
      if (drumHistorySourceFilter === 'indoor' && r.source_type !== 'indoor') return false
      if (drumHistorySourceFilter === 'outdoor' && r.source_type !== 'outdoor') return false
      if (drumHistorySourceFilter === 'unrecorded' && (r.source_type !== null && r.source_type !== undefined)) return false
      if (drumHistoryDrainFilter === 'even' && r.source_bed_batch?.discharge_drain_status !== 'even') return false
      if (drumHistoryDrainFilter === 'uneven' && r.source_bed_batch?.discharge_drain_status !== 'uneven') return false
      if (drumHistorySearch.trim()) {
        const q = drumHistorySearch.toLowerCase().trim()
        const matchBatch = r.batch_code.toLowerCase().includes(q)
        const matchCoffee = (r.coffee_type || '').toLowerCase().includes(q)
        const matchOperator = (r.operator_name || '').toLowerCase().includes(q)
        const matchBed = r.source_bed_number ? `sàn ${r.source_bed_number}`.includes(q) : false
        if (!matchBatch && !matchCoffee && !matchOperator && !matchBed) return false
      }
      return true
    })

    const runningCount = drumHistoryRuns.filter((r) => r.status === 'in_progress').length
    const caDepCount = drumHistoryRuns.filter((r) => r.quality_assessment === 'ca_dep').length
    const datChuanCount = drumHistoryRuns.filter((r) => r.quality_assessment === 'dat_chuan').length
    const caXauCount = drumHistoryRuns.filter((r) => r.quality_assessment === 'ca_xau').length

    return (
      <>
        <div className="page-content dp-page">
          <button
            className="d02-back"
            onClick={() => {
              setSelectedDrumId(null)
              setSelectedDrumDetail(null)
            }}
          >
            <ArrowLeft size={16} /> Quay lại danh sách tất cả trống sấy
          </button>

          <div className="welcome-row">
            <div>
              <div className="eyebrow">
                <span className="eyebrow-line" /> THÔNG TIN THIẾT BỊ · {selectedDrumDetail.drum_code}
              </div>
              <h1>{selectedDrumDetail.drum_name}</h1>
              <p className="page-subtitle">
                Sức chứa: <strong>{selectedDrumDetail.capacity_kg ? `${Number(selectedDrumDetail.capacity_kg).toLocaleString('vi-VN')} kg` : 'Theo mẻ'}</strong>
                {' · '}Chế độ đo: <strong>{selectedDrumDetail.measurement_mode === 'two_ends' ? 'Đo 2 đầu (Đầu & Đuôi)' : 'Đo giữa trống'}</strong>
                {' · '}Trạng thái:{' '}
                {isRunning ? (
                  <span style={{ color: '#ea580c', fontWeight: 700 }}>
                    Đang sấy mẻ {selectedDrumDetail.active_batch_code}
                  </span>
                ) : (
                  <span style={{ color: '#059669', fontWeight: 700 }}>Sẵn sàng nạp mẻ mới</span>
                )}
              </p>
            </div>
            <div className="d02-actions">
              <Button variant="outline" onClick={() => void openDrumDetail(selectedDrumDetail.id)} disabled={loading}>
                <RefreshCw size={15} className={loading ? 'spin' : ''} /> Làm mới
              </Button>
              {isManagerOrAdmin && (
                <Button variant="outline" onClick={() => openEditDrum(selectedDrumDetail)}>
                  <Settings size={15} /> Sửa thông tin trống
                </Button>
              )}
              {isRunning && selectedDrumDetail.active_run_id ? (
                <Button onClick={() => void openRunDetail(selectedDrumDetail.active_run_id!)}>
                  <Thermometer size={15} /> Đến mẻ đang sấy
                </Button>
              ) : (
                <Button
                  onClick={() => {
                    setCoffeeCategory('ca_qua')
                    setRatioQua(50)
                    setRatioLua(50)
                    setCustomCoffeeType('')
                    setInitialTemp('75.0')
                    setStartRunDrum(selectedDrumDetail)
                  }}
                >
                  <Plus size={15} /> Nạp mẻ vào trống
                </Button>
              )}
            </div>
          </div>

          {error && <div className="d02-error" role="alert">{error}</div>}
          {notice && <div className="accounts-alert alert-success" role="status">{notice}</div>}

          {/* THÔNG SỐ KỸ THUẬT VÀ ĐẶC TÍNH CỦA TRỐNG */}
          <div className="dp-specs-panel">
            <div className="dp-specs-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Gauge size={18} color="#ea580c" />
                <h3>Đặc tính kỹ thuật & Tình trạng thiết bị</h3>
              </div>
              {isManagerOrAdmin && (
                <Button size="sm" variant="outline" onClick={() => openEditDrum(selectedDrumDetail)}>
                  <Settings size={14} /> Chỉnh sửa cấu hình
                </Button>
              )}
            </div>

            <div className="dp-specs-grid">
              <div className="dp-specs-item">
                <span>Mã định danh</span>
                <strong>{selectedDrumDetail.drum_code}</strong>
                <small>Mã số quản lý thiết bị</small>
              </div>
              <div className="dp-specs-item">
                <span>Sức chứa thiết kế</span>
                <strong>{selectedDrumDetail.capacity_kg ? `${Number(selectedDrumDetail.capacity_kg).toLocaleString('vi-VN')} kg` : 'Theo từng mẻ'}</strong>
                <small>Tải trọng buồng sấy</small>
              </div>
              <div className="dp-specs-item">
                <span>Phương thức đo độ ẩm</span>
                <div style={{ marginTop: '2px' }}>
                  <span className="dp-badge-mode">
                    {selectedDrumDetail.measurement_mode === 'two_ends' ? '📍 Đo 2 đầu (Đầu & Đuôi buồng)' : '📍 Đo tâm giữa trống'}
                  </span>
                </div>
                <small>
                  {selectedDrumDetail.measurement_mode === 'two_ends'
                    ? 'Thợ bắt buộc đo cả 2 đầu buồng sấy'
                    : 'Đo 1 điểm tại tâm buồng sấy'}
                </small>
              </div>
              <div className="dp-specs-item">
                <span>Tình trạng cơ học</span>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                  {selectedDrumDetail.has_moisture_imbalance && (
                    <span className="dp-tag-defect">⚠️ Lệch ẩm 2 đầu nặng</span>
                  )}
                  {selectedDrumDetail.has_blade_issue && (
                    <span className="dp-tag-defect">⚠️ Lỗi cánh đảo cà</span>
                  )}
                  {!selectedDrumDetail.has_moisture_imbalance && !selectedDrumDetail.has_blade_issue && (
                    <span style={{ color: '#059669', fontSize: '13px', fontWeight: 600 }}>
                      ✅ Buồng & cánh đảo bình thường
                    </span>
                  )}
                </div>
                <small>Cảnh báo cơ học thiết bị</small>
              </div>
            </div>

            {selectedDrumDetail.characteristics_notes ? (
              <div className="dp-specs-notes">
                <Info size={16} style={{ color: '#0284c7', marginTop: '2px', flexShrink: 0 }} />
                <div>
                  <strong>Lưu ý vận hành cho thợ trực: </strong>
                  <span>{selectedDrumDetail.characteristics_notes}</span>
                </div>
              </div>
            ) : (
              <div className="dp-specs-notes" style={{ color: '#94a3b8' }}>
                <Info size={16} style={{ marginTop: '2px', flexShrink: 0 }} />
                <span>Chưa có ghi chú kinh nghiệm vận hành cho trống này. Quản lý có thể thêm bằng nút "Sửa thông tin trống".</span>
              </div>
            )}
          </div>

          {/* KPI Grid for this Drum */}
          <div className="dp-kpi-grid">
            <div className="dp-kpi-card">
              <div className="dp-kpi-icon dp-icon-flame"><Timer size={20} /></div>
              <div className="dp-kpi-copy">
                <span>Tổng số mẻ đã vào</span>
                <strong>{drumHistoryRuns.length} mẻ</strong>
                <small>Lịch sử hoạt động của trống</small>
              </div>
            </div>
            <div className="dp-kpi-card">
              <div className="dp-kpi-icon dp-icon-check"><Award size={20} /></div>
              <div className="dp-kpi-copy">
                <span>Tỷ lệ cà đẹp</span>
                <strong style={{ color: '#059669' }}>
                  {drumAnalytics ? `${drumAnalytics.ca_dep_rate_percent}%` : '—'}
                </strong>
                <small>{caDepCount} cà đẹp / {drumHistoryRuns.length} mẻ</small>
              </div>
            </div>
            <div className="dp-kpi-card">
              <div className="dp-kpi-icon dp-icon-inspect"><Thermometer size={20} /></div>
              <div className="dp-kpi-copy">
                <span>Nhiệt độ hơi tối ưu</span>
                <strong>
                  {drumAnalytics?.strategy.recommended_heat_temp_celsius ? `${drumAnalytics.strategy.recommended_heat_temp_celsius}°C` : '75-80°C'}
                </strong>
                <small>Đúc kết từ mẻ cà đẹp</small>
              </div>
            </div>
            <div className="dp-kpi-card">
              <div className="dp-kpi-icon dp-icon-flame"><Droplets size={20} /></div>
              <div className="dp-kpi-copy">
                <span>Độ ẩm nên tắt nhiệt</span>
                <strong style={{ color: '#ea580c' }}>
                  {drumAnalytics?.strategy.recommended_stop_heat_moisture ? `${drumAnalytics.strategy.recommended_stop_heat_moisture}%` : '15-16%'}
                </strong>
                <small>Ủ {drumAnalytics?.strategy.recommended_incubation_minutes || '30-45'}p về ~{drumAnalytics?.strategy.expected_final_moisture || '12.5'}%</small>
              </div>
            </div>
          </div>

          {/* Strategy Advisory Summary if available */}
          {drumAnalytics && (
            <div className="dp-strategy-summary-box" style={{ margin: 0 }}>
              <Lightbulb size={18} color="#ea580c" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong>Chiến lược vận hành tối ưu cho {selectedDrumDetail.drum_code}: </strong>
                <span>{drumAnalytics.strategy.strategy_summary}</span>
              </div>
            </div>
          )}

          {/* LỊCH SỬ VÀO TRỐNG CHI TIẾT */}
          <div className="panel" style={{ padding: '20px' }}>
            <div className="panel-heading" style={{ marginBottom: '16px' }}>
              <div>
                <span className="section-kicker">LỊCH SỬ VẬN HÀNH THIẾT BỊ</span>
                <h2 style={{ fontSize: '18px', margin: '4px 0 0' }}>
                  Lịch sử các mẻ sấy vào trống ({filteredRuns.length} / {drumHistoryRuns.length})
                </h2>
              </div>
            </div>

            {/* Filter and Search Toolbar */}
            <div className="dp-history-toolbar">
              <div className="dp-filter-tabs">
                <button
                  type="button"
                  className={`dp-filter-tab ${drumHistoryFilter === 'all' ? 'is-active' : ''}`}
                  onClick={() => setDrumHistoryFilter('all')}
                >
                  Tất cả ({drumHistoryRuns.length})
                </button>
                <button
                  type="button"
                  className={`dp-filter-tab ${drumHistoryFilter === 'in_progress' ? 'is-active' : ''}`}
                  onClick={() => setDrumHistoryFilter('in_progress')}
                >
                  Đang sấy ({runningCount})
                </button>
                <button
                  type="button"
                  className={`dp-filter-tab ${drumHistoryFilter === 'ca_dep' ? 'is-active' : ''}`}
                  onClick={() => setDrumHistoryFilter('ca_dep')}
                >
                  Cà đẹp ({caDepCount})
                </button>
                <button
                  type="button"
                  className={`dp-filter-tab ${drumHistoryFilter === 'dat_chuan' ? 'is-active' : ''}`}
                  onClick={() => setDrumHistoryFilter('dat_chuan')}
                >
                  Đạt chuẩn ({datChuanCount})
                </button>
                <button
                  type="button"
                  className={`dp-filter-tab ${drumHistoryFilter === 'ca_xau' ? 'is-active' : ''}`}
                  onClick={() => setDrumHistoryFilter('ca_xau')}
                >
                  Cà xấu ({caXauCount})
                </button>
              </div>

              <div className="dp-search-box">
                <Search size={15} color="#94a3b8" />
                <input
                  type="text"
                  placeholder="Tìm mã mẻ, loại cà, thợ trực..."
                  value={drumHistorySearch}
                  onChange={(e) => setDrumHistorySearch(e.target.value)}
                />
                {drumHistorySearch && (
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => setDrumHistorySearch('')}
                    style={{ padding: '2px' }}
                  >
                    <X size={13} />
                  </button>
                )}
              </div>
            </div>

            {/* Source & Drain Status Filters */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '14px', padding: '8px 12px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Lọc nguồn cà:</span>
              <button
                type="button"
                className={`dp-filter-tab ${drumHistorySourceFilter === 'all' ? 'is-active' : ''}`}
                onClick={() => setDrumHistorySourceFilter('all')}
              >
                Tất cả
              </button>
              <button
                type="button"
                className={`dp-filter-tab ${drumHistorySourceFilter === 'indoor' ? 'is-active' : ''}`}
                onClick={() => setDrumHistorySourceFilter('indoor')}
              >
                Sàn xưởng trong
              </button>
              <button
                type="button"
                className={`dp-filter-tab ${drumHistorySourceFilter === 'outdoor' ? 'is-active' : ''}`}
                onClick={() => setDrumHistorySourceFilter('outdoor')}
              >
                Sàn xưởng ngoài
              </button>
              <button
                type="button"
                className={`dp-filter-tab ${drumHistorySourceFilter === 'unrecorded' ? 'is-active' : ''}`}
                onClick={() => setDrumHistorySourceFilter('unrecorded')}
              >
                Chưa ghi nhận nguồn
              </button>

              <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginLeft: '10px' }}>Độ ráo sàn:</span>
              <button
                type="button"
                className={`dp-filter-tab ${drumHistoryDrainFilter === 'all' ? 'is-active' : ''}`}
                onClick={() => setDrumHistoryDrainFilter('all')}
              >
                Tất cả
              </button>
              <button
                type="button"
                className={`dp-filter-tab ${drumHistoryDrainFilter === 'even' ? 'is-active' : ''}`}
                onClick={() => setDrumHistoryDrainFilter('even')}
              >
                Ráo đều
              </button>
              <button
                type="button"
                className={`dp-filter-tab ${drumHistoryDrainFilter === 'uneven' ? 'is-active' : ''}`}
                onClick={() => setDrumHistoryDrainFilter('uneven')}
              >
                Chưa ráo đều
              </button>
            </div>

            {/* Detailed Batch History Table */}
            {filteredRuns.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                <History size={32} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                <p>Chưa có mẻ sấy nào phù hợp với bộ lọc tìm kiếm.</p>
              </div>
            ) : (
              <div className="dp-table-wrap">
                <table className="dp-timeline-table">
                  <thead>
                    <tr>
                      <th>Mã mẻ & Ngày vào</th>
                      <th>Nguồn cà</th>
                      <th>Loại cà & Tỷ lệ</th>
                      <th>Nạp & Nhiệt ban đầu</th>
                      <th>Thời gian Sấy / Ủ</th>
                      <th>Ẩm tắt nhiệt</th>
                      <th>Ẩm ra trống</th>
                      <th>Giảm khi ủ</th>
                      <th>Đánh giá chất lượng</th>
                      <th>Thợ phụ trách</th>
                      <th>Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRuns.map((r) => {
                      const isRunInProgress = r.status === 'in_progress'
                      const drop = r.moisture_at_heat_off !== null && r.final_moisture_percent !== null
                        ? (Number(r.moisture_at_heat_off) - Number(r.final_moisture_percent)).toFixed(2)
                        : null

                      return (
                        <tr key={r.id}>
                          <td>
                            <button
                              type="button"
                              className="dp-batch-link"
                              onClick={() => void openRunDetail(r.id)}
                              style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', textAlign: 'left' }}
                            >
                              {r.batch_code}
                            </button>
                            {isRunInProgress && (
                              <span className="dp-badge dp-badge-running" style={{ marginLeft: '6px', fontSize: '10px', padding: '2px 6px' }}>
                                Đang sấy
                              </span>
                            )}
                            <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                              {dt(r.entry_time)}
                            </div>
                          </td>

                          <td>
                            {r.source_type === 'indoor' ? (
                              <div>
                                <span className="dp-badge" style={{ background: '#ecfdf5', color: '#047857', fontSize: '11px' }}>
                                  Sàn {r.source_bed_number} (Xưởng trong)
                                </span>
                                {r.source_bed_batch ? (
                                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                                    Mẻ <strong>{r.source_bed_batch.batch_code}</strong>
                                    {' · '}
                                    <strong style={{ color: r.source_bed_batch.discharge_drain_status === 'even' ? '#059669' : '#d97706' }}>
                                      {r.source_bed_batch.discharge_drain_status === 'even' ? 'Ráo đều' : 'Chưa ráo đều'}
                                    </strong>
                                    {r.source_bed_batch.raw_material_status === 'spoiled' && (
                                      <span style={{ color: '#dc2626', marginLeft: '4px' }}>
                                        · Úng: {r.source_bed_batch.estimated_spoiled_percent != null ? `${r.source_bed_batch.estimated_spoiled_percent}%` : 'Chưa ước tính'}
                                      </span>
                                    )}
                                  </div>
                                ) : (
                                  <div style={{ fontSize: '11px', color: '#94a3b8', fontStyle: 'italic', marginTop: '2px' }}>Chưa có bản ghi mẻ sàn</div>
                                )}
                              </div>
                            ) : r.source_type === 'outdoor' ? (
                              <span className="dp-badge" style={{ background: '#eff6ff', color: '#1d4ed8', fontSize: '11px' }}>
                                Sàn tĩnh xưởng ngoài
                              </span>
                            ) : (
                              <span style={{ fontSize: '11px', color: '#94a3b8' }}>Chưa ghi nhận nguồn</span>
                            )}
                          </td>

                          <td>
                            <span style={{ fontWeight: 600, color: '#047857' }}>
                              {r.coffee_type || 'Cà phê nhân'}
                            </span>
                            {r.blend_ratio_qua_percent !== null && r.blend_ratio_lua_percent !== null && (
                              <div style={{ fontSize: '11px', color: '#64748b', marginTop: '1px' }}>
                                {r.blend_ratio_qua_percent}% Quả · {r.blend_ratio_lua_percent}% Lụa
                              </div>
                            )}
                          </td>

                          <td>
                            <strong>{r.initial_weight_kg ? `${Number(r.initial_weight_kg).toLocaleString('vi-VN')} kg` : '—'}</strong>
                            {r.initial_temperature_celsius !== null && (
                              <div style={{ fontSize: '11px', color: '#ea580c', marginTop: '1px' }}>
                                Nhiệt đầu: <strong>{r.initial_temperature_celsius}°C</strong>
                              </div>
                            )}
                          </td>

                          <td>
                            {isRunInProgress ? (
                              <span style={{ color: '#ea580c', fontWeight: 600 }}>
                                {r.heat_off_at ? 'Đang ủ nhiệt' : 'Đang cấp nhiệt'}
                              </span>
                            ) : (
                              <div>
                                <div>Sấy: <strong>{r.heat_off_at && r.entry_time ? `${Math.max(0, Math.round((new Date(r.heat_off_at).getTime() - new Date(r.entry_time).getTime()) / 60000))}p` : '—'}</strong></div>
                                <div style={{ fontSize: '11px', color: '#059669' }}>
                                  Ủ: <strong>{r.incubation_minutes ? `${r.incubation_minutes}p` : '—'}</strong>
                                </div>
                              </div>
                            )}
                          </td>

                          <td>
                            {r.moisture_at_heat_off ? (
                              <span style={{ color: '#ea580c', fontWeight: 600 }}>{r.moisture_at_heat_off}%</span>
                            ) : isRunInProgress ? (
                              <small style={{ color: '#94a3b8' }}>Đang sấy</small>
                            ) : (
                              '—'
                            )}
                          </td>

                          <td>
                            {r.final_moisture_percent !== null ? (
                              <div>
                                <strong style={{ color: '#0284c7', fontSize: '14px' }}>
                                  {r.final_moisture_percent}%
                                </strong>
                                {r.final_moisture_head_percent !== null && r.final_moisture_tail_percent !== null && (
                                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '1px' }}>
                                    Đầu: {r.final_moisture_head_percent}% · Đuôi: {r.final_moisture_tail_percent}%
                                  </div>
                                )}
                              </div>
                            ) : (
                              <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>
                                {r.latest_moisture_percent ? `Đang đo: ${r.latest_moisture_percent}%` : 'Chưa có'}
                              </span>
                            )}
                          </td>

                          <td>
                            {drop !== null ? (
                              <span style={{ color: '#059669', fontWeight: 600 }}>-{drop}%</span>
                            ) : (
                              '—'
                            )}
                          </td>

                          <td>
                            {isRunInProgress ? (
                              <span className="dp-badge dp-badge-running">Đang chạy</span>
                            ) : (
                              <div>
                                {renderQualityBadge(r.quality_assessment)}
                                {r.quality_note && (
                                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px', maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.quality_note}>
                                    {r.quality_note}
                                  </div>
                                )}
                              </div>
                            )}
                          </td>

                          <td>
                            <strong>{r.operator_name}</strong>
                            <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                              {r.log_count} lần đo · {r.inspection_count} thanh tra
                            </div>
                          </td>

                          <td>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void openRunDetail(r.id)}
                              style={{ whiteSpace: 'nowrap' }}
                            >
                              Chi tiết mẻ
                            </Button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
        {renderModals()}
      </>
    )
  }

  // MAIN DASHBOARD VIEW
  return (
    <div className="page-content dp-page">
      <div className="welcome-row">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" /> GIÁM SÁT VẬN HÀNH SẤY CÀ PHÊ
          </div>
          <h1>{mainTab === 'drums' ? 'Trông trống cà' : 'Trông sàn sấy tĩnh'}</h1>
          <p className="page-subtitle">
            Cơ sở: <strong>{user.active_facility?.name || 'Chưa chọn cơ sở'}</strong>
            {' · '}
            {mainTab === 'drums'
              ? 'Kiểm soát mẻ sấy, nhiệt độ nạp, thời gian ủ và đúc kết chiến lược ra cà đẹp.'
              : 'Theo dõi tình trạng ráo nước, cà úng, các lượt đảo hạt và thời gian làm ráo trước khi vào trống.'}
          </p>
        </div>
        <div className="d02-actions">
          <Button variant="outline" onClick={() => void loadData()} disabled={loading}>
            <RefreshCw size={15} className={loading ? 'spin' : ''} /> Làm mới
          </Button>
          {mainTab === 'drums' ? (
            isManagerOrAdmin && (
              <Button onClick={() => setCreateDrumModal(true)}>
                <Plus size={15} /> Thêm trống sấy
              </Button>
            )
          ) : (
            <>
              <Button
                onClick={() => {
                  setEnterBedWaterStatus('wet')
                  setEnterBedRawMaterialStatus('fresh')
                  setEnterBedSpoiledPercent('')
                  const defaultBed = staticBeds.find(
                    (b) => b.is_active && !staticBedBatches.some((sb) => sb.bed_id === b.id && sb.status === 'on_bed')
                  ) || staticBeds[0] || null
                  setSelectedBedForNewBatch(defaultBed)
                  setCreateBedBatchModal(true)
                }}
              >
                <Plus size={15} /> Đưa cà vào sàn
              </Button>
              {isManagerOrAdmin && (
                <Button variant="outline" onClick={() => setCreateStaticBedModal(true)}>
                  <Plus size={15} /> Thêm sàn sấy mới
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {error && <div className="d02-error" role="alert">{error}</div>}
      {notice && <div className="accounts-alert alert-success" role="status">{notice}</div>}

      {/* TABS ĐIỀU HƯỚNG CHÍNH: TRỐNG SẤY CÀ VS TRÔNG SÀN SẤY TĨNH */}
      <div className="dp-main-nav-tabs">
        <button
          type="button"
          className={`dp-main-nav-tab ${mainTab === 'drums' ? 'is-active' : ''}`}
          onClick={() => setMainTab('drums')}
        >
          <Flame size={17} />
          <span>Trống sấy cà ({drums.length})</span>
        </button>

        <button
          type="button"
          className={`dp-main-nav-tab ${mainTab === 'static_beds' ? 'is-active' : ''}`}
          onClick={() => setMainTab('static_beds')}
        >
          <Layers size={17} />
          <span>Trông sàn sấy tĩnh ({staticBeds.length})</span>
        </button>
      </div>

      {mainTab === 'drums' ? (
        <>
          {/* KPI Cards for Drums (Tạm thời ẩn các chỉ số chu kỳ đo nhiệt định kỳ) */}
          <div className="dp-kpi-grid">
            <div className="dp-kpi-card">
              <div className="dp-kpi-icon dp-icon-flame"><Flame size={22} /></div>
              <div className="dp-kpi-copy">
                <span>Trống đang sấy</span>
                <strong>
                  {drums.filter((d) => d.status === 'running').length} / {drums.length} trống
                </strong>
                <small>Đang cấp nhiệt / ủ trong ca</small>
              </div>
            </div>

            <div className="dp-kpi-card">
              <div className="dp-kpi-icon dp-icon-check"><CheckCircle2 size={22} /></div>
              <div className="dp-kpi-copy">
                <span>Trống sẵn sàng</span>
                <strong>
                  {drums.filter((d) => d.status !== 'running').length} / {drums.length} trống
                </strong>
                <small>Sẵn sàng nạp mẻ cà mới</small>
              </div>
            </div>

            <div className="dp-kpi-card">
              <div className="dp-kpi-icon dp-icon-flame" style={{ background: '#eff6ff', color: '#2563eb' }}><Layers size={22} /></div>
              <div className="dp-kpi-copy">
                <span>Sàn sấy tĩnh xưởng</span>
                <strong>{staticBeds.filter((b) => b.is_active).length} sàn</strong>
                <small>
                  {staticBedBatches.filter((b) => b.status === 'on_bed').length} sàn đang có mẻ làm ráo
                </small>
              </div>
            </div>

            <div className="dp-kpi-card">
              <div className="dp-kpi-icon dp-icon-inspect" style={{ background: '#f0fdf4', color: '#16a34a' }}><ShieldCheck size={22} /></div>
              <div className="dp-kpi-copy">
                <span>Trạng thái thiết bị</span>
                <strong style={{ color: '#16a34a' }}>Sẵn sàng vận hành</strong>
                <small>Hệ thống giám sát ổn định</small>
              </div>
            </div>
          </div>

          {/* Drums Cards Grid */}
          <div className="panel" style={{ padding: '20px' }}>
            <div className="panel-heading" style={{ marginBottom: '16px' }}>
              <div>
                <span className="section-kicker">DANH SÁCH THIẾT BỊ SẤY</span>
                <h2 style={{ fontSize: '18px', margin: '4px 0 0' }}>Trạng thái các trống sấy</h2>
              </div>
            </div>

            {drums.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                <Gauge size={36} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                <p>Chưa có trống sấy nào được thiết lập tại cơ sở này.</p>
                {isManagerOrAdmin && (
                  <Button size="sm" onClick={() => setCreateDrumModal(true)} style={{ marginTop: '10px' }}>
                    <Plus size={14} /> Khởi tạo trống sấy đầu tiên
                  </Button>
                )}
              </div>
            ) : (
              <div className="dp-drums-grid">
                {drums.map((drum) => {
                  const isRunning = drum.status === 'running'
                  return (
                    <div
                      key={drum.id}
                      className={`dp-drum-card ${isRunning ? 'is-running' : 'is-idle'}`}
                    >
                      <div className="dp-drum-header">
                        <div
                          className="dp-drum-title dp-drum-card-title-clickable"
                          onClick={() => void openDrumDetail(drum.id)}
                          title="Bấm để xem thông tin chi tiết & lịch sử vào trống"
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span className="dp-drum-code">{drum.drum_code}</span>
                            <span className="dp-badge-mode">
                              {drum.measurement_mode === 'two_ends' ? '📍 Đo 2 đầu' : '📍 Đo giữa'}
                            </span>
                          </div>
                          <h3>{drum.drum_name}</h3>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className={`dp-badge ${isRunning ? 'dp-badge-running' : 'dp-badge-idle'}`}>
                            {isRunning ? <Flame size={12} /> : null}
                            {isRunning ? 'Đang sấy' : 'Sẵn sàng'}
                          </span>
                          {isManagerOrAdmin && (
                            <button
                              type="button"
                              className="icon-button"
                              title="Cấu hình & đặc tính trống"
                              onClick={() => openEditDrum(drum)}
                              style={{ padding: '4px', color: '#64748b' }}
                            >
                              <Settings size={15} />
                            </button>
                          )}
                        </div>
                      </div>

                      <div className="dp-drum-body">
                        <div className="dp-stat-row">
                          <span>Sức chứa:</span>
                          <strong>
                            {drum.capacity_kg ? `${Number(drum.capacity_kg).toLocaleString('vi-VN')} kg` : 'Theo mẻ'}
                          </strong>
                        </div>

                        {(drum.has_moisture_imbalance || drum.has_blade_issue || drum.characteristics_notes) && (
                          <div className="dp-drum-defects">
                            {drum.has_moisture_imbalance && (
                              <span className="dp-tag-defect">⚠️ Lệch ẩm 2 đầu</span>
                            )}
                            {drum.has_blade_issue && (
                              <span className="dp-tag-defect">⚠️ Lỗi cánh đảo cà</span>
                            )}
                            {drum.characteristics_notes && (
                              <div className="dp-defect-note">ℹ️ {drum.characteristics_notes}</div>
                            )}
                          </div>
                        )}

                        {isRunning ? (
                          <>
                            <div className="dp-stat-row">
                              <span>Mã mẻ hiện tại:</span>
                              <strong style={{ color: '#ea580c' }}>{drum.active_batch_code}</strong>
                            </div>

                            <div className="dp-highlight-box" style={{ background: '#fff7ed', borderColor: '#fdba74' }}>
                              🔥 Mẻ đang sấy trong buồng. Nhấn <strong>Chi tiết mẻ sấy</strong> để theo dõi hoặc tắt nhiệt ủ / xả trống.
                            </div>
                          </>
                        ) : (
                          <p style={{ margin: 0, color: '#64748b', fontSize: '12px' }}>
                            Trống đang rảnh, sẵn sàng nạp mẻ cà phê mới.
                          </p>
                        )}
                      </div>

                      <div className="dp-drum-actions">
                        {isRunning && drum.active_run_id ? (
                          <Button
                            size="sm"
                            onClick={() => void openRunDetail(drum.active_run_id!)}
                            style={{ flex: 1 }}
                          >
                            <Eye size={14} /> Chi tiết mẻ sấy
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() => {
                              setCoffeeCategory('ca_qua')
                              setRatioQua(50)
                              setRatioLua(50)
                              setCustomCoffeeType('')
                              setInitialTemp('75.0')
                              setStartRunSourceType('indoor')
                              const defaultBed = staticBeds.find((b) => b.is_active) || null
                              setStartRunBedId(defaultBed ? defaultBed.id : null)
                              setStartRunSelectedBatchId(null)
                              if (defaultBed) {
                                void loadBedBatchesForStartRun(defaultBed.id)
                              } else {
                                setStartRunBedBatches([])
                              }
                              setStartRunDrum(drum)
                            }}
                            style={{ flex: 1 }}
                          >
                            <Plus size={14} /> Nạp mẻ vào trống
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          title="Xem thông tin chi tiết & lịch sử vào trống"
                          onClick={() => void openDrumDetail(drum.id)}
                        >
                          <Info size={14} /> Chi tiết trống
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          title="Xem chiến lược & lịch sử sấy"
                          onClick={() => void openStrategyForDrum(drum)}
                        >
                          <TrendingUp size={14} /> Chiến lược
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </>
      ) : (
        /* STATIC DRYING BEDS DASHBOARD VIEW */
        <>
          {/* Reference Notice Banner */}
          <div className="dp-incubation-banner" style={{ background: '#f0fdf4', borderColor: '#bbf7d0', color: '#166534', margin: '0 0 16px', display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
            <Lightbulb size={20} style={{ color: '#059669', flexShrink: 0, marginTop: '2px' }} />
            <div>
              <strong style={{ fontSize: '14px' }}>Quy trình tham chiếu sàn sấy tĩnh xưởng:</strong>
              <span style={{ display: 'block', marginTop: '2px', fontSize: '13px', lineHeight: 1.5 }}>
                Giai đoạn làm ráo nước trên sàn tĩnh thường kéo dài từ <strong>12–24 tiếng</strong>, định kỳ <strong>mỗi 3 tiếng</strong> thực hiện 1 lần đảo cà. Hệ thống ghi nhận linh hoạt theo thời gian và số lượt đảo thực tế của ca trực, cho phép hoàn tất và chuyển sang nạp trống sấy bất kỳ lúc nào.
              </span>
            </div>
          </div>

          {/* Static Bed KPIs */}
          {(() => {
            const activeOnBed = staticBedBatches.filter((b) => b.status === 'on_bed')
            const discharged = staticBedBatches.filter((b) => b.status === 'discharged')
            const evenCount = discharged.filter((b) => b.discharge_drain_status === 'even').length
            const evenRate = discharged.length > 0 ? Math.round((evenCount / discharged.length) * 100) : 100
            const spoiledCount = staticBedBatches.filter((b) => b.raw_material_status === 'spoiled').length

            return (
              <div className="dp-kpi-grid">
                <div className="dp-kpi-card">
                  <div className="dp-kpi-icon dp-icon-flame"><Layers size={22} /></div>
                  <div className="dp-kpi-copy">
                    <span>Sàn đang làm ráo</span>
                    <strong>{activeOnBed.length} / {staticBeds.length} sàn</strong>
                    <small>Đang có cà trên sàn sấy</small>
                  </div>
                </div>

                <div className="dp-kpi-card">
                  <div className="dp-kpi-icon dp-icon-check"><CheckCircle2 size={22} /></div>
                  <div className="dp-kpi-copy">
                    <span>Mẻ đã ra sàn</span>
                    <strong>{discharged.length} mẻ</strong>
                    <small>Sẵn sàng làm nguồn nạp trống</small>
                  </div>
                </div>

                <div className="dp-kpi-card">
                  <div className="dp-kpi-icon dp-icon-inspect"><Sparkles size={22} /></div>
                  <div className="dp-kpi-copy">
                    <span>Tỷ lệ ráo đều</span>
                    <strong style={{ color: '#047857' }}>{evenRate}%</strong>
                    <small>{evenCount} / {discharged.length} mẻ ráo đều</small>
                  </div>
                </div>

                <div className="dp-kpi-card">
                  <div className="dp-kpi-icon dp-icon-warn"><AlertTriangle size={22} /></div>
                  <div className="dp-kpi-copy">
                    <span>Mẻ có cà úng</span>
                    <strong style={{ color: spoiledCount > 0 ? '#ea580c' : '#0f172a' }}>{spoiledCount} mẻ</strong>
                    <small>Được theo dõi đối chiếu</small>
                  </div>
                </div>
              </div>
            )
          })()}

          {/* SÀN SẤY TĨNH CARDS GRID */}
          <div className="panel" style={{ padding: '20px' }}>
            <div className="panel-heading" style={{ marginBottom: '16px' }}>
              <div>
                <span className="section-kicker">KHU VỰC SÀN SẤY TĨNH XƯỞNG TRONG</span>
                <h2 style={{ fontSize: '18px', margin: '4px 0 0' }}>Trạng thái các sàn sấy ({staticBeds.length} sàn)</h2>
              </div>
            </div>

            {staticBeds.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                <Layers size={36} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                <p>Chưa có sàn sấy tĩnh nào được cấu hình tại cơ sở này.</p>
                {isManagerOrAdmin && (
                  <Button size="sm" onClick={() => setCreateStaticBedModal(true)} style={{ marginTop: '10px' }}>
                    <Plus size={14} /> Khởi tạo sàn sấy đầu tiên
                  </Button>
                )}
              </div>
            ) : (
              <div className="dp-beds-grid">
                {staticBeds.map((bed) => {
                  const currentBatch = staticBedBatches.find((b) => b.bed_id === bed.id && b.status === 'on_bed')
                  const isOnBed = Boolean(currentBatch)

                  const calcElapsed = (startStr: string) => {
                    const diffMs = Date.now() - new Date(startStr).getTime()
                    const diffMins = Math.max(0, Math.floor(diffMs / 60000))
                    const h = Math.floor(diffMins / 60)
                    const m = diffMins % 60
                    return `${h} tiếng ${m} phút`
                  }

                  return (
                    <div
                      key={bed.id}
                      className={`dp-bed-card ${isOnBed ? 'is-on-bed' : 'is-idle'}`}
                    >
                      <div className="dp-drum-header">
                        <div className="dp-drum-title">
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span className="dp-drum-code">SÀN {bed.bed_number}</span>
                            <span className="dp-badge-mode">{bed.bed_code}</span>
                          </div>
                          <h3>{bed.bed_name}</h3>
                        </div>
                        <div>
                          <span className={`dp-badge ${isOnBed ? 'dp-badge-on-bed' : 'dp-badge-idle'}`}>
                            {isOnBed ? 'Đang trên sàn' : 'Sẵn sàng'}
                          </span>
                        </div>
                      </div>

                      <div className="dp-drum-body">
                        {isOnBed && currentBatch ? (
                          <>
                            <div className="dp-stat-row">
                              <span>Mã mẻ cà:</span>
                              <strong style={{ color: '#ea580c', fontSize: '15px' }}>{currentBatch.batch_code}</strong>
                            </div>

                            {currentBatch.coffee_type && (
                              <div className="dp-stat-row">
                                <span>Loại cà phê:</span>
                                <strong style={{ color: '#047857' }}>{currentBatch.coffee_type}</strong>
                              </div>
                            )}

                            {currentBatch.input_weight_kg && (
                              <div className="dp-stat-row">
                                <span>Khối lượng vào sàn:</span>
                                <strong>{Number(currentBatch.input_weight_kg).toLocaleString('vi-VN')} kg</strong>
                              </div>
                            )}

                            <div className="dp-stat-row">
                              <span>Vào sàn lúc:</span>
                              <small>{dt(currentBatch.entered_at)}</small>
                            </div>

                            <div className="dp-stat-row">
                              <span>Thời gian trên sàn:</span>
                              <strong style={{ color: '#2563eb' }}>{calcElapsed(currentBatch.entered_at)}</strong>
                            </div>

                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', margin: '4px 0' }}>
                              <span
                                className="dp-badge"
                                style={{
                                  background: currentBatch.water_drained_status === 'wet' ? '#fff7ed' : '#ecfdf5',
                                  color: currentBatch.water_drained_status === 'wet' ? '#c2410c' : '#047857',
                                  border: '1px solid currentColor',
                                }}
                              >
                                {currentBatch.water_drained_status === 'wet' ? '💧 Cà Ướt' : '✨ Cà Ráo'}
                              </span>

                              <span
                                className="dp-badge"
                                style={{
                                  background: currentBatch.raw_material_status === 'spoiled' ? '#fef2f2' : '#ecfdf5',
                                  color: currentBatch.raw_material_status === 'spoiled' ? '#dc2626' : '#047857',
                                  border: '1px solid currentColor',
                                }}
                              >
                                {currentBatch.raw_material_status === 'spoiled'
                                  ? `⚠️ Cà Úng (${currentBatch.estimated_spoiled_percent !== null && currentBatch.estimated_spoiled_percent !== undefined ? `${currentBatch.estimated_spoiled_percent}%` : 'Chưa ước tính'})`
                                  : '✅ Cà Tươi'}
                              </span>

                              <span className="dp-badge" style={{ background: '#eff6ff', color: '#1d4ed8' }}>
                                🔄 {currentBatch.stirring_count} lượt đảo đã ghi
                              </span>
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="dp-stat-row">
                              <span>Sức chứa thiết kế:</span>
                              <strong>{bed.capacity_kg ? `${Number(bed.capacity_kg).toLocaleString('vi-VN')} kg` : 'Theo mẻ'}</strong>
                            </div>
                            <p style={{ margin: '8px 0 0', color: '#64748b', fontSize: '13px' }}>
                              Sàn đang trống rảnh, sẵn sàng tiếp nhận mẻ cà mới để làm ráo nước.
                            </p>
                          </>
                        )}
                      </div>

                      <div className="dp-drum-actions">
                        {isOnBed && currentBatch ? (
                          <>
                            <Button
                              size="sm"
                              onClick={() => {
                                setStirringModalBatch(currentBatch)
                              }}
                              style={{ flex: 1 }}
                            >
                              <Wind size={14} /> Ghi lượt đảo
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setDischargeDrainStatus('even')
                                setDischargeDryStatus('not_dry')
                                setDischargeBedModalBatch(currentBatch)
                              }}
                              style={{ borderColor: '#047857', color: '#047857' }}
                            >
                              <CheckCircle2 size={14} /> Đưa ra sàn
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void openBedBatchDetail(currentBatch.id)}
                            >
                              <Info size={14} /> Chi tiết
                            </Button>
                          </>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() => {
                              setSelectedBedForNewBatch(bed)
                              setEnterBedWaterStatus('wet')
                              setEnterBedRawMaterialStatus('fresh')
                              setEnterBedSpoiledPercent('')
                              setCreateBedBatchModal(true)
                            }}
                            style={{ flex: 1 }}
                          >
                            <Plus size={14} /> Đưa cà vào sàn này
                          </Button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* LỊCH SỬ MẺ ĐÃ RA SÀN */}
          {(() => {
            const dischargedBatches = staticBedBatches.filter((b) => b.status === 'discharged')
            const filteredDischarged = dischargedBatches.filter((b) => {
              if (staticBatchesFilter === 'even' && b.discharge_drain_status !== 'even') return false
              if (staticBatchesFilter === 'uneven' && b.discharge_drain_status !== 'uneven') return false
              if (staticBatchesFilter === 'spoiled' && b.raw_material_status !== 'spoiled') return false
              if (staticBatchSearch.trim()) {
                const q = staticBatchSearch.toLowerCase().trim()
                const matchCode = b.batch_code.toLowerCase().includes(q)
                const matchBed = `sàn ${b.bed_number}`.includes(q)
                const matchCoffee = (b.coffee_type || '').toLowerCase().includes(q)
                const matchOp = b.operator_name.toLowerCase().includes(q)
                if (!matchCode && !matchBed && !matchCoffee && !matchOp) return false
              }
              return true
            })

            return (
              <div className="panel" style={{ padding: '20px' }}>
                <div className="panel-heading" style={{ marginBottom: '16px' }}>
                  <div>
                    <span className="section-kicker">LỊCH SỬ HOÀN TẤT LÀM RÁO</span>
                    <h2 style={{ fontSize: '18px', margin: '4px 0 0' }}>
                      Lịch sử mẻ đã ra sàn ({filteredDischarged.length} / {dischargedBatches.length} mẻ)
                    </h2>
                  </div>
                </div>

                {/* Filter and Search Bar */}
                <div className="dp-history-toolbar">
                  <div className="dp-filter-tabs">
                    <button
                      type="button"
                      className={`dp-filter-tab ${staticBatchesFilter === 'all' ? 'is-active' : ''}`}
                      onClick={() => setStaticBatchesFilter('all')}
                    >
                      Tất cả ({dischargedBatches.length})
                    </button>
                    <button
                      type="button"
                      className={`dp-filter-tab ${staticBatchesFilter === 'even' ? 'is-active' : ''}`}
                      onClick={() => setStaticBatchesFilter('even')}
                    >
                      Ráo đều
                    </button>
                    <button
                      type="button"
                      className={`dp-filter-tab ${staticBatchesFilter === 'uneven' ? 'is-active' : ''}`}
                      onClick={() => setStaticBatchesFilter('uneven')}
                    >
                      Chưa ráo đều
                    </button>
                    <button
                      type="button"
                      className={`dp-filter-tab ${staticBatchesFilter === 'spoiled' ? 'is-active' : ''}`}
                      onClick={() => setStaticBatchesFilter('spoiled')}
                    >
                      Cà úng
                    </button>
                  </div>

                  <div className="dp-search-box">
                    <Search size={15} color="#94a3b8" />
                    <input
                      type="text"
                      placeholder="Tìm mã mẻ sàn, số sàn, thợ trực..."
                      value={staticBatchSearch}
                      onChange={(e) => setStaticBatchSearch(e.target.value)}
                    />
                    {staticBatchSearch && (
                      <button
                        type="button"
                        className="icon-button"
                        onClick={() => setStaticBatchSearch('')}
                        style={{ padding: '2px' }}
                      >
                        <X size={13} />
                      </button>
                    )}
                  </div>
                </div>

                {filteredDischarged.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>
                    <History size={32} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                    <p>Chưa có mẻ sàn nào phù hợp với bộ lọc tìm kiếm.</p>
                  </div>
                ) : (
                  <div className="dp-table-wrap">
                    <table className="dp-timeline-table">
                      <thead>
                        <tr>
                          <th>Mã mẻ & Sàn số</th>
                          <th>Loại cà & Khối lượng</th>
                          <th>Vào sàn · Ra sàn</th>
                          <th>Thời gian trên sàn</th>
                          <th>Số lượt đảo</th>
                          <th>Tình trạng lúc vào</th>
                          <th>Kết quả ra sàn</th>
                          <th>Thợ phụ trách</th>
                          <th>Thao tác</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredDischarged.map((b) => (
                          <tr key={b.id}>
                            <td>
                              <strong style={{ color: '#047857' }}>{b.batch_code}</strong>
                              <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                                Sàn số {b.bed_number} ({b.bed_code})
                              </div>
                            </td>

                            <td>
                              <span>{b.coffee_type || 'Cà quả thu hoạch'}</span>
                              {b.input_weight_kg && (
                                <div style={{ fontSize: '11px', color: '#64748b', marginTop: '1px' }}>
                                  {Number(b.input_weight_kg).toLocaleString('vi-VN')} kg
                                </div>
                              )}
                            </td>

                            <td>
                              <small>
                                Vào: <strong>{dt(b.entered_at)}</strong>
                                <br />
                                Ra: <strong>{b.discharged_at ? dt(b.discharged_at) : '—'}</strong>
                              </small>
                            </td>

                            <td>
                              <strong style={{ color: '#2563eb' }}>
                                {b.total_bed_duration_minutes
                                  ? `${Math.floor(b.total_bed_duration_minutes / 60)}h ${b.total_bed_duration_minutes % 60}p`
                                  : '—'}
                              </strong>
                            </td>

                            <td>
                              <span className="dp-badge" style={{ background: '#eff6ff', color: '#1d4ed8' }}>
                                {b.stirring_count} lượt đảo
                              </span>
                            </td>

                            <td>
                              <div>
                                <span style={{ fontWeight: 600, color: b.water_drained_status === 'wet' ? '#c2410c' : '#047857' }}>
                                  {b.water_drained_status === 'wet' ? 'Ướt' : 'Ráo'}
                                </span>
                                {' · '}
                                <span style={{ fontWeight: 600, color: b.raw_material_status === 'spoiled' ? '#dc2626' : '#047857' }}>
                                  {b.raw_material_status === 'spoiled'
                                    ? `Úng (${b.estimated_spoiled_percent !== null && b.estimated_spoiled_percent !== undefined ? `${b.estimated_spoiled_percent}%` : 'Chưa ước tính'})`
                                    : 'Tươi'}
                                </span>
                              </div>
                            </td>

                            <td>
                              <div>
                                <strong style={{ color: b.discharge_drain_status === 'even' ? '#059669' : '#d97706' }}>
                                  {b.discharge_drain_status === 'even' ? '🌟 Ráo đều' : b.discharge_drain_status === 'uneven' ? '⚠️ Chưa ráo đều' : '—'}
                                </strong>
                                {b.dry_status && (
                                  <span
                                    style={{
                                      marginLeft: '6px',
                                      fontSize: '11px',
                                      fontWeight: 600,
                                      padding: '1px 6px',
                                      borderRadius: '4px',
                                      background: b.dry_status === 'dry' ? '#fef2f2' : '#ecfdf5',
                                      color: b.dry_status === 'dry' ? '#dc2626' : '#047857',
                                      border: `1px solid ${b.dry_status === 'dry' ? '#fecaca' : '#a7f3d0'}`,
                                    }}
                                  >
                                    {b.dry_status === 'dry' ? '⚠️ Bị khô' : '✅ Không bị khô'}
                                  </span>
                                )}
                              </div>
                              {b.discharge_note && (
                                <div style={{ fontSize: '11px', color: '#64748b', fontStyle: 'italic', marginTop: '2px' }}>
                                  {b.discharge_note}
                                </div>
                              )}
                            </td>

                            <td>
                              <small>{b.operator_name}</small>
                            </td>

                            <td>
                              <Button size="sm" variant="outline" onClick={() => void openBedBatchDetail(b.id)}>
                                <Info size={13} /> Chi tiết
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })()}
        </>
      )}

      {renderModals()}
    </div>
  )

  function renderModals() {
    return (
      <>
        {/* MODAL 1: NẠP MẺ VÀO TRỐNG (START RUN) */}
        {startRunDrum && (
        <div className="dp-modal-scrim" onClick={() => setStartRunDrum(null)}>
          <div className="dp-modal dp-modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <div>
                <h2>Nạp mẻ cà vào {startRunDrum.drum_code}</h2>
                <small style={{ color: '#64748b' }}>{startRunDrum.drum_name}</small>
              </div>
              <button className="icon-button" onClick={() => setStartRunDrum(null)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleStartRun(e)} className="dp-modal-form">
              <label>
                Mã mẻ cà sấy
                <input
                  name="batch_code"
                  placeholder="Ví dụ: ME-20261116-01"
                  required
                  defaultValue={`ME-${new Date().toISOString().slice(2, 10).replace(/-/g, '')}-01`}
                />
              </label>

              {/* NGUỒN CÀ VÀO TRỐNG */}
              <div className="dp-form-section">
                <span className="dp-field-label">Nguồn cà vào trống</span>
                <div className="dp-source-selector">
                  <button
                    type="button"
                    className={`dp-source-pill ${startRunSourceType === 'indoor' ? 'is-selected' : ''}`}
                    onClick={() => {
                      setStartRunSourceType('indoor')
                      if (staticBeds.length > 0 && !startRunBedId) {
                        const firstBed = staticBeds.find((b) => b.is_active) || staticBeds[0]
                        setStartRunBedId(firstBed.id)
                        void loadBedBatchesForStartRun(firstBed.id)
                      }
                    }}
                  >
                    <span className="dp-pill-title">🏢 Sàn tĩnh xưởng trong</span>
                    <span className="dp-pill-desc">Chọn số sàn & liên kết mẻ đã làm ráo</span>
                  </button>

                  <button
                    type="button"
                    className={`dp-source-pill ${startRunSourceType === 'outdoor' ? 'is-selected' : ''}`}
                    onClick={() => {
                      setStartRunSourceType('outdoor')
                      setStartRunBedId(null)
                      setStartRunSelectedBatchId(null)
                    }}
                  >
                    <span className="dp-pill-title">☀️ Sàn tĩnh xưởng ngoài</span>
                    <span className="dp-pill-desc">Lưu nguồn xưởng ngoài (không bắt buộc số sàn)</span>
                  </button>
                </div>

                {/* Sàn tĩnh xưởng trong: Chọn số sàn & mẻ nguồn */}
                {startRunSourceType === 'indoor' && (
                  <div style={{ marginTop: '12px', padding: '14px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #cbd5e1' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px' }}>
                      <label>
                        <span style={{ fontWeight: 600 }}>Số sàn xưởng trong (Bắt buộc)</span>
                        <select
                          value={startRunBedId || ''}
                          onChange={(e) => {
                            const bedId = Number(e.target.value)
                            setStartRunBedId(bedId)
                            void loadBedBatchesForStartRun(bedId)
                          }}
                          required
                        >
                          <option value="" disabled>-- Chọn số sàn --</option>
                          {staticBeds.filter((b) => b.is_active).map((b) => (
                            <option key={b.id} value={b.id}>
                              Sàn {b.bed_number} ({b.bed_code})
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        <span style={{ fontWeight: 600 }}>Mẻ nguồn đã ra sàn</span>
                        <select
                          value={startRunSelectedBatchId || ''}
                          onChange={(e) => setStartRunSelectedBatchId(e.target.value ? Number(e.target.value) : null)}
                        >
                          {startRunBedBatches.length > 0 ? (
                            <>
                              <option value="">-- Không liên kết mẻ cụ thể (Chưa có bản ghi) --</option>
                              {startRunBedBatches.map((b) => (
                                <option key={b.id} value={b.id}>
                                  {b.batch_code} · {b.discharge_drain_status === 'even' ? 'Ráo đều' : 'Chưa ráo đều'}
                                  {b.raw_material_status === 'spoiled' ? ` (Úng ${b.estimated_spoiled_percent != null ? `${b.estimated_spoiled_percent}%` : 'Chưa ước tính'})` : ' (Tươi)'}
                                  {' · Ra sàn: '}{dt(b.discharged_at || b.entered_at)}
                                </option>
                              ))}
                            </>
                          ) : (
                            <option value="">-- Chưa có bản ghi mẻ sàn (Vẫn cho nạp trống) --</option>
                          )}
                        </select>
                      </label>
                    </div>

                    {startRunBedBatches.length === 0 ? (
                      <div style={{ fontSize: '12px', color: '#64748b', marginTop: '6px', fontStyle: 'italic' }}>
                        ℹ️ Sàn này hiện chưa có bản ghi mẻ đã ra sàn. Vẫn cho nạp trống bằng số sàn đã chọn. Chi tiết mẻ trống sẽ ghi rõ "Chưa có bản ghi mẻ sàn".
                      </div>
                    ) : (
                      <div style={{ fontSize: '12px', color: '#047857', marginTop: '6px' }}>
                        ✓ Một mẻ sàn có thể chia cho nhiều trống. Khi liên kết, thông tin ráo nước và độ úng sẽ tự động hiển thị trong chi tiết mẻ trống mà không cần nhập lại.
                      </div>
                    )}
                  </div>
                )}

                {startRunSourceType === 'outdoor' && (
                  <div style={{ fontSize: '12px', color: '#1d4ed8', marginTop: '8px', padding: '8px 12px', background: '#eff6ff', borderRadius: '6px', border: '1px solid #bfdbfe' }}>
                    ℹ️ Nguồn cà sẽ được lưu là "Sàn tĩnh xưởng ngoài". Không cần chọn số sàn hay tạo bản ghi mẻ sàn.
                  </div>
                )}
              </div>

              {/* LOẠI CÀ PHÊ VÀO TRỐNG */}
              <div className="dp-form-section">
                <span className="dp-field-label">Loại cà phê vào trống</span>
                <div className="dp-coffee-selector">
                  <button
                    type="button"
                    className={`dp-coffee-pill ${coffeeCategory === 'ca_qua' ? 'is-selected' : ''}`}
                    onClick={() => setCoffeeCategory('ca_qua')}
                  >
                    <span className="dp-pill-title">Cà quả sấy ráo</span>
                    <span className="dp-pill-desc">100% cà quả sấy ráo</span>
                  </button>

                  <button
                    type="button"
                    className={`dp-coffee-pill ${coffeeCategory === 'ca_lua' ? 'is-selected' : ''}`}
                    onClick={() => setCoffeeCategory('ca_lua')}
                  >
                    <span className="dp-pill-title">Cà lụa sấy ráo</span>
                    <span className="dp-pill-desc">100% cà lụa sấy ráo</span>
                  </button>

                  <button
                    type="button"
                    className={`dp-coffee-pill ${coffeeCategory === 'ca_tron' ? 'is-selected' : ''}`}
                    onClick={() => setCoffeeCategory('ca_tron')}
                  >
                    <span className="dp-pill-title">Cà quả trộn cà lụa</span>
                    <span className="dp-pill-desc">Tùy chỉnh % mỗi loại</span>
                  </button>

                  <button
                    type="button"
                    className={`dp-coffee-pill ${coffeeCategory === 'khac' ? 'is-selected' : ''}`}
                    onClick={() => setCoffeeCategory('khac')}
                  >
                    <span className="dp-pill-title">Tùy chỉnh khác</span>
                    <span className="dp-pill-desc">Nhập tên tự do</span>
                  </button>
                </div>

                {/* Sub-panel for ca_tron */}
                {coffeeCategory === 'ca_tron' && (
                  <div className="dp-blend-panel">
                    <div className="dp-blend-header">
                      <strong>Tỷ lệ phối trộn (% Khối lượng)</strong>
                      <span className="dp-blend-total">
                        Tổng: <strong>{ratioQua + ratioLua}%</strong>
                      </span>
                    </div>

                    <div className="dp-ratio-bar-wrap">
                      <div className="dp-ratio-bar">
                        <div
                          className="dp-ratio-segment dp-segment-qua"
                          style={{ width: `${ratioQua}%` }}
                        >
                          {ratioQua >= 15 ? `${ratioQua}% Quả` : ''}
                        </div>
                        <div
                          className="dp-ratio-segment dp-segment-lua"
                          style={{ width: `${ratioLua}%` }}
                        >
                          {ratioLua >= 15 ? `${ratioLua}% Lụa` : ''}
                        </div>
                      </div>
                    </div>

                    <div className="dp-blend-inputs">
                      <label>
                        <span>% Cà quả sấy ráo</span>
                        <div className="dp-input-suffix">
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="1"
                            value={ratioQua}
                            onChange={(e) => handleRatioQuaChange(Number(e.target.value))}
                            required
                          />
                          <span>%</span>
                        </div>
                      </label>

                      <label>
                        <span>% Cà lụa sấy ráo</span>
                        <div className="dp-input-suffix">
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="1"
                            value={ratioLua}
                            onChange={(e) => handleRatioLuaChange(Number(e.target.value))}
                            required
                          />
                          <span>%</span>
                        </div>
                      </label>
                    </div>

                    <div className="dp-preset-chips">
                      <span className="dp-preset-label">Tỷ lệ nhanh:</span>
                      <button
                        type="button"
                        className={`dp-chip ${ratioQua === 50 && ratioLua === 50 ? 'active' : ''}`}
                        onClick={() => {
                          setRatioQua(50)
                          setRatioLua(50)
                        }}
                      >
                        50% Quả / 50% Lụa
                      </button>
                      <button
                        type="button"
                        className={`dp-chip ${ratioQua === 60 && ratioLua === 40 ? 'active' : ''}`}
                        onClick={() => {
                          setRatioQua(60)
                          setRatioLua(40)
                        }}
                      >
                        60% Quả / 40% Lụa
                      </button>
                      <button
                        type="button"
                        className={`dp-chip ${ratioQua === 70 && ratioLua === 30 ? 'active' : ''}`}
                        onClick={() => {
                          setRatioQua(70)
                          setRatioLua(30)
                        }}
                      >
                        70% Quả / 30% Lụa
                      </button>
                      <button
                        type="button"
                        className={`dp-chip ${ratioQua === 80 && ratioLua === 20 ? 'active' : ''}`}
                        onClick={() => {
                          setRatioQua(80)
                          setRatioLua(20)
                        }}
                      >
                        80% Quả / 20% Lụa
                      </button>
                    </div>
                  </div>
                )}

                {/* Sub-panel for khac */}
                {coffeeCategory === 'khac' && (
                  <div className="dp-custom-panel">
                    <label>
                      Tên loại cà phê
                      <input
                        type="text"
                        placeholder="Ví dụ: Robusta chế biến ướt, Arabica chín cây..."
                        value={customCoffeeType}
                        onChange={(e) => setCustomCoffeeType(e.target.value)}
                        required
                        autoFocus
                      />
                    </label>
                  </div>
                )}
              </div>

              {/* KHỐI LƯỢNG NẠP & NHIỆT ĐỘ BAN ĐẦU */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <label>
                  Khối lượng nạp (kg)
                  <input
                    name="initial_weight"
                    type="number"
                    step="0.1"
                    placeholder="Ví dụ: 1200"
                    defaultValue={startRunDrum.capacity_kg ? String(startRunDrum.capacity_kg) : ''}
                  />
                </label>

                <label>
                  Nhiệt độ ban đầu (°C)
                  <div className="dp-input-suffix">
                    <input
                      name="initial_temperature"
                      type="number"
                      step="0.1"
                      min="0"
                      max="350"
                      placeholder="Ví dụ: 75.0"
                      value={initialTemp}
                      onChange={(e) => setInitialTemp(e.target.value)}
                    />
                    <span>°C</span>
                  </div>
                </label>
              </div>

              {/* NGÀY GIỜ VÀO TRỐNG & VỊ TRÍ ĐO NHIỆT (TẠM ẨN CHU KỲ KIỂM TRA ĐỊNH KỲ) */}
              <input type="hidden" name="cycle_minutes" value="30" />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <label>
                  Ngày / Giờ vào trống
                  <input name="entry_time" type="datetime-local" defaultValue={localNowInput()} required />
                </label>
                <label>
                  Vị trí đo nhiệt ban đầu
                  <input name="initial_temperature_location" maxLength={120} placeholder="Ví dụ: khí cấp; để trống nếu chưa rõ" />
                </label>
              </div>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setStartRunDrum(null)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading}>
                  Bắt đầu sấy mẻ
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: GHI NHẬT KÝ CHU KỲ (PERIODIC LOG) */}
      {logModalRun && (
        <div className="dp-modal-scrim" onClick={() => setLogModalRun(null)}>
          <div className="dp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <h2>Ghi nhật ký chu kỳ · {logModalRun.batch_code}</h2>
              <button className="icon-button" onClick={() => setLogModalRun(null)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleRecordLog(e)} className="dp-modal-form">
              <div className="dp-highlight-box">
                Đợt đo thứ <strong>#{logModalRun.logs.length + 1}</strong>. Thời điểm máy chủ nhận dữ liệu sẽ được lưu để đối soát kỷ luật ca trực.
              </div>

              {/* Warnings for Drum Characteristics */}
              {logModalRun.drum_has_moisture_imbalance && (
                <div className="dp-incubation-banner" style={{ background: '#fffbeb', borderColor: '#fde68a', color: '#b45309', padding: '10px 14px' }}>
                  <AlertTriangle size={18} />
                  <span><strong>Lưu ý đặc tính:</strong> Trống có hiện tượng lệch độ ẩm 2 đầu nặng. Hãy kẹp ẩm cả 2 đầu buồng sấy và ghi nhận chính xác để hệ thống cảnh báo chênh lệch.</span>
                </div>
              )}

              {logModalRun.drum_has_blade_issue && (
                <div className="dp-incubation-banner" style={{ background: '#fef2f2', borderColor: '#fecaca', color: '#b91c1c', padding: '10px 14px' }}>
                  <AlertTriangle size={18} />
                  <span><strong>Lỗi cánh đảo cà:</strong> Cà bên trong xáo trộn không đều. Vui lòng lấy mẫu sâu trong buồng sấy và đảo đều trước khi đo!</span>
                </div>
              )}

              {logModalRun.drum_measurement_mode === 'two_ends' ? (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <label>
                      Độ ẩm đầu trống (%)
                      <input
                        name="moisture_head_percent"
                        type="number"
                        step="0.01"
                        min="0"
                        max="100"
                        placeholder="Ví dụ: 29.5"
                        value={logHeadMoisture}
                        onChange={(e) => setLogHeadMoisture(e.target.value)}
                        autoFocus
                      />
                    </label>
                    <label>
                      Độ ẩm đuôi trống (%)
                      <input
                        name="moisture_tail_percent"
                        type="number"
                        step="0.01"
                        min="0"
                        max="100"
                        placeholder="Ví dụ: 27.5"
                        value={logTailMoisture}
                        onChange={(e) => setLogTailMoisture(e.target.value)}
                      />
                    </label>
                  </div>

                  {logHeadMoisture && logTailMoisture && !isNaN(parseFloat(logHeadMoisture)) && !isNaN(parseFloat(logTailMoisture)) && (
                    <div
                      className="dp-two-ends-pill"
                      style={{
                        borderColor: Math.abs(parseFloat(logHeadMoisture) - parseFloat(logTailMoisture)) > 1.5 ? '#fca5a5' : '#86efac',
                        background: Math.abs(parseFloat(logHeadMoisture) - parseFloat(logTailMoisture)) > 1.5 ? '#fef2f2' : '#f0fdf4',
                      }}
                    >
                      <span>Độ ẩm trung bình: <strong style={{ color: '#0284c7' }}>{((parseFloat(logHeadMoisture) + parseFloat(logTailMoisture)) / 2).toFixed(2)}%</strong></span>
                      <span> · Chênh lệch 2 đầu: <strong style={{ color: Math.abs(parseFloat(logHeadMoisture) - parseFloat(logTailMoisture)) > 1.5 ? '#dc2626' : '#059669' }}>Δ {Math.abs(parseFloat(logHeadMoisture) - parseFloat(logTailMoisture)).toFixed(2)}%</strong></span>
                      {Math.abs(parseFloat(logHeadMoisture) - parseFloat(logTailMoisture)) > 1.5 && (
                        <span style={{ color: '#dc2626', fontWeight: 600 }}> (⚠️ Chênh lệch cao &gt; 1.5%)</span>
                      )}
                    </div>
                  )}

                  <label>
                    Nhiệt độ luồng hơi (°C)
                    <input
                      name="temperature_celsius"
                      type="number"
                      step="0.1"
                      min="0"
                      max="350"
                      placeholder="Ví dụ: 75.0"
                      required
                    />
                  </label>
                </>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <label>
                    Độ ẩm cà giữa trống (%)
                    <input
                      name="moisture_percent"
                      type="number"
                      step="0.01"
                      min="0"
                      max="100"
                      placeholder="Ví dụ: 28.5"
                      required
                      autoFocus
                    />
                  </label>
                  <label>
                    Nhiệt độ luồng hơi (°C)
                    <input
                      name="temperature_celsius"
                      type="number"
                      step="0.1"
                      min="0"
                      max="350"
                      placeholder="Ví dụ: 75.0"
                      required
                    />
                  </label>
                </div>
              )}

              <label>Vị trí đo nhiệt<input name="temperature_location" placeholder="Ví dụ: khí cấp; để trống nếu chưa rõ" maxLength={120} /></label>
              <label>
                Thời điểm đo thực tế
                <input name="measured_at" type="datetime-local" defaultValue={localNowInput()} required />
              </label>

              <label>
                Ghi chú tình trạng hạt / luồng hơi
                <input name="note" placeholder="Ví dụ: Hơi cấp đều, cà đã se mặt vỏ" />
              </label>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setLogModalRun(null)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading}>
                  Lưu nhật ký chu kỳ
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: TẮT NHIỆT & BẮT ĐẦU Ủ (STOP HEAT) */}
      {stopHeatModalRun && (
        <div className="dp-modal-scrim" onClick={() => setStopHeatModalRun(null)}>
          <div className="dp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <h2>Tắt nhiệt & Bắt đầu ủ · {stopHeatModalRun.batch_code}</h2>
              <button className="icon-button" onClick={() => setStopHeatModalRun(null)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleStopHeat(e)} className="dp-modal-form">
              <div className="dp-highlight-box" style={{ background: '#f0fdf4', borderColor: '#86efac', color: '#166534' }}>
                💡 <strong>Kinh nghiệm sấy:</strong> Khi tắt nhiệt, cà phê vẫn được ủ trong trống để độ ẩm giảm dần và hạt chín đều từ trong lõi ra ngoài vỏ.
              </div>

              <label>
                Thời điểm tắt nhiệt buồng đốt
                <input name="heat_off_at" type="datetime-local" defaultValue={localNowInput()} required />
              </label>

              <label>
                Độ ẩm đo được khi tắt nhiệt (%)
                <input
                  name="moisture_at_heat_off"
                  type="number"
                  step="0.01"
                  min="0"
                  max="100"
                  placeholder="Ví dụ: 15.5"
                  defaultValue={
                    stopHeatModalRun.logs.length
                      ? String(stopHeatModalRun.logs[stopHeatModalRun.logs.length - 1].moisture_percent)
                      : ''
                  }
                  required
                />
                <small style={{ color: '#64748b' }}>
                  Thông thường tắt nhiệt khi độ ẩm còn khoảng 15% - 16% để ủ xuống 12.5% là cà đẹp nhất.
                </small>
              </label>

              <label>
                Thời điểm tắt trống quay (nếu khác thời điểm tắt nhiệt)
                <input name="rotation_off_at" type="datetime-local" defaultValue={localNowInput()} />
              </label>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setStopHeatModalRun(null)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading} style={{ background: '#ea580c', borderColor: '#ea580c' }}>
                  Xác nhận tắt nhiệt & Ủ
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 4: XẢ TRỐNG / RA TRỐNG (DISCHARGE) */}
      {dischargeModalRun && (
        <div className="dp-modal-scrim" onClick={() => setDischargeModalRun(null)}>
          <div className="dp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <h2>Xả trống / Ra trống · {dischargeModalRun.batch_code}</h2>
              <button className="icon-button" onClick={() => setDischargeModalRun(null)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleDischarge(e)} className="dp-modal-form">
              {dischargeModalRun.heat_off_at && (
                <div className="dp-incubation-banner">
                  <strong>⏱ Mẻ sấy đã được ủ từ: {dt(dischargeModalRun.heat_off_at)}</strong>
                  {dischargeModalRun.moisture_at_heat_off && (
                    <span>Độ ẩm khi tắt nhiệt: {dischargeModalRun.moisture_at_heat_off}%</span>
                  )}
                </div>
              )}

              <label>
                Ngày / Giờ ra trống thực tế
                <input name="exit_time" type="datetime-local" defaultValue={localNowInput()} required />
              </label>

              {dischargeModalRun.drum_measurement_mode === 'two_ends' ? (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <label>
                      Độ ẩm đầu trống khi ra (%)
                      <input
                        name="final_moisture_head_percent"
                        type="number"
                        step="0.01"
                        min="0"
                        max="100"
                        placeholder="Ví dụ: 12.8"
                        value={dischargeHeadMoisture}
                        onChange={(e) => setDischargeHeadMoisture(e.target.value)}
                        required
                        autoFocus
                      />
                    </label>
                    <label>
                      Độ ẩm đuôi trống khi ra (%)
                      <input
                        name="final_moisture_tail_percent"
                        type="number"
                        step="0.01"
                        min="0"
                        max="100"
                        placeholder="Ví dụ: 12.2"
                        value={dischargeTailMoisture}
                        onChange={(e) => setDischargeTailMoisture(e.target.value)}
                        required
                      />
                    </label>
                  </div>
                  {dischargeHeadMoisture && dischargeTailMoisture && !isNaN(parseFloat(dischargeHeadMoisture)) && !isNaN(parseFloat(dischargeTailMoisture)) && (
                    <div className="dp-two-ends-pill">
                      <span>Độ ẩm TB ra trống: <strong style={{ color: '#0284c7' }}>{((parseFloat(dischargeHeadMoisture) + parseFloat(dischargeTailMoisture)) / 2).toFixed(2)}%</strong></span>
                      <span> · Chênh lệch: <strong>Δ {Math.abs(parseFloat(dischargeHeadMoisture) - parseFloat(dischargeTailMoisture)).toFixed(2)}%</strong></span>
                    </div>
                  )}
                </>
              ) : (
                <label>
                  Kết quả độ ẩm khi ra trống (%)
                  <input
                    name="final_moisture_percent"
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    placeholder="Ví dụ: 12.5"
                    required
                    autoFocus
                  />
                  <small style={{ color: '#64748b' }}>Độ ẩm chuẩn kho thường từ 12.0% - 13.0%</small>
                </label>
              )}

              <label>
                Đánh giá chất lượng cà ra trống
                <select name="quality_assessment" defaultValue="ca_dep">
                  <option value="ca_dep">Cà đẹp (Hạt đều màu, khô chuẩn, bóng đẹp, thơm)</option>
                  <option value="dat_chuan">Đạt chuẩn (Độ ẩm đạt ngưỡng lưu kho)</option>
                  <option value="ca_xau">Cà xấu (Khô quá mức, sém cạnh hoặc ẩm chưa đều)</option>
                </select>
              </label>

              <label>
                Nhận xét chi tiết về chất lượng mẻ sấy
                <input
                  name="quality_note"
                  placeholder="Ví dụ: Màu sắc đồng đều, mùi thơm nhẹ, không vỡ hạt..."
                />
              </label>

              <label>
                Ghi chú xuất kho / chuyển xưởng
                <textarea
                  name="discharge_note"
                  rows={2}
                  placeholder="Ví dụ: Đóng bao chờ chuyển sang kho phân loại."
                />
              </label>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setDischargeModalRun(null)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading}>
                  Xác nhận xả trống
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 5: THANH TRA NGẪU NHIÊN (INSPECTION) */}
      {inspectModalRun && (
        <div className="dp-modal-scrim" onClick={() => setInspectModalRun(null)}>
          <div className="dp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <h2>Thanh tra ngẫu nhiên · {inspectModalRun.batch_code}</h2>
              <button className="icon-button" onClick={() => setInspectModalRun(null)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleInspection(e)} className="dp-modal-form">
              <div className="dp-highlight-box" style={{ background: '#eff6ff', borderColor: '#93c5fd', color: '#1e40af' }}>
                Thanh tra đột xuất độc lập tại hiện trường. Hệ thống sẽ tự động so sánh sai lệch với số liệu thợ trông trống vừa báo cáo để phát hiện gian lận hoặc sai sót kỹ thuật.
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <label>
                  Mẫu độ ẩm thanh tra (%)
                  <input
                    name="sample_moisture_percent"
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    placeholder="Ví dụ: 28.2"
                    required
                  />
                </label>
                <label>
                  Mẫu nhiệt độ luồng hơi (°C)
                  <input
                    name="sample_temperature_celsius"
                    type="number"
                    step="0.1"
                    min="0"
                    max="350"
                    placeholder="Ví dụ: 78.0"
                    required
                  />
                </label>
              </div>

              <label>
                Thời điểm thanh tra
                <input name="inspected_at" type="datetime-local" defaultValue={localNowInput()} required />
              </label>

              <label>
                Nhận xét / Đánh giá của thanh tra
                <textarea
                  name="notes"
                  rows={2}
                  placeholder="Ghi nhận hiện trạng lò đốt, đồng hồ áp suất và máy đo..."
                />
              </label>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setInspectModalRun(null)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading}>
                  Lưu kết quả thanh tra
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 6: THÊM TRỐNG MỚI (CREATE DRUM) */}
      {createDrumModal && (
        <div className="dp-modal-scrim" onClick={() => setCreateDrumModal(false)}>
          <div className="dp-modal dp-modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <h2>Thêm trống sấy mới</h2>
              <button className="icon-button" onClick={() => setCreateDrumModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleCreateDrum(e)} className="dp-modal-form">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <label>
                  Mã định danh trống
                  <input name="drum_code" placeholder="Ví dụ: TRONG-03" required />
                </label>
                <label>
                  Sức chứa thiết kế (kg)
                  <input name="capacity_kg" type="number" step="10" placeholder="Ví dụ: 2000" />
                </label>
              </div>

              <label>
                Tên trống sấy
                <input name="drum_name" placeholder="Ví dụ: Trống sấy tầng 1 - Số 3" required />
              </label>

              {/* PHƯƠNG THỨC ĐO ĐỘ ẨM */}
              <div className="dp-form-section">
                <span className="dp-field-label">Phương thức đo độ ẩm của thợ trống</span>
                <div className="dp-mode-selector">
                  <button
                    type="button"
                    className={`dp-mode-card ${createMeasurementMode === 'center_only' ? 'is-selected' : ''}`}
                    onClick={() => setCreateMeasurementMode('center_only')}
                  >
                    <span className="dp-mode-title">📍 Đo giữa trống</span>
                    <span className="dp-mode-desc">Chỉ đo 1 điểm tâm buồng sấy (mặc định chuẩn)</span>
                  </button>
                  <button
                    type="button"
                    className={`dp-mode-card ${createMeasurementMode === 'two_ends' ? 'is-selected' : ''}`}
                    onClick={() => setCreateMeasurementMode('two_ends')}
                  >
                    <span className="dp-mode-title">📍 Đo 2 đầu buồng sấy</span>
                    <span className="dp-mode-desc">Đo độ ẩm cả đầu trống và đuôi trống để theo dõi sai lệch</span>
                  </button>
                </div>
              </div>

              {/* ĐẶC TÍNH VÀ LỖI CƠ HỌC */}
              <div className="dp-form-section">
                <span className="dp-field-label">Đặc tính kỹ thuật & Lỗi cơ học của trống</span>
                <div className="dp-checkbox-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={createHasMoistureImbalance}
                      onChange={(e) => setCreateHasMoistureImbalance(e.target.checked)}
                    />
                    <span>Trống bị lệch độ ẩm cà 2 đầu nặng (cần theo dõi độ lệch đầu - đuôi)</span>
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={createHasBladeIssue}
                      onChange={(e) => setCreateHasBladeIssue(e.target.checked)}
                    />
                    <span>Trống bị lỗi cánh đảo cà (cà bên trong xáo trộn không đều, ra không đồng nhất)</span>
                  </label>
                </div>
              </div>

              <label>
                Ghi chú chi tiết đặc tính trống
                <textarea
                  rows={2}
                  placeholder="Ví dụ: Đầu gió nóng hơn đuôi 2-3 độ, cần đảo tay thêm khi ra cà..."
                  value={createCharacteristicsNotes}
                  onChange={(e) => setCreateCharacteristicsNotes(e.target.value)}
                />
              </label>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setCreateDrumModal(false)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading}>
                  Tạo trống
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 6b: CẬP NHẬT ĐẶC TÍNH TRỐNG SẤY (EDIT DRUM) */}
      {editDrumModal && (
        <div className="dp-modal-scrim" onClick={() => setEditDrumModal(null)}>
          <div className="dp-modal dp-modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <div>
                <h2>Cấu hình thiết bị · {editDrumModal.drum_code}</h2>
                <small style={{ color: '#64748b' }}>Cập nhật phương thức đo và tình trạng cơ học</small>
              </div>
              <button className="icon-button" onClick={() => setEditDrumModal(null)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleUpdateDrum(e)} className="dp-modal-form">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <label>
                  Tên trống sấy
                  <input
                    name="drum_name"
                    defaultValue={editDrumModal.drum_name}
                    required
                  />
                </label>
                <label>
                  Sức chứa thiết kế (kg)
                  <input
                    name="capacity_kg"
                    type="number"
                    step="10"
                    defaultValue={editDrumModal.capacity_kg ? String(editDrumModal.capacity_kg) : ''}
                  />
                </label>
              </div>

              {/* PHƯƠNG THỨC ĐO ĐỘ ẨM */}
              <div className="dp-form-section">
                <span className="dp-field-label">Phương thức đo độ ẩm của thợ trông</span>
                <div className="dp-mode-selector">
                  <button
                    type="button"
                    className={`dp-mode-card ${editMeasurementMode === 'center_only' ? 'is-selected' : ''}`}
                    onClick={() => setEditMeasurementMode('center_only')}
                  >
                    <span className="dp-mode-title">📍 Đo giữa trống</span>
                    <span className="dp-mode-desc">Chỉ đo 1 điểm tâm buồng sấy (tiêu chuẩn)</span>
                  </button>
                  <button
                    type="button"
                    className={`dp-mode-card ${editMeasurementMode === 'two_ends' ? 'is-selected' : ''}`}
                    onClick={() => setEditMeasurementMode('two_ends')}
                  >
                    <span className="dp-mode-title">📍 Đo 2 đầu buồng sấy</span>
                    <span className="dp-mode-desc">Thợ sẽ nhập cả đầu trống & đuôi trống</span>
                  </button>
                </div>
              </div>

              {/* ĐẶC TÍNH VÀ LỖI CƠ HỌC */}
              <div className="dp-form-section">
                <span className="dp-field-label">Tình trạng cơ học & Lỗi kỹ thuật</span>
                <div className="dp-checkbox-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={editHasMoistureImbalance}
                      onChange={(e) => setEditHasMoistureImbalance(e.target.checked)}
                    />
                    <span>Trống bị lệch độ ẩm cà 2 đầu nặng</span>
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={editHasBladeIssue}
                      onChange={(e) => setEditHasBladeIssue(e.target.checked)}
                    />
                    <span>Trống bị lỗi cánh đảo cà (cà bên trong ra không đều)</span>
                  </label>
                </div>
              </div>

              <label>
                Ghi chú kinh nghiệm / tình trạng thiết bị
                <textarea
                  rows={2}
                  placeholder="Ghi nhận lỗi cơ học hoặc lưu ý cho thợ trực..."
                  value={editCharacteristicsNotes}
                  onChange={(e) => setEditCharacteristicsNotes(e.target.value)}
                />
              </label>

              <div className="dp-modal-actions" style={{ justifyContent: 'space-between' }}>
                {isManagerOrAdmin && (
                  <Button
                    type="button"
                    variant="outline"
                    style={{ borderColor: '#ef4444', color: '#ef4444' }}
                    onClick={() => void handleDeleteDrum(editDrumModal)}
                    disabled={loading}
                  >
                    🗑️ Xóa trống này
                  </Button>
                )}
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Button type="button" variant="outline" onClick={() => setEditDrumModal(null)}>
                    Hủy
                  </Button>
                  <Button type="submit" disabled={loading}>
                    Lưu thay đổi
                  </Button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 7: CHIẾN LƯỢC SẤY & LỊCH SỬ TỪNG TRỐNG (STRATEGY & HISTORY) */}
      {analyticsDrum && analyticsData && (
        <div className="dp-modal-scrim" onClick={() => setAnalyticsDrum(null)}>
          <div
            className="dp-modal"
            style={{ maxWidth: '900px', maxHeight: '90vh', overflowY: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="dp-modal-header">
              <div>
                <h2>Chiến lược & Lịch sử sấy · {analyticsData.drum_code}</h2>
                <small style={{ color: '#64748b' }}>
                  {analyticsData.drum_name} · Sức chứa: {analyticsData.capacity_kg ? `${analyticsData.capacity_kg} kg` : 'Theo mẻ'}
                </small>
              </div>
              <button className="icon-button" onClick={() => setAnalyticsDrum(null)}>
                <X size={18} />
              </button>
            </div>

            <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Strategy Header & Advice */}
              <div className="dp-strategy-panel">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Lightbulb size={20} color="#ea580c" />
                  <strong style={{ fontSize: '16px', color: '#0f172a' }}>Chiến lược sấy tối ưu đúc kết từ thực tế</strong>
                </div>

                <div className="dp-strategy-grid">
                  <div className="dp-strategy-metric">
                    <span>Nhiệt độ luồng hơi</span>
                    <strong>{analyticsData.strategy.recommended_heat_temp_celsius ? `${analyticsData.strategy.recommended_heat_temp_celsius}°C` : '75-80°C'}</strong>
                    <small>Nhiệt độ cấp ổn định</small>
                  </div>
                  <div className="dp-strategy-metric">
                    <span>Độ ẩm nên tắt nhiệt</span>
                    <strong style={{ color: '#ea580c' }}>
                      {analyticsData.strategy.recommended_stop_heat_moisture ? `${analyticsData.strategy.recommended_stop_heat_moisture}%` : '15.0 - 16.0%'}
                    </strong>
                    <small>Ngưỡng ngắt luồng nhiệt</small>
                  </div>
                  <div className="dp-strategy-metric">
                    <span>Thời gian ủ khuyến nghị</span>
                    <strong style={{ color: '#059669' }}>
                      {analyticsData.strategy.recommended_incubation_minutes ? `${analyticsData.strategy.recommended_incubation_minutes} phút` : '30-45 phút'}
                    </strong>
                    <small>Ủ hạt chín đều trong trống</small>
                  </div>
                  <div className="dp-strategy-metric">
                    <span>Giảm ẩm khi ủ</span>
                    <strong style={{ color: '#0284c7' }}>
                      ~{analyticsData.strategy.expected_incubation_moisture_drop ? `${analyticsData.strategy.expected_incubation_moisture_drop}%` : '2.5%'}
                    </strong>
                    <small>Về mức ~{analyticsData.strategy.expected_final_moisture || '12.5'}%</small>
                  </div>
                </div>

                <div className="dp-strategy-summary-box">
                  <strong>💡 Gợi ý cho thợ trống: </strong>
                  {analyticsData.strategy.strategy_summary}
                </div>
              </div>

              {/* History Table */}
              <div className="panel" style={{ padding: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <History size={17} />
                    <strong style={{ fontSize: '15px' }}>Lịch sử các mẻ sấy gần nhất ({analyticsData.history.length})</strong>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', fontSize: '12px' }}>
                    <span>Cà đẹp: <strong style={{ color: '#059669' }}>{analyticsData.ca_dep_count}</strong></span>
                    <span>· Đạt chuẩn: <strong style={{ color: '#2563eb' }}>{analyticsData.dat_chuan_count}</strong></span>
                    <span>· Cà xấu: <strong style={{ color: '#dc2626' }}>{analyticsData.ca_xau_count}</strong></span>
                  </div>
                </div>

                {analyticsData.history.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '30px', color: '#94a3b8' }}>
                    <Info size={24} style={{ margin: '0 auto 6px', opacity: 0.5 }} />
                    <p>Chưa có mẻ sấy nào hoàn tất trên trống này.</p>
                  </div>
                ) : (
                  <div className="dp-table-wrap">
                    <table className="dp-timeline-table">
                      <thead>
                        <tr>
                          <th>Mã mẻ</th>
                          <th>Thời gian sấy / ủ</th>
                          <th>Ẩm tắt nhiệt</th>
                          <th>Ẩm ra trống</th>
                          <th>Giảm khi ủ</th>
                          <th>Đánh giá</th>
                          <th>Ghi chú & Thợ trực</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analyticsData.history.map((item) => (
                          <tr key={item.id}>
                            <td>
                              <strong>{item.batch_code}</strong>
                              {item.coffee_type && (
                                <div style={{ fontSize: '11px', color: '#047857', marginTop: '2px', fontWeight: 600 }}>
                                  {item.coffee_type}
                                </div>
                              )}
                              {item.initial_temperature_celsius !== null && item.initial_temperature_celsius !== undefined && (
                                <div style={{ fontSize: '11px', color: '#ea580c', marginTop: '1px' }}>
                                  Nhiệt ban đầu: <strong>{item.initial_temperature_celsius}°C</strong>
                                </div>
                              )}
                              <small style={{ color: '#64748b' }}>{dt(item.entry_time)}</small>
                            </td>
                            <td>
                              <small>
                                Sấy nhiệt: <strong>{item.heat_duration_minutes ? `${item.heat_duration_minutes}p` : '—'}</strong>
                                <br />
                                Thời gian ủ: <strong style={{ color: '#059669' }}>{item.incubation_minutes ? `${item.incubation_minutes}p` : '—'}</strong>
                              </small>
                            </td>
                            <td>
                              {item.moisture_at_heat_off ? `${item.moisture_at_heat_off}%` : '—'}
                            </td>
                            <td>
                              <strong style={{ color: '#0284c7' }}>
                                {item.final_moisture_percent ? `${item.final_moisture_percent}%` : '—'}
                              </strong>
                            </td>
                            <td>
                              {item.moisture_drop_in_incubation ? (
                                <span style={{ color: '#059669', fontWeight: 600 }}>
                                  -{item.moisture_drop_in_incubation}%
                                </span>
                              ) : (
                                '—'
                              )}
                            </td>
                            <td>{renderQualityBadge(item.quality_assessment)}</td>
                            <td>
                              <small>
                                {item.quality_note || '—'}
                                <br />
                                <em>Thợ: {item.operator_name}</em>
                              </small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="dp-modal-actions">
                <Button variant="outline" onClick={() => setAnalyticsDrum(null)}>
                  Đóng
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: ĐƯA CÀ VÀO SÀN SẤY TĨNH */}
      {createBedBatchModal && (
        <div className="dp-modal-scrim" onClick={() => setCreateBedBatchModal(false)}>
          <div className="dp-modal dp-modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <div>
                <h2>Đưa cà vào sàn sấy tĩnh</h2>
                <small style={{ color: '#64748b' }}>
                  {selectedBedForNewBatch
                    ? `Sàn ${selectedBedForNewBatch.bed_number} (${selectedBedForNewBatch.bed_name})`
                    : 'Ghi nhận mẻ làm ráo mới'}
                </small>
              </div>
              <button className="icon-button" onClick={() => setCreateBedBatchModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleCreateBedBatch(e)} className="dp-modal-form">
              <label>
                Số sàn sấy tĩnh (Bắt buộc)
                <select
                  name="bed_id"
                  defaultValue={selectedBedForNewBatch?.id || ''}
                  required
                >
                  {staticBeds.filter((b) => b.is_active).map((b) => (
                    <option key={b.id} value={b.id}>
                      Sàn {b.bed_number} ({b.bed_code} · {b.bed_name})
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Mã mẻ cà trên sàn
                <input
                  name="batch_code"
                  placeholder="Ví dụ: SAN2-20261119-01"
                  required
                  defaultValue={`SAN${selectedBedForNewBatch?.bed_number || 1}-${new Date().toISOString().slice(2, 10).replace(/-/g, '')}-01`}
                />
              </label>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <label>
                  Loại cà phê
                  <input name="coffee_type" placeholder="Ví dụ: Cà quả tươi, cà lụa..." defaultValue="Cà quả tươi thu hái" />
                </label>

                <label>
                  Khối lượng vào sàn (kg)
                  <input
                    name="input_weight_kg"
                    type="number"
                    step="0.1"
                    placeholder="Ví dụ: 2500"
                    defaultValue={selectedBedForNewBatch?.capacity_kg ? String(selectedBedForNewBatch.capacity_kg) : '2400'}
                  />
                </label>
              </div>

              <label>
                Ngày / Giờ thực tế đưa cà vào sàn
                <input name="entered_at" type="datetime-local" defaultValue={localNowInput()} required />
              </label>

              {/* TÌNH TRẠNG RÁO NƯỚC: RÁO HOẶC ƯỚT */}
              <div className="dp-form-section">
                <span className="dp-field-label">Tình trạng ráo nước lúc vào sàn</span>
                <div className="dp-segmented-group">
                  <button
                    type="button"
                    className={`dp-segment-btn ${enterBedWaterStatus === 'drained' ? 'is-active-primary' : ''}`}
                    onClick={() => setEnterBedWaterStatus('drained')}
                  >
                    ✨ Ráo
                  </button>
                  <button
                    type="button"
                    className={`dp-segment-btn ${enterBedWaterStatus === 'wet' ? 'is-active-warning' : ''}`}
                    onClick={() => setEnterBedWaterStatus('wet')}
                  >
                    💧 Ướt
                  </button>
                </div>
              </div>

              {/* TÌNH TRẠNG NGUYÊN LIỆU: TƯƠI HOẶC ÚNG */}
              <div className="dp-form-section">
                <span className="dp-field-label">Tình trạng nguyên liệu (Độc lập với Ráo/Ướt)</span>
                <div className="dp-segmented-group">
                  <button
                    type="button"
                    className={`dp-segment-btn ${enterBedRawMaterialStatus === 'fresh' ? 'is-active-primary' : ''}`}
                    onClick={() => setEnterBedRawMaterialStatus('fresh')}
                  >
                    ✅ Tươi
                  </button>
                  <button
                    type="button"
                    className={`dp-segment-btn ${enterBedRawMaterialStatus === 'spoiled' ? 'is-active-danger' : ''}`}
                    onClick={() => setEnterBedRawMaterialStatus('spoiled')}
                  >
                    ⚠️ Úng
                  </button>
                </div>

                {enterBedRawMaterialStatus === 'spoiled' && (
                  <div style={{ marginTop: '10px', padding: '10px 14px', background: '#fef2f2', borderRadius: '8px', border: '1px solid #fecaca' }}>
                    <label style={{ margin: 0 }}>
                      <span style={{ fontWeight: 600, color: '#b91c1c' }}>Tỷ lệ cà úng ước tính (%)</span>
                      <div className="dp-input-suffix" style={{ marginTop: '4px' }}>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          step="0.1"
                          placeholder="Để trống nếu chưa ước tính"
                          value={enterBedSpoiledPercent}
                          onChange={(e) => setEnterBedSpoiledPercent(e.target.value)}
                        />
                        <span>%</span>
                      </div>
                      <small style={{ color: '#64748b', display: 'block', marginTop: '4px' }}>
                        Có thể để trống nếu chưa ước tính được (hệ thống sẽ hiển thị là "Chưa ước tính").
                      </small>
                    </label>
                  </div>
                )}
              </div>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setCreateBedBatchModal(false)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading}>
                  Xác nhận vào sàn
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: GHI NHẬN LƯỢT ĐẢO CÀ */}
      {stirringModalBatch && (
        <div className="dp-modal-scrim" onClick={() => setStirringModalBatch(null)}>
          <div className="dp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <div>
                <h2>Ghi nhận lượt đảo cà</h2>
                <small style={{ color: '#64748b' }}>
                  Sàn {stirringModalBatch.bed_number} · Mẻ {stirringModalBatch.batch_code}
                </small>
              </div>
              <button className="icon-button" onClick={() => setStirringModalBatch(null)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleRecordStirring(e)} className="dp-modal-form">
              <div className="dp-highlight-box">
                Đợt đảo thứ <strong>#{stirringModalBatch.stirring_count + 1}</strong>. Quy trình chuẩn khuyến nghị đảo mỗi ~3 tiếng trong giai đoạn làm ráo 12–24h.
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <label>
                  Giờ bắt đầu đảo
                  <input name="started_at" type="datetime-local" defaultValue={localNowInput()} required />
                </label>

                <label>
                  Giờ kết thúc đảo (Tùy chọn)
                  <input name="ended_at" type="datetime-local" />
                </label>
              </div>

              <label>
                Hoặc thời lượng đảo thực tế (phút)
                <div className="dp-input-suffix">
                  <input name="duration_minutes" type="number" min="1" max="1440" defaultValue="20" />
                  <span>phút</span>
                </div>
              </label>

              <label>
                Phương pháp đảo
                <input name="stirring_method" placeholder="Ví dụ: Cào đảo thủ công bằng cào gỗ" defaultValue="Cào đảo thủ công" />
              </label>

              <label>
                Ghi chú tình trạng hạt / mặt sàn
                <input name="note" placeholder="Ví dụ: Mặt sàn ráo nhẹ, thông thoáng, không bị ứ nước" />
              </label>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setStirringModalBatch(null)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading}>
                  Lưu lượt đảo
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: ĐƯA CÀ RA SÀN SẤY TĨNH */}
      {dischargeBedModalBatch && (
        <div className="dp-modal-scrim" onClick={() => setDischargeBedModalBatch(null)}>
          <div className="dp-modal dp-modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <div>
                <h2>Đưa cà ra sàn (Hoàn tất làm ráo)</h2>
                <small style={{ color: '#64748b' }}>
                  Sàn {dischargeBedModalBatch.bed_number} · Mẻ {dischargeBedModalBatch.batch_code}
                </small>
              </div>
              <button className="icon-button" onClick={() => setDischargeBedModalBatch(null)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleDischargeBed(e)} className="dp-modal-form">
              <div className="dp-highlight-box">
                Vào sàn lúc: <strong>{dt(dischargeBedModalBatch.entered_at)}</strong> · Đã thực hiện: <strong>{dischargeBedModalBatch.stirring_count} lượt đảo</strong>.
              </div>

              <label>
                Ngày / Giờ thực tế đưa cà ra sàn
                <input name="discharged_at" type="datetime-local" defaultValue={localNowInput()} required />
              </label>

              {/* ĐÁNH GIÁ MỨC RÁO NƯỚC SAU SÀN TĨNH: BẮT BUỘC RÁO ĐỀU HOẶC CHƯA RÁO ĐỀU */}
              <div className="dp-form-section">
                <span className="dp-field-label">Đánh giá mức ráo nước sau sàn (Bắt buộc)</span>
                <div className="dp-segmented-group">
                  <button
                    type="button"
                    className={`dp-segment-btn ${dischargeDrainStatus === 'even' ? 'is-active-primary' : ''}`}
                    onClick={() => setDischargeDrainStatus('even')}
                  >
                    🌟 Ráo đều
                  </button>
                  <button
                    type="button"
                    className={`dp-segment-btn ${dischargeDrainStatus === 'uneven' ? 'is-active-warning' : ''}`}
                    onClick={() => setDischargeDrainStatus('uneven')}
                  >
                    ⚠️ Chưa ráo đều
                  </button>
                </div>
                <small style={{ color: '#64748b', display: 'block', marginTop: '6px' }}>
                  ℹ️ "Ráo đều" là đánh giá mức độ ráo nước sau giai đoạn sàn tĩnh; không quy đổi thành độ ẩm thành phẩm hay kết quả QC của trống sấy.
                </small>
              </div>

              {/* TÌNH TRẠNG CÀ CÓ BỊ KHÔ HAY KHÔNG (BẮT BUỘC) */}
              <div className="dp-form-section">
                <span className="dp-field-label">Tình trạng cà có bị khô không? (Bắt buộc)</span>
                <div className="dp-segmented-group">
                  <button
                    type="button"
                    className={`dp-segment-btn ${dischargeDryStatus === 'not_dry' ? 'is-active-primary' : ''}`}
                    onClick={() => setDischargeDryStatus('not_dry')}
                  >
                    ✅ Không bị khô (Vỏ mềm, ráo nước đạt chuẩn)
                  </button>
                  <button
                    type="button"
                    className={`dp-segment-btn ${dischargeDryStatus === 'dry' ? 'is-active-danger' : ''}`}
                    onClick={() => setDischargeDryStatus('dry')}
                  >
                    ⚠️ Bị khô (Cà bị khô vỏ / quá nhiệt trên sàn)
                  </button>
                </div>
                <small style={{ color: '#64748b', display: 'block', marginTop: '6px' }}>
                  ℹ️ Kiểm tra độ mềm của vỏ và nhân: Sàn tĩnh chỉ làm ráo nước bề mặt, cần xác nhận xem cà có bị khô quắt/khô quá mức trước khi nạp vào trống sấy hay không.
                </small>
              </div>

              <label>
                Ghi chú vùng còn ướt hoặc lưu ý khác
                <textarea
                  name="discharge_note"
                  rows={3}
                  placeholder="Mô tả cụ thể nếu có vùng còn ướt, hạt bị khô hoặc lưu ý để thợ trông trống điều chỉnh nhiệt..."
                />
              </label>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setDischargeBedModalBatch(null)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading}>
                  Hoàn tất đưa cà ra sàn
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: CHI TIẾT MẺ SÀN SẤY TĨNH */}
      {detailBedBatchModal && (
        <div className="dp-modal-scrim" onClick={() => setDetailBedBatchModal(null)}>
          <div className="dp-modal dp-modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <div>
                <h2>Chi tiết mẻ sàn {detailBedBatchModal.batch_code}</h2>
                <small style={{ color: '#64748b' }}>
                  Sàn số {detailBedBatchModal.bed_number} ({detailBedBatchModal.bed_name})
                </small>
              </div>
              <button className="icon-button" onClick={() => setDetailBedBatchModal(null)}>
                <X size={18} />
              </button>
            </div>

            <div className="dp-modal-body">
              <div className="dp-specs-grid">
                <div className="dp-specs-card">
                  <span>Trạng thái mẻ</span>
                  <strong style={{ color: detailBedBatchModal.status === 'discharged' ? '#047857' : '#ea580c' }}>
                    {detailBedBatchModal.status === 'discharged' ? 'Đã ra sàn' : 'Đang trên sàn'}
                  </strong>
                  <small>{detailBedBatchModal.operator_name}</small>
                </div>

                <div className="dp-specs-card">
                  <span>Tình trạng ráo vào sàn</span>
                  <strong>{detailBedBatchModal.water_drained_status === 'wet' ? '💧 Cà Ướt' : '✨ Cà Ráo'}</strong>
                  <small>Ghi nhận lúc vào</small>
                </div>

                <div className="dp-specs-card">
                  <span>Tình trạng nguyên liệu</span>
                  <strong style={{ color: detailBedBatchModal.raw_material_status === 'spoiled' ? '#dc2626' : '#047857' }}>
                    {detailBedBatchModal.raw_material_status === 'spoiled'
                      ? `⚠️ Úng (${detailBedBatchModal.estimated_spoiled_percent != null ? `${detailBedBatchModal.estimated_spoiled_percent}%` : 'Chưa ước tính'})`
                      : '✅ Tươi'}
                  </strong>
                  <small>Tỷ lệ úng ban đầu</small>
                </div>

                <div className="dp-specs-card">
                  <span>Kết quả ráo nước</span>
                  <strong>
                    {detailBedBatchModal.discharge_drain_status === 'even'
                      ? '🌟 Ráo đều'
                      : detailBedBatchModal.discharge_drain_status === 'uneven'
                      ? '⚠️ Chưa ráo đều'
                      : 'Chưa ra sàn'}
                  </strong>
                  <small>Mức ráo sau sàn</small>
                </div>

                <div className="dp-specs-card">
                  <span>Tình trạng khô hạt</span>
                  <strong
                    style={{
                      color:
                        detailBedBatchModal.status !== 'discharged'
                          ? '#94a3b8'
                          : detailBedBatchModal.dry_status === 'dry'
                          ? '#dc2626'
                          : '#047857',
                    }}
                  >
                    {detailBedBatchModal.status !== 'discharged'
                      ? 'Chưa ra sàn'
                      : detailBedBatchModal.dry_status === 'dry'
                      ? '⚠️ Bị khô'
                      : '✅ Không bị khô'}
                  </strong>
                  <small>Đánh giá lúc ra sàn</small>
                </div>
              </div>

              <div className="dp-highlight-box" style={{ fontSize: '13px' }}>
                Vào sàn lúc: <strong>{dt(detailBedBatchModal.entered_at)}</strong>
                {detailBedBatchModal.discharged_at && (
                  <> · Ra sàn lúc: <strong>{dt(detailBedBatchModal.discharged_at)}</strong></>
                )}
                {detailBedBatchModal.total_bed_duration_minutes && (
                  <> · Tổng thời gian trên sàn: <strong style={{ color: '#2563eb' }}>{Math.floor(detailBedBatchModal.total_bed_duration_minutes / 60)}h {detailBedBatchModal.total_bed_duration_minutes % 60}p</strong></>
                )}
                {detailBedBatchModal.discharge_note && (
                  <div style={{ marginTop: '4px', fontStyle: 'italic', color: '#64748b' }}>
                    Ghi chú ra sàn: "{detailBedBatchModal.discharge_note}"
                  </div>
                )}
              </div>

              {/* Stirrings History */}
              <div className="panel" style={{ padding: '16px', margin: 0, borderRadius: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <strong style={{ fontSize: '14px' }}>Nhật ký các lượt đảo ({detailBedBatchModal.stirrings.length} lượt)</strong>
                </div>

                {detailBedBatchModal.stirrings.length === 0 ? (
                  <p style={{ textAlign: 'center', color: '#94a3b8', padding: '20px' }}>Chưa ghi nhận lượt đảo nào cho mẻ này.</p>
                ) : (
                  <div className="dp-table-wrap">
                    <table className="dp-timeline-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Giờ bắt đầu</th>
                          <th>Thời lượng / Kết thúc</th>
                          <th>Phương pháp</th>
                          <th>Ghi chú kiểm tra</th>
                          <th>Thợ đảo</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detailBedBatchModal.stirrings.map((s) => (
                          <tr key={s.id}>
                            <td><strong>#{s.stirring_number}</strong></td>
                            <td>{dt(s.started_at)}</td>
                            <td>{s.duration_minutes ? `${s.duration_minutes} phút` : s.ended_at ? dt(s.ended_at) : '—'}</td>
                            <td>{s.stirring_method || 'Đảo cào tay'}</td>
                            <td>{s.note || '—'}</td>
                            <td><small>{s.operator_name}</small></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="dp-modal-actions" style={{ marginTop: '16px', justifyContent: 'space-between' }}>
                {isManagerOrAdmin && (
                  <Button
                    type="button"
                    variant="outline"
                    style={{ borderColor: '#ef4444', color: '#ef4444' }}
                    onClick={() => void handleDeleteBedBatch(detailBedBatchModal.id, detailBedBatchModal.batch_code)}
                    disabled={loading}
                  >
                    🗑️ Xóa mẻ sàn này
                  </Button>
                )}
                <Button variant="outline" onClick={() => setDetailBedBatchModal(null)}>
                  Đóng
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: THÊM SÀN SẤY TĨNH MỚI */}
      {createStaticBedModal && (
        <div className="dp-modal-scrim" onClick={() => setCreateStaticBedModal(false)}>
          <div className="dp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="dp-modal-header">
              <h2>Thêm sàn sấy tĩnh mới</h2>
              <button className="icon-button" onClick={() => setCreateStaticBedModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={(e) => void handleCreateStaticBed(e)} className="dp-modal-form">
              <label>
                Số thứ tự sàn
                <input
                  name="bed_number"
                  type="number"
                  min="1"
                  max="100"
                  defaultValue={staticBeds.length + 1}
                  required
                />
              </label>

              <label>
                Mã định danh sàn
                <input
                  name="bed_code"
                  placeholder="Ví dụ: SAN-05"
                  defaultValue={`SAN-0${staticBeds.length + 1}`}
                  required
                />
              </label>

              <label>
                Tên hiển thị sàn sấy
                <input
                  name="bed_name"
                  placeholder="Ví dụ: Sàn sấy tĩnh số 5 (Xưởng trong)"
                  defaultValue={`Sàn sấy tĩnh số ${staticBeds.length + 1} (Xưởng trong)`}
                  required
                />
              </label>

              <label>
                Sức chứa thiết kế (kg)
                <input name="capacity_kg" type="number" step="0.1" placeholder="Ví dụ: 2500" defaultValue="2500" />
              </label>

              <div className="dp-modal-actions">
                <Button type="button" variant="outline" onClick={() => setCreateStaticBedModal(false)}>
                  Hủy
                </Button>
                <Button type="submit" disabled={loading}>
                  Thêm sàn sấy
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
}
