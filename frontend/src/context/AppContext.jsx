import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from '../api/client'
import { translations } from '../i18n/translations'

const AppCtx = createContext(null)

export function AppProvider({ children }) {
  const [appName, setAppNameState] = useState('JSG Soft.')
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')
  const [locale, setLocaleState] = useState(() => localStorage.getItem('locale') || 'es')

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

  // Aplicar idioma al elemento <html> y persistir en localStorage
  useEffect(() => {
    document.documentElement.setAttribute('lang', locale)
    localStorage.setItem('locale', locale)
  }, [locale])

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

  function setLocale(lang) {
    setLocaleState(lang)
  }

  /** Función de traducción. Devuelve la cadena del idioma activo o la clave si no existe. */
  const t = useCallback(
    (key) => translations[locale]?.[key] ?? translations['es']?.[key] ?? key,
    [locale]
  )

  return (
    <AppCtx.Provider value={{ appName, setAppName, theme, toggleTheme, locale, setLocale, t }}>
      {children}
    </AppCtx.Provider>
  )
}

export function useAppConfig() {
  return useContext(AppCtx)
}
