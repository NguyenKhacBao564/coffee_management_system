/* D05i mode of the existing D05e crop review; local labels only, no OCR. */
(function (root) {
  'use strict';
  const editable = new Set(['readability', 'readable_lines', 'layout', 'split_y_crop',
    'full_text', 'top_text', 'bottom_text', 'single_text', 'notes', 'reviewed_at']);
  const stable = x => JSON.stringify(x, function (key, value) {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? Object.fromEntries(Object.keys(value).sort().map(k => [k, value[k]])) : value;
  });
  function validateItem(item, draft = false) {
    if (!['pending', 'readable_full', 'readable_partial', 'unreadable'].includes(item.readability)) throw Error('Khả năng đọc không hợp lệ');
    if (!['pending', 'single-line', 'two-line'].includes(item.layout)) throw Error('Bố cục không hợp lệ');
    const lines = item.readable_lines;
    if (!Array.isArray(lines) || new Set(lines).size !== lines.length || lines.some(x => !['top', 'bottom', 'single'].includes(x))) throw Error('Dòng đọc được không hợp lệ');
    if (!draft && ['readable_full', 'readable_partial'].includes(item.readability)) {
      if (item.layout === 'pending') throw Error('Cần xác nhận bố cục cho crop đọc được');
      const allowed = item.layout === 'two-line' ? ['top', 'bottom'] : ['single'];
      if (!lines.length || lines.some(x => !allowed.includes(x))) throw Error('Hãy đánh dấu dòng đọc được');
      if (item.readability === 'readable_full' && lines.length !== allowed.length) throw Error('Đọc toàn biển cần đủ các dòng');
    }
    if (!draft && item.readability === 'unreadable' && lines.length) throw Error('Không đọc được thì không chọn dòng đọc chắc');
    if (item.split_y_crop !== null && (!Number.isInteger(item.split_y_crop) || item.split_y_crop <= 0 || item.split_y_crop >= item.height)) throw Error('Vị trí tách dòng phải nằm trong crop gốc');
    for (const k of ['full_text', 'top_text', 'bottom_text', 'single_text', 'notes', 'reviewed_at']) if (typeof item[k] !== 'string') throw Error(`${k} phải là chuỗi`);
  }
  function validateReview(initial, received, draft = false) {
    if (received.dataset_id !== initial.dataset_id || received.schema_version !== initial.schema_version) throw Error('Nhãn thuộc bộ crop khác');
    if (stable(Object.keys(received).sort()) !== stable(Object.keys(initial).sort())) throw Error('Metadata nhãn thiếu hoặc có trường lạ');
    for (const [k, v] of Object.entries(initial)) if (!['items', 'label_origin', 'review_provenance'].includes(k) && stable(received[k]) !== stable(v)) throw Error(`Metadata nguồn bị đổi: ${k}`);
    if (!['manual_review_required', 'manual_review'].includes(received.label_origin)) throw Error('Nguồn nhãn không hợp lệ');
    const items = received.items;
    if (!Array.isArray(items) || items.length !== initial.items.length || new Set(items.map(i => i.crop_id)).size !== items.length) throw Error('Danh sách crop thiếu hoặc trùng');
    const base = new Map(initial.items.map(i => [i.crop_id, i]));
    for (const item of items) {
      const original = base.get(item.crop_id);
      if (!original || stable(Object.keys(item).sort()) !== stable(Object.keys(original).sort())) throw Error('Crop không thuộc bộ này hoặc thiếu trường');
      for (const [k, v] of Object.entries(original)) if (!editable.has(k) && stable(item[k]) !== stable(v)) throw Error(`Metadata crop bị đổi: ${k}`);
      validateItem(item, draft);
    }
    return structuredClone(received);
  }
  function exportReview(initial, data, now = new Date().toISOString()) {
    const result = validateReview(initial, data);
    result.label_origin = 'manual_review';
    result.review_provenance = {origin: 'human_crop_readability_review; no OCR-derived labels', exported_at_utc: now};
    return result;
  }
  function mount(initial) {
    document.title = 'D05i · Khả năng đọc crop native';
    const $ = id => document.getElementById(id);
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    const storageKey = `d05i:readability:${initial.dataset_id}`;
    let data = structuredClone(initial), page = 0;
    const pageSize = 12;
    document.querySelector('header').innerHTML = `<h1>D05i · Khả năng đọc trên từng crop</h1>
      <p class="hint">Đánh giá thông tin nhìn thấy trong chính crop, không suy ra từ ảnh khác hoặc biển đã biết. Ảnh gốc và bản nearest-neighbor 8× không làm mượt. OCR và transcript cũ không hiển thị. Chưa xem thì giữ pending; bbox khớp không tự chứng minh crop đủ chữ.</p>
      <nav><button id="save">Xuất nhãn JSON</button><button id="csv">Xuất CSV</button><label>Nạp JSON <input id="load" type="file" accept=".json"></label>
      <label>Khả năng đọc <select id="filter"><option value="all">Tất cả</option><option value="pending">Pending</option><option value="readable_full">Đọc toàn biển</option><option value="readable_partial">Đọc một phần</option><option value="unreadable">Không đọc được</option></select></label>
      <label>Crop <select id="source"><option value="all">Manual + detector</option><option value="manual">Manual</option><option value="detector">Detector</option></select></label></nav>
      <p class="small">${initial.summary.crops} crop · ${initial.summary.manual_plate_annotations} bbox biển đã xác nhận · ${initial.summary.unique_confirmed_plate_strings} chuỗi biển xác nhận · ${initial.summary.captures} lượt quay. Crop/frame có tương quan, không phải số lượt xe độc lập. ${initial.summary.excluded_pending_detector_crops.length} crop D05e chưa xác nhận được giữ ngoài bộ này.</p>
      <p id="summary"></p><p id="message" role="status"></p><nav><button id="previous">← Trang trước</button><span id="page"></span><button id="next">Trang sau →</button></nav>`;
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) data = validateReview(initial, JSON.parse(saved), true);
    } catch (e) { $('message').textContent = `Không nạp bản lưu không hợp lệ: ${e.message}`; }
    function incomplete(item) { try { validateItem(item); return false; } catch { return true; } }
    function summary() {
      const counts = {pending: 0, readable_full: 0, readable_partial: 0, unreadable: 0};
      for (const item of data.items) counts[item.readability]++;
      $('summary').textContent = `Toàn biển ${counts.readable_full} · một phần ${counts.readable_partial} · không đọc ${counts.unreadable} · pending ${counts.pending} · mục cần bổ sung ${data.items.filter(incomplete).length}. Nhãn được lưu trong trình duyệt; hãy xuất JSON để bàn giao.`;
    }
    function saveLocal() {
      data.label_origin = 'manual_review';
      try { localStorage.setItem(storageKey, JSON.stringify(data)); } catch (e) { $('message').textContent = `Lưu local thất bại; hãy xuất JSON: ${e.message}`; }
      summary();
    }
    function download(name, body, type) {
      const a = document.createElement('a'), url = URL.createObjectURL(new Blob([body], {type}));
      a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    function card(item) {
      const el = document.createElement('article');
      el.className = `card ${item.readability === 'pending' ? 'pending' : 'confirmed'}`;
      const refs = item.references.map(r => `${r.kind} · ${r.model ?? 'manual'} · IoU ${r.bbox_iou == null ? '—' : r.bbox_iou.toFixed(3)} · score ${r.score == null ? 'không lưu trong nguồn' : r.score.toFixed(5)}`).join('\n');
      el.innerHTML = `<h2>${esc(item.sample_id)} · ${esc(item.crop_source)} · ${item.media_seconds.toFixed(3)} s</h2>
        <p class="meta">${esc(item.crop_id)}\n${item.width}×${item.height} px · bbox ${item.frame_bbox_xyxy.join(', ')} · ${esc(item.capture_group_id)}\n${esc(refs)}</p>
        <div class="grid"><div><h3>Pixel gốc</h3><div class="cropbox"><img loading="lazy" class="crop" style="max-width:none" width="${item.width}" height="${item.height}" src="${esc(item.crop_path)}" alt="Crop native"></div></div>
        <div><h3>Nearest-neighbor 8×</h3><div class="cropbox"><img loading="lazy" class="zoom" width="${item.width * 8}" height="${item.height * 8}" src="${esc(item.zoom8_path)}" alt="Phóng đúng 8 lần, không làm mượt"></div></div></div>
        <details><summary>Xem toàn cảnh định vị bbox (không dùng để đoán chữ trong crop)</summary><div class="imagebox"><img loading="lazy" class="context" src="${esc(item.annotated_path)}" alt="Xanh: bbox thủ công; cam: crop đang đánh giá"></div><p class="small">Xanh: bbox thủ công; cam: crop đang đánh giá.</p></details>
        <div class="form"><label>Khả năng đọc <select data-field="readability"><option value="pending">Chưa xem — pending</option><option value="readable_full">Đọc chắc toàn biển</option><option value="readable_partial">Đọc chắc một phần</option><option value="unreadable">Không đọc được</option></select></label>
        <label>Bố cục trong crop <select data-field="layout"><option value="pending">Chưa xác nhận</option><option value="single-line">Một dòng</option><option value="two-line">Hai dòng</option></select></label>
        <fieldset class="wide"><legend>Dòng đọc chắc (đọc toàn biển hai dòng: chọn cả trên và dưới)</legend>${[['top', 'Dòng trên'], ['bottom', 'Dòng dưới'], ['single', 'Biển một dòng']].map(([v, label]) => `<label style="display:inline-block;margin:6px"><input type="checkbox" data-line="${v}"> ${label}</label>`).join('')}</fieldset>
        <label>Toàn biển — nếu đọc chắc <input data-field="full_text" autocomplete="off"></label>
        <label>Tách dòng y theo pixel crop gốc (tùy chọn) <input data-field="split_y_crop" type="number" min="1" max="${item.height - 1}"></label>
        <label>Dòng trên <input data-field="top_text" autocomplete="off"></label><label>Dòng dưới <input data-field="bottom_text" autocomplete="off"></label>
        <label>Nội dung biển một dòng <input data-field="single_text" autocomplete="off"></label>
        <p class="small">Nội dung tùy chọn, chỉ nhập chữ nhìn trực tiếp. Để trống phần chưa chắc. Dòng thiếu nhãn sẽ không được chấm riêng; không tự suy từ chuỗi biển đã biết.</p>
        <label class="wide">Ghi chú <textarea data-field="notes"></textarea></label><p class="wide small" data-validation></p></div>`;
      function changed() {
        item.reviewed_at = new Date().toISOString();
        saveLocal();
        el.className = `card ${item.readability === 'pending' || incomplete(item) ? 'pending' : 'confirmed'}`;
        try { validateItem(item); el.querySelector('[data-validation]').textContent = ''; }
        catch (e) { el.querySelector('[data-validation]').textContent = e.message; }
      }
      for (const input of el.querySelectorAll('[data-field]')) {
        const key = input.dataset.field;
        input.value = item[key] ?? '';
        input.addEventListener('input', () => {
          item[key] = key === 'split_y_crop' ? (input.value === '' ? null : Number(input.value)) : input.value;
          if (key === 'readability' && item.readability === 'unreadable') {
            item.readable_lines = [];
            for (const check of el.querySelectorAll('[data-line]')) check.checked = false;
          }
          changed();
        });
      }
      for (const check of el.querySelectorAll('[data-line]')) {
        check.checked = item.readable_lines.includes(check.dataset.line);
        check.addEventListener('change', () => {
          item.readable_lines = [...el.querySelectorAll('[data-line]:checked')].map(x => x.dataset.line);
          changed();
        });
      }
      return el;
    }
    function filtered() { return data.items.filter(i => ($('filter').value === 'all' || i.readability === $('filter').value) && ($('source').value === 'all' || i.crop_source === $('source').value)); }
    function render() {
      const items = filtered(), pages = Math.max(1, Math.ceil(items.length / pageSize));
      page = Math.min(page, pages - 1);
      $('items').replaceChildren(...items.slice(page * pageSize, (page + 1) * pageSize).map(card));
      $('page').textContent = `Trang ${page + 1}/${pages} · ${items.length} mục sau lọc`;
      $('previous').disabled = page === 0; $('next').disabled = page === pages - 1;
      summary();
    }
    $('save').onclick = () => {
      try {
        const result = exportReview(initial, data);
        download('d05i-readability.manual.json', JSON.stringify(result, null, 2), 'application/json');
        $('message').textContent = 'Đã xuất JSON riêng; các mục pending giữ nguyên. Chuyển file tải xuống cho Codex để import/đối chiếu.';
      } catch (e) { $('message').textContent = `Chưa xuất: ${e.message}. Có thể để mục chưa hoàn tất về pending.`; }
    };
    $('csv').onclick = () => {
      const fields = ['crop_id', 'sample_id', 'crop_source', 'media_seconds', 'readability', 'readable_lines', 'layout', 'full_text', 'top_text', 'bottom_text', 'single_text', 'split_y_crop', 'notes'];
      const quote = x => '"' + String(Array.isArray(x) ? x.join('|') : x ?? '').replaceAll('"', '""') + '"';
      download('d05i-readability.manual.csv', '\ufeff' + [fields.join(','), ...data.items.map(i => fields.map(k => quote(i[k])).join(','))].join('\n'), 'text/csv');
    };
    $('load').onchange = async () => {
      try {
        const file = $('load').files[0]; if (!file) return;
        data = validateReview(initial, JSON.parse(await file.text()));
        saveLocal(); render(); $('message').textContent = 'Đã nạp JSON; nguồn, hash, bbox và scene_hash được giữ nguyên.';
      } catch (e) { $('message').textContent = `Không nạp: ${e.message}`; }
    };
    for (const id of ['filter', 'source']) $(id).onchange = () => {page = 0; render();};
    $('previous').onclick = () => {page--; render();};
    $('next').onclick = () => {page++; render();};
    render();
  }
  const api = {validateItem, validateReview, exportReview, mount};
  if (typeof module !== 'undefined') module.exports = api;
  root.CropReadability = api;
})(globalThis);
