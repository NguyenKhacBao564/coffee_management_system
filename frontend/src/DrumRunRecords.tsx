import { useEffect, useState } from 'react'

type Obj = Record<string, any>
const base = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '') + '/drum-processing'
const local = (v: string | null) => v ? new Date(new Date(v).getTime() + 7 * 3600000).toISOString().slice(0, 16) : ''
const utc = (v: FormDataEntryValue | null) => v ? new Date(`${v}:00+07:00`).toISOString() : null
const numeric = (v: FormDataEntryValue | null) => v === '' || v === null ? null : Number(v)

export default function DrumRunRecords({ runId, completed, role, csrf }: { runId: number; completed: boolean; role: string; csrf: string }) {
  const [source, setSource] = useState<Obj | null>(null)
  const [incidents, setIncidents] = useState<Obj[]>([])
  const [qc, setQc] = useState<Obj | null>(null)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  const api = async (path: string, method = 'GET', body?: Obj) => {
    const r = await fetch(`${base}/runs/${runId}/${path}`, { method, credentials: 'same-origin', headers: method === 'GET' ? {} : { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: body ? JSON.stringify(body) : undefined })
    const data = await r.json()
    if (!r.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'Dữ liệu không hợp lệ')
    return data
  }
  useEffect(() => { let active = true; Promise.all([api('source'), api('incidents'), api('qc')]).then(([s, i, q]) => { if (active) { setSource(s); setIncidents(i); setQc(q) } }).catch(e => setError(e.message)); return () => { active = false } }, [runId, version])
  const submit = async (path: string, method: string, body: Obj) => { try { setError(''); await api(path, method, body); setVersion(v => v + 1) } catch (e) { setError(e instanceof Error ? e.message : 'Không lưu được') } }
  const show = (v: unknown) => v === null || v === undefined ? 'Chưa ghi nhận' : String(v)
  return <section className="panel" style={{ margin: '20px 0', padding: 20 }}>
    <h2>Dữ liệu đầu vào, sự cố và QC</h2>{error && <p role="alert" style={{ color: '#b91c1c' }}>{error}</p>}
    {source && <details><summary>Đầu vào sau xay · {source.waiting_minutes == null ? 'Chưa đủ giờ tính thời gian chờ' : `${source.waiting_minutes} phút chờ${source.times_estimated ? ' (ước tính)' : ''}`}</summary>
      <form className="dp-modal-form" key={version} onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void submit('source', 'PUT', { source_lot_code: f.get('lot') || null, traceability: f.get('trace') || null, source_note: f.get('source_note') || null, ground_at: utc(f.get('ground')), drying_started_at: utc(f.get('dry')), drying_route: f.get('route') || null, times_estimated: f.get('estimated') === '' ? null : f.get('estimated') === 'yes', water_exposure: f.get('water') || null, water_exposure_minutes: numeric(f.get('water_minutes')), water_exposure_note: f.get('water_note') || null }) }}>
        <label>Truy xuất lô<select name="trace" defaultValue={source.traceability || ''}><option value="">Chưa ghi nhận</option><option value="known">Một lô xác định</option><option value="unknown">Chưa xác định</option><option value="mixed">Trộn nhiều lô</option></select></label>
        <label>Mã truy xuất lô gốc<input name="lot" defaultValue={source.source_lot_code || ''} maxLength={120}/></label><label>Ghi chú lô<input name="source_note" defaultValue={source.source_note || ''} maxLength={500}/></label>
        <label>Giờ xay<input name="ground" type="datetime-local" defaultValue={local(source.ground_at)}/></label><label>Giờ bắt đầu sấy lần đầu<input name="dry" type="datetime-local" defaultValue={local(source.drying_started_at)}/></label>
        <label>Tuyến sấy<select name="route" defaultValue={source.drying_route || ''}><option value="">Chưa ghi nhận</option><option value="static">Qua sàn tĩnh</option><option value="direct">Đi thẳng vào trống</option><option value="unknown">Chưa rõ</option></select></label><label>Độ chính xác giờ<select name="estimated" defaultValue={source.times_estimated == null ? "" : source.times_estimated ? "yes" : "no"}><option value="">Chưa ghi nhận</option><option value="yes">Giờ ước tính</option><option value="no">Giờ thực tế</option></select></label>
        <label>Đọng nước hoặc ngâm<select name="water" defaultValue={source.water_exposure || ''}><option value="">Chưa ghi nhận</option><option value="yes">Có</option><option value="no">Không ghi nhận</option><option value="unknown">Chưa rõ</option></select></label><label>Thời gian tiếp xúc nước ước tính (phút)<input name="water_minutes" type="number" min="0" defaultValue={source.water_exposure_minutes ?? ''}/></label><label>Ghi chú<input name="water_note" defaultValue={source.water_exposure_note || ''} maxLength={500}/></label><button type="submit">Lưu đầu vào</button>
      </form></details>}
    <details><summary>Sự cố theo mẻ ({incidents.length})</summary>{incidents.map(i => <p key={i.id}>{({ blade: 'Hỏng cánh đảo', rotation: 'Dừng quay', heat: 'Gián đoạn cấp nhiệt', other: 'Khác' } as Obj)[i.kind]} · {i.started_at ? new Date(i.started_at).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }) : 'Chưa rõ giờ'} · {show(i.note)} · {i.recorded_name}</p>)}
      <form className="dp-modal-form" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void submit('incidents', 'POST', { kind: f.get('kind'), started_at: utc(f.get('start')), ended_at: utc(f.get('end')), note: f.get('note') || null }) }}><label>Loại sự cố<select name="kind"><option value="blade">Hỏng cánh đảo</option><option value="rotation">Dừng quay</option><option value="heat">Gián đoạn cấp nhiệt</option><option value="other">Khác</option></select></label><label>Bắt đầu<input type="datetime-local" name="start"/></label><label>Kết thúc<input type="datetime-local" name="end"/></label><label>Ghi chú<input name="note" maxLength={1000}/></label><button>Ghi sự cố</button></form></details>
    <details open><summary>QC sau xả · {qc ? 'Đã có QC' : completed ? 'Chờ QC' : 'Chưa xả'}</summary>{qc && <p>Mẫu {qc.sample_size} {qc.method === 'gram' ? 'g' : 'hạt'} · {qc.sample_point} · Tổng lỗi {Number(qc.total_percent).toFixed(2)}% · Đen đặc {qc.black_percent == null ? 'Chưa chấm' : `${Number(qc.black_percent).toFixed(2)}%`} · Cháy {qc.burnt_percent == null ? 'Chưa chấm' : `${Number(qc.burnt_percent).toFixed(2)}%`} · {qc.recorded_name}</p>}
      {completed && !qc && ['manager', 'admin'].includes(role) && <form className="dp-modal-form" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void submit('qc', 'POST', { sampled_at: utc(f.get('sampled')), sample_point: f.get('point'), method: f.get('method'), sample_size: numeric(f.get('size')), total_defect: numeric(f.get('total')), black_defect: numeric(f.get('black')), burnt_defect: numeric(f.get('burnt')) }) }}><label>Thời điểm lấy mẫu<input type="datetime-local" name="sampled" required/></label><label>Điểm lấy mẫu<input name="point" required maxLength={200}/></label><label>Đơn vị<select name="method"><option value="gram">Gram</option><option value="count">Số hạt</option></select></label><label>Cỡ mẫu<input name="size" type="number" step="0.001" min="0.001" required/></label><label>Tổng lượng lỗi<input name="total" type="number" step="0.001" min="0" required/></label><label>Đen đặc (để trống nếu chưa chấm)<input name="black" type="number" step="0.001" min="0"/></label><label>Cháy (để trống nếu chưa chấm)<input name="burnt" type="number" step="0.001" min="0"/></label><button>Lưu QC</button></form>}
    </details>
  </section>
}
