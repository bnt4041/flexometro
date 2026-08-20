import { useSyncExternalStore } from 'react'

/** Si la barra lateral del menú principal está recogida — compartido entre
 *  `AppShell` (que la pinta) y `ModalPantalla` (que necesita poder recogerla
 *  también desde dentro de una ficha, porque su propio botón vive en la
 *  topbar de `AppShell` y una ficha a pantalla completa la tapa entera). Vive
 *  fuera de React a propósito: son dos árboles de componentes distintos —la
 *  ficha se porta a `document.body`— y no hay un ancestro común del que
 *  colgar el estado. */
const CLAVE = 'obrai:sidebar-colapsada'
const escuchas = new Set<() => void>()
let colapsada = localStorage.getItem(CLAVE) === '1'

function aplicar(valor: boolean) {
  colapsada = valor
  localStorage.setItem(CLAVE, valor ? '1' : '0')
  // Puente hacia el CSS: `.modal-pantalla-backdrop` (portada a `document.body`,
  // fuera de `.shell`) lee esta variable para saber cuánto hueco ceder a la
  // izquierda — sin ella se quedaba reservando el ancho de la barra aunque ya
  // no hubiera barra que mostrar.
  document.documentElement.style.setProperty('--sidebar-w-actual', valor ? '0px' : 'var(--sidebar-w)')
  for (const escucha of escuchas) escucha()
}

// Deja la variable CSS coherente con lo persistido desde el primer render,
// no solo a partir del primer toggle.
aplicar(colapsada)

export function useSidebarColapsada(): [boolean, () => void] {
  const valor = useSyncExternalStore(
    (escucha) => {
      escuchas.add(escucha)
      return () => escuchas.delete(escucha)
    },
    () => colapsada,
  )
  return [valor, () => aplicar(!colapsada)]
}
