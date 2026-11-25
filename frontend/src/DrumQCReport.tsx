import { useState } from 'react'

type QCRunItem = {
  run_id: number
  drum_code: string
  batch_code: string
  source_type: string | null
  source_bed_number: number | null
  source_bed_batch_code: string | null
  water_drained_status: string | null
  raw_material_status: string | null
  estimated_spoiled_percent: number | string | null
  discharge_drain_status: string | null
  qc: { total_percent: number } | null
}

type Report = {
  total_runs: number
  qc_count: number
  pending_count: number
  groups: {
    method: string
    sample_point: string
    count: number
    sample_size: number
    total_percent: number
    black_count: number
    black_size: number
    black_percent: number | null
    burnt_count: number
    burnt_size: number
    burnt_percent: number | null
  }[]
  runs: QCRunItem[]
}

export default function DrumQCReport({ openRun }: { openRun: (id: number) => void }) {
  const [data, setData] = useState<Report | null>(null)
  const [error, setError] = useState('')

  const handleFilter = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const q = new URLSearchParams()
    for (const [k, v] of f.entries()) {
      if (v) q.set(k, String(v))
    }
    const api = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
    fetch(`${api}/drum-processing/reports/qc?${q}`, { credentials: 'same-origin' })
      .then(async (r) => {
        if (!r.ok) throw new Error('Không tải được báo cáo QC')
        setData(await r.json())
        setError('')
      })
      .catch((e) => setError(e.message))
  }

  const renderSourceBadge = (r: QCRunItem) => {
    if (r.source_type === 'indoor') {
      return (
        <span style={{ fontSize: '11px', background: '#ecfdf5', color: '#047857', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>
          Sàn {r.source_bed_number || '?'} (Xưởng trong)
          {r.discharge_drain_status && ` · ${r.discharge_drain_status === 'even' ? 'Ráo đều' : 'Chưa ráo đều'}`}
          {r.raw_material_status === 'spoiled' && ` · Úng: ${r.estimated_spoiled_percent !== null && r.estimated_spoiled_percent !== undefined ? `${r.estimated_spoiled_percent}%` : 'Chưa ước tính'}`}
          {r.raw_material_status === 'fresh' && ' · Cà tươi'}
        </span>
      )
    }
    if (r.source_type === 'outdoor') {
      return (
        <span style={{ fontSize: '11px', background: '#eff6ff', color: '#1d4ed8', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>
          Sàn tĩnh xưởng ngoài
        </span>
      )
    }
    return (
      <span style={{ fontSize: '11px', background: '#f1f5f9', color: '#64748b', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>
        Chưa ghi nhận nguồn
      </span>
    )
  }

  return (
    <details className="panel" style={{ padding: 20, margin: '20px 0' }}>
      <summary style={{ fontWeight: 600, cursor: 'pointer' }}>Báo cáo QC theo cơ sở & Đối chiếu nguồn sấy tĩnh</summary>
      <form className="dp-modal-form" onSubmit={handleFilter} style={{ marginTop: '12px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
          <label>
            Từ ngày xả
            <input name="start_day" type="date" />
          </label>
          <label>
            Đến ngày xả
            <input name="end_day" type="date" />
          </label>
          <label>
            Mã ID trống
            <input name="drum_id" type="number" min="1" />
          </label>
          <label>
            Phương pháp
            <select name="method">
              <option value="">Tất cả</option>
              <option value="gram">Gram</option>
              <option value="count">Số hạt</option>
            </select>
          </label>
          <label>
            Nguồn cà
            <select name="source_type">
              <option value="">Tất cả nguồn</option>
              <option value="indoor">Sàn tĩnh xưởng trong</option>
              <option value="outdoor">Sàn tĩnh xưởng ngoài</option>
              <option value="unrecorded">Chưa ghi nhận nguồn</option>
            </select>
          </label>
          <label>
            Số sàn (Xưởng trong)
            <input name="source_bed_number" type="number" min="1" placeholder="Ví dụ: 2" />
          </label>
          <label>
            Tình trạng ráo đều
            <select name="discharge_drain_status">
              <option value="">Tất cả</option>
              <option value="even">Ráo đều</option>
              <option value="uneven">Chưa ráo đều</option>
            </select>
          </label>
        </div>
        <button style={{ marginTop: '10px', alignSelf: 'flex-start' }}>Xem báo cáo đối chiếu</button>
      </form>

      {error && <p role="alert" style={{ color: '#dc2626', marginTop: '10px' }}>{error}</p>}

      {data && (
        <div style={{ marginTop: '16px' }}>
          <p style={{ fontWeight: 600 }}>
            {data.total_runs} mẻ xả · {data.qc_count} đã QC · {data.pending_count} chờ QC · Tỷ lệ QC{' '}
            {data.total_runs ? ((100 * data.qc_count) / data.total_runs).toFixed(1) : '0'}%
          </p>
          {data.groups.map((g) => (
            <p key={`${g.method}-${g.sample_point}`} style={{ fontSize: '13px', margin: '4px 0' }}>
              {g.method === 'gram' ? 'Gram' : 'Số hạt'} · {g.sample_point}: {g.count} mẻ, cỡ mẫu {g.sample_size}, lỗi gộp{' '}
              {Number(g.total_percent).toFixed(2)}%; đen đặc{' '}
              {g.black_percent == null
                ? 'chưa chấm'
                : `${Number(g.black_percent).toFixed(2)}% (${g.black_count} mẻ / ${g.black_size} mẫu)`}
              ; cháy{' '}
              {g.burnt_percent == null
                ? 'chưa chấm'
                : `${Number(g.burnt_percent).toFixed(2)}% (${g.burnt_count} mẻ / ${g.burnt_size} mẫu)`}
            </p>
          ))}
          <p style={{ fontSize: '12px', color: '#64748b', fontStyle: 'italic', margin: '8px 0' }}>
            Tỷ lệ gộp tính trên mẫu đã kiểm. Nhấp vào mẻ để xem chi tiết đối chiếu:
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {[...data.runs]
              .sort((a, b) => Number(b.qc?.total_percent ?? -1) - Number(a.qc?.total_percent ?? -1))
              .map((r) => (
                <div key={r.run_id} style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '6px', fontSize: '13px' }}>
                  <button
                    type="button"
                    style={{ background: 'none', border: 'none', color: '#0284c7', textDecoration: 'underline', cursor: 'pointer', padding: 0 }}
                    onClick={() => openRun(r.run_id)}
                  >
                    {r.drum_code} · {r.batch_code}
                  </button>
                  <span>· {r.qc ? <strong>{Number(r.qc.total_percent).toFixed(2)}% lỗi</strong> : 'Chờ QC'}</span>
                  {renderSourceBadge(r)}
                </div>
              ))}
          </div>
        </div>
      )}
    </details>
  )
}
