import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowLeftRight, ExternalLink, Trash2 } from 'lucide-react'

import { BuscadorSustitutoModal } from './BuscadorSustitutoModal'
import type { ColumnaRejilla, ItemMenuContextual, OpcionCelda } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { ConceptoDetalle, Linea } from '../lib/api'

/** Fila en blanco al final para dar de alta buscando en el banco, igual que
 *  hace `DescompuestoPartida` con las partidas. */
const ID_BORRADOR = '__nuevo__'

interface FilaComponente {
  id: string
  hijoId: string | null
  codigo: string
  resumen: string
  unidad: string
  rendimiento: string
  precio: string
  importe: string
}

/** Descompuesto de una ficha del banco (Fase 50).
 *
 *  Hermano de `DescompuestoPartida`, no el mismo componente: aquel habla con
 *  `api.partidas.*` y distingue si el desglose es propio de la partida o
 *  heredado del banco, distinción que aquí no existe — en el banco el
 *  descompuesto SIEMPRE es de la ficha. */
export function DescompuestoConcepto({
  conceptoId,
  onCambio,
}: {
  conceptoId: string
  onCambio?: () => void
}) {
  const [detalle, setDetalle] = useState<ConceptoDetalle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sustituyendo, setSustituyendo] = useState<FilaComponente | null>(null)

  const cargar = useCallback(async () => {
    try {
      setDetalle(await api.conceptos.get(conceptoId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [conceptoId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function conError(accion: () => Promise<unknown>) {
    setError(null)
    try {
      await accion()
      await cargar()
      onCambio?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const filas: FilaComponente[] = useMemo(() => {
    const lineas: Linea[] = detalle?.lineas ?? []
    return [
      ...lineas.map((l) => ({
        id: l.id,
        hijoId: l.hijo_id,
        codigo: l.hijo_codigo,
        resumen: l.hijo_resumen,
        unidad: l.hijo_unidad,
        rendimiento: l.rendimiento,
        precio: l.hijo_precio,
        importe: l.importe,
      })),
      {
        id: ID_BORRADOR,
        hijoId: null,
        codigo: '',
        resumen: '',
        unidad: '',
        rendimiento: '',
        precio: '',
        importe: '',
      },
    ]
  }, [detalle])

  const columnas: ColumnaRejilla<FilaComponente>[] = [
    { id: 'codigo', etiqueta: 'Código', ancho: '130px', valor: (f) => f.codigo },
    {
      id: 'resumen',
      etiqueta: 'Componente',
      ancho: '260px',
      valor: (f) => f.resumen,
      // Solo la fila en blanco es editable: cambiar el resumen de una línea
      // ya guardada sería editar la FICHA hija, no esta línea — se hace
      // abriendo esa ficha, que para eso está el botón de la derecha.
      editable: (f) => f.id === ID_BORRADOR,
      tipo: 'autocompletado',
      buscar: async (q) => {
        if (q.trim().length < 2) return []
        const pagina = await api.conceptos.list({ q, activo: true, limit: 8 })
        return pagina.items
          .filter((c) => c.id !== conceptoId)
          .map<OpcionCelda>((c) => ({
            valor: c.id,
            etiqueta: `${c.codigo} · ${c.resumen}`,
            detalle: `${formatoImporte(c.precio)} €/${c.unidad}`,
          }))
      },
    },
    { id: 'unidad', etiqueta: 'Ud.', ancho: '80px', valor: (f) => f.unidad },
    {
      id: 'rendimiento',
      etiqueta: 'Rendimiento',
      ancho: '120px',
      tipo: 'numero',
      valor: (f) => (f.id === ID_BORRADOR ? '' : formatoImporte(f.rendimiento, 3)),
      editable: (f) => f.id !== ID_BORRADOR,
    },
    {
      id: 'precio',
      etiqueta: 'Precio',
      ancho: '110px',
      tipo: 'numero',
      valor: (f) => (f.id === ID_BORRADOR ? '' : formatoImporte(f.precio)),
      // Es el precio de la FICHA hija, no de esta línea: se edita aquí para
      // no obligar a abrir cada componente aparte, pero el cambio se aplica
      // a la ficha (y de ahí en cascada a todo lo que la use).
      editable: (f) => f.hijoId !== null,
    },
    {
      id: 'importe',
      etiqueta: 'Importe',
      ancho: '110px',
      tipo: 'numero',
      valor: (f) => (f.id === ID_BORRADOR ? '' : formatoImporte(f.importe)),
      total: detalle ? `${formatoImporte(detalle.coste_directo)} €` : undefined,
    },
  ]

  if (!detalle) return null

  return (
    <>
      <ErrorNotice error={error} />
      <RejillaEditable
        filas={filas}
        columnas={columnas}
        idDe={(f) => f.id}
        onEditar={(fila, columnaId, valor, opcion) => {
          if (fila.id === ID_BORRADOR) {
            // El alta solo ocurre al elegir una ficha del autocompletado:
            // `opcion.valor` es su id. Escribir texto libre no crea nada.
            if (columnaId !== 'resumen' || !opcion) return
            void conError(() =>
              api.conceptos.addLinea(conceptoId, { hijo_id: opcion.valor, rendimiento: '1' }),
            )
            return
          }
          if (columnaId === 'rendimiento') {
            void conError(() =>
              api.descomposicion.update(fila.id, { rendimiento: valor.replace(',', '.') }),
            )
            return
          }
          if (columnaId === 'precio' && fila.hijoId) {
            void conError(() =>
              api.conceptos.update(fila.hijoId!, { precio: valor.replace(',', '.') }),
            )
          }
        }}
        onEliminarFila={(f) => {
          if (f.id === ID_BORRADOR) return
          void conError(() => api.descomposicion.remove(f.id))
        }}
        menuContextual={(f): ItemMenuContextual[] | null =>
          f.id === ID_BORRADOR || f.hijoId === null
            ? null
            : [
                {
                  id: 'sustituir',
                  etiqueta: 'Cambiar por banco de precios…',
                  icono: <ArrowLeftRight size={14} aria-hidden="true" />,
                  onClick: () => setSustituyendo(f),
                },
              ]
        }
        vacia={
          <EmptyState title="Sin descompuesto">
            Escribe en la última fila para buscar una ficha del banco y añadirla como componente.
          </EmptyState>
        }
        acciones={(f) =>
          f.id === ID_BORRADOR ? null : (
            <>
              <Tooltip texto="Abrir la ficha de este componente">
                <button
                  className="btn btn--sm btn--solo-icono"
                  aria-label="Abrir ficha del componente"
                  // No es un `<a href>`: la celda de acciones de la rejilla
                  // captura el mousedown para mover el cursor de edición
                  // (`irA`), y eso llega a cancelar la navegación nativa del
                  // enlace a mitad del clic. Con `onClick` + `window.open`
                  // (mismo patrón que "Abrir en banco de precios" en la
                  // rejilla del presupuesto) no depende de ese clic nativo.
                  onClick={() => f.hijoId && window.open(`/banco-precios/${f.hijoId}`, '_blank')}
                  disabled={!f.hijoId}
                >
                  <ExternalLink size={14} aria-hidden="true" />
                </button>
              </Tooltip>
              <Tooltip texto="Quitar este componente">
                <button
                  className="btn btn--sm btn--danger btn--solo-icono"
                  aria-label="Quitar componente"
                  onClick={() => void conError(() => api.descomposicion.remove(f.id))}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            </>
          )
        }
      />

      {sustituyendo && (
        <BuscadorSustitutoModal
          resumenActual={sustituyendo.resumen}
          unidadActual={sustituyendo.unidad}
          modo="componente"
          onAplicar={async (candidato) => {
            if (!candidato.concepto_id) return
            // Mismo par de llamadas que ya usa el resto de esta rejilla
            // (quitar + añadir): no hay un endpoint de "sustituir" propio
            // para un componente, es siempre un Concepto de por medio.
            await api.descomposicion.remove(sustituyendo.id)
            await api.conceptos.addLinea(conceptoId, {
              hijo_id: candidato.concepto_id,
              rendimiento: sustituyendo.rendimiento,
            })
            await cargar()
            onCambio?.()
          }}
          onClose={() => setSustituyendo(null)}
        />
      )}
    </>
  )
}
