import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle, ArrowDownLeft, ArrowUpRight, Calendar, Camera, Check,
  Clock3, Edit3, Eye, RefreshCw, Scale, Search, Sparkles, Truck, X
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import CameraLivePanel from './CameraLivePanel'
import './VehiclePilotPage.css'

type Facility = { id: number; code: string; name: string }

type Visit = {
  visit_id: string
  facility_id: number
  camera_id: string
  source_mode: 'live' | 'replay'
  source_ref: string | null
  start_media_seconds: string | null
  end_media_seconds: string | null
  observed_at_utc: string | null
  received_at_utc: string
  status: string
  version: number
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  plate_text?: string | null
  plate_source?: 'confirmed' | 'suggestion' | 'unknown'
  review_state?: 'confirmed' | 'unknown' | 'needs_review'
  identifier_kind?: string | null
  prediction_source?: string | null
  scale_weight_kg?: string | null
  thumbnail_url?: string | null
}

type Trip = {
  trip_id: string
  plate_text: string
  status: 'completed' | 'in_yard'
  trip_type: 'import' | 'export' | 'reweigh' | 'unknown'
  goods_weight_kg: string | null
  first_visit: Visit
  second_visit: Visit | null
  created_at: string
}

type TripsResponse = {
  trips: Trip[]
  total_trips: number
  kpis: {
    total_import_kg: string
    total_export_kg: string
    total_import_tons: string
    total_export_tons: string
    in_yard_count: number
    completed_count: number
    total_trips: number
  }
  date: string
  total_visits_today: number
}

