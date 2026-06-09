import { Component } from 'react'

/**
 * Error Boundary global. Captura cualquier error de runtime de los componentes
 * hijos y muestra un mensaje recuperable en lugar de dejar la pantalla en negro
 * (que es lo que ocurre cuando un error tumba el árbol de React sin boundary).
 *
 * Es un class component porque sólo los class components pueden ser error
 * boundaries (getDerivedStateFromError / componentDidCatch). No usa el contexto
 * de i18n a propósito: debe funcionar aunque el fallo venga de ese contexto, así
 * que lee el idioma directamente de localStorage de forma defensiva.
 */
const TXT = {
  es: {
    title: 'Algo ha fallado',
    body: 'Se ha producido un error al mostrar esta sección. Puedes recargar la página para continuar.',
    reload: 'Recargar',
  },
  en: {
    title: 'Something went wrong',
    body: 'An error occurred while rendering this section. You can reload the page to continue.',
    reload: 'Reload',
  },
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    // Log para diagnóstico en la consola del navegador.
    console.error('ErrorBoundary capturó un error:', error, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    let locale = 'es'
    try { locale = localStorage.getItem('locale') || 'es' } catch { /* noop */ }
    const t = TXT[locale] || TXT.es

    return (
      <div className="state-error" style={{ margin: 24, padding: 24, textAlign: 'center' }}>
        <h2 style={{ marginTop: 0 }}>{t.title}</h2>
        <p style={{ color: 'var(--text-muted)' }}>{t.body}</p>
        <button className="btn-primary btn-sm" onClick={() => window.location.reload()}>
          {t.reload}
        </button>
      </div>
    )
  }
}
