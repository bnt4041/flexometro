/** Portapapeles de Ctrl+C/Ctrl+V para copiar/mover partidas, líneas de
 *  medición y componentes de descompuesto (Fase 1b). En `localStorage`, no en
 *  memoria: así sobrevive a cambiar de pestaña o de presupuesto, que es
 *  justo lo que hace falta para pegar de un presupuesto a otro (Fase 1c). */

export type TipoPortapapeles = 'partidas' | 'lineas_medicion' | 'componentes_descompuesto'

export interface ContenidoPortapapeles {
  tipo: TipoPortapapeles
  ids: string[]
  /** Solo para mostrar en el mensaje de confirmación ("3 partidas de «Reforma cocina»"). */
  origenEtiqueta: string
  copiadoEn: number
}

const CLAVE = 'obras.portapapeles'

export function copiarAlPortapapeles(
  contenido: Omit<ContenidoPortapapeles, 'copiadoEn'>,
): void {
  const valor: ContenidoPortapapeles = { ...contenido, copiadoEn: Date.now() }
  localStorage.setItem(CLAVE, JSON.stringify(valor))
}

export function leerPortapapeles(): ContenidoPortapapeles | null {
  const bruto = localStorage.getItem(CLAVE)
  if (!bruto) return null
  try {
    const valor = JSON.parse(bruto) as ContenidoPortapapeles
    if (!valor.tipo || !Array.isArray(valor.ids) || valor.ids.length === 0) return null
    return valor
  } catch {
    return null
  }
}
