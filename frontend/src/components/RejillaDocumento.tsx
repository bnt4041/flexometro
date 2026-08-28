/** Rejilla de capítulos/partidas para Pedido, Factura y FacturaRecibida
 *  (Fase 3 — ver `/root/.claude/plans/shimmering-frolicking-patterson.md`).
 *
 *  Hermana simplificada de `RejillaObra`/`RejillaPresupuesto`: parte del mismo
 *  motor `RejillaEditable`, pero los capítulos de estas tres entidades son
 *  **planos** (sin `parent_id`/subcapítulos — así los devuelve el backend), así
 *  que no hace falta nada de indentado/anidado ni de arrastrar entre objetos
 *  (eso es la Fase 5, fuera de alcance aquí). Tampoco hay banco de precios,
 *  versiones ni "Preguntar a la IA" — por eso no se reutiliza `RejillaObra` tal
 *  cual, que lleva toda esa lógica de más.
 *
 *  Parametrizada por props inyectadas (mismo criterio que `DocumentoIAModal`):
 *  quien la monta decide contra qué API real escribe (`api.pedidosPartidas`,
 *  `api.facturasPartidas`, `api.facturasRecibidasPartidas`…), esta rejilla solo
 *  sabe pintar y encolar ediciones. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Clipboard, Copy, FolderPlus, Plus, Trash2 } from 'lucide-react'

import { PegarModal } from './PegarModal'
import type { ColumnaRejilla, ItemMenuContextual } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'
import type { AlcancePegado, ResultadoPegado } from '../lib/api'
import type { OrigenEntidadPortapapeles } from '../lib/portapapeles'
import { copiarAlPortapapeles, leerPortapapeles } from '../lib/portapapeles'
import { useDiccionario } from '../lib/useDiccionario'
import { useToast } from '../toast'

/** Forma mínima de una partida de Pedido/Factura/FacturaRecibida que necesita
 *  esta rejilla. `PedidoPartidaDetalle`/`FacturaPartidaDetalle` (con venta) y
 *  `FacturaRecibidaPartidaDetalle` (sin venta) de `lib/api.ts` cumplen esto:
 *  `precio_venta`/`importe_venta` son opcionales aquí precisamente porque la
 *  factura recibida no los tiene. */
export interface PartidaDocumento {
  id: string
  capitulo_id: string
  codigo: string
  resumen: string
  unidad: string
  precio: string
  medicion: string
  importe: string
  orden: number
  tiene_desglose: boolean
  precio_venta?: string
  importe_venta?: string
}

/** Capítulo con sus partidas ya anidadas — `PedidoCapituloConPartidas`,
 *  `FacturaCapituloConPartidas` o `FacturaRecibidaCapituloConPartidas`. */
export interface CapituloDocumento<P extends PartidaDocumento> {
  id: string
  codigo: string
  resumen: string
  orden: number
  partidas: P[]
}

interface FilaDocumento<P extends PartidaDocumento> {
  id: string
  tipo: 'capitulo' | 'partida'
  capituloId: string | null
  codigo: string
  resumen: string
  unidad: string
  medicion: string
  precio: string
  importe: string
  precioVenta: string
  importeVenta: string
  tieneDesglose: boolean
  orden: number
  partida?: P
}

type Campo = 'codigo' | 'resumen' | 'unidad' | 'medicion' | 'precio' | 'precio_venta'

const RETARDO_GUARDADO = 700

function aplanar<P extends PartidaDocumento>(capitulos: CapituloDocumento<P>[]): FilaDocumento<P>[] {
  const filas: FilaDocumento<P>[] = []
  for (const capitulo of capitulos) {
    const importeCap = capitulo.partidas.reduce((s, p) => s + Number(p.importe), 0)
    const importeVentaCap = capitulo.partidas.reduce((s, p) => s + Number(p.importe_venta ?? '0'), 0)
    filas.push({
      id: capitulo.id,
      tipo: 'capitulo',
      capituloId: null,
      codigo: capitulo.codigo,
      resumen: capitulo.resumen,
      unidad: '',
      medicion: '',
      precio: '',
      importe: String(importeCap),
      precioVenta: '',
      importeVenta: String(importeVentaCap),
      tieneDesglose: false,
      orden: capitulo.orden,
    })
    for (const partida of capitulo.partidas) {
      filas.push({
        id: partida.id,
        tipo: 'partida',
        capituloId: capitulo.id,
        codigo: partida.codigo,
        resumen: partida.resumen,
        unidad: partida.unidad,
        medicion: partida.medicion,
        precio: partida.precio,
        importe: partida.importe,
        precioVenta: partida.precio_venta ?? '',
        importeVenta: partida.importe_venta ?? '',
        tieneDesglose: partida.tiene_desglose,
        orden: partida.orden,
        partida,
      })
    }
  }
  return filas
}

