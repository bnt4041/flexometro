import { useMemo, useState } from 'react'
import { Check, ChevronDown, ChevronRight, Minus } from 'lucide-react'

import type { ColumnaRejilla } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { api } from '../lib/api'
import type { NodoCapitulo } from '../lib/api'
import {
  ID_CARGANDO,
  alternarFila,
  aplanarArbol,
  estadoDeFila,
  filtrarArbol,
  partidasBajo,
} from '../lib/arbolSolicitud'
import type { Descompuestos, FilaArbol, SeleccionSolicitud } from '../lib/arbolSolicitud'

export type { SeleccionSolicitud }

/** El texto por el que se filtra cada columna. Tiene que coincidir con lo que
 *  pinta la celda, o filtrar por lo que se ve no encontraría nada. */
function valorDeColumna(fila: FilaArbol, columnaId: string): string {
  if (columnaId === 'resumen') return fila.resumen
  if (columnaId === 'unidad') return fila.unidad
  if (columnaId === 'medicion') return fila.medicion
  return ''
}

/** El árbol del presupuesto —capítulos, partidas y descompuestos— desde el
 *  que se decide qué entra en una solicitud de precios.
 *
 *  Se monta sobre `RejillaEditable`, que es UI pura y no toca la red: aquí no
 *  se edita el presupuesto, solo se marca qué se le pide al proveedor, así
 *  que ninguna columna es editable. El descompuesto de una partida se pide al
 *  desplegarla, para no traer de golpe el de todas.
 *
 *  La lógica de aplanado y selección vive aparte, en `lib/arbolSolicitud.ts`,
 *  donde se puede comprobar sin montar React. */
