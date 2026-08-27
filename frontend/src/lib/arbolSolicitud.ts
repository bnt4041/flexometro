import type { ComponentePedido, LineaDescomposicion, NodoCapitulo } from './api'

/** Qué se le pide al proveedor: partidas enteras y/o componentes sueltos del
 *  descompuesto de una partida. */
export interface SeleccionSolicitud {
  partidaIds: Set<string>
  componentes: ComponentePedido[]
}

export interface FilaArbol {
  id: string
  tipo: 'capitulo' | 'partida' | 'componente'
  nivel: number
  padreId: string | null
  resumen: string
  unidad: string
  medicion: string
  /** Solo en partidas y componentes. */
  partidaId?: string
  /** Solo en componentes; nulo si el concepto ya no está en el banco. */
  conceptoId?: string | null
}

export const ID_CARGANDO = '__cargando__'

/** Descompuestos ya pedidos, por id de partida. `'cargando'` mientras vuelve. */
export type Descompuestos = Record<string, LineaDescomposicion[] | 'cargando'>

/** Redondea a 3 decimales sin arrastrar el error binario de los flotantes,
 *  que en una medición se ve enseguida (0.1 * 3 = 0.30000000000000004). */
function medicionDeComponente(
  rendimiento: string,
  factor: string,
  medicionPartida: string,
): string {
  const valor = Number(rendimiento) * Number(factor) * Number(medicionPartida)
  return (Math.round(valor * 1000) / 1000).toFixed(3)
}

/** Aplana el árbol del presupuesto a filas, intercalando el descompuesto de
 *  las partidas que se hayan desplegado. */
export function aplanarArbol(
  capitulos: NodoCapitulo[],
  descompuestos: Descompuestos,
  expandidas: Set<string>,
): FilaArbol[] {
  const filas: FilaArbol[] = []

  function recorrer(nodos: NodoCapitulo[], nivel: number, padreId: string | null) {
    for (const nodo of nodos) {
      const idCap = `cap:${nodo.id}`
      filas.push({
        id: idCap,
        tipo: 'capitulo',
        nivel,
        padreId,
        resumen: nodo.resumen,
        unidad: '',
        medicion: '',
      })

      for (const partida of nodo.partidas) {
        const idPar = `par:${partida.id}`
        filas.push({
          id: idPar,
          tipo: 'partida',
          nivel: nivel + 1,
          padreId: idCap,
          resumen: partida.resumen,
          unidad: partida.unidad,
          medicion: partida.medicion,
          partidaId: partida.id,
        })

        if (!expandidas.has(idPar)) continue
        const desc = descompuestos[partida.id]
        if (desc === 'cargando') {
          filas.push({
            id: `${ID_CARGANDO}${partida.id}`,
            tipo: 'componente',
            nivel: nivel + 2,
            padreId: idPar,
            resumen: 'Cargando descompuesto…',
            unidad: '',
            medicion: '',
          })
        } else if (desc) {
          for (const linea of desc) {
            filas.push({
              id: `comp:${partida.id}:${linea.hijo_id ?? linea.id}`,
              tipo: 'componente',
              nivel: nivel + 2,
              padreId: idPar,
              resumen: linea.resumen,
              unidad: linea.unidad,
              // Lo que de verdad hay que comprar: el rendimiento es por
              // unidad de partida, así que se multiplica por su medición.
              medicion: medicionDeComponente(
                linea.rendimiento,
                linea.factor,
                partida.medicion,
              ),
              partidaId: partida.id,
              conceptoId: linea.hijo_id,
            })
          }
        }
      }

      // Los sub-capítulos van DESPUÉS de las partidas propias, igual que en
      // la rejilla del presupuesto.
      recorrer(nodo.hijos, nivel + 1, idCap)
    }
  }

  recorrer(capitulos, 0, null)
  return filas
}

/** Todas las partidas que cuelgan de una fila, bajando por los
 *  sub-capítulos. Una partida se devuelve a sí misma. */
export function partidasBajo(filas: FilaArbol[], fila: FilaArbol): string[] {
  if (fila.tipo === 'partida') return fila.partidaId ? [fila.partidaId] : []
  if (fila.tipo === 'componente') return []

  const resultado: string[] = []
  const pendientes = [fila.id]
  while (pendientes.length > 0) {
    const id = pendientes.pop()!
    for (const f of filas) {
      if (f.padreId !== id) continue
      if (f.tipo === 'partida' && f.partidaId) resultado.push(f.partidaId)
      else if (f.tipo === 'capitulo') pendientes.push(f.id)
    }
  }
  return resultado
}

