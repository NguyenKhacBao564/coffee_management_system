import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, ArrowDownLeft, ArrowRight, ArrowUpRight, Building2, Camera, ChevronDown, CircleHelp, Clock3, Eye, FileClock, Flame, Menu, RefreshCw,
  Scale, Search, ShieldCheck, Truck,
  UsersRound, Wifi, WifiOff, X, LogOut, KeyRound, Plus, Pencil, ChevronLeft, ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import D02Page from './D02Page'
import DrumProcessingPage from './DrumProcessingPage'
import ScaleMonitoring from './ScaleMonitoring'
import VehiclePilotPage from './VehiclePilotPage'
import {
  getDefaultPageForRole,
  getOperationalNav,
  getAdministrationNav,
  isPageAllowedForRole,
  isVisibleAppPage,
  navigationConfig,
  type AppPage,
} from './navigation-config'

type ServiceState = 'checking' | 'online' | 'offline'
type Health = { live: ServiceState; database: ServiceState; checkedAt: Date | null }

const apiBase = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

function useHealth(enabled: boolean) {
  const [health, setHealth] = useState<Health>({ live: 'checking', database: 'checking', checkedAt: null })
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!enabled) return
    setLoading(true)
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 4500)
    const [liveResult, readyResult] = await Promise.allSettled([
      fetch(`${apiBase}/health/live`, { signal: controller.signal, cache: 'no-store', credentials: 'same-origin' }),
      fetch(`${apiBase}/admin/system/status`, { signal: controller.signal, cache: 'no-store', credentials: 'same-origin' }),
    ])
    window.clearTimeout(timeout)
    const now = new Date()
    if (readyResult.status === 'fulfilled' && readyResult.value.status === 401) {
      window.dispatchEvent(new Event('nhu-tung-session-expired'))
    }
    setHealth({
      live: liveResult.status === 'fulfilled' && liveResult.value.ok ? 'online' : 'offline',
      database: readyResult.status === 'fulfilled' && readyResult.value.ok ? 'online' : 'offline',
      checkedAt: now,
    })
    setLoading(false)
  }, [enabled])

  useEffect(() => {
    if (!enabled) {
      setHealth({ live: 'checking', database: 'checking', checkedAt: null })
      return
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 30000)
    return () => window.clearInterval(timer)
  }, [enabled, refresh])

  return { health, loading, refresh }
}