const api = '/api/vehicle-pilot'

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${api}${path}`, {
    credentials: 'same-origin',
    cache: 'no-store',
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init.headers || {}),
    },
  })
  if (!response.ok) {
    let message = `API trả HTTP ${response.status}.`
    try {
      const value = await response.json()
      message = value.detail?.message || value.detail || message
    } catch {
      // Keep default
    }
    throw new Error(typeof message === 'string' ? message : `API trả HTTP ${response.status}.`)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

export default function VehiclePilotPage({
  facilities,
  initialFacilityId,
  csrf,
  isAdmin: _isAdmin,
}: {
  facilities: Facility[]
  initialFacilityId: number | null
  csrf: string
  isAdmin?: boolean
}) {
  const [facilityId, setFacilityId] = useState<number | 'all'>(
    initialFacilityId ?? (facilities[0]?.id ?? 'all')
  )
  const [viewMode, setViewMode] = useState<'trips' | 'timeline'>('trips')
  const [dateFilter, setDateFilter] = useState(() => new Date().toISOString().slice(0, 10))
  const [statusFilter, setStatusFilter] = useState<'all' | 'in_yard' | 'import' | 'export'>('all')
  const [searchPlate, setSearchPlate] = useState('')

  // Trips data
  const [tripsData, setTripsData] = useState<TripsResponse | null>(null)
  // Timeline visits data
  const [timelineVisits, setTimelineVisits] = useState<Visit[]>([])
  const [timelineTotal, setTimelineTotal] = useState(0)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  // Modal / Quick edit state
  const [editingVisit, setEditingVisit] = useState<{ id: string; plate: string; version: number } | null>(null)
  const [editPlateValue, setEditPlateValue] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)
  const [aiLoadingId, setAiLoadingId] = useState<string | null>(null)
  const [previewImage, setPreviewImage] = useState<{ url: string; title: string } | null>(null)

  const loadData = useCallback(async (signal?: AbortSignal) => {
    try {
      setError('')
      const facQuery = facilityId !== 'all' ? `&facility_id=${facilityId}` : ''

      if (viewMode === 'trips') {
        const result = await request<TripsResponse>(
          `/visits/trips?day=${dateFilter}${facQuery}`,
          { signal }
        )
        setTripsData(result)
      } else {
        const fromIso = new Date(`${dateFilter}T00:00:00+07:00`).toISOString()
        const toIso = new Date(`${dateFilter}T23:59:59+07:00`).toISOString()
        const params = new URLSearchParams({
          page: '1',
          page_size: '50',
          observed_from: fromIso,
          observed_to: toIso,
        })
        if (facilityId !== 'all') params.set('facility_id', String(facilityId))
        if (searchPlate.trim()) params.set('plate', searchPlate.trim())
        const result = await request<{ items: Visit[]; total: number }>(`/visits?${params}`, { signal })
        setTimelineVisits(result.items)
        setTimelineTotal(result.total)
      }
    } catch (err) {
      if (signal?.aborted) return
      setError(err instanceof Error ? err.message : 'Không tải được dữ liệu chuyến xe.')
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [facilityId, viewMode, dateFilter, searchPlate])

  useEffect(() => {
    setLoading(true)
    const controller = new AbortController()
    void loadData(controller.signal)
    return () => controller.abort()
  }, [loadData])

  // Call Google Gemini Vision OCR
  const triggerGoogleAiOcr = async (visitId: string) => {
    setAiLoadingId(visitId)
    setNotice('')
    setError('')
    try {
      const res = await request<{ plate_text: string }>(`/visits/${visitId}/gemini-ocr`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrf },
      })
      setNotice(`Google AI đã nhận diện thành công biển số: ${res.plate_text}`)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi khi gọi Google AI nhận diện biển số.')
    } finally {
      setAiLoadingId(null)
    }
  }

  // Quick edit plate number
  const savePlateEdit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!editingVisit || !editPlateValue.trim()) return
    setSavingEdit(true)
    setError('')
    try {
      await request(`/visits/${editingVisit.id}/confirmations`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrf },
        body: JSON.stringify({
          expected_version: editingVisit.version,
          decision: {
            action: 'confirmed',
            identifier_kind: 'tractor_plate',
            confirmed_text: editPlateValue.trim().toUpperCase(),
          },
          note: 'Chỉnh sửa nhanh bởi quản lý',
        }),
      })
      setNotice(`Đã cập nhật biển số: ${editPlateValue.trim().toUpperCase()}`)
      setEditingVisit(null)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không lưu được biển số.')
    } finally {
      setSavingEdit(false)
    }
  }

  // Filtered trips
  const filteredTrips = useMemo(() => {
    if (!tripsData) return []
    return tripsData.trips.filter((t) => {
      if (statusFilter === 'in_yard' && t.status !== 'in_yard') return false
      if (statusFilter === 'import' && t.trip_type !== 'import') return false
      if (statusFilter === 'export' && t.trip_type !== 'export') return false
      if (searchPlate.trim()) {
        const query = searchPlate.trim().toLowerCase().replace(/[-. ]/g, '')
        const p = t.plate_text.toLowerCase().replace(/[-. ]/g, '')
        return p.includes(query)
      }
      return true
    })
  }, [tripsData, statusFilter, searchPlate])

  const formatWeight = (kgStr: string | null | undefined) => {
    if (!kgStr) return '—'
    const kg = Number(kgStr)
    if (isNaN(kg)) return '—'
    return `${kg.toLocaleString('vi-VN')} kg`
  }

  const formatTime = (iso: string | null | undefined) => {
    if (!iso) return '—'
    return new Intl.DateTimeFormat('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Ho_Chi_Minh',
    }).format(new Date(iso))
  }

  return (
    <div className="page-content vehicle-trips-page">
      {/* Top Banner & Header */}
      <section className="welcome-row">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" /> QUẢN LÝ VẬN HÀNH TRẠM CÂN
          </div>
          <h1>Chuyến xe xuất / nhập hàng</h1>
          <p className="page-subtitle">
            Theo dõi lượt xe vào và ra khỏi xưởng, tự động xác định chuyến Nhập hoặc Xuất dựa trên trọng lượng cân 2 lượt.
          </p>
        </div>
        <div className="trips-header-actions">
          <Button variant="outline" onClick={() => void loadData()} disabled={loading} className="refresh-btn">
            <RefreshCw size={15} className={loading ? 'spin' : ''} /> Tải lại
          </Button>
        </div>
      </section>

      {/* KPI Cards Row */}
      {tripsData && (
        <section className="trips-kpis-grid" aria-label="Thống kê sản lượng trong ngày">
          <div className="trip-kpi-card import-card">
            <div className="kpi-top">
              <span className="kpi-icon import-icon"><ArrowDownLeft size={20} /></span>
              <span className="kpi-tag">Nhập hàng</span>
            </div>
            <div className="kpi-number">{Number(tripsData.kpis.total_import_tons).toLocaleString('vi-VN')} <small>tấn</small></div>
            <div className="kpi-sub">{Number(tripsData.kpis.total_import_kg).toLocaleString('vi-VN')} kg hàng nhập vào xưởng</div>
          </div>

          <div className="trip-kpi-card export-card">
            <div className="kpi-top">
              <span className="kpi-icon export-icon"><ArrowUpRight size={20} /></span>
              <span className="kpi-tag">Xuất hàng</span>
            </div>
            <div className="kpi-number">{Number(tripsData.kpis.total_export_tons).toLocaleString('vi-VN')} <small>tấn</small></div>
            <div className="kpi-sub">{Number(tripsData.kpis.total_export_kg).toLocaleString('vi-VN')} kg hàng xuất giao đi</div>
          </div>

          <div className="trip-kpi-card in-yard-card">
            <div className="kpi-top">
              <span className="kpi-icon in-yard-icon"><Clock3 size={20} /></span>
              <span className="kpi-tag">Đang trong xưởng</span>
            </div>
            <div className="kpi-number">{tripsData.kpis.in_yard_count} <small>xe</small></div>
            <div className="kpi-sub">Đã cân lần 1, đang bốc dỡ chờ cân lần 2</div>
          </div>

          <div className="trip-kpi-card completed-card">
            <div className="kpi-top">
              <span className="kpi-icon completed-icon"><Check size={20} /></span>
              <span className="kpi-tag">Hoàn tất</span>
            </div>
            <div className="kpi-number">{tripsData.kpis.completed_count} <small>chuyến</small></div>
            <div className="kpi-sub">Đã hoàn thành cả 2 lượt cân trong ngày</div>
          </div>
        </section>
      )}

      {/* Notifications */}
      {notice && (
        <div className="trips-alert alert-success" role="status">
          <Check size={16} /> <span>{notice}</span>
          <button className="alert-close" onClick={() => setNotice('')}><X size={14} /></button>
        </div>
      )}
      {error && (
        <div className="trips-alert alert-error" role="alert">
          <AlertCircle size={16} /> <span>{error}</span>
          <button className="alert-close" onClick={() => setError('')}><X size={14} /></button>
        </div>
      )}

      {/* Control Bar: Filters & View Switcher */}
      <section className="trips-control-bar panel">
        <div className="view-switcher" role="tablist">
          <button
            className={`tab-btn ${viewMode === 'trips' ? 'tab-active' : ''}`}
            onClick={() => setViewMode('trips')}
            role="tab"
            aria-selected={viewMode === 'trips'}
          >
            <Truck size={16} /> Chuyến xe ghép cặp {tripsData ? `(${tripsData.total_trips})` : ''}
          </button>
          <button
            className={`tab-btn ${viewMode === 'timeline' ? 'tab-active' : ''}`}
            onClick={() => setViewMode('timeline')}
            role="tab"
            aria-selected={viewMode === 'timeline'}
          >
            <Scale size={16} /> Tất cả lượt cân {timelineTotal ? `(${timelineTotal})` : ''}
          </button>
        </div>

        <div className="filter-controls">
          <div className="control-group">
            <Calendar size={15} className="control-icon" />
            <input
              type="date"
              aria-label="Chọn ngày"
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="control-input"
            />
          </div>

          <div className="control-group search-group">
            <Search size={15} className="control-icon" />
            <input
              type="text"
              placeholder="Tìm biển số xe..."
              value={searchPlate}
              onChange={(e) => setSearchPlate(e.target.value)}
              className="control-input"
            />
            {searchPlate && (
              <button className="clear-search" onClick={() => setSearchPlate('')} aria-label="Xóa tìm kiếm">
                <X size={13} />
              </button>
            )}
          </div>

          {viewMode === 'trips' && (
            <div className="control-group">
              <select
                aria-label="Lọc trạng thái"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as any)}
                className="control-select"
              >
                <option value="all">Tất cả chuyến xe</option>
                <option value="in_yard">Đang trong xưởng (Cân lần 1)</option>
                <option value="import">Xe nhập hàng (Lần 1 &gt; Lần 2)</option>
                <option value="export">Xe xuất hàng (Lần 1 &lt; Lần 2)</option>
              </select>
            </div>
          )}

          {facilities.length > 1 && (
            <div className="control-group">
              <select
                aria-label="Chọn cơ sở"
                value={facilityId}
                onChange={(e) => setFacilityId(e.target.value === 'all' ? 'all' : Number(e.target.value))}
                className="control-select"
              >
                <option value="all">Tất cả cơ sở</option>
                {facilities.map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      </section>

      {/* Main Content Area */}
      {viewMode === 'trips' ? (
        /* Trips Pairing View */
        <section className="trips-content-section">
          {loading && !tripsData ? (
            <div className="trips-loading-state panel">
              <RefreshCw size={24} className="spin" />
              <p>Đang tổng hợp dữ liệu chuyến xe...</p>
            </div>
          ) : !filteredTrips.length ? (
            <div className="trips-empty-state panel">
              <Truck size={36} strokeWidth={1.5} />
              <h3>Không có chuyến xe nào phù hợp</h3>
              <p>Chưa có dữ liệu lượt cân của ngày được chọn hoặc bộ lọc không khớp.</p>
            </div>
          ) : (
            <div className="trips-cards-list">
              {filteredTrips.map((trip) => {
                const isImport = trip.trip_type === 'import'
                const isExport = trip.trip_type === 'export'
                const isInYard = trip.status === 'in_yard'
                const v1 = trip.first_visit
                const v2 = trip.second_visit

                return (
                  <article key={trip.trip_id} className={`trip-card panel ${trip.trip_type}`}>
                    {/* Header: Plate & Status badge */}
                    <div className="trip-card-header">
                      <div className="plate-badge-row">
                        {v1.thumbnail_url ? (
                          <button
                            className="plate-thumb-btn"
                            onClick={() => setPreviewImage({ url: v1.thumbnail_url!, title: trip.plate_text })}
                            title="Bấm xem ảnh camera"
                          >
                            <img src={v1.thumbnail_url} alt={trip.plate_text} className="plate-thumb" />
                            <Eye size={12} className="thumb-hover-icon" />
                          </button>
                        ) : (
                          <div className="plate-thumb-placeholder"><Truck size={18} /></div>
                        )}
                        <div>
                          <div className="plate-title-row">
                            <span className="plate-number">{trip.plate_text}</span>
                            <button
                              className="quick-edit-btn"
                              title="Sửa biển số"
                              onClick={() => {
                                setEditingVisit({ id: v1.visit_id, plate: trip.plate_text, version: v1.version })
                                setEditPlateValue(trip.plate_text === 'Chưa rõ biển' ? '' : trip.plate_text)
                              }}
                            >
                              <Edit3 size={13} /> Sửa
                            </button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="ai-ocr-btn"
                              disabled={aiLoadingId === v1.visit_id}
                              onClick={() => void triggerGoogleAiOcr(v1.visit_id)}
                              title="Gọi Google Gemini Vision đọc lại biển số"
                            >
                              <Sparkles size={13} className={aiLoadingId === v1.visit_id ? 'spin' : ''} />
                              {aiLoadingId === v1.visit_id ? 'Đang đọc...' : 'Google AI'}
                            </Button>
                          </div>
                          <span className="camera-tag">Camera: {v1.camera_id}</span>
                        </div>
                      </div>

                      <div className="trip-status-pill">
                        {isInYard && (
                          <span className="badge badge-in-yard">
                            <Clock3 size={13} /> Đang trong xưởng (Cân lần 1)
                          </span>
                        )}
                        {isImport && (
                          <span className="badge badge-import">
                            <ArrowDownLeft size={13} /> Nhập hàng vào xưởng
                          </span>
                        )}
                        {isExport && (
                          <span className="badge badge-export">
                            <ArrowUpRight size={13} /> Xuất hàng đi giao
                          </span>
                        )}
                        {trip.trip_type === 'reweigh' && (
                          <span className="badge badge-reweigh">Cân lại / Không chênh lệch</span>
                        )}
                      </div>
                    </div>

                    {/* Weighing Details Row */}
                    <div className="weighings-flow-grid">
                      {/* Weighing 1 */}
                      <div className="weighing-box box-first">
                        <div className="box-label">Lượt cân 1 ({isImport ? 'Xe + Hàng vào' : isExport ? 'Xe rỗng vào' : 'Lượt vào'})</div>
                        <div className="box-weight">{formatWeight(v1.scale_weight_kg)}</div>
                        <div className="box-time">Lúc {formatTime(v1.observed_at_utc || v1.created_at)}</div>
                      </div>

                      {/* Arrow / Flow */}
                      <div className="flow-divider">
                        <span className="flow-line" />
                        <span className="flow-symbol">➜</span>
                      </div>

                      {/* Weighing 2 */}
                      <div className={`weighing-box box-second ${!v2 ? 'box-pending' : ''}`}>
                        <div className="box-label">Lượt cân 2 ({isImport ? 'Xe rỗng ra' : isExport ? 'Xe + Hàng ra' : 'Lượt ra'})</div>
                        {v2 ? (
                          <>
                            <div className="box-weight">{formatWeight(v2.scale_weight_kg)}</div>
                            <div className="box-time">Lúc {formatTime(v2.observed_at_utc || v2.created_at)}</div>
                          </>
                        ) : (
                          <div className="box-waiting">
                            <Clock3 size={14} className="spin-slow" /> Chờ xe bốc dỡ xong lên cân...
                          </div>
                        )}
                      </div>

                      {/* Result / Net Weight */}
                      <div className="weighing-result-box">
                        <div className="result-label">Khối lượng hàng tịnh</div>
                        {trip.goods_weight_kg ? (
                          <>
                            <div className="result-weight">
                              {Number(trip.goods_weight_kg).toLocaleString('vi-VN')} <small>kg</small>
                            </div>
                            <div className="result-tons">
                              ≈ {(Number(trip.goods_weight_kg) / 1000).toLocaleString('vi-VN', { maximumFractionDigits: 3 })} tấn
                            </div>
                          </>
                        ) : (
                          <div className="result-pending">—</div>
                        )}
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </section>
      ) : (
        /* Timeline View */
        <section className="timeline-content-section panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">LỊCH SỬ SỰ KIỆN QUA BÀN CÂN</span>
              <h2>Tất cả lượt xe ({timelineTotal})</h2>
            </div>
            <span className="scale-muted">Ngày {dateFilter}</span>
          </div>

          {!timelineVisits.length ? (
            <div className="trips-empty-state">
              <Camera size={32} />
              <p>Chưa có lượt camera / cân nào ghi nhận trong ngày này.</p>
            </div>
          ) : (
            <div className="timeline-table-wrapper">
              <table className="timeline-table">
                <thead>
                  <tr>
                    <th>Thời điểm</th>
                    <th>Ảnh xe</th>
                    <th>Biển số xe</th>
                    <th>Nguồn đọc</th>
                    <th>Trọng lượng đo được</th>
                    <th>Camera</th>
                    <th>Hành động</th>
                  </tr>
                </thead>
                <tbody>
                  {timelineVisits.map((v) => (
                    <tr key={v.visit_id}>
                      <td className="cell-time">{formatTime(v.observed_at_utc || v.created_at)}</td>
                      <td className="cell-photo">
                        {v.thumbnail_url ? (
                          <button
                            className="table-thumb-btn"
                            onClick={() => setPreviewImage({ url: v.thumbnail_url!, title: v.plate_text || 'Ảnh xe' })}
                          >
                            <img src={v.thumbnail_url} alt="" className="table-thumb" />
                          </button>
                        ) : (
                          <span className="no-photo">—</span>
                        )}
                      </td>
                      <td className="cell-plate">
                        <strong>{v.plate_text || 'Chưa rõ biển'}</strong>
                      </td>
                      <td className="cell-source">
                        <span className={`source-pill ${v.prediction_source || 'unknown'}`}>
                          {v.plate_source === 'confirmed' ? 'Đã duyệt' : v.prediction_source === 'api' ? 'Google AI' : 'Local OCR'}
                        </span>
                      </td>
                      <td className="cell-weight">
                        <strong>{formatWeight(v.scale_weight_kg)}</strong>
                      </td>
                      <td className="cell-camera">{v.camera_id}</td>
                      <td className="cell-actions">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={aiLoadingId === v.visit_id}
                          onClick={() => void triggerGoogleAiOcr(v.visit_id)}
                          title="Quét lại bằng Google AI"
                        >
                          <Sparkles size={12} className={aiLoadingId === v.visit_id ? 'spin' : ''} /> AI
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditingVisit({ id: v.visit_id, plate: v.plate_text || '', version: v.version })
                            setEditPlateValue(v.plate_text || '')
                          }}
                        >
                          <Edit3 size={12} /> Sửa
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Camera Live Diagnostic Tool (Collapsible) */}
      <details className="pilot-camera-tools">
        <summary>Công cụ camera trực tiếp và chụp chẩn đoán thiết bị</summary>
        <CameraLivePanel facilityId={facilityId} csrf={csrf} />
      </details>

      {/* Edit Plate Dialog */}
      {editingVisit && (
        <div className="trips-modal-scrim">
          <form className="panel trips-modal" onSubmit={savePlateEdit}>
            <div className="modal-header">
              <h3>Hiệu chỉnh biển số xe</h3>
              <button type="button" className="close-btn" onClick={() => setEditingVisit(null)}><X size={16} /></button>
            </div>
            <p className="modal-desc">
              Nhập chính xác biển số xe theo chuẩn Việt Nam (ví dụ: <code>49C-026.55</code> hoặc <code>51D-123.45</code>).
            </p>
            <div className="modal-body">
              <label>Biển số mới</label>
              <input
                autoFocus
                type="text"
                value={editPlateValue}
                onChange={(e) => setEditPlateValue(e.target.value)}
                placeholder="Ví dụ: 49C-026.55"
                className="modal-input"
                required
              />
            </div>
            <div className="modal-footer">
              <Button type="button" variant="outline" onClick={() => setEditingVisit(null)}>Đóng</Button>
              <Button type="submit" disabled={savingEdit}>
                {savingEdit ? 'Đang lưu...' : 'Lưu xác nhận'}
              </Button>
            </div>
          </form>
        </div>
      )}

      {/* Image Preview Modal */}
      {previewImage && (
        <div className="trips-modal-scrim" onClick={() => setPreviewImage(null)}>
          <div className="image-preview-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="preview-top">
              <strong>{previewImage.title}</strong>
              <button className="close-btn" onClick={() => setPreviewImage(null)}><X size={18} /></button>
            </div>
            <div className="preview-body">
              <img src={previewImage.url} alt={previewImage.title} className="preview-img" />
            </div>
            <div className="preview-bottom">
              <a href={previewImage.url} target="_blank" rel="noreferrer" className="open-raw-link">
                Mở ảnh gốc trong tab mới
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
