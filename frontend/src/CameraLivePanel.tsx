import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'

type CameraHealth = { camera_id: string; facility_id: number; source_state: string; processing_state: string; worker_reporting: boolean; preview_url: string; last_frame_received_at: string | null; last_frame_decoded_at: string | null; last_frame_processed_at: string | null; receive_fps: number; process_fps: number; latency_ms: number | null; queue_depth: number; reconnect_count: number; last_error_code: string | null; processing_error_code: string | null; outbox_error_code: string | null; diagnostic_error_code: string | null; outbox_depth: number; last_evidence_saved_at: string | null; ai_job_state: string; roi_status: string; active_visits: number; mode?: string; preview_enabled?: boolean; preview_until_utc?: string; capture_active?: boolean; scale_contact?: string; scale_reader_status?: string; capture_metrics?: { candidate_count?: number; qualifying_plate_count?: number; evidence_count?: number; completion_reason?: string | null }; capture_policy?: { selection_mode?: string; capture_seconds?: number; max_evidence_frames?: number; success_plate_frames?: number } }
type Diagnostic = { diagnostic_id: string; kind: string; status: string; content_url: string | null; created_at: string }
const base = '/api/vehicle-pilot'
const date = (value: string | null) => value ? new Intl.DateTimeFormat('vi-VN', { timeStyle: 'medium', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(value)) : 'chưa có'

function CameraCard({ camera, csrf }: { camera: CameraHealth; csrf: string }) {
  const [preview, setPreview] = useState('')
  const [error, setError] = useState('')
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([])
  const [requesting, setRequesting] = useState(false)
  const [notice, setNotice] = useState('')
  const [requestedClip, setRequestedClip] = useState<{ id: string; status: string } | null>(null)
  useEffect(() => {
    let closed = false, timer = 0, objectUrl = '', tickCount = 0
    let controller: AbortController | null = null
    const tick = async () => {
      if (closed) return
      if (document.hidden) { timer = window.setTimeout(tick, 1000); return }
      controller = new AbortController()
      try {
        if (camera.preview_enabled) {
        const response = await fetch(camera.preview_url, { cache: 'no-store', credentials: 'same-origin', signal: controller.signal })
        if (!response.ok) throw new Error('Preview chưa cập nhật được; không kết luận camera offline.')
        const blob = await response.blob()
        if (!closed) { if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = URL.createObjectURL(blob); setPreview(objectUrl); setError('') }
        } else { if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = '' }; setPreview(''); setError('') }
        if (tickCount++ % 5 === 0) {
          const results = await fetch(`${base}/cameras/${camera.camera_id}/diagnostics`, { cache: 'no-store', signal: controller.signal })
          if (results.ok && !closed) setDiagnostics((await results.json()).items)
        }
      } catch (reason) {
        if (!controller.signal.aborted && !closed) setError(reason instanceof Error ? reason.message : 'Không cập nhật preview.')
      } finally { if (!closed) timer = window.setTimeout(tick, 1000) }
    }
    void tick()
    const onVisibility = () => { if (document.hidden) controller?.abort() }
    document.addEventListener('visibilitychange', onVisibility)
    return () => { closed = true; clearTimeout(timer); controller?.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); document.removeEventListener('visibilitychange', onVisibility) }
  }, [camera.camera_id, camera.preview_url, camera.preview_enabled])
  async function action(kind: 'process' | 'photo' | 'preview' | 'preview_stop') {
    setRequesting(true); setNotice('')
    try {
      const response = await fetch(`${base}/cameras/${camera.camera_id}/actions`, { method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: crypto.randomUUID(), action: kind, duration_seconds: 120 }) })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Không thực hiện được yêu cầu camera.')
      setNotice(kind === 'preview' ? 'Đã yêu cầu preview tối đa 2 phút; tự tắt khi hết hạn.' : kind === 'preview_stop' ? 'Đã yêu cầu tắt preview.' : kind === 'process' ? `Đã yêu cầu tìm và chụp biển tối đa ${camera?.capture_policy?.capture_seconds ?? 120} giây; crop đạt tiêu chí vẫn cần xác nhận thủ công.` : 'Đã yêu cầu một ảnh native; không gọi AI.')
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : 'Lỗi điều khiển camera.') }
    finally { setRequesting(false) }
  }
  async function capture() {
    setRequesting(true); setNotice(''); setRequestedClip(null)
    try {
      const response = await fetch(`${base}/cameras/${camera.camera_id}/diagnostics`, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf } })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Không tạo được clip kiểm tra.')
      setRequestedClip({ id: result.diagnostic_id, status: result.status })
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : 'Lỗi thu clip.') }
    finally { setRequesting(false) }
  }
  const clipStatus = requestedClip ? diagnostics.find(item => item.diagnostic_id === requestedClip.id)?.status || requestedClip.status : null
  const clipStatusText = ({ queued: 'đang chờ', capturing: 'đang thu', stored: 'đã lưu', interrupted: 'thu bị gián đoạn' } as Record<string, string>)[clipStatus || ''] || clipStatus
  return <article className="pilot-live-card">
    <div className="pilot-subheading"><h3>{camera.camera_id} · Live main</h3><span>{camera.worker_reporting ? 'Worker gửi health' : 'Health worker gián đoạn'}</span></div>
    {preview ? <img className="pilot-live-preview" src={preview} alt={`Preview live ${camera.camera_id}`} /> : <div className="pilot-empty">{camera.preview_enabled ? 'Đang chờ frame preview mới…' : 'Preview đang tắt để tiết kiệm tài nguyên.'}</div>}
    {error && <p className="pilot-alert pilot-error">{error} Ảnh đang giữ có thể là ảnh cũ.</p>}
    <div className="pilot-live-states"><strong>Nguồn: {camera.source_state === 'receiving' ? 'Đang nhận hình' : camera.source_state === 'reconnecting' ? 'Kết nối lại' : camera.source_state === 'idle_unchecked' ? 'Chưa kiểm tra gần đây · đang chờ kích hoạt' : camera.source_state === 'starting' ? 'Đang mở nguồn' : 'Gián đoạn / lỗi'}</strong><strong>Xử lý: {camera.processing_state === 'processing' ? 'Đang xử lý' : camera.processing_state === 'error' ? 'Lỗi inference' : camera.processing_state === 'stopped' ? 'Đã dừng' : camera.processing_state === 'idle' ? 'Đang chờ · không detect/OCR' : camera.processing_state === 'preview_only' ? 'Chỉ xem/chụp · không detect/OCR' : 'Gián đoạn / chưa có'}</strong></div>
    <dl className="pilot-live-metrics">
      <dt>Chế độ / phiên xử lý</dt><dd>{camera.mode === 'event_driven' ? 'Theo tín hiệu hoặc thao tác' : 'Liên tục'} · {camera.capture_active ? 'đợt xử lý đang mở' : 'không có đợt xử lý'}</dd>
      {camera.capture_policy?.selection_mode === 'plate_guided' && <><dt>Tìm ảnh có biển</dt><dd>{camera.capture_active ? `Đang tìm · tối đa ${camera.capture_policy.capture_seconds}s` : camera.capture_metrics?.completion_reason === 'plate_quality_target_reached_requires_review' ? 'Đã có crop đạt tiêu chí · cần xem xác nhận' : camera.capture_metrics?.completion_reason ? 'Đợt tìm đã kết thúc · cần xem lại' : 'Chờ kích hoạt'} · {camera.capture_metrics?.qualifying_plate_count ?? 0}/{camera.capture_policy.success_plate_frames} crop đạt tiêu chí · giữ tối đa {camera.capture_policy.max_evidence_frames} bộ ảnh</dd></>}
      <dt>PC cân / reader</dt><dd>{({ communicating: 'Đang liên lạc', delayed: 'Liên lạc chậm', lost_contact: 'Mất liên lạc', never_received: 'Chưa nhận heartbeat' } as Record<string, string>)[camera.scale_contact || ''] || 'chưa cập nhật'} · reader {camera.scale_reader_status || 'chưa đo'} · vẫn dùng nút chụp thủ công được</dd>
      <dt>Frame nhận / giải mã / xử lý (giờ VN)</dt><dd>{date(camera.last_frame_received_at)} / {date(camera.last_frame_decoded_at)} / {date(camera.last_frame_processed_at)}</dd>
      <dt>FPS nhận / xử lý</dt><dd>{camera.receive_fps} / {camera.process_fps} · queue {camera.queue_depth}/2 · trễ {camera.latency_ms ?? '—'} ms</dd>
      <dt>Reconnect / outbox</dt><dd>{camera.reconnect_count} / {camera.outbox_depth} · lượt đang mở {camera.active_visits ?? 0}</dd>
      <dt>Evidence xe gần nhất / AI job</dt><dd>{date(camera.last_evidence_saved_at)} / {camera.ai_job_state || 'chưa có'}</dd>
    </dl>
    {(camera.last_error_code || camera.processing_error_code || camera.outbox_error_code || camera.diagnostic_error_code) && <p className="pilot-alert pilot-error">{[camera.last_error_code, camera.processing_error_code, camera.outbox_error_code, camera.diagnostic_error_code].filter(Boolean).join(' · ')}</p>}
    <p className="pilot-muted">Không có xe hoặc OCR là bình thường. ROI bàn cân còn cần xác nhận trên snapshot overlay. Giờ frame là giờ Mac nhận, chưa phải giờ OSD của camera.</p>
    <div className="pilot-live-states">
      <Button variant="outline" disabled={requesting || !csrf || !camera.worker_reporting} onClick={() => void action('process')}>Tìm và chụp biển xe</Button>
      <Button variant="outline" disabled={requesting || !csrf || !camera.worker_reporting} onClick={() => void action('photo')}>Chụp ảnh native</Button>
      <Button variant="outline" disabled={requesting || !csrf || !camera.worker_reporting} onClick={() => void action(camera.preview_enabled ? 'preview_stop' : 'preview')}>{camera.preview_enabled ? 'Tắt preview' : 'Bật preview 2 phút'}</Button>
    </div>
    <Button variant="outline" disabled={requesting || !csrf || camera.source_state !== 'receiving'} onClick={() => void capture()}>Thu clip kiểm tra 15 giây</Button>
    {requestedClip && <p className="pilot-muted" role="status">Clip {requestedClip.id.slice(0, 8)}: {clipStatusText}. Chỉ thu khi nguồn còn cung cấp frame; không gọi AI.</p>}
    {notice && <p className="pilot-muted" role="status">{notice}</p>}
    <div className="pilot-diagnostics">{diagnostics.filter(item => item.kind === 'clip' || item.kind === 'snapshot' || item.kind === 'photo').slice(0, 4).map(item => <span key={item.diagnostic_id}>{item.content_url ? <a href={item.content_url} target="_blank" rel="noreferrer">{item.kind === 'clip' ? 'Clip kiểm tra' : 'Ảnh native / ROI'} · {date(item.created_at)}</a> : `${item.kind} · ${item.status}`}</span>)}</div>
    <small>Preview 640×360; evidence xe giữ ảnh native. Tìm biển có giới hạn; ảnh ứng viên kém/trùng được dọn, crop đạt tiêu chí vẫn cần người xác nhận. Snapshot kiểm tra tối đa 1/10 phút; ảnh chụp theo yêu cầu/đợt xử lý có giới hạn, diagnostic giữ 24 giờ; evidence xe 30 ngày.</small>
  </article>
}

