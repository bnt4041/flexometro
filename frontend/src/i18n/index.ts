import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import { es } from './es'

void i18n.use(initReactI18next).init({
  lng: 'es',
  fallbackLng: 'es',
  resources: { es: { translation: es } },
  interpolation: { escapeValue: false },
  returnNull: false,
})

/** Funde los overrides de la cuenta (Fase 19) sobre el bundle base — se
 *  llama tras cada login/recarga de sesión, nunca al revés: el bundle base
 *  de este fichero nunca se toca en tiempo de ejecución. */
export function aplicarOverridesTraduccion(overrides: Record<string, string>): void {
  const anidado: Record<string, unknown> = {}
  for (const [clave, texto] of Object.entries(overrides)) {
    const partes = clave.split('.')
    let nodo = anidado
    for (const parte of partes.slice(0, -1)) {
      nodo = (nodo[parte] as Record<string, unknown>) ??= {}
    }
    nodo[partes[partes.length - 1]] = texto
  }
  i18n.addResourceBundle('es', 'translation', anidado, true, true)
}

export default i18n
