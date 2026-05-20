/**
 * Cliente HTTP para el backend.
 *
 * - Todas las peticiones incluyen credenciales (cookie de sesión).
 * - HTTP 401 → dispara el evento global 'auth:logout' para que
 *   AuthContext limpie el estado y la app redirija a /login.
 * - Errores HTTP se convierten en Error con el mensaje del cuerpo JSON.
 */

const BASE = '/api'

async function request(method, path, body) {
  const opts = {
    method,
    credentials: 'include',
    headers: {},
  }

  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  const res = await fetch(`${BASE}${path}`, opts)

  if (res.status === 401) {
    window.dispatchEvent(new Event('auth:logout'))
    throw new Error('No autenticado')
  }

  if (res.status === 204) return null

  const data = await res.json().catch(() => null)

  if (!res.ok) {
    const msg = data?.detail ?? `Error ${res.status}`
    throw new Error(Array.isArray(msg) ? msg.map(e => e.msg).join('; ') : msg)
  }

  return data
}

export const api = {
  get:    (path)        => request('GET',    path),
  post:   (path, body)  => request('POST',   path, body),
  patch:  (path, body)  => request('PATCH',  path, body),
  delete: (path)        => request('DELETE', path),
}