export default function CameraLivePanel({ facilityId, csrf }: { facilityId: number | 'all'; csrf: string }) {
  const [cameras, setCameras] = useState<CameraHealth[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let closed = false, timer = 0
    let controller: AbortController | null = null
    setCameras([]); setLoading(true)
    const tick = async () => {
      if (closed) return
      if (document.hidden) { timer = window.setTimeout(tick, 1000); return }
      controller = new AbortController()
      try {
        const query = facilityId === 'all' ? '' : `?facility_id=${facilityId}`
        const response = await fetch(`${base}/cameras${query}`, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
        if (!response.ok) throw new Error(`API HTTP ${response.status}`)
        const value = await response.json()
        if (!closed) { setCameras(value.items); setError('') }
      } catch (reason) {
        if (!closed && !controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Lỗi API')
      } finally { if (!closed) { setLoading(false); timer = window.setTimeout(tick, 5000) } }
    }
    void tick()
    const onVisibility = () => { if (document.hidden) controller?.abort() }
    document.addEventListener('visibilitychange', onVisibility)
    return () => { closed = true; clearTimeout(timer); controller?.abort(); document.removeEventListener('visibilitychange', onVisibility) }
  }, [facilityId, retry])
  return <section className="pilot-live-section"><h2>Camera trực tiếp · nguồn và xử lý</h2>
    {error && <div className="pilot-alert pilot-error">Không cập nhật được camera từ API. Dữ liệu giữ lại có thể cũ; không kết luận camera/PC cân offline. {error}<Button variant="outline" onClick={() => setRetry(x => x + 1)}>Thử lại</Button></div>}
    {loading ? <p className="pilot-muted">Đang tải trạng thái camera…</p> : !cameras.length && !error ? <p className="pilot-muted">Chưa có camera báo health tại cơ sở này.</p> : null}
    <div className="pilot-live-grid">{cameras.map(camera => <CameraCard key={camera.camera_id} camera={camera} csrf={csrf} />)}</div>
  </section>
}