function Dashboard({ user, onLogout, onChangePassword, onSelectFacility, onAccounts, page, csrf, onNavigate }: { user: UserProfile; onLogout: () => void; onChangePassword: () => void; onSelectFacility: (id: number) => void; onAccounts: () => void; page: AppPage; csrf: string; onNavigate: (page: AppPage) => void }) {
  const isAdmin = user.role === 'admin'
  const isOperator = user.role === 'drum_operator'
  const operationalNav = getOperationalNav(user.role)
  const adminNav = getAdministrationNav(user.role)

  const pageLabel =
    page === 'drums'
      ? 'Trông trống cà'
      : page === 'visits' || page === 'pilot'
      ? 'Lượt xe'
      : page === 'scales'
      ? 'Tín hiệu cân'
      : page === 'trips'
      ? 'Chuyến xe'
      : page === 'schedules'
      ? 'Lịch hàng'
      : page === 'pending'
      ? 'Cần xác nhận'
      : page === 'home'
      ? 'Tổng quan'
      : page === 'accounts'
      ? 'Tài khoản'
      : 'Vận hành'
  const { health, loading, refresh } = useHealth(isAdmin)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const serviceOnline = health.live === 'online' && health.database === 'online'
  const allChecked = health.checkedAt !== null

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNavOpen ? 'sidebar-open' : ''}`}>
        <div className="brand-row">
          <div className="brand-mark"><Scale size={21} strokeWidth={2.2} /></div>
          <div className="brand-copy"><span>NHƯ TÙNG</span><small>Vận hành cân hàng</small></div>
          <button className="mobile-close" onClick={() => setMobileNavOpen(false)} aria-label="Đóng menu"><X size={18} /></button>
        </div>

        <div className="site-picker">
          <div className="site-icon"><Building2 size={17} /></div>
          <select className="site-select" aria-label="Chọn cơ sở" value={user.active_facility?.id ?? ''} onChange={(event) => onSelectFacility(Number(event.target.value))} disabled={!user.facilities.length}>
            {user.facilities.length === 0 && <option value="">Chưa có cơ sở</option>}
            {user.facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}
          </select>
          <ChevronDown size={15} className="site-chevron" />
        </div>

        <nav className="nav-groups" aria-label="Điều hướng chính">
          {operationalNav.length > 0 && <p className="nav-caption">VẬN HÀNH</p>}
          {operationalNav.map(({ label, icon: Icon, page: target }) => (
            <button key={label} className={`nav-item ${page === target || (target === 'visits' && page === 'pilot') ? 'nav-active' : ''}`} onClick={() => { onNavigate(target); setMobileNavOpen(false) }}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
            </button>
          ))}
          {adminNav.length > 0 && <><p className="nav-caption nav-caption-system">QUẢN TRỊ</p>
            {adminNav.map(({ label, icon: Icon, page: target }) => (
              <button key={label} className={`nav-item ${page === target ? 'nav-active' : ''}`} onClick={() => { if (target === 'accounts') onAccounts(); else onNavigate(target); setMobileNavOpen(false) }}>
                <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              </button>
            ))}</>}
        </nav>

        <div className="sidebar-bottom">
          {navigationConfig.showBusinessOperations && !isOperator && !isAdmin && (
            <div className="help-card"><div className="help-icon"><CircleHelp size={17} /></div><div><strong>D02 · Nhập liệu thủ công</strong><span>Lịch, chuyến, cân manual và giao dịch có audit.</span></div></div>
          )}
          <div className="profile-row"><div className="profile-avatar">{user.display_name.slice(0, 2).toUpperCase()}</div><div className="profile-copy"><strong>{user.display_name}</strong><span>{roleLabel(user.role)}</span></div><span className="profile-dot profile-dot-online" aria-label="Đã đăng nhập" /></div>
        </div>
      </aside>

      {mobileNavOpen && <button className="mobile-scrim" onClick={() => setMobileNavOpen(false)} aria-label="Đóng menu" />}

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu" onClick={() => setMobileNavOpen(true)} aria-label="Mở menu"><Menu size={20} /></button>
            <div className="breadcrumb"><span>Không gian làm việc</span><span className="breadcrumb-slash">/</span><strong>{pageLabel}</strong></div>
          </div>
          <div className="topbar-actions">
            {isAdmin ? <div className="system-pill"><span className={`status-dot ${!serviceOnline && allChecked ? 'dot-offline' : ''}`} /><span>{!allChecked ? 'Đang kiểm tra' : serviceOnline ? 'Hệ thống hoạt động' : 'Mất kết nối API'}</span></div> : <div className="system-pill"><span className="status-dot" /><span>Phiên làm việc</span></div>}
            <span className="topbar-divider" />
            <button className="icon-button" aria-label="Đổi mật khẩu" title="Đổi mật khẩu" onClick={onChangePassword}><KeyRound size={16} /></button>
            <button className="icon-button" aria-label="Đăng xuất" title="Đăng xuất" onClick={onLogout}><LogOut size={17} /></button>
            <div className="topbar-avatar">{user.display_name.slice(0, 2).toUpperCase()}</div>
          </div>
        </header>

        {page === 'drums' ? (
          <DrumProcessingPage user={user} csrf={csrf} />
        ) : page === 'visits' || page === 'pilot' ? (
          <VehiclePilotPage facilities={user.facilities} initialFacilityId={user.active_facility?.id ?? null} csrf={csrf} isAdmin={user.role === 'admin'} />
        ) : page === 'scales' ? (
          <ScaleMonitoring key={user.active_facility?.id ?? 'none'} facilities={user.facilities} initialFacilityId={user.active_facility?.id ?? null} />
        ) : page !== 'home' && page !== 'accounts' ? (
          navigationConfig.showBusinessOperations ? (
            <D02Page page={page as 'trips' | 'schedules' | 'pending'} csrf={csrf} user={user} onNavigate={onNavigate} />
          ) : (
            <OperationalOverview facilityId={user.active_facility?.id ?? null} onNavigate={onNavigate} />
          )
        ) : (
          <div className="page-content">
          <section className="welcome-row">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" /> KHÔNG GIAN VẬN HÀNH</div>
              <h1>Xin chào, {user.display_name}</h1>
              <p className="page-subtitle">{user.active_facility ? `Đang làm việc tại ${user.active_facility.name}.` : 'Tài khoản chưa được gán cơ sở đang hoạt động.'}</p>
            </div>
            <div className="date-chip"><Clock3 size={15} /><span>{new Intl.DateTimeFormat('vi-VN', { dateStyle: 'full', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date())}</span></div>
          </section>

          {isAdmin && <section className={`connection-banner ${!serviceOnline && allChecked ? 'connection-banner-offline' : ''}`} aria-live="polite">
            <div className="connection-symbol">{!allChecked ? <Activity size={20} /> : serviceOnline ? <Wifi size={20} /> : <WifiOff size={20} />}</div>
            <div className="connection-copy">
              <strong>{!allChecked ? 'Đang kiểm tra kết nối' : serviceOnline ? 'Các dịch vụ đang sẵn sàng' : 'Chưa kết nối được đầy đủ dịch vụ'}</strong>
              <span>{!allChecked ? 'Đang kiểm tra API và cơ sở dữ liệu.' : serviceOnline ? 'API phản hồi và cơ sở dữ liệu đã kết nối.' : health.live === 'offline' ? 'Không thể kết nối API. Hãy kiểm tra dịch vụ backend.' : 'API đang hoạt động nhưng cơ sở dữ liệu chưa sẵn sàng.'}</span>
            </div>
            <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading} className="refresh-button">
              <RefreshCw size={15} className={loading ? 'spin' : ''} /> Kiểm tra lại
            </Button>
          </section>}

          <OperationalOverview facilityId={user.active_facility?.id ?? null} onNavigate={onNavigate} />

          {isAdmin && <section className="panel overview-system-status"><span className="section-kicker">TRẠNG THÁI ỨNG DỤNG</span><div><span>API {health.live === 'online' ? 'đang hoạt động' : health.live === 'offline' ? 'không kết nối' : 'đang kiểm tra'}</span><span>Cơ sở dữ liệu {health.database === 'online' ? 'đang hoạt động' : health.database === 'offline' ? 'chưa sẵn sàng' : 'đang kiểm tra'}</span><button onClick={() => void refresh()} disabled={loading}><RefreshCw size={14} className={loading ? 'spin' : ''} /> Kiểm tra lại</button></div></section>}
          <footer className="page-footer"><span>© 2026 Công ty TNHH Như Tùng</span><span className="footer-separator">·</span><span>Demo nội bộ</span><span className="footer-build"><span className="footer-build-dot" /> Theo dõi lượt xe và tín hiệu cân</span></footer>
        </div>
        )}
      </main>
    </div>
  )
}

function OperationalOverview({ facilityId, onNavigate }: { facilityId: number | null; onNavigate?: (page: AppPage) => void }) {
  type CameraHealth = { camera_id: string; source_state: string; processing_state: string; health_received_at?: string; last_frame_decoded_at?: string; worker_reporting: boolean }
  type ScaleAgent = { agent_id: string; scale_code: string; state: string; reader_status: string | null; received_at_utc: string | null; age_seconds: number | null }
  type TripItem = {
    plate_number: string
    direction: 'import' | 'export' | 'reweigh' | 'in_yard'
    first_weight_kg: number | null
    second_weight_kg: number | null
    net_weight_kg: number | null
    net_weight_tons: number | null
    entry_time_utc: string | null
    exit_time_utc: string | null
    first_visit?: { camera_id?: string; plate_text?: string; weight_kg?: number | null }
    second_visit?: { camera_id?: string; plate_text?: string; weight_kg?: number | null }
    status: 'completed' | 'in_yard'
  }
  type TripSummary = {
    total_import_kg: number
    total_import_tons: number
    total_export_kg: number
    total_export_tons: number
    in_yard_count: number
    completed_count: number
    total_trips: number
  }
  type TripsResponse = {
    date: string
    summary: TripSummary
    trips: TripItem[]
  }

  const [tripsData, setTripsData] = useState<TripsResponse | null>(null)
  const [cameras, setCameras] = useState<CameraHealth[] | null>(null)
  const [agents, setAgents] = useState<ScaleAgent[] | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true, running = false, timer: number | undefined, controller: AbortController | undefined
    const run = async () => {
      if (!alive || running || document.hidden || !facilityId) return
      running = true; controller = new AbortController()
      try {
        const base = `${(import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')}/vehicle-pilot`
        const paths = [
          `/visits/trips?facility_id=${facilityId}`,
          `/cameras?facility_id=${facilityId}`,
          `/heartbeat/scale-agents?facility_id=${facilityId}`
        ]
        const results = await Promise.all(paths.map(async path => {
          const response = await fetch(`${base}${path}`, { credentials: 'same-origin', cache: 'no-store', signal: controller?.signal })
          if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'Không có quyền xem trạng thái cơ sở.' : 'Không tải được dữ liệu vận hành.')
          return response.json()
        }))
        if (!alive) return
        setTripsData(results[0] as TripsResponse)
        setCameras((results[1] as { items: CameraHealth[] }).items)
        setAgents((results[2] as { items: ScaleAgent[] }).items)
        setCheckedAt(new Date())
        setError('')
      } catch (reason) {
        if (!alive || controller?.signal.aborted) return
        setError(reason instanceof Error ? reason.message : 'Không tải được dữ liệu vận hành.')
      } finally {
        running = false
        if (alive && !document.hidden) timer = window.setTimeout(() => void run(), 15000)
      }
    }
    const visibility = () => { window.clearTimeout(timer); if (document.hidden) controller?.abort(); else void run() }
    void run(); document.addEventListener('visibilitychange', visibility)
    return () => { alive = false; controller?.abort(); window.clearTimeout(timer); document.removeEventListener('visibilitychange', visibility) }
  }, [facilityId])

  const cameraLabel = (camera: CameraHealth) => camera.source_state === 'receiving' && camera.worker_reporting ? 'Đang nhận hình' : camera.source_state === 'reconnecting' ? 'Đang kết nối lại' : camera.source_state === 'idle_unchecked' ? 'Chưa kiểm tra gần đây' : camera.worker_reporting ? 'Nguồn cần kiểm tra' : 'Chưa cập nhật trạng thái'
  const heartbeatLabel = (agent: ScaleAgent) => ({ communicating: 'Đang liên lạc', delayed: 'Liên lạc chậm', lost: 'Mất liên lạc', never_received: 'Chưa có tín hiệu', legacy_snapshot: 'Snapshot cũ', disabled: 'Đã vô hiệu hóa' }[agent.state] || 'Chưa rõ')
  const readerLabel = (status: string | null) => ({ starting: 'Đang khởi động', ok: 'Đọc được nguồn', empty: 'Nguồn trống', error: 'Lỗi đọc nguồn', unavailable: 'Nguồn không khả dụng' }[status || ''] || 'Chưa có trạng thái reader')
  const summary = tripsData?.summary

  return (
    <div className="operational-overview">
      <section className="metrics-grid" aria-label="Tổng quan sản lượng và chuyến xe hôm nay">
        <MetricCard
          icon={<ArrowDownLeft size={18} />}
          label="Sản lượng nhập hôm nay"
          value={summary ? `${summary.total_import_tons.toLocaleString('vi-VN', { maximumFractionDigits: 2 })} tấn` : '—'}
          note={summary ? `${summary.total_import_kg.toLocaleString('vi-VN')} kg nguyên liệu` : 'Đang tính toán'}
        />
        <MetricCard
          icon={<ArrowUpRight size={18} />}
          label="Sản lượng xuất hôm nay"
          value={summary ? `${summary.total_export_tons.toLocaleString('vi-VN', { maximumFractionDigits: 2 })} tấn` : '—'}
          note={summary ? `${summary.total_export_kg.toLocaleString('vi-VN')} kg thành phẩm / phế` : 'Đang tính toán'}
        />
        <MetricCard
          icon={<Truck size={18} />}
          label="Xe đang trong xưởng"
          value={summary ? `${summary.in_yard_count.toLocaleString('vi-VN')} xe` : '—'}
          note="Đã cân lần 1, chờ cân lần 2"
        />
        <MetricCard
          icon={<ShieldCheck size={18} />}
          label="Chuyến hoàn tất"
          value={summary ? `${summary.completed_count.toLocaleString('vi-VN')} chuyến` : '—'}
          note="Đã đối chiếu đủ 2 lượt cân"
        />
      </section>

      {error && (
        <div className="d02-error" role="alert" style={{ marginBottom: '16px' }}>
          Không cập nhật được trạng thái vận hành. {error}
          {checkedAt && ` Lần tải tốt gần nhất: ${new Intl.DateTimeFormat('vi-VN', { timeStyle: 'medium', timeZone: 'Asia/Ho_Chi_Minh' }).format(checkedAt)}.`}
        </div>
      )}

      <section className="panel" style={{ marginBottom: '18px' }}>
        <div className="panel-heading" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <span className="section-kicker">THEO DÕI THỰC TẾ HÔM NAY</span>
            <h2 style={{ margin: '4px 0 0', fontSize: '18px' }}>Lượt xe vào / ra gần nhất</h2>
          </div>
          {onNavigate && (
            <Button variant="outline" size="sm" onClick={() => onNavigate('visits')} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>Xem tất cả chuyến xe</span>
              <ArrowRight size={14} />
            </Button>
          )}
        </div>

        {(!tripsData || tripsData.trips.length === 0) ? (
          <div style={{ textAlign: 'center', padding: '36px 16px', color: '#64748b' }}>
            <Truck size={36} style={{ margin: '0 auto 8px', opacity: 0.35, display: 'block' }} />
            <p style={{ fontWeight: 600, color: '#334155', margin: '4px 0' }}>Chưa ghi nhận lượt xe nào trong hôm nay</p>
            <small style={{ color: '#94a3b8' }}>Dữ liệu tự động cập nhật khi camera nhận diện biển số hoặc đầu cân ghi nhận tín hiệu.</small>
          </div>
        ) : (
          <div style={{ overflowX: 'auto', marginTop: '14px' }}>
            <table className="vp-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', textAlign: 'left', fontSize: '11px', textTransform: 'uppercase' }}>
                  <th style={{ padding: '10px 12px' }}>Biển số</th>
                  <th style={{ padding: '10px 12px' }}>Phân loại</th>
                  <th style={{ padding: '10px 12px' }}>Cân lần 1 (Vào)</th>
                  <th style={{ padding: '10px 12px' }}>Cân lần 2 (Ra)</th>
                  <th style={{ padding: '10px 12px' }}>Khối lượng ròng</th>
                  <th style={{ padding: '10px 12px' }}>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {tripsData.trips.slice(0, 5).map((trip, idx) => {
                  const isImport = trip.direction === 'import'
                  const isExport = trip.direction === 'export'
                  const isInYard = trip.direction === 'in_yard' || trip.status === 'in_yard'
                  return (
                    <tr key={`${trip.plate_number}-${idx}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '11px 12px', fontWeight: 600 }}>
                        <span className="vp-plate-badge">{trip.plate_number}</span>
                      </td>
                      <td style={{ padding: '11px 12px' }}>
                        {isImport ? (
                          <span className="vp-badge vp-badge-in">📥 Nhập hàng</span>
                        ) : isExport ? (
                          <span className="vp-badge vp-badge-out">📤 Xuất hàng</span>
                        ) : isInYard ? (
                          <span className="vp-badge vp-badge-warn">⏳ Trong xưởng</span>
                        ) : (
                          <span className="vp-badge">⚖️ Cân lại</span>
                        )}
                      </td>
                      <td style={{ padding: '11px 12px' }}>
                        <div style={{ fontWeight: 600, color: '#1e293b' }}>
                          {trip.first_weight_kg ? `${trip.first_weight_kg.toLocaleString('vi-VN')} kg` : '—'}
                        </div>
                        <small style={{ color: '#64748b', fontSize: '11px' }}>
                          {trip.entry_time_utc ? new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(trip.entry_time_utc)) : ''}
                        </small>
                      </td>
                      <td style={{ padding: '11px 12px' }}>
                        <div style={{ fontWeight: 600, color: '#1e293b' }}>
                          {trip.second_weight_kg ? `${trip.second_weight_kg.toLocaleString('vi-VN')} kg` : '—'}
                        </div>
                        <small style={{ color: '#64748b', fontSize: '11px' }}>
                          {trip.exit_time_utc ? new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(trip.exit_time_utc)) : ''}
                        </small>
                      </td>
                      <td style={{ padding: '11px 12px' }}>
                        {trip.net_weight_kg !== null ? (
                          <div>
                            <strong style={{ color: isImport ? '#059669' : '#0284c7', fontSize: '14px' }}>
                              {trip.net_weight_kg.toLocaleString('vi-VN')} kg
                            </strong>
                            <span style={{ fontSize: '11px', color: '#64748b', marginLeft: '5px' }}>
                              ({trip.net_weight_tons} tấn)
                            </span>
                          </div>
                        ) : (
                          <span style={{ color: '#94a3b8', fontSize: '12px' }}>Chờ cân lần 2</span>
                        )}
                      </td>
                      <td style={{ padding: '11px 12px' }}>
                        {trip.status === 'completed' ? (
                          <span style={{ color: '#059669', fontSize: '12px', fontWeight: 600 }}>✓ Hoàn tất</span>
                        ) : (
                          <span style={{ color: '#d97706', fontSize: '12px', fontWeight: 600 }}>⏳ Đang bốc dỡ</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel overview-device-panel">
        <div className="panel-heading">
          <div>
            <span className="section-kicker">THIẾT BỊ VÀ ĐẦU CÂN</span>
            <h2>Trạng thái kết nối trạm</h2>
          </div>
          <span className="scale-muted">
            {checkedAt ? `Cập nhật ${new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }).format(checkedAt)}` : 'Đang kiểm tra'}
          </span>
        </div>
        <div className="overview-device-grid">
          <div>
            <h3>Camera biển số</h3>
            {cameras?.length ? cameras.map(camera => (
              <article className="overview-device-row" key={camera.camera_id}>
                <strong>{camera.camera_id}</strong>
                <span>{cameraLabel(camera)}</span>
                <small>{camera.last_frame_decoded_at ? `Frame giải mã ${new Intl.DateTimeFormat('vi-VN', { timeStyle: 'medium', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(camera.last_frame_decoded_at))}` : 'Chưa có frame mới'}</small>
              </article>
            )) : <p className="scale-muted">{cameras ? 'Chưa có camera được cấu hình.' : 'Chưa tải được trạng thái camera.'}</p>}
          </div>
          <div>
            <h3>PC cân & Tín hiệu</h3>
            {agents?.length ? agents.map(agent => (
              <article className="overview-device-row" key={agent.agent_id}>
                <strong>{agent.scale_code} · {heartbeatLabel(agent)}</strong>
                <span>Reader: {readerLabel(agent.reader_status)}</span>
                <small>{agent.received_at_utc ? `Heartbeat ${agent.age_seconds ?? '—'}s trước` : 'Chưa nhận heartbeat'}</small>
              </article>
            )) : <p className="scale-muted">{agents ? 'Chưa có agent cân được gán.' : 'Chưa tải được trạng thái PC cân.'}</p>}
          </div>
        </div>
        <p className="overview-boundary-note">
          Hệ thống tự động liên kết 2 lần cân theo biển số xe trong ngày để xác định xe vào/ra và tính khối lượng hàng ròng.
        </p>
      </section>
    </div>
  )
}

function MetricCard({ icon, label, value, note }: { icon: React.ReactNode; label: string; value: string; note: string }) {
  return <div className="metric-card"><div className="metric-top"><span className="metric-icon">{icon}</span><span className="metric-period">Hôm nay</span></div><div className="metric-value">{value}</div><div className="metric-label">{label}</div><div className="metric-note"><span className="metric-note-dot" />{note}</div></div>
}

type FacilityProfile = { id: number; code: string; name: string; is_active?: boolean }
type FacilityOverview = {
  id: number
  code: string
  name: string
  is_active: boolean
  is_demo: boolean
  created_at: string
  employees_count: number
  drums_count: number
  running_drums_count: number
  cameras_count: number
  scales_count: number
  drum_status: 'running' | 'ready' | 'no_drums'
  camera_status: 'active' | 'unconfigured'
  scale_status: 'active' | 'unconfigured'
}
type FacilityEmployee = {
  id: number
  username: string
  display_name: string
  role: string
  is_active: boolean
}
type FacilityDrum = {
  id: number
  drum_code: string
  drum_name: string
  capacity_kg: number | null
  measurement_mode: string
  has_moisture_imbalance: boolean
  has_blade_issue: boolean
  status: string
  is_active: boolean
}
type FacilityModuleStatus = {
  status: string
  label: string
  details: string
}
type FacilityDetail = {
  id: number
  code: string
  name: string
  is_active: boolean
  is_demo: boolean
  created_at: string
  employees: FacilityEmployee[]
  drums: FacilityDrum[]
  drum_processing_status: FacilityModuleStatus
  camera_status: FacilityModuleStatus
  scale_status: FacilityModuleStatus
}
type UserProfile = { id: number; username: string; display_name: string; role: 'admin' | 'manager' | 'staff' | 'drum_operator'; facilities: FacilityProfile[]; active_facility: FacilityProfile | null }
type Account = UserProfile & { is_active: boolean; created_at: string; last_login_at: string | null }
type AuditItem = { id: number; event: string; actor_username: string | null; target_username: string | null; changes: Record<string, unknown>; created_at: string }
type PageState = 'loading' | 'anonymous' | 'authenticated' | 'unavailable'

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function apiRequest<T>(path: string, csrf: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers.set('X-CSRF-Token', csrf)
  let response: Response
  try {
    response = await fetch(`${apiBase}${path}`, { ...init, method, headers, credentials: 'same-origin', cache: 'no-store' })
  } catch {
    throw new ApiError(0, 'Không thể kết nối API. Hãy kiểm tra dịch vụ rồi thử lại.')
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('nhu-tung-session-expired'))
    const detail = typeof data?.detail === 'string' ? data.detail : response.status === 503 ? 'Dịch vụ tạm thời chưa sẵn sàng.' : 'Không thể hoàn tất yêu cầu.'
    throw new ApiError(response.status, detail)
  }
  return data as T
}

function App() {
  const [pageState, setPageState] = useState<PageState>('loading')
  const [user, setUser] = useState<UserProfile | null>(null)
  const [csrf, setCsrf] = useState('')
  const routePage = (currentUser?: UserProfile | null) => {
    const raw = navigationConfig.routes[window.location.pathname] || 'home'
    const target = isVisibleAppPage(raw) ? raw : 'home'
    const u = currentUser !== undefined ? currentUser : user
    if (u && !isPageAllowedForRole(target, u.role)) {
      return getDefaultPageForRole(u.role)
    }
    return target
  }
  const [page, setPage] = useState<AppPage>(() => routePage())
  const [dialog, setDialog] = useState<'password' | null>(null)
  const [error, setError] = useState('')
  const [sessionNotice, setSessionNotice] = useState('')
  const restoredOnce = useRef(false)

  const fetchCsrf = useCallback(async () => {
    const result = await apiRequest<{ csrf_token: string }>('/auth/csrf', '', { method: 'GET' })
    setCsrf(result.csrf_token)
    return result.csrf_token
  }, [])

  const navigate = useCallback((next: AppPage) => {
    const path = next === 'accounts' ? '/admin/accounts' : next === 'home' ? '/' : next === 'visits' || next === 'pilot' ? '/visits' : `/${next}`
    if (window.location.pathname !== path) window.history.pushState({}, '', path)
    setPage(next)
  }, [])

  const restoreSession = useCallback(async () => {
    setPageState('loading')
    setError('')
    try {
      const profile = await apiRequest<UserProfile>('/auth/me', '', { method: 'GET' })
      await fetchCsrf()
      setUser(profile)
      setPageState('authenticated')
      const target = routePage(profile)
      if (window.location.pathname === '/' || !isPageAllowedForRole(target, profile.role)) {
        navigate(getDefaultPageForRole(profile.role))
      } else {
        setPage(target)
      }
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) {
        try { await fetchCsrf(); setUser(null); setPageState('anonymous') }
        catch (csrfError) { setError(csrfError instanceof Error ? csrfError.message : 'Không thể kết nối API.'); setPageState('unavailable') }
      } else {
        setError(reason instanceof Error ? reason.message : 'Dịch vụ tạm thời chưa sẵn sàng.')
        setPageState('unavailable')
      }
    }
  }, [fetchCsrf, navigate])

  useEffect(() => {
    if (restoredOnce.current) return
    restoredOnce.current = true
    void restoreSession()
  }, [restoreSession])

  useEffect(() => {
    const onPopState = () => setPage(routePage())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [user])

  const handleSessionExpired = useCallback(() => {
    setUser(null)
    setCsrf('')
    setPageState('anonymous')
    setSessionNotice('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
    navigate('home')
  }, [navigate])

  useEffect(() => {
    const onExpired = () => { if (pageState === 'authenticated') handleSessionExpired() }
    window.addEventListener('nhu-tung-session-expired', onExpired)
    return () => window.removeEventListener('nhu-tung-session-expired', onExpired)
  }, [pageState, handleSessionExpired])

  useEffect(() => {
    if (pageState === 'authenticated' && user) {
      if (!isPageAllowedForRole(page, user.role)) {
        navigate(getDefaultPageForRole(user.role))
      }
    }
  }, [page, pageState, user, navigate])

  const handleLogin = async (username: string, password: string) => {
    setError('')
    try {
      const token = csrf || await fetchCsrf()
      const result = await apiRequest<{ user: UserProfile; csrf_token: string }>('/auth/login', token, { method: 'POST', body: JSON.stringify({ username, password }) })
      setCsrf(result.csrf_token)
      setUser(result.user)
      setSessionNotice('')
      setPageState('authenticated')
      navigate(getDefaultPageForRole(result.user.role))
    } catch (reason) {
      const apiError = reason instanceof ApiError ? reason : new ApiError(0, 'Không thể kết nối API.')
      if (apiError.status === 0 || apiError.status === 503) setError('Dịch vụ chưa sẵn sàng. Hãy kiểm tra kết nối và thử lại.')
      else setError(apiError.message)
      throw apiError
    }
  }

  const handleLogout = async () => {
    try { await apiRequest('/auth/logout', csrf, { method: 'POST' }) }
    catch { /* Clear the local view even when the session has already expired. */ }
    setUser(null)
    setCsrf('')
    navigate('home')
    void restoreSession()
  }

  const handleSelectFacility = async (facilityId: number) => {
    try {
      const result = await apiRequest<{ user: UserProfile }>('/auth/active-facility', csrf, { method: 'POST', body: JSON.stringify({ facility_id: facilityId }) })
      setUser(result.user)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể đổi cơ sở.') }
  }

  const handlePasswordChange = async (current_password: string, new_password: string) => {
    const result = await apiRequest<{ user: UserProfile; csrf_token: string }>('/auth/change-password', csrf, { method: 'POST', body: JSON.stringify({ current_password, new_password }) })
    setUser(result.user)
    setCsrf(result.csrf_token)
    setDialog(null)
  }

  if (pageState === 'loading') return <LoadingScreen message="Đang kiểm tra phiên đăng nhập…" />
  if (pageState === 'unavailable') return <UnavailableScreen message={error} onRetry={() => void restoreSession()} />
  if (pageState === 'anonymous' || !user) return <LoginScreen notice={sessionNotice} onLogin={handleLogin} />
  if (page === 'accounts' && (user.role === 'admin' || user.role === 'manager')) {
    return <>
      <AccountsPage user={user} csrf={csrf} onHome={() => navigate(getDefaultPageForRole(user.role))} onLogout={() => void handleLogout()} onChangePassword={() => setDialog('password')} onExpired={handleSessionExpired} />
      {dialog === 'password' && <PasswordDialog onClose={() => setDialog(null)} onSubmit={handlePasswordChange} />}
    </>
  }
  return <>
    <Dashboard user={user} onLogout={() => void handleLogout()} onChangePassword={() => setDialog('password')} onSelectFacility={(id) => void handleSelectFacility(id)} onAccounts={() => navigate('accounts')} page={page} csrf={csrf} onNavigate={navigate} />
    {dialog === 'password' && <PasswordDialog onClose={() => setDialog(null)} onSubmit={handlePasswordChange} />}
  </>
}

function LoadingScreen({ message }: { message: string }) {
  return <main className="auth-screen"><div className="auth-card"><div className="brand-mark"><Scale size={21} /></div><p>{message}</p></div></main>
}

function UnavailableScreen({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <main className="auth-screen"><div className="auth-card"><div className="brand-mark"><Scale size={21} /></div><div className="eyebrow"><span className="eyebrow-line" /> KẾT NỐI DỊCH VỤ</div><h1>Chưa kết nối được</h1><p>{message || 'Dịch vụ chưa sẵn sàng. Hãy thử lại sau.'}</p><Button onClick={onRetry}><RefreshCw size={15} /> Thử lại</Button></div></main>
}

function LoginScreen({ onLogin, notice }: { onLogin: (username: string, password: string) => Promise<void>; notice: string }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try { await onLogin(username, password) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể đăng nhập.') }
    finally { setBusy(false) }
  }
  return <main className="auth-screen">
    <section className="auth-card login-card">
      <div className="auth-brand"><div className="brand-mark"><Scale size={21} strokeWidth={2.2} /></div><div><strong>NHƯ TÙNG</strong><span>Vận hành cân hàng</span></div></div>
      <div className="eyebrow"><span className="eyebrow-line" /> KHÔNG GIAN NỘI BỘ</div>
      <h1>Đăng nhập</h1><p className="auth-subtitle">Sử dụng tài khoản đã được cấp.</p>
      {notice && <div className="session-notice" role="status">{notice}</div>}
      <form onSubmit={(event) => void submit(event)} className="auth-form">
        <label>Tên đăng nhập<input autoComplete="username" required minLength={3} maxLength={64} value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label>Mật khẩu<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <Button type="submit" disabled={busy} className="auth-submit">{busy ? 'Đang đăng nhập…' : 'Đăng nhập'}</Button>
      </form>
      <div className="auth-footnote"><ShieldCheck size={15} /> Phiên làm việc được bảo vệ bằng cookie bảo mật.</div>
    </section>
    <span className="auth-copyright">© 2026 Công ty TNHH Như Tùng · Demo nội bộ</span>
  </main>
}

function PasswordDialog({ onClose, onSubmit }: { onClose: () => void; onSubmit: (current: string, next: string) => Promise<void> }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError('')
    if (next !== confirm) { setError('Mật khẩu mới không khớp.'); return }
    setBusy(true)
    try { await onSubmit(current, next) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể đổi mật khẩu.') }
    finally { setBusy(false) }
  }
  return <div className="modal-scrim" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}><section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="password-title"><div className="modal-heading"><div><span className="section-kicker">BẢO MẬT TÀI KHOẢN</span><h2 id="password-title">Đổi mật khẩu</h2></div><button className="icon-button" onClick={onClose} aria-label="Đóng"><X size={18} /></button></div><form className="auth-form" onSubmit={(event) => void submit(event)}><label>Mật khẩu hiện tại<input type="password" autoComplete="current-password" required value={current} onChange={(event) => setCurrent(event.target.value)} /></label><label>Mật khẩu mới<input type="password" autoComplete="new-password" minLength={12} maxLength={256} required value={next} onChange={(event) => setNext(event.target.value)} /><small>Tối thiểu 12 ký tự.</small></label><label>Nhập lại mật khẩu mới<input type="password" autoComplete="new-password" minLength={12} maxLength={256} required value={confirm} onChange={(event) => setConfirm(event.target.value)} /></label>{error && <div className="form-error" role="alert">{error}</div>}<div className="modal-actions"><Button type="button" variant="outline" onClick={onClose}>Hủy</Button><Button type="submit" disabled={busy}>{busy ? 'Đang lưu…' : 'Cập nhật mật khẩu'}</Button></div></form></section></div>
}

function FacilityDialog({ csrf, onClose, onSaved }: { csrf: string; onClose: () => void; onSaved: () => void }) {
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      await apiRequest('/admin/facilities', csrf, {
        method: 'POST',
        body: JSON.stringify({ code: code.trim().toUpperCase(), name: name.trim() }),
      })
      onSaved()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Không thể tạo chi nhánh.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-scrim" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <section className="modal-card account-modal" role="dialog" aria-modal="true">
        <div className="modal-heading">
          <div><span className="section-kicker">QUẢN TRỊ HỆ THỐNG</span><h2>Thêm chi nhánh mới</h2></div>
          <button className="icon-button" onClick={onClose} aria-label="Đóng"><X size={18} /></button>
        </div>
        <form className="auth-form" onSubmit={(e) => void submit(e)}>
          <label>Mã chi nhánh<input required minLength={2} maxLength={32} placeholder="Ví dụ: FAC-GL, GL01" value={code} onChange={(e) => setCode(e.target.value)} /><small>Dùng chữ và số viết hoa để làm mã định danh chi nhánh.</small></label>
          <label>Tên chi nhánh / Cơ sở<input required minLength={2} maxLength={120} placeholder="Ví dụ: Chi nhánh Gia Lai, Kho Cân Đức Trọng" value={name} onChange={(e) => setName(e.target.value)} /></label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <div className="modal-actions">
            <Button type="button" variant="outline" onClick={onClose}>Hủy</Button>
            <Button type="submit" disabled={busy}>{busy ? 'Đang tạo…' : 'Tạo chi nhánh'}</Button>
          </div>
        </form>
      </section>
    </div>
  )
}

function EditFacilityDialog({
  facility,
  csrf,
  onClose,
  onSaved,
}: {
  facility: FacilityProfile | FacilityOverview
  csrf: string
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(facility.name)
  const [isActive, setIsActive] = useState(facility.is_active !== false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await apiRequest(`/admin/facilities/${facility.id}`, csrf, {
        method: 'PATCH',
        body: JSON.stringify({ name: name.trim(), is_active: isActive }),
      })
      onSaved()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Không thể cập nhật chi nhánh.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-scrim" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <section className="modal-card account-modal" role="dialog" aria-modal="true">
        <div className="modal-heading">
          <div><span className="section-kicker">QUẢN TRỊ HỆ THỐNG</span><h2>Sửa thông tin chi nhánh</h2></div>
          <button className="icon-button" onClick={onClose} aria-label="Đóng"><X size={18} /></button>
        </div>
        <form className="auth-form" onSubmit={(e) => void submit(e)}>
          <label>
            Mã chi nhánh
            <input disabled value={facility.code} style={{ background: '#f1f5f9', cursor: 'not-allowed', color: '#64748b' }} />
            <small>Mã định danh không thể thay đổi để đảm bảo tính toàn vẹn dữ liệu.</small>
          </label>
          <label>
            Tên chi nhánh / Cơ sở
            <input required minLength={2} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label style={{ flexDirection: 'row', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} style={{ width: 16, height: 16 }} />
            <span>Đang hoạt động</span>
          </label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <div className="modal-actions">
            <Button type="button" variant="outline" onClick={onClose}>Hủy</Button>
            <Button type="submit" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu thay đổi'}</Button>
          </div>
        </form>
      </section>
    </div>
  )
}

function FacilityDetailDialog({
  facilityId,
  csrf,
  onClose,
  onEdit,
}: {
  facilityId: number
  csrf: string
  onClose: () => void
  onEdit: (facility: FacilityDetail) => void
}) {
  const [detail, setDetail] = useState<FacilityDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let ignore = false
    setLoading(true)
    apiRequest<FacilityDetail>(`/admin/facilities/${facilityId}/detail`, csrf)
      .then((data) => {
        if (!ignore) setDetail(data)
      })
      .catch((err) => {
        if (!ignore) setError(err instanceof Error ? err.message : 'Không tải được chi tiết chi nhánh.')
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => { ignore = true }
  }, [facilityId, csrf])

  return (
    <div className="modal-scrim" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <section className="modal-card facility-detail-modal" role="dialog" aria-modal="true">
        <div className="modal-heading">
          <div>
            <span className="section-kicker">CHI TIẾT CHI NHÁNH & THIẾT BỊ</span>
            <h2>{detail ? `${detail.name} (${detail.code})` : 'Chi tiết chi nhánh'}</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Đóng"><X size={18} /></button>
        </div>

        {loading && <div className="empty-state">Đang tải thông tin chi nhánh…</div>}
        {error && <div className="accounts-alert alert-error">{error}</div>}

        {detail && (
          <div className="facility-detail-body">
            {/* Cards trạng thái các chức năng hệ thống */}
            <div className="facility-modules-grid">
              <div className={`facility-module-card ${detail.drum_processing_status.status}`}>
                <div className="facility-module-header">
                  <span className="facility-module-title"><Flame size={15} color="#ea580c" /> Trông trống cà</span>
                  <span className={`badge ${detail.drum_processing_status.status === 'active' ? 'badge-running' : detail.drum_processing_status.status === 'ready' ? 'badge-ready' : 'badge-inactive'}`}>
                    {detail.drum_processing_status.label}
                  </span>
                </div>
                <div className="facility-module-details">{detail.drum_processing_status.details}</div>
              </div>

              <div className={`facility-module-card ${detail.camera_status.status}`}>
                <div className="facility-module-header">
                  <span className="facility-module-title"><Camera size={15} color="#0284c7" /> Camera giám sát</span>
                  <span className={`badge ${detail.camera_status.status === 'active' ? 'badge-camera-active' : 'badge-inactive'}`}>
                    {detail.camera_status.label}
                  </span>
                </div>
                <div className="facility-module-details">{detail.camera_status.details}</div>
              </div>

              <div className={`facility-module-card ${detail.scale_status.status}`}>
                <div className="facility-module-header">
                  <span className="facility-module-title"><Scale size={15} color="#7c3aed" /> Trạm cân hàng</span>
                  <span className={`badge ${detail.scale_status.status === 'active' ? 'badge-scale-active' : 'badge-inactive'}`}>
                    {detail.scale_status.label}
                  </span>
                </div>
                <div className="facility-module-details">{detail.scale_status.details}</div>
              </div>
            </div>

            {/* Danh sách Trống cà đang hiện hữu */}
            <div className="facility-section-title">
              <span>Trống cà hiện hữu ({detail.drums.length})</span>
            </div>
            {detail.drums.length ? (
              <div className="table-wrap">
                <table className="facility-subtable">
                  <thead>
                    <tr>
                      <th>MÃ TRỐNG</th>
                      <th>TÊN TRỐNG SẤY</th>
                      <th>SỨC CHỨA</th>
                      <th>CHẾ ĐỘ ĐO</th>
                      <th>ĐẶC TÍNH CƠ KHÍ</th>
                      <th>TRẠNG THÁI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.drums.map((d) => (
                      <tr key={d.id}>
                        <td><strong>{d.drum_code}</strong></td>
                        <td>{d.drum_name}</td>
                        <td>{d.capacity_kg ? `${Number(d.capacity_kg).toLocaleString('vi-VN')} kg` : '—'}</td>
                        <td>
                          {d.measurement_mode === 'two_ends'
                            ? 'Đo 2 đầu'
                            : d.measurement_mode === 'three_points'
                            ? 'Đo 3 điểm'
                            : 'Đo giữa trống'}
                        </td>
                        <td>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                            {d.has_moisture_imbalance && <span className="muted-tag" style={{ color: '#b45309', background: '#fffbeb', padding: '2px 5px', borderRadius: 4 }}>Lệch ẩm 2 đầu</span>}
                            {d.has_blade_issue && <span className="muted-tag" style={{ color: '#b45309', background: '#fffbeb', padding: '2px 5px', borderRadius: 4 }}>Lỗi cánh đảo</span>}
                            {!d.has_moisture_imbalance && !d.has_blade_issue && <span style={{ color: '#16a34a' }}>Bình thường</span>}
                          </div>
                        </td>
                        <td>
                          <span className={`status-label ${d.status === 'running' ? 'status-enabled' : ''}`}>
                            <i style={{ background: d.status === 'running' ? '#ea580c' : '#94a3b8' }} />
                            {d.status === 'running' ? 'Đang sấy' : d.status === 'maintenance' ? 'Bảo trì' : 'Rảnh'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={{ color: '#94a3b8', fontSize: 11, padding: '10px 0' }}>Chưa có trống cà nào được tạo cho chi nhánh này.</p>
            )}

            {/* Danh sách Nhân viên của Chi nhánh */}
            <div className="facility-section-title">
              <span>Nhân sự thuộc chi nhánh ({detail.employees.length})</span>
            </div>
            {detail.employees.length ? (
              <div className="table-wrap">
                <table className="facility-subtable">
                  <thead>
                    <tr>
                      <th>NHÂN VIÊN</th>
                      <th>TÊN ĐĂNG NHẬP</th>
                      <th>VAI TRÒ</th>
                      <th>TRẠNG THÁI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.employees.map((e) => (
                      <tr key={e.id}>
                        <td><strong>{e.display_name}</strong></td>
                        <td><small style={{ color: '#64748b' }}>@{e.username}</small></td>
                        <td>
                          <span className={`role-badge role-${e.role}`}>
                            {roleLabel(e.role as UserProfile['role'])}
                          </span>
                        </td>
                        <td>
                          <span className={`status-label ${e.is_active ? 'status-enabled' : 'status-disabled'}`}>
                            <i />{e.is_active ? 'Hoạt động' : 'Vô hiệu'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={{ color: '#94a3b8', fontSize: 11, padding: '10px 0' }}>Chưa có nhân sự nào được phân bổ cho chi nhánh này.</p>
            )}

            <div className="modal-actions" style={{ marginTop: 15 }}>
              <Button variant="outline" onClick={() => { onClose(); onEdit(detail) }}>
                <Pencil size={15} /> Sửa chi nhánh
              </Button>
              <Button onClick={onClose}>Đóng</Button>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

function AccountsPage({ user, csrf, onHome, onLogout, onChangePassword, onExpired }: { user: UserProfile; csrf: string; onHome: () => void; onLogout: () => void; onChangePassword: () => void; onExpired: () => void }) {
  const isAdmin = user.role === 'admin'
  const isManager = user.role === 'manager'
  const [items, setItems] = useState<Account[]>([])
  const [facilities, setFacilities] = useState<FacilityProfile[]>([])
  const [facilitiesOverview, setFacilitiesOverview] = useState<FacilityOverview[]>([])
  const [audit, setAudit] = useState<AuditItem[]>([])
  const [tab, setTab] = useState<'accounts' | 'facilities' | 'audit'>('accounts')
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [role, setRole] = useState('')
  const [active, setActive] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState<Account | null | 'new'>(null)
  const [editingFacility, setEditingFacility] = useState(false)
  const [editingFacilityData, setEditingFacilityData] = useState<FacilityOverview | FacilityProfile | null>(null)
  const [viewingFacilityId, setViewingFacilityId] = useState<number | null>(null)
  const [resetting, setResetting] = useState<Account | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const params = new URLSearchParams({ page: String(page), page_size: '10' })
      if (query) params.set('q', query)
      if (role) params.set('role', role)
      if (active) params.set('active', active)
      const [result, sites, overview] = await Promise.all([
        apiRequest<{ items: Account[]; total: number }>(`/admin/accounts?${params}`, csrf),
        apiRequest<FacilityProfile[]>('/facilities', csrf),
        isAdmin ? apiRequest<FacilityOverview[]>('/admin/facilities/overview', csrf) : Promise.resolve([]),
      ])
      setItems(result.items); setTotal(result.total); setFacilities(sites); setFacilitiesOverview(overview)
      if (tab === 'audit' && isAdmin) {
        const log = await apiRequest<{ items: AuditItem[] }>('/admin/audit?page_size=30', csrf)
        setAudit(log.items)
      }
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) onExpired()
      setError(reason instanceof Error ? reason.message : 'Không tải được dữ liệu.')
    } finally { setLoading(false) }
  }, [csrf, page, query, role, active, tab, isAdmin, onExpired])

  useEffect(() => { void load() }, [load])
  const afterSave = (message: string) => {
    setEditing(null)
    setEditingFacility(false)
    setEditingFacilityData(null)
    setResetting(null)
    setNotice(message)
    void load()
  }
  const setStatus = async (account: Account, enabled: boolean) => {
    setError(''); setNotice('')
    try {
      await apiRequest(`/admin/accounts/${account.id}/status?is_active=${enabled}`, csrf, { method: 'PATCH' })
      setNotice(enabled ? 'Đã kích hoạt tài khoản.' : 'Đã vô hiệu hóa tài khoản.')
      void load()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể cập nhật trạng thái.') }
  }
  const pageCount = Math.max(1, Math.ceil(total / 10))

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand-row"><div className="brand-mark"><Scale size={21} /></div><div className="brand-copy"><span>NHƯ TÙNG</span><small>Vận hành cân hàng</small></div></div>
      <button className="back-home" onClick={onHome}><ChevronLeft size={16} /> {isManager ? 'Về vận hành' : 'Về trang chủ'}</button>
      <nav className="nav-groups" aria-label="Điều hướng quản trị">
        <p className="nav-caption">{isAdmin ? 'QUẢN TRỊ HỆ THỐNG' : 'QUẢN LÝ NHÂN SỰ'}</p>
        <button className={`nav-item ${tab === 'accounts' ? 'nav-active' : ''}`} onClick={() => setTab('accounts')}>
          <UsersRound size={18} /><span>{isAdmin ? 'Tài khoản' : 'Nhân viên chi nhánh'}</span>
        </button>
        {isAdmin && (
          <button className={`nav-item ${tab === 'facilities' ? 'nav-active' : ''}`} onClick={() => setTab('facilities')}>
            <Building2 size={18} /><span>Chi nhánh</span>
          </button>
        )}
        {isAdmin && (
          <button className={`nav-item ${tab === 'audit' ? 'nav-active' : ''}`} onClick={() => setTab('audit')}>
            <FileClock size={18} /><span>Nhật ký thao tác</span>
          </button>
        )}
      </nav>
      <div className="sidebar-bottom"><div className="help-card"><div className="help-icon"><ShieldCheck size={17} /></div><div><strong>Quản lý phân quyền</strong><span>Quyền và chi nhánh được kiểm tra tại API mỗi yêu cầu.</span></div></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar">
        <div className="breadcrumb"><span>Quản trị</span><span className="breadcrumb-slash">/</span><strong>{isAdmin ? (tab === 'audit' ? 'Nhật ký thao tác' : tab === 'facilities' ? 'Chi nhánh' : 'Tài khoản') : 'Nhân sự chi nhánh'}</strong></div>
        <div className="topbar-actions">
          <span className="system-pill"><span className="status-dot" /> {isAdmin ? 'Quản trị viên hệ thống' : 'Quản lý chi nhánh'}</span>
          <span className="topbar-divider" />
          <button className="icon-button" aria-label="Đổi mật khẩu" title="Đổi mật khẩu" onClick={onChangePassword}><KeyRound size={16} /></button>
          <button className="icon-button" aria-label="Đăng xuất" title="Đăng xuất" onClick={onLogout}><LogOut size={17} /></button>
        </div>
      </header>
      <div className="page-content accounts-content">
        <section className="welcome-row">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> {tab === 'accounts' ? (isAdmin ? 'QUẢN TRỊ HỆ THỐNG' : 'QUẢN LÝ CHI NHÁNH') : tab === 'facilities' ? 'HỆ THỐNG CHI NHÁNH & THIẾT BỊ' : 'NHẬT KÝ QUẢN TRỊ'}</div>
            <h1>{tab === 'accounts' ? (isAdmin ? 'Tài khoản & Phân quyền' : 'Nhân sự chi nhánh') : tab === 'facilities' ? 'Chi nhánh & Thiết bị' : 'Nhật ký thao tác'}</h1>
            <p className="page-subtitle">{tab === 'accounts' ? (isAdmin ? 'Quản lý tài khoản đăng nhập, khởi tạo Quản lý (Manager) và kiểm soát hệ thống.' : 'Quản lý nhân viên vận hành trạm cân và thợ trông trống thuộc chi nhánh.') : tab === 'facilities' ? 'Quản lý các cơ sở chi nhánh xưởng, các trống cà hiện hữu và trạng thái kết nối camera / trạm cân.' : 'Ghi nhận lịch sử thay đổi tài khoản, phân quyền và cập nhật chi nhánh.'}</p>
          </div>
          <div className="d02-actions">
            {isAdmin && tab === 'facilities' ? (
              <Button onClick={() => setEditingFacility(true)}><Plus size={16} /> Thêm chi nhánh</Button>
            ) : tab === 'accounts' ? (
              <Button onClick={() => setEditing('new')}><Plus size={16} /> {isManager ? 'Tạo nhân viên mới' : 'Tạo tài khoản'}</Button>
            ) : (
              <Button variant="outline" onClick={() => void load()}><RefreshCw size={15} /> Làm mới</Button>
            )}
          </div>
        </section>

        {tab !== 'audit' && (
          <div className="accounts-tabs">
            <button className={tab === 'accounts' ? 'tab-active' : ''} onClick={() => setTab('accounts')}>
              {isAdmin ? 'Tài khoản' : 'Nhân viên'} <span>{total}</span>
            </button>
            {isAdmin && (
              <button className={tab === 'facilities' ? 'tab-active' : ''} onClick={() => setTab('facilities')}>
                Chi nhánh <span>{facilitiesOverview.length || facilities.length}</span>
              </button>
            )}
          </div>
        )}

        {error && <div className="accounts-alert alert-error" role="alert">{error}</div>}
        {notice && <div className="accounts-alert alert-success" role="status">{notice}</div>}

        {tab === 'accounts' ? (
          <>
            <form className="account-filters" onSubmit={(event) => { event.preventDefault(); setPage(1); setQuery(q.trim()) }}>
              <label className="search-field"><Search size={16} /><input placeholder="Tìm tên hoặc tên đăng nhập" value={q} onChange={(event) => setQ(event.target.value)} /></label>
              <select aria-label="Lọc theo vai trò" value={role} onChange={(event) => { setRole(event.target.value); setPage(1) }}>
                <option value="">Tất cả vai trò</option>
                {isAdmin && <option value="admin">Quản trị viên</option>}
                {isAdmin && <option value="manager">Quản lý chi nhánh</option>}
                <option value="staff">Nhân viên trạm cân</option>
                <option value="drum_operator">Thợ trông trống cà</option>
              </select>
              <select aria-label="Lọc theo trạng thái" value={active} onChange={(event) => { setActive(event.target.value); setPage(1) }}><option value="">Mọi trạng thái</option><option value="true">Đang hoạt động</option><option value="false">Đã vô hiệu hóa</option></select>
              <Button variant="outline" type="submit">Tìm kiếm</Button>
            </form>
            <div className="panel account-table-panel"><div className="table-wrap"><table className="account-table"><thead><tr><th>TÀI KHOẢN</th><th>VAI TRÒ</th><th>CƠ SỞ</th><th>TRẠNG THÁI</th><th>NGÀY TẠO</th><th>ĐĂNG NHẬP GẦN NHẤT</th><th></th></tr></thead><tbody>
              {!loading && items.map((account) => <tr key={account.id}><td><div className="account-name"><span className="account-avatar">{account.display_name.slice(0, 2).toUpperCase()}</span><span><strong>{account.display_name}</strong><small>@{account.username}</small></span></div></td><td><span className={`role-badge role-${account.role}`}>{roleLabel(account.role)}</span></td><td><div className="facility-tags">{account.role === 'admin' && !account.facilities.length ? <span className="muted-tag">Toàn hệ thống</span> : account.facilities.length ? account.facilities.map((facility) => <span key={facility.id}>{facility.name}</span>) : <span className="muted-tag">Chưa gán</span>}</div></td><td><span className={`status-label ${account.is_active ? 'status-enabled' : 'status-disabled'}`}><i />{account.is_active ? 'Hoạt động' : 'Vô hiệu hóa'}</span></td><td>{formatDate(account.created_at)}</td><td>{account.last_login_at ? formatDate(account.last_login_at) : <span className="muted-text">Chưa đăng nhập</span>}</td><td><div className="row-actions"><button className="icon-button" title="Chỉnh sửa" aria-label={`Chỉnh sửa ${account.username}`} onClick={() => setEditing(account)}><Pencil size={15} /></button><button className="icon-button" title="Đặt lại mật khẩu" aria-label={`Đặt lại mật khẩu ${account.username}`} onClick={() => setResetting(account)}><KeyRound size={15} /></button><button className="text-action" onClick={() => void setStatus(account, !account.is_active)}>{account.is_active ? 'Vô hiệu hóa' : 'Kích hoạt'}</button></div></td></tr>)}
              {!loading && items.length === 0 && <tr><td colSpan={7}><div className="empty-state"><UsersRound size={22} /><strong>Chưa có tài khoản phù hợp</strong><span>Thay đổi bộ lọc hoặc tạo tài khoản mới.</span></div></td></tr>}
              {loading && <tr><td colSpan={7}><div className="empty-state">Đang tải tài khoản…</div></td></tr>}
            </tbody></table></div><div className="table-footer"><span>{total ? `Hiển thị ${Math.min((page - 1) * 10 + 1, total)}–${Math.min(page * 10, total)} trong ${total} tài khoản` : '0 tài khoản'}</span><div className="pagination"><button className="icon-button" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Trang trước"><ChevronLeft size={16} /></button><span>Trang {page} / {pageCount}</span><button className="icon-button" disabled={page >= pageCount} onClick={() => setPage(page + 1)} aria-label="Trang sau"><ChevronRight size={16} /></button></div></div></div>
          </>
        ) : tab === 'facilities' && isAdmin ? (
          <div className="panel account-table-panel">
            <div className="table-wrap">
              <table className="account-table">
                <thead>
                  <tr>
                    <th>MÃ CHI NHÁNH</th>
                    <th>TÊN CHI NHÁNH</th>
                    <th>TRẠNG THÁI</th>
                    <th>QUY MÔ</th>
                    <th>CHỨC NĂNG HỆ THỐNG</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {(facilitiesOverview.length ? facilitiesOverview : facilities.map(f => ({
                    ...f,
                    is_active: f.is_active !== false,
                    is_demo: false,
                    created_at: new Date().toISOString(),
                    employees_count: 0,
                    drums_count: 0,
                    running_drums_count: 0,
                    cameras_count: 0,
                    scales_count: 0,
                    drum_status: 'ready' as const,
                    camera_status: 'unconfigured' as const,
                    scale_status: 'unconfigured' as const,
                  }))).map((fac) => (
                    <tr key={fac.id}>
                      <td><strong>{fac.code}</strong> {fac.is_demo && <span className="muted-tag" style={{ marginLeft: 6 }}>Demo</span>}</td>
                      <td><span style={{ fontWeight: 600 }}>{fac.name}</span></td>
                      <td><span className={`status-label ${fac.is_active ? 'status-enabled' : 'status-disabled'}`}><i />{fac.is_active ? 'Hoạt động' : 'Tạm ngừng'}</span></td>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                          <span><strong>{fac.employees_count}</strong> nhân sự</span>
                          <small style={{ color: '#64748b' }}><strong>{fac.drums_count}</strong> trống cà</small>
                        </div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                          <span
                            className={`badge ${fac.drum_status === 'running' ? 'badge-running' : fac.drum_status === 'ready' ? 'badge-ready' : 'badge-inactive'}`}
                            title={fac.drum_status === 'running' ? `${fac.running_drums_count} trống đang sấy cà` : fac.drum_status === 'ready' ? `${fac.drums_count} trống sấy sẵn sàng` : 'Chưa thiết lập trống sấy'}
                          >
                            <Flame size={12} />
                            {fac.drum_status === 'running' ? `Trống sấy: Đang chạy (${fac.running_drums_count}/${fac.drums_count})` : fac.drum_status === 'ready' ? `Trống sấy: Sẵn sàng (${fac.drums_count})` : 'Trống: Chưa có'}
                          </span>
                          <span
                            className={`badge ${fac.camera_status === 'active' ? 'badge-camera-active' : 'badge-inactive'}`}
                            title={fac.camera_status === 'active' ? `${fac.cameras_count} camera đang kết nối` : 'Chưa cấu hình camera giám sát'}
                          >
                            <Camera size={12} />
                            {fac.camera_status === 'active' ? `Camera: Đang kết nối (${fac.cameras_count})` : 'Camera: Chưa kết nối'}
                          </span>
                          <span
                            className={`badge ${fac.scale_status === 'active' ? 'badge-scale-active' : 'badge-inactive'}`}
                            title={fac.scale_status === 'active' ? `${fac.scales_count} trạm cân đang online` : 'Chưa có đầu cân'}
                          >
                            <Scale size={12} />
                            {fac.scale_status === 'active' ? 'Cân: Hoạt động' : 'Cân: Chưa kết nối'}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="icon-button"
                            title="Xem chi tiết chi nhánh"
                            aria-label={`Xem chi tiết ${fac.name}`}
                            onClick={() => setViewingFacilityId(fac.id)}
                          >
                            <Eye size={15} />
                          </button>
                          <button
                            className="icon-button"
                            title="Sửa thông tin chi nhánh"
                            aria-label={`Sửa ${fac.name}`}
                            onClick={() => setEditingFacilityData(fac)}
                          >
                            <Pencil size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {facilitiesOverview.length === 0 && facilities.length === 0 && (
                    <tr><td colSpan={6} style={{ textAlign: 'center', padding: '30px', color: '#94a3b8' }}>Chưa có chi nhánh nào. Hãy nhấn "+ Thêm chi nhánh" để tạo.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="panel audit-panel">
            <div className="panel-heading"><div><span className="section-kicker">LỊCH SỬ QUẢN TRỊ</span><h2>Nhật ký tài khoản</h2></div><FileClock size={18} /></div>
            {loading ? <div className="empty-state">Đang tải nhật ký…</div> : audit.length ? <div className="audit-list">{audit.map((entry) => <div className="audit-row" key={entry.id}><span className="audit-icon"><ShieldCheck size={15} /></span><div><strong>{auditLabel(entry.event)}</strong><span>{entry.actor_username || 'Hệ thống'}{entry.target_username ? ` · ${entry.target_username}` : ''}</span><span className="audit-summary">{auditSummary(entry, facilities)}</span></div><time>{formatDate(entry.created_at)}</time></div>)}</div> : <div className="empty-state"><FileClock size={22} /><strong>Chưa có thao tác nào</strong><span>Thay đổi tài khoản sẽ được ghi nhận tại đây.</span></div>}
          </div>
        )}
        <footer className="page-footer"><span>© 2026 Công ty TNHH Như Tùng</span><span className="footer-separator">·</span><span>Nhật ký không lưu mật khẩu hoặc session secret.</span></footer>
      </div>
    </main>
    {editing && <AccountDialog account={editing === 'new' ? null : editing} facilities={facilities} csrf={csrf} currentUserRole={user.role} managerFacilities={user.facilities} onClose={() => setEditing(null)} onSaved={() => afterSave(editing === 'new' ? 'Đã tạo tài khoản thành công.' : 'Đã cập nhật tài khoản.')} />}
    {editingFacility && <FacilityDialog csrf={csrf} onClose={() => setEditingFacility(false)} onSaved={() => afterSave('Đã tạo chi nhánh mới thành công.')} />}
    {editingFacilityData && <EditFacilityDialog facility={editingFacilityData} csrf={csrf} onClose={() => setEditingFacilityData(null)} onSaved={() => afterSave('Đã cập nhật chi nhánh thành công.')} />}
    {viewingFacilityId !== null && <FacilityDetailDialog facilityId={viewingFacilityId} csrf={csrf} onClose={() => setViewingFacilityId(null)} onEdit={(fac) => { setViewingFacilityId(null); setEditingFacilityData(fac) }} />}
    {resetting && <ResetPasswordDialog account={resetting} csrf={csrf} onClose={() => setResetting(null)} onSaved={() => afterSave('Đã đặt lại mật khẩu và kết thúc các phiên cũ.')} />}
  </div>
}

function roleLabel(role: UserProfile['role']) {
  return role === 'admin'
    ? 'Quản trị viên'
    : role === 'manager'
    ? 'Quản lý chi nhánh'
    : role === 'drum_operator'
    ? 'Trông trống cà'
    : 'Nhân viên cân'
}
function formatDate(value: string) { return new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(value)) }
function auditLabel(event: string) { const names: Record<string, string> = { account_created: 'Tạo tài khoản', account_updated: 'Cập nhật tài khoản', account_activated: 'Kích hoạt tài khoản', account_deactivated: 'Vô hiệu hóa tài khoản', password_reset: 'Đặt lại mật khẩu', password_changed: 'Đổi mật khẩu', first_admin_bootstrapped: 'Khởi tạo quản trị viên đầu tiên', facility_created: 'Tạo chi nhánh mới', facility_updated: 'Cập nhật chi nhánh' }; return names[event] || event }
function auditSummary(entry: AuditItem, facilities: FacilityProfile[]) {
  if (entry.event === 'password_reset' || entry.event === 'password_changed') return 'Các phiên đăng nhập cũ đã bị thu hồi.'
  const before = entry.changes.before as Record<string, unknown> | undefined
  const after = entry.changes.after as Record<string, unknown> | undefined
  if (!after) return entry.event === 'first_admin_bootstrapped' ? 'Khởi tạo quyền quản trị.' : entry.event === 'facility_created' ? `Tạo cơ sở ${(entry.changes as any).name || ''}` : entry.event === 'facility_updated' ? `Cập nhật chi nhánh ${(entry.changes as any).code || ''}` : 'Đã ghi nhận thao tác.'
  const parts: string[] = []
  if (typeof after.role === 'string' && after.role !== before?.role) parts.push(`Vai trò: ${roleLabel(after.role as UserProfile['role'])}`)
  if (Array.isArray(after.facility_ids)) {
    const oldIds = Array.isArray(before?.facility_ids) ? before.facility_ids.join(',') : ''
    if (entry.event === 'account_created' || after.facility_ids.join(',') !== oldIds) {
      const names = after.facility_ids.map((id) => facilities.find((facility) => facility.id === id)?.name || `Cơ sở ${id}`)
      parts.push(`Cơ sở: ${names.length ? names.join(', ') : after.role === 'admin' ? 'Toàn hệ thống' : 'Chưa gán'}`)
    }
  }
  if (typeof after.is_active === 'boolean' && after.is_active !== before?.is_active) parts.push(`Trạng thái: ${after.is_active ? 'Hoạt động' : 'Vô hiệu hóa'}`)
  if (typeof after.display_name === 'string' && after.display_name !== before?.display_name) parts.push(`Tên hiển thị: ${after.display_name}`)
  return parts.join(' · ') || 'Đã ghi nhận thao tác.'
}

function FacilityChecklist({ facilities, selected, onChange }: { facilities: FacilityProfile[]; selected: number[]; onChange: (ids: number[]) => void }) {
  return <fieldset className="facility-checklist"><legend>Cơ sở được phép truy cập</legend>{facilities.length ? facilities.map((facility) => <label key={facility.id}><input type="checkbox" checked={selected.includes(facility.id)} onChange={(event) => onChange(event.target.checked ? [...selected, facility.id] : selected.filter((id) => id !== facility.id))} /><span>{facility.name}</span><small>{facility.code}</small></label>) : <p>Chưa có cơ sở đang hoạt động.</p>}</fieldset>
}

function AccountDialog({
  account,
  facilities,
  csrf,
  currentUserRole,
  managerFacilities,
  onClose,
  onSaved,
}: {
  account: Account | null
  facilities: FacilityProfile[]
  csrf: string
  currentUserRole: UserProfile['role']
  managerFacilities?: FacilityProfile[]
  onClose: () => void
  onSaved: () => void
}) {
  const isManager = currentUserRole === 'manager'
  const [username, setUsername] = useState(account?.username || '')
  const [displayName, setDisplayName] = useState(account?.display_name || '')
  const [role, setRole] = useState<UserProfile['role']>(account?.role || (isManager ? 'staff' : 'manager'))
  const [selected, setSelected] = useState<number[]>(
    account?.facilities.map((item) => item.id) ||
    (isManager && managerFacilities?.length ? managerFacilities.map((f) => f.id) : [])
  )
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const allowedFacilities = isManager && managerFacilities?.length
    ? facilities.filter((f) => managerFacilities.some((mf) => mf.id === f.id))
    : facilities

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      if (role !== 'admin' && selected.length === 0) throw new Error('Quản lý, nhân viên và trông trống cần ít nhất một cơ sở.')
      if (account) await apiRequest(`/admin/accounts/${account.id}`, csrf, { method: 'PATCH', body: JSON.stringify({ display_name: displayName, role, facility_ids: selected }) })
      else await apiRequest('/admin/accounts', csrf, { method: 'POST', body: JSON.stringify({ username, display_name: displayName, role, facility_ids: selected, password }) })
      onSaved()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể lưu tài khoản.') }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-scrim" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="modal-card account-modal" role="dialog" aria-modal="true" aria-labelledby="account-title">
        <div className="modal-heading">
          <div><span className="section-kicker">TÀI KHOẢN & PHÂN QUYỀN</span><h2 id="account-title">{account ? 'Chỉnh sửa tài khoản' : 'Tạo tài khoản'}</h2></div>
          <button className="icon-button" onClick={onClose} aria-label="Đóng"><X size={18} /></button>
        </div>
        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          {!account && <label>Tên đăng nhập<input autoComplete="off" required minLength={3} maxLength={64} value={username} onChange={(event) => setUsername(event.target.value)} /><small>Dùng chữ thường, số, dấu chấm, gạch dưới hoặc gạch ngang.</small></label>}
          <label>Tên hiển thị<input required maxLength={120} value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label>
          <label>Vai trò
            <select value={role} onChange={(event) => setRole(event.target.value as UserProfile['role'])}>
              {isManager ? (
                <>
                  <option value="staff">Nhân viên trạm cân</option>
                  <option value="drum_operator">Thợ trông trống cà</option>
                </>
              ) : (
                <>
                  <option value="manager">Quản lý chi nhánh (Manager)</option>
                  <option value="admin">Quản trị viên (Admin)</option>
                  <option value="staff">Nhân viên trạm cân</option>
                  <option value="drum_operator">Thợ trông trống cà</option>
                </>
              )}
            </select>
          </label>
          <FacilityChecklist facilities={allowedFacilities} selected={selected} onChange={setSelected} />
          {!account && <label>Mật khẩu ban đầu<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} /><small>Tối thiểu 12 ký tự. Mật khẩu không xuất hiện trong nhật ký.</small></label>}
          {error && <div className="form-error" role="alert">{error}</div>}
          <div className="modal-actions">
            <Button type="button" variant="outline" onClick={onClose}>Hủy</Button>
            <Button type="submit" disabled={busy}>{busy ? 'Đang lưu…' : account ? 'Lưu thay đổi' : 'Tạo tài khoản'}</Button>
          </div>
        </form>
      </section>
    </div>
  )
}

function ResetPasswordDialog({ account, csrf, onClose, onSaved }: { account: Account; csrf: string; onClose: () => void; onSaved: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try { await apiRequest(`/admin/accounts/${account.id}/reset-password`, csrf, { method: 'POST', body: JSON.stringify({ new_password: password }) }); onSaved() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể đặt lại mật khẩu.') }
    finally { setBusy(false) }
  }
  return <div className="modal-scrim" role="presentation"><section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="reset-title"><div className="modal-heading"><div><span className="section-kicker">KẾT THÚC PHIÊN HIỆN TẠI</span><h2 id="reset-title">Đặt lại mật khẩu</h2></div><button className="icon-button" onClick={onClose} aria-label="Đóng"><X size={18} /></button></div><p className="dialog-description">Mật khẩu mới của <strong>{account.display_name}</strong> sẽ kết thúc mọi phiên đăng nhập cũ.</p><form className="auth-form" onSubmit={(event) => void submit(event)}><label>Mật khẩu mới<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} /><small>Tối thiểu 12 ký tự.</small></label>{error && <div className="form-error" role="alert">{error}</div>}<div className="modal-actions"><Button type="button" variant="outline" onClick={onClose}>Hủy</Button><Button type="submit" disabled={busy}>{busy ? 'Đang lưu…' : 'Đặt lại mật khẩu'}</Button></div></form></section></div>
}

export default App