export type EstadoMarca = 'si' | 'no' | 'parcial'

/** `parcial` solo lo tienen los capítulos: de sus partidas se pide alguna,
 *  pero no todas. */
export function estadoDeFila(
  filas: FilaArbol[],
  fila: FilaArbol,
  seleccion: SeleccionSolicitud,
): EstadoMarca {
  if (fila.tipo === 'componente') {
    const dentro = seleccion.componentes.some(
      (c) => c.partida_id === fila.partidaId && c.concepto_id === fila.conceptoId,
    )
    return dentro ? 'si' : 'no'
  }
  if (fila.tipo === 'partida') {
    return fila.partidaId && seleccion.partidaIds.has(fila.partidaId) ? 'si' : 'no'
  }

  const hijas = partidasBajo(filas, fila)
  if (hijas.length === 0) return 'no'
  const dentro = hijas.filter((id) => seleccion.partidaIds.has(id)).length
  if (dentro === 0) return 'no'
  return dentro === hijas.length ? 'si' : 'parcial'
}

/** Marca o desmarca una fila y devuelve la selección resultante. Un capítulo
 *  arrastra a todas sus partidas; un capítulo a medias se completa. */
export function alternarFila(
  filas: FilaArbol[],
  fila: FilaArbol,
  seleccion: SeleccionSolicitud,
): SeleccionSolicitud {
  if (fila.id.startsWith(ID_CARGANDO)) return seleccion

  if (fila.tipo === 'componente') {
    // Sin `conceptoId` la línea no apunta a ningún concepto del banco (se
    // borró): no hay nada estable a lo que referirse, así que no se pide.
    if (!fila.partidaId || !fila.conceptoId) return seleccion
    const dentro = seleccion.componentes.some(
      (c) => c.partida_id === fila.partidaId && c.concepto_id === fila.conceptoId,
    )
    return {
      ...seleccion,
      componentes: dentro
        ? seleccion.componentes.filter(
            (c) => !(c.partida_id === fila.partidaId && c.concepto_id === fila.conceptoId),
          )
        : [
            ...seleccion.componentes,
            { partida_id: fila.partidaId, concepto_id: fila.conceptoId },
          ],
    }
  }

  const objetivo = partidasBajo(filas, fila)
  if (objetivo.length === 0) return seleccion

  const meter = estadoDeFila(filas, fila, seleccion) !== 'si'
  const partidaIds = new Set(seleccion.partidaIds)
  for (const id of objetivo) {
    if (meter) partidaIds.add(id)
    else partidaIds.delete(id)
  }
  return { ...seleccion, partidaIds }
}


/** Filas que pasan el filtro, con su contexto: los ancestros de lo que
 *  coincide se conservan aunque no coincidan (si no, un acierto quedaría
 *  colgando sin capítulo), y de un capítulo que coincide se conserva todo lo
 *  que cuelga de él. Mismo criterio que el filtro de la rejilla del
 *  presupuesto. */
export function filtrarArbol(
  filas: FilaArbol[],
  filtros: Record<string, string>,
  valorDe: (fila: FilaArbol, columnaId: string) => string,
): Set<string> | null {
  const activos = Object.entries(filtros)
    .map(([id, v]) => [id, v.trim().toLowerCase()] as const)
    .filter(([, v]) => v !== '')
  if (activos.length === 0) return null

  const porId = new Map(filas.map((f) => [f.id, f]))
  const hijosDe = new Map<string, FilaArbol[]>()
  for (const f of filas) {
    if (!f.padreId) continue
    const lista = hijosDe.get(f.padreId)
    if (lista) lista.push(f)
    else hijosDe.set(f.padreId, [f])
  }

  const ids = new Set<string>()
  const marcarDescendientes = (id: string) => {
    for (const hijo of hijosDe.get(id) ?? []) {
      if (ids.has(hijo.id)) continue
      ids.add(hijo.id)
      marcarDescendientes(hijo.id)
    }
  }

  for (const f of filas) {
    const coincide = activos.every(([id, q]) => valorDe(f, id).toLowerCase().includes(q))
    if (!coincide) continue
    ids.add(f.id)
    let padre = f.padreId
    while (padre) {
      ids.add(padre)
      padre = porId.get(padre)?.padreId ?? null
    }
    if (f.tipo !== "componente") marcarDescendientes(f.id)
  }
  return ids
}