export function ArbolSolicitud({
  capitulos,
  seleccion,
  onCambiarSeleccion,
}: {
  capitulos: NodoCapitulo[]
  seleccion: SeleccionSolicitud
  onCambiarSeleccion: (nueva: SeleccionSolicitud) => void
}) {
  const [replegados, setReplegados] = useState<Set<string>>(new Set())
  const [expandidas, setExpandidas] = useState<Set<string>>(new Set())
  const [descompuestos, setDescompuestos] = useState<Descompuestos>({})
  const [filtros, setFiltros] = useState<Record<string, string>>({})

  const filas = useMemo(
    () => aplanarArbol(capitulos, descompuestos, expandidas),
    [capitulos, descompuestos, expandidas],
  )
  const porId = useMemo(() => new Map(filas.map((f) => [f.id, f])), [filas])
  const conHijos = useMemo(
    () => new Set(filas.map((f) => f.padreId).filter((id): id is string => id != null)),
    [filas],
  )

  function ocultaPorAncestro(fila: FilaArbol): boolean {
    let padre = fila.padreId
    while (padre) {
      if (replegados.has(padre)) return true
      padre = porId.get(padre)?.padreId ?? null
    }
    return false
  }

  // Con filtro manda el filtro y se ignora el plegado a mano: si no, un
  // acierto podría quedar escondido dentro de un capítulo replegado sin que
  // nada lo explique.
  const coincidentes = useMemo(
    () => filtrarArbol(filas, filtros, (fila, columnaId) => valorDeColumna(fila, columnaId)),
    [filas, filtros],
  )
  const visibles =
    coincidentes !== null
      ? filas.filter((f) => coincidentes.has(f.id))
      : filas.filter((f) => !ocultaPorAncestro(f))

  function alternarReplegado(id: string) {
    setReplegados((previos) => {
      const nuevos = new Set(previos)
      if (nuevos.has(id)) nuevos.delete(id)
      else nuevos.add(id)
      return nuevos
    })
  }

  async function alternarDescompuesto(fila: FilaArbol) {
    const partidaId = fila.partidaId
    if (!partidaId) return

    const yaEstaba = expandidas.has(fila.id)
    setExpandidas((previas) => {
      const nuevas = new Set(previas)
      if (yaEstaba) nuevas.delete(fila.id)
      else nuevas.add(fila.id)
      return nuevas
    })
    if (yaEstaba || descompuestos[partidaId]) return

    setDescompuestos((previos) => ({ ...previos, [partidaId]: 'cargando' }))
    try {
      const datos = await api.partidas.descomposicion(partidaId)
      setDescompuestos((previos) => ({ ...previos, [partidaId]: datos.lineas }))
    } catch {
      // Se quita el "cargando" para que se pueda reintentar plegando y
      // volviendo a desplegar, en vez de quedarse colgado para siempre.
      setDescompuestos((previos) => {
        const copia = { ...previos }
        delete copia[partidaId]
        return copia
      })
    }
  }

  const columnas: ColumnaRejilla<FilaArbol>[] = [
    {
      id: 'pedido',
      etiqueta: '',
      ancho: '44px',
      valor: () => '',
      filtrable: false,
      // La casilla va en `prefijo` porque el valor de una celda de
      // `RejillaEditable` es siempre texto: no hay render propio.
      prefijo: (f) => {
        if (f.id.startsWith(ID_CARGANDO)) return null
        const estado = estadoDeFila(filas, f, seleccion)
        const vacio = f.tipo === 'capitulo' && partidasBajo(filas, f).length === 0
        if (vacio) return null
        return (
          <button
            className="arbol-solicitud__marca"
            aria-label={estado === 'si' ? `Quitar ${f.resumen}` : `Pedir ${f.resumen}`}
            aria-pressed={estado === 'si'}
            data-estado={estado}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              onCambiarSeleccion(alternarFila(filas, f, seleccion))
            }}
          >
            {estado === 'si' && <Check size={13} aria-hidden="true" />}
            {estado === 'parcial' && <Minus size={13} aria-hidden="true" />}
          </button>
        )
      },
    },
    {
      id: 'resumen',
      etiqueta: 'Descripción',
      ancho: '400px',
      valor: (f) => f.resumen,
      sangrada: true,
      prefijo: (f) => {
        if (f.tipo === 'capitulo' && conHijos.has(f.id)) {
          return (
            <button
              className="rejilla__plegar"
              aria-label={replegados.has(f.id) ? `Desplegar ${f.resumen}` : `Plegar ${f.resumen}`}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation()
                alternarReplegado(f.id)
              }}
            >
              {replegados.has(f.id) ? (
                <ChevronRight size={14} aria-hidden="true" />
              ) : (
                <ChevronDown size={14} aria-hidden="true" />
              )}
            </button>
          )
        }
        if (f.tipo === 'partida') {
          return (
            <button
              className="rejilla__plegar"
              aria-label={
                expandidas.has(f.id)
                  ? 'Ocultar el descompuesto'
                  : `Ver el descompuesto de ${f.resumen}`
              }
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation()
                void alternarDescompuesto(f)
              }}
            >
              {expandidas.has(f.id) ? (
                <ChevronDown size={14} aria-hidden="true" />
              ) : (
                <ChevronRight size={14} aria-hidden="true" />
              )}
            </button>
          )
        }
        return null
      },
    },
    { id: 'unidad', etiqueta: 'Ud', ancho: '70px', valor: (f) => f.unidad },
    {
      id: 'medicion',
      etiqueta: 'Medición',
      ancho: '120px',
      tipo: 'numero',
      valor: (f) => f.medicion,
    },
  ]

  return (
    <RejillaEditable
      filas={visibles}
      columnas={columnas}
      idDe={(f) => f.id}
      nivelDe={(f) => f.nivel}
      claseDe={(f) => (f.tipo === 'componente' ? 'arbol-solicitud__componente' : undefined)}
      // Ninguna columna declara `editable`, así que esto no llega a llamarse:
      // aquí no se edita el presupuesto, solo se marca qué se pide.
      onEditar={() => {}}
      filtros={filtros}
      onFiltrar={(columnaId, valor) => setFiltros((f) => ({ ...f, [columnaId]: valor }))}
      vacia="Este presupuesto no tiene partidas todavía."
    />
  )
}