export interface RejillaDocumentoProps<P extends PartidaDocumento> {
  capitulos: CapituloDocumento<P>[]
  /** `false` para Pedido `tipo=proveedor` y para FacturaRecibida: sin
   *  columnas de venta y sin panel de descompuesto (eso lo decide quien monte
   *  esta rejilla, aquí solo condiciona las columnas). */
  permiteDescompuesto: boolean
  onCrearCapitulo: () => Promise<unknown>
  onActualizarCapitulo: (id: string, cambios: Partial<{ codigo: string; resumen: string }>) => Promise<unknown>
  onEliminarCapitulo: (id: string) => Promise<unknown>
  onCrearPartida: (capituloId: string) => Promise<unknown>
  onActualizarPartida: (
    id: string,
    cambios: Partial<{
      codigo: string
      resumen: string
      unidad: string
      precio: string
      medicion: string
      precio_venta: string
    }>,
  ) => Promise<unknown>
  onEliminarPartida: (id: string) => Promise<unknown>
  /** Para mostrar mediciones/descompuesto de la partida elegida en un panel
   *  lateral — mismo patrón que `seleccion` en `PresupuestoDetalle.tsx`. */
  onSeleccionarPartida: (partidaId: string | null) => void
  seleccionadaId?: string | null
  /** Recarga tras cualquier escritura — la llama esta rejilla, no hace falta
   *  que los callbacks de arriba también recarguen. */
  onCambio: () => void
  /** Qué entidad es este documento (Fase 5): Ctrl+C/Ctrl+V y el menú
   *  contextual "Copiar"/"Pegar" solo ofrecen pegar cuando lo copiado viene
   *  de la MISMA entidad — un capítulo de un Pedido no se puede pegar en una
   *  Factura, aunque los dos tengan capítulos. */
  origenEntidad: OrigenEntidadPortapapeles
  /** Etiqueta del documento propio, para el mensaje "3 partidas de «PED-24»"
   *  al pegar en otro. */
  etiquetaDocumento: string
  /** `PedidoCapitulo`/`FacturaCapitulo`/`FacturaRecibidaCapitulo` son de un
   *  solo nivel (sin `parent_id`): pegar capítulos siempre los añade al
   *  documento entero, nunca "dentro" de otro capítulo. */
  onPegarCapitulos: (datos: { capitulo_ids: string[]; alcance: AlcancePegado }) => Promise<ResultadoPegado>
  onPegarPartidas: (
    capituloId: string,
    datos: { partida_ids: string[]; alcance: AlcancePegado },
  ) => Promise<ResultadoPegado>
}

