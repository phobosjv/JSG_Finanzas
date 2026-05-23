import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../api/client'

const AppCtx = createContext(null)

export function AppProvider({ children }) {
  const [appName, setAppNameState] = useState('FJS Finanzas')
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  // Cargar nombre de la app desde el backend (endpoint público)
  useEffect(() => {
    api.get('/config')
      .then(d => { if (d?.app_name) setAppNameState(d.app_name) })
      .catch(() => {})
  }, [])

  // Aplicar tema al elemento <html> y persistir en localStorage
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  // Actualizar título del navegador cuando cambia el nombre
  useEffect(() => {
    document.title = appName
  }, [appName])

  function setAppName(name) {
    setAppNameState(name)
  }

  function toggleTheme() {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'))
  }

  return (
    <AppCtx.Provider value={{ appName, setAppName, theme, toggleTheme }}>
      {children}
    </AppCtx.Provider>
  )
}

export function useAppConfig() {
  return useContext(AppCtx)
}
