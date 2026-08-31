/* Service worker de Flexómetro.
 *
 * LA REGLA QUE NO SE PUEDE ROMPER: aquí NO se cachea nada de `/api` ni de
 * `/auth`. Esto es una aplicación multi-empresa con sesión; una respuesta de
 * API guardada en el disco del dispositivo puede acabar enseñándole a un
 * usuario los datos de otra organización, o los de antes de un cambio que
 * acaba de hacer. Un ERP que miente sobre el estado de una obra es peor que
 * un ERP que no abre sin cobertura.
 *
 * Lo que sí se cachea es la cáscara: el HTML, el JavaScript y los iconos. Con
 * eso la aplicación abre al instante y se instala en el móvil; los datos
 * siguen viniendo siempre de la red.
 */

const VERSION = 'flexometro-v1'
const ESENCIALES = [
  '/',
  '/manifest.webmanifest',
  '/favicon.ico',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png',
]

self.addEventListener('install', (evento) => {
  evento.waitUntil(
    caches.open(VERSION).then((cache) =>
      // `reload` para saltarse la caché del navegador: si no, al instalar se
      // guardaría lo que ya hubiera guardado, que puede ser lo viejo.
      cache.addAll(ESENCIALES.map((u) => new Request(u, { cache: 'reload' }))),
    ),
  )
  // NO se llama a skipWaiting: cambiar los ficheros bajo una aplicación que
  // está corriendo rompe los trozos que carga bajo demanda. El worker nuevo
  // espera, y la aplicación avisa de que hay versión nueva.
})

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((nombres) =>
        Promise.all(nombres.filter((n) => n !== VERSION).map((n) => caches.delete(n))),
      )
      .then(() => self.clients.claim()),
  )
})

/** Lo que nunca pasa por aquí. */
function esDatos(url) {
  return (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/auth/') ||
    url.pathname === '/health'
  )
}

self.addEventListener('fetch', (evento) => {
  const peticion = evento.request
  if (peticion.method !== 'GET') return

  const url = new URL(peticion.url)
  // Solo lo de este origen. Una fuente o un script de fuera se dejan pasar.
  if (url.origin !== self.location.origin) return
  if (esDatos(url)) return

  // Navegación: primero la red, para que un despliegue nuevo entre sin
  // esperar. Sin cobertura, la cáscara guardada — la aplicación abre y avisa
  // de que no hay conexión.
  if (peticion.mode === 'navigate') {
    evento.respondWith(
      fetch(peticion)
        .then((respuesta) => {
          const copia = respuesta.clone()
          caches.open(VERSION).then((cache) => cache.put('/', copia))
          return respuesta
        })
        .catch(() => caches.match('/').then((r) => r || Response.error())),
    )
    return
  }

  // El resto (JS, CSS, iconos): primero la caché. Vite les pone un hash en el
  // nombre, así que un fichero con un nombre dado no cambia nunca de
  // contenido y guardarlo para siempre es correcto.
  evento.respondWith(
    caches.match(peticion).then((guardada) => {
      if (guardada) return guardada
      return fetch(peticion).then((respuesta) => {
        // Solo lo que salió bien: guardar un 404 o un error de red lo
        // convertiría en permanente.
        if (respuesta.ok && respuesta.type === 'basic') {
          const copia = respuesta.clone()
          caches.open(VERSION).then((cache) => cache.put(peticion, copia))
        }
        return respuesta
      })
    }),
  )
})