export function RejillaDocumento<P extends PartidaDocumento>({
  capitulos,
  permiteDescompuesto,
  onCrearCapitulo,
  onActualizarCapitulo,
  onEliminarCapitulo,
  onCrearPartida,
  onActualizarPartida,
  onEliminarPartida,
  onSeleccionarPartida,
  seleccionadaId,
  onCambio,
  origenEntidad,
  etiquetaDocumento,
  onPegarCapitulos,
  onPegarPartidas,
}: RejillaDocumentoProps<P>) {
  const { notificar } = useToast()
  const unidadesMedida = useDiccionario('unidad_medida')
  const filasDelServidor = useMemo(() => aplanar(capitulos), [capitulos])
  const [filas, setFilas] = useState<FilaDocumento<P>[]>(filasDelServidor)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const filaActiva = useRef<FilaDocumento<P> | null>(null)
  const [pegando, setPegando] = useState<{
    tipo: 'capitulos' | 'partidas'
    ids: string[]
    origenEtiqueta: string
    /** Capítulo destino de unas partidas (siempre relleno); `null` para
     *  capítulos, que se pegan al documento entero, no "dentro" de nada. */
    destino: string | null
  } | null>(null)

  // Cola de cambios pendientes con retardo, mismo patrón que `RejillaObra`:
  // se teclea seguido y se manda una sola vez por campo.
  const cambios = useRef<Map<string, { fila: FilaDocumento<P>; campo: Campo; valor: string }>>(new Map())
  const temporizador = useRef<number | undefined>(undefined)

  // Si no hay nada a medio teclear, una recarga del padre reemplaza el
  // estado local sin más — igual que `RejillaObra`.
  useEffect(() => {
    if (cambios.current.size === 0) setFilas(filasDelServidor)
  }, [filasDelServidor])

  const volcar = useCallback(async () => {
    const tanda = [...cambios.current.values()]
    if (tanda.length === 0) return
    cambios.current.clear()
    setGuardando(true)
    try {
      for (const { fila, campo, valor } of tanda) {
        if (fila.tipo === 'capitulo') {
          if (campo === 'codigo' || campo === 'resumen') {
            await onActualizarCapitulo(fila.id, { [campo]: valor })
          }
          continue
        }
        await onActualizarPartida(fila.id, { [campo]: valor })
      }
      setError(null)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }, [onActualizarCapitulo, onActualizarPartida, onCambio])

  useEffect(() => {
    return () => {
      void volcar()
    }
  }, [volcar])

  function encolar(fila: FilaDocumento<P>, campo: Campo, valor: string) {
    cambios.current.set(`${fila.tipo}:${fila.id}:${campo}`, { fila, campo, valor })
    window.clearTimeout(temporizador.current)
    temporizador.current = window.setTimeout(() => void volcar(), RETARDO_GUARDADO)
  }

  function editarLocal(id: string, cambio: Partial<FilaDocumento<P>>) {
    setFilas((actuales) => actuales.map((f) => (f.id === id ? { ...f, ...cambio } : f)))
  }

  function alEditar(fila: FilaDocumento<P>, columnaId: string, valor: string) {
    switch (columnaId) {
      case 'codigo':
        editarLocal(fila.id, { codigo: valor })
        return encolar(fila, 'codigo', valor)
      case 'resumen':
        editarLocal(fila.id, { resumen: valor })
        return encolar(fila, 'resumen', valor)
      case 'unidad':
        editarLocal(fila.id, { unidad: valor })
        return encolar(fila, 'unidad', valor)
      case 'medicion':
        editarLocal(fila.id, { medicion: valor })
        return encolar(fila, 'medicion', valor)
      case 'precio':
        editarLocal(fila.id, { precio: valor })
        return encolar(fila, 'precio', valor)
      case 'precio_venta':
        editarLocal(fila.id, { precioVenta: valor })
        return encolar(fila, 'precio_venta', valor)
    }
  }

  function capituloDe(fila: FilaDocumento<P> | null): string | null {
    if (!fila) return null
    return fila.tipo === 'capitulo' ? fila.id : fila.capituloId
  }

  /** El portapapeles no distingue de qué Pedido/Factura/FacturaRecibida en
   *  concreto viene una fila, solo de qué ENTIDAD (`origenEntidad`): un
   *  capítulo copiado de otro pedido se puede pegar aquí, uno copiado de una
   *  factura no, aunque los dos se llamen "capitulos" en `tipo`. */
  function contenidoPegable() {
    const contenido = leerPortapapeles()
    if (!contenido) return null
    if (contenido.origenEntidad !== origenEntidad) return null
    if (contenido.tipo !== 'capitulos' && contenido.tipo !== 'partidas') return null
    return contenido
  }

  function copiar(ids: string[]) {
    const seleccionadas = ids
      .map((id) => filas.find((f) => f.id === id))
      .filter((f): f is FilaDocumento<P> => f != null)
    if (seleccionadas.length === 0) return
    // Igual que `RejillaPresupuesto.copiar`: una marca puede mezclar
    // capítulos y partidas, se copia solo el tipo de la primera.
    const tipo = seleccionadas[0].tipo
    const mismos = seleccionadas.filter((f) => f.tipo === tipo).map((f) => f.id)
    copiarAlPortapapeles({
      tipo: tipo === 'capitulo' ? 'capitulos' : 'partidas',
      origenEntidad,
      ids: mismos,
      origenEtiqueta: etiquetaDocumento,
    })
    notificar(
      tipo === 'capitulo'
        ? mismos.length === 1
          ? 'Capítulo copiado'
          : `${mismos.length} capítulos copiados`
        : mismos.length === 1
          ? 'Partida copiada'
          : `${mismos.length} partidas copiadas`,
    )
  }

  /** Ctrl+V usa la fila con el cursor encima (`filaActiva`); el menú
   *  contextual manda la fila sobre la que se hizo clic derecho, que puede
   *  ser distinta. */
  function pegar(filaDestino?: FilaDocumento<P> | null) {
    const contenido = leerPortapapeles()
    if (!contenido) {
      notificar('No hay nada copiado')
      return
    }
    if (contenido.origenEntidad !== origenEntidad) {
      notificar('Lo copiado es de otro tipo de documento y no se puede pegar aquí')
      return
    }
    if (contenido.tipo === 'capitulos') {
      setPegando({ tipo: 'capitulos', ids: contenido.ids, origenEtiqueta: contenido.origenEtiqueta, destino: null })
      return
    }
    if (contenido.tipo === 'partidas') {
      const actual = filaDestino !== undefined ? filaDestino : filaActiva.current
      const destino = capituloDe(actual)
      if (!destino) {
        notificar('Selecciona antes un capítulo, o una partida dentro de uno, para pegar ahí')
        return
      }
      setPegando({ tipo: 'partidas', ids: contenido.ids, origenEtiqueta: contenido.origenEtiqueta, destino })
      return
    }
    notificar('Lo copiado no se puede pegar aquí')
  }

  async function confirmarPegado(alcance: AlcancePegado) {
    if (!pegando) return
    try {
      const resultado =
        pegando.tipo === 'partidas'
          ? await onPegarPartidas(pegando.destino!, { partida_ids: pegando.ids, alcance })
          : await onPegarCapitulos({ capitulo_ids: pegando.ids, alcance })
      setPegando(null)
      onCambio()
      if (resultado.pegadas === 0) {
        notificar('No se pegó nada')
        return
      }
      notificar(
        pegando.tipo === 'partidas'
          ? resultado.pegadas === 1
            ? '1 partida pegada'
            : `${resultado.pegadas} partidas pegadas`
          : resultado.pegadas === 1
            ? '1 capítulo pegado'
            : `${resultado.pegadas} capítulos pegados`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setPegando(null)
    }
  }

  async function nuevaPartida(actual: FilaDocumento<P> | null) {
    const capituloId = capituloDe(actual ?? filaActiva.current)
    if (!capituloId) {
      setError('Crea antes un capítulo: una partida siempre cuelga de uno.')
      return
    }
    try {
      await onCrearPartida(capituloId)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function nuevoCapitulo() {
    try {
      await onCrearCapitulo()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminarFila(fila: FilaDocumento<P>) {
    const que =
      fila.tipo === 'capitulo'
        ? `el capítulo «${fila.resumen}» y todas sus partidas`
        : `la partida «${fila.resumen}»`
    if (!window.confirm(`¿Eliminar ${que}?`)) return
    try {
      if (fila.tipo === 'capitulo') await onEliminarCapitulo(fila.id)
      else await onEliminarPartida(fila.id)
      if (seleccionadaId === fila.id) onSeleccionarPartida(null)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const totalCoste = capitulos.reduce(
    (s, c) => s + c.partidas.reduce((s2, p) => s2 + Number(p.importe), 0),
    0,
  )
  const totalVenta = capitulos.reduce(
    (s, c) => s + c.partidas.reduce((s2, p) => s2 + Number(p.importe_venta ?? '0'), 0),
    0,
  )

  const columnas: ColumnaRejilla<FilaDocumento<P>>[] = [
    {
      id: 'codigo',
      etiqueta: 'Código',
      ancho: '140px',
      sangrada: true,
      valor: (f) => f.codigo,
      editable: () => true,
    },
    {
      id: 'resumen',
      etiqueta: 'Resumen',
      ancho: '280px',
      valor: (f) => f.resumen,
      editable: () => true,
    },
    {
      id: 'unidad',
      etiqueta: 'Ud.',
      ancho: '90px',
      tipo: 'select',
      valor: (f) => f.unidad,
      editable: (f) => f.tipo === 'partida',
      opciones: () => unidadesMedida.map((u) => ({ valor: u.clave, etiqueta: u.etiqueta })),
    },
    {
      id: 'precio',
      etiqueta: 'Precio',
      ancho: '105px',
      tipo: 'numero',
      valor: (f) => (f.tipo === 'partida' ? formatoImporte(f.precio) : ''),
      editable: (f) => f.tipo === 'partida',
    },
    {
      id: 'medicion',
      etiqueta: 'Medición',
      ancho: '110px',
      tipo: 'numero',
      valor: (f) => (f.tipo === 'partida' ? formatoImporte(f.medicion, 3) : ''),
      // Con mediciones (parciales), la cantidad es su suma: teclearla a mano
      // se perdería en el siguiente recálculo del backend.
      editable: (f) => f.tipo === 'partida' && !f.tieneDesglose,
    },
    {
      id: 'importe',
      etiqueta: 'Importe',
      ancho: '125px',
      tipo: 'numero',
      valor: (f) => formatoImporte(f.importe),
      total: `${formatoImporte(String(totalCoste))} €`,
    },
    ...(permiteDescompuesto
      ? ([
          {
            id: 'precio_venta',
            etiqueta: 'P. venta',
            ancho: '105px',
            tipo: 'numero',
            valor: (f: FilaDocumento<P>) => (f.tipo === 'partida' ? formatoImporte(f.precioVenta) : ''),
            editable: (f: FilaDocumento<P>) => f.tipo === 'partida',
          },
          {
            id: 'importe_venta',
            etiqueta: 'Importe venta',
            ancho: '125px',
            tipo: 'numero',
            valor: (f: FilaDocumento<P>) => formatoImporte(f.importeVenta),
            total: `${formatoImporte(String(totalVenta))} €`,
          },
        ] satisfies ColumnaRejilla<FilaDocumento<P>>[])
      : []),
  ]

  function menuContextualDe(f: FilaDocumento<P>): ItemMenuContextual[] {
    return [
      {
        id: 'copiar',
        etiqueta: f.tipo === 'capitulo' ? 'Copiar capítulo' : 'Copiar partida',
        icono: <Copy size={14} aria-hidden="true" />,
        onClick: () => copiar([f.id]),
      },
      {
        id: 'pegar',
        etiqueta: 'Pegar',
        icono: <Clipboard size={14} aria-hidden="true" />,
        onClick: () => pegar(f),
        disabled: !contenidoPegable(),
      },
    ]
  }

  const pegable = contenidoPegable()

  return (
    <>
      <div className="rejilla-barra">
        <span className="rejilla-barra__estado">
          {guardando ? 'Guardando…' : cambios.current.size > 0 ? 'Sin guardar…' : ''}
        </span>
        <button className="btn btn--sm" onClick={() => void nuevoCapitulo()}>
          <FolderPlus size={14} aria-hidden="true" />
          Capítulo
        </button>
        {pegable && (
          <Tooltip texto={`Pegar ${pegable.tipo === 'capitulos' ? 'capítulo(s)' : 'partida(s)'} de «${pegable.origenEtiqueta}»`}>
            <button className="btn btn--sm" onClick={() => pegar()}>
              <Clipboard size={14} aria-hidden="true" />
              Pegar
            </button>
          </Tooltip>
        )}
      </div>

      <ErrorNotice error={error} />

      <RejillaEditable
        filas={filas}
        columnas={columnas}
        idDe={(f) => f.id}
        nivelDe={(f) => (f.tipo === 'partida' ? 1 : 0)}
        claseDe={(f) => (f.tipo === 'capitulo' ? 'fila-capitulo' : undefined)}
        onEditar={(f, col, valor) => alEditar(f, col, valor)}
        onNuevaFila={(actual) => void nuevaPartida(actual)}
        onEliminarFila={(f) => void eliminarFila(f)}
        onSeleccionar={(f) => {
          filaActiva.current = f
          onSeleccionarPartida(f?.tipo === 'partida' ? f.id : null)
        }}
        seleccionadaId={seleccionadaId}
        onCopiar={copiar}
        onPegar={() => pegar()}
        menuContextual={menuContextualDe}
        vacia={
          <EmptyState title="Sin capítulos todavía">
            Crea un capítulo para empezar a añadir partidas.
          </EmptyState>
        }
        acciones={(f) => (
          <>
            {f.tipo === 'capitulo' && (
              <Tooltip texto="Añadir partida en este capítulo">
                <button className="btn btn--sm" onClick={() => void nuevaPartida(f)}>
                  <Plus size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            )}
            <Tooltip texto="Eliminar">
              <button className="btn btn--sm btn--danger btn--solo-icono" onClick={() => void eliminarFila(f)}>
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </Tooltip>
          </>
        )}
      />

      {pegando && (
        <PegarModal
          cantidad={pegando.ids.length}
          origenEtiqueta={pegando.origenEtiqueta}
          onElegir={(alcance) => void confirmarPegado(alcance)}
          onClose={() => setPegando(null)}
        />
      )}
    </>
  )
}
