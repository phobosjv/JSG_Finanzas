/**
 * Service Worker personalizado — JSG Portfolio
 *
 * Usa injectManifest: vite-plugin-pwa inyecta self.__WB_MANIFEST con los
 * assets a precargar. El resto del código gestiona push notifications y
 * notificationclick.
 */
import { precacheAndRoute } from 'workbox-precaching'

// Precargar todos los assets del build (inyectado por vite-plugin-pwa)
precacheAndRoute(self.__WB_MANIFEST)

// ---------------------------------------------------------------------------
//  Push notifications
// ---------------------------------------------------------------------------

self.addEventListener('push', event => {
  let data = {}
  try {
    data = event.data?.json() ?? {}
  } catch { /* payload no JSON, ignorar */ }

  const title   = data.title || 'JSG Portfolio'
  const options = {
    body:              data.body || '',
    icon:              '/icons/icon-192.png',
    badge:             '/icons/icon-192.png',
    data:              { url: data.url || '/markets' },
    requireInteraction: false,
    silent:             false,
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', event => {
  event.notification.close()
  const url = event.notification.data?.url || '/markets'

  event.waitUntil(
    clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then(wins => {
        // Si la app ya está abierta en alguna pestaña, enfocamos esa
        for (const win of wins) {
          if ('focus' in win) {
            win.focus()
            win.navigate?.(url)
            return
          }
        }
        // Si no hay ventana, abrimos una nueva
        return clients.openWindow(url)
      })
  )
})
