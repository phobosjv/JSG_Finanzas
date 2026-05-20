import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../api/client'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(undefined) // undefined = cargando
  const [loading, setLoading] = useState(true)

  // Al montar, comprueba si hay sesión activa
  useEffect(() => {
    api.get('/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  // Escucha el evento global de logout (disparado por el cliente de API en 401)
  useEffect(() => {
    const handler = () => setUser(null)
    window.addEventListener('auth:logout', handler)
    return () => window.removeEventListener('auth:logout', handler)
  }, [])

  async function login(username, password) {
    const u = await api.post('/auth/login', { username, password })
    setUser(u)
    return u
  }

  async function logout() {
    await api.post('/auth/logout').catch(() => {})
    setUser(null)
  }

  return (
    <AuthCtx.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthCtx.Provider>
  )
}

export function useAuth() {
  return useContext(AuthCtx)
}
