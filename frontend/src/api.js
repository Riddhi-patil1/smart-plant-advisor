// Thin fetch wrapper. Every call returns `data` from the { data } envelope or throws ApiError.
export class ApiError extends Error {
  constructor(message, { status = 0, code = 'error', fields = {} } = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

async function request(method, path, body) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('The backend is not reachable. Start the Flask server (python run.py) and retry.', { code: 'network' });
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    /* non-JSON response */
  }
  if (!response.ok) {
    const e = payload?.error;
    throw new ApiError(e?.message || `Request failed (${response.status}).`, {
      status: response.status,
      code: e?.code,
      fields: e?.fields || {},
    });
  }
  return payload?.data;
}

export function qs(params) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, v);
  });
  const s = q.toString();
  return s ? `?${s}` : '';
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b = {}) => request('POST', p, b),
  put: (p, b = {}) => request('PUT', p, b),
  del: (p) => request('DELETE', p),
};
