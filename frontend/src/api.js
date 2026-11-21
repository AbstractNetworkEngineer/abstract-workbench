const BASE = '';

/** 访问令牌由后端注入 index.html；跨域页面无法读取它（同源策略保护）。 */
function accessToken() {
  return document.querySelector('meta[name="netdeck-token"]')?.content || '';
}

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', 'X-Access-Token': accessToken() },
    ...options,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail || j);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  del: (path) => request(path, { method: 'DELETE' }),
};

/** FormData 上传（手册导入等），不设置 Content-Type 让浏览器带 boundary。 */
export async function upload(path, file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'X-Access-Token': accessToken() },
    body: fd,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail || j);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export function wsUrl(params) {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, v);
  });
  q.set('token', accessToken());
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/session?${q.toString()}`;
}
