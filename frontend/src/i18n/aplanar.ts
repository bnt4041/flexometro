/** Convierte el bundle anidado (`{ comun: { guardar: 'Guardar' } }`) en pares
 *  clave punteada → texto (`'comun.guardar'` → `'Guardar'`) — lo que necesita
 *  tanto el editor de Ajustes > Traducción como `aplicarOverridesTraduccion`
 *  para saber qué claves existen. */
export function aplanar(objeto: unknown, prefijo = ''): Record<string, string> {
  const resultado: Record<string, string> = {}
  if (typeof objeto !== 'object' || objeto === null) return resultado
  for (const [clave, valor] of Object.entries(objeto)) {
    const claveCompleta = prefijo ? `${prefijo}.${clave}` : clave
    if (typeof valor === 'string') {
      resultado[claveCompleta] = valor
    } else if (typeof valor === 'object' && valor !== null) {
      Object.assign(resultado, aplanar(valor, claveCompleta))
    }
  }
  return resultado
}
