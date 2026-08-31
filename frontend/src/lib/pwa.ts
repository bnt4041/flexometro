/** Registro del service worker y aviso de versión nueva.
 *
 *  El worker se registra solo en producción: en desarrollo se quedaría con
 *  los ficheros guardados y taparía los cambios en caliente de Vite, que es
 *  exactamente lo contrario de lo que se quiere mientras se programa. */

type Escucha = (hayVersionNueva: boolean) => void

let avisar: Escucha | null = null

export function alHaberVersionNueva(escucha: Escucha) {
  avisar = escucha
}

export function registrarServiceWorker() {
  if (!('serviceWorker' in navigator)) return
  if (import.meta.env.DEV) return

  window.addEventListener('load', () => {
    void navigator.serviceWorker
      .register('/sw.js')
      .then((registro) => {
        // Un worker ya esperando significa que la última visita dejó una
        // versión nueva sin aplicar.
        if (registro.waiting) avisar?.(true)

        registro.addEventListener('updatefound', () => {
          const nuevo = registro.installing
          if (!nuevo) return
          nuevo.addEventListener('statechange', () => {
            // `controller` presente = ya había una versión antes, así que
            // esto es una actualización y no la primera instalación.
            if (nuevo.state === 'installed' && navigator.serviceWorker.controller) {
              avisar?.(true)
            }
          })
        })
      })
      .catch(() => {
        // Sin service worker la aplicación funciona igual: pierde la
        // instalación y el arranque instantáneo, nada más.
      })
  })
}
