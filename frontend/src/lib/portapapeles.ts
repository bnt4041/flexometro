/** Portapapeles de Ctrl+C/Ctrl+V para copiar/mover partidas, líneas de
 *  medición y componentes de descompuesto (Fase 1b). En `localStorage`, no en
 *  memoria: así sobrevive a cambiar de pestaña o de presupuesto, que es
 *  justo lo que hace falta para pegar de un presupuesto a otro (Fase 1c). */

export type TipoPortapapeles =
  | 'capitulos'
  | 'partidas'
  | 'lineas_medicion'
  | 'componentes_descompuesto'
  // Fichas del banco de precios (Fase 50) — al pegarlas se MUEVEN de
  // capítulo, no se duplican: una ficha del banco es única por código y
  // tenerla dos veces sería un error, no una copia.
  | 'fichas_banco'

/** De qué ENTIDAD viene lo copiado (Fase 5): un capítulo copiado de un
 *  Pedido no debe poder pegarse en una Factura, aunque `tipo` coincida
 *  ('capitulos' en los dos). Cada destino comprueba `origenEntidad` además de
 *  `tipo` antes de ofrecer "Pegar" — copiar entre TIPOS de objeto distintos
 *  (Presupuesto → Pedido, Pedido → Factura...) sigue fuera de alcance, esto
 *  solo evita ofrecerlo, no lo permite. */
export type OrigenEntidadPortapapeles = 'presupuesto' | 'pedido' | 'factura' | 'factura_recibida'

export interface ContenidoPortapapeles {
  tipo: TipoPortapapeles
  /** `'presupuesto'` por defecto: es lo único que copiaban `RejillaPresupuesto`
   *  (vía `PresupuestoDetalle`/`RejillaObra`), `DescompuestoPartida` y
   *  `MedicionesPartida` antes de la Fase 5, y ninguno de esos sitios pasa
   *  este campo explícitamente — ver `copiarAlPortapapeles`. */
  origenEntidad: OrigenEntidadPortapapeles
  ids: string[]
  /** Solo para mostrar en el mensaje de confirmación ("3 partidas de «Reforma cocina»"). */
  origenEtiqueta: string
  copiadoEn: number
}

const CLAVE = 'obras.portapapeles'

export function copiarAlPortapapeles(
  contenido: Omit<ContenidoPortapapeles, 'copiadoEn' | 'origenEntidad'> & {
    origenEntidad?: OrigenEntidadPortapapeles
  },
): void {
  const valor: ContenidoPortapapeles = {
    origenEntidad: 'presupuesto',
    ...contenido,
    copiadoEn: Date.now(),
  }
  localStorage.setItem(CLAVE, JSON.stringify(valor))
}

export function leerPortapapeles(): ContenidoPortapapeles | null {
  const bruto = localStorage.getItem(CLAVE)
  if (!bruto) return null
  try {
    const valor = JSON.parse(bruto) as ContenidoPortapapeles
    if (!valor.tipo || !Array.isArray(valor.ids) || valor.ids.length === 0) return null
    // Contenido copiado antes de la Fase 5 (sin `origenEntidad` en disco):
    // es de un presupuesto, el único origen que existía entonces.
    return { ...valor, origenEntidad: valor.origenEntidad ?? 'presupuesto' }
  } catch {
    return null
  }
}
