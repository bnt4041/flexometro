/** Descompuesto de una partida de Pedido (tipo=cliente) o Factura de venta
 *  (Fase 3 — ver `/root/.claude/plans/shimmering-frolicking-patterson.md`).
 *
 *  Hermano generalizado de `DescompuestoPartida.tsx` (que sigue intacto y
 *  sirve solo a `PresupuestoDetalle`): mismo motor de rejilla y la misma idea
 *  de alta en dos pasos (buscar/crear concepto → tipo de línea si es nuevo →
 *  rendimiento), pero sin "pegar", "cambiar por banco de precios" ni
 *  "solicitar precios…", que no están en el alcance de esta fase y son los
 *  que más complejidad añadían al original.
 *
 *  Parametrizado por props inyectadas (mismo criterio que `RejillaDocumento`):
 *  quien lo monta decide contra qué API real escribe. */

import { useCallback, useEffect, useState } from 'react'
import { Clipboard, Plus, Save, Trash2, Unlink, X } from 'lucide-react'

import { BotonAtajos } from './AtajosTeclado'
import { PegarModal } from './PegarModal'
import type { ColumnaRejilla, OpcionCelda } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Modal, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type {
  AlcancePegado,
  ConceptoDetalle,
  DescomposicionPartida,
  LineaDescomposicion,
  NaturalezaConcepto,
  ResultadoPegado,
} from '../lib/api'
import { ETIQUETA_NATURALEZA } from '../lib/api'
import type { OrigenEntidadPortapapeles } from '../lib/portapapeles'
import { copiarAlPortapapeles, leerPortapapeles } from '../lib/portapapeles'
import { useDiccionario } from '../lib/useDiccionario'
import { useToast } from '../toast'

const ID_BORRADOR = '__nuevo__'

type TipoLinea = 'material' | 'mano_obra' | 'maquinaria' | 'servicio' | 'unitario'

const OPCIONES_TIPO_LINEA: OpcionCelda[] = [
  { valor: 'material', etiqueta: 'Material' },
  { valor: 'mano_obra', etiqueta: 'Mano de obra' },
  { valor: 'maquinaria', etiqueta: 'Maquinaria' },
  { valor: 'servicio', etiqueta: 'Servicio' },
  { valor: 'unitario', etiqueta: 'Auxiliar (unitario) — poco uso' },
]

const OPCIONES_NATURALEZA_EXISTENTE: OpcionCelda[] = [
  { valor: 'sin_clasificar', etiqueta: 'Sin clasificar' },
  { valor: 'material', etiqueta: 'Material' },
  { valor: 'mano_obra', etiqueta: 'Mano de obra' },
  { valor: 'maquinaria', etiqueta: 'Maquinaria' },
  { valor: 'servicio', etiqueta: 'Servicio' },
]

export interface DescompuestoDocumentoProps {
  codigo: string
  resumen: string
  unidad: string
  precio: string
  costesIndirectos: string | null
  /** "En todo el pedido donde aparezca" / "...factura..." — el banco de
   *  precios no se toca en ningún caso, solo cambia el texto del botón. */
  etiquetaAlcanceAmplio: string
  cargar: () => Promise<DescomposicionPartida>
  anadirComponente: (datos: { hijo_id: string; rendimiento?: string; factor?: string }) => Promise<DescomposicionPartida>
  quitarComponente: (lineaId: string) => Promise<DescomposicionPartida>
  independizarDescomposicion: () => Promise<DescomposicionPartida>
  cambiarPrecioComponente: (datos: {
    hijo_id: string
    precio: string
    alcance: 'partida' | 'amplio'
  }) => Promise<{ partidas_afectadas: number; descomposicion: DescomposicionPartida }>
  cambiarRendimientoComponente: (datos: { hijo_id: string; rendimiento: string }) => Promise<DescomposicionPartida>
  cambiarResumenComponente: (datos: { hijo_id: string; resumen: string }) => Promise<DescomposicionPartida>
  cambiarNaturalezaComponente: (datos: {
    hijo_id: string
    naturaleza: NaturalezaConcepto
  }) => Promise<DescomposicionPartida>
  cambiarUnidadComponente: (datos: { hijo_id: string; unidad: string }) => Promise<DescomposicionPartida>
  onCambio: () => void
  /** Qué entidad es este documento (Fase 5): un componente copiado de otro
   *  Pedido/Factura solo se ofrece pegar si viene de la MISMA entidad. */
  origenEntidad: OrigenEntidadPortapapeles
  pegarComponentes: (datos: { linea_ids: string[]; alcance: AlcancePegado }) => Promise<ResultadoPegado>
}

export function DescompuestoDocumento({
  codigo,
  resumen,
  unidad,
  precio,
  costesIndirectos,
  etiquetaAlcanceAmplio,
  cargar: cargarDescomposicion,
  anadirComponente,
  quitarComponente,
  independizarDescomposicion,
  cambiarPrecioComponente,
  cambiarRendimientoComponente,
  cambiarResumenComponente,
  cambiarNaturalezaComponente,
  cambiarUnidadComponente,
  onCambio,
  origenEntidad,
  pegarComponentes,
}: DescompuestoDocumentoProps) {
  const { notificar } = useToast()
  const [datos, setDatos] = useState<DescomposicionPartida | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pendiente, setPendiente] = useState<{ linea: LineaDescomposicion; precio: string } | null>(null)
  const [conceptoNuevo, setConceptoNuevo] = useState<ConceptoDetalle | null>(null)
  const [borradorNuevo, setBorradorNuevo] = useState<{ resumen: string; tipoLinea?: TipoLinea } | null>(null)
  const [anadiendo, setAnadiendo] = useState(false)
  const [filtros, setFiltros] = useState<Record<string, string>>({})
  const [pegando, setPegando] = useState<{ ids: string[]; origenEtiqueta: string } | null>(null)
  const unidadesMedida = useDiccionario('unidad_medida')

  const cargar = useCallback(async () => {
    try {
      setDatos(await cargarDescomposicion())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [cargarDescomposicion])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function aplicar(alcance: 'partida' | 'amplio') {
    if (!pendiente?.linea.hijo_id) return
    try {
      const { partidas_afectadas, descomposicion } = await cambiarPrecioComponente({
        hijo_id: pendiente.linea.hijo_id,
        precio: pendiente.precio,
        alcance,
      })
      setPendiente(null)
      setDatos(descomposicion)
      onCambio()
      notificar(
        partidas_afectadas === 1
          ? 'Precio cambiado en 1 partida'
          : `Precio cambiado en ${partidas_afectadas} partidas`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setPendiente(null)
    }
  }

  async function quitar(linea: LineaDescomposicion) {
    if (!window.confirm(`¿Quitar «${linea.resumen}» del descompuesto?`)) return
    try {
      setDatos(await quitarComponente(linea.id))
      onCambio()
      notificar('Componente quitado del descompuesto')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  /** Copiar/pegar entre partidas (Fase 5) — calcado de
   *  `DescompuestoPartida.copiarComponentes`/`pegar`/`confirmarPegado`: si la
   *  partida aún hereda del banco, se independiza primero (si no, el id que
   *  se ve en pantalla es el de la línea del banco, que el backend no
   *  encuentra al pegar) y se recupera qué línea es cuál por `hijo_id`, lo
   *  único que no cambia al clonarlas. */
  async function copiarComponentes(ids: string[]) {
    const reales = ids.filter((id) => id !== ID_BORRADOR)
    if (reales.length === 0 || !datos) return
    let base = datos
    if (!base.propia) {
      const hijoIds = new Set(
        reales
          .map((id) => base?.lineas.find((l) => l.id === id)?.hijo_id)
          .filter((x): x is string => Boolean(x)),
      )
      try {
        base = await independizarDescomposicion()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido')
        return
      }
      setDatos(base)
      onCambio()
      const idsFinales = base.lineas.filter((l) => l.hijo_id && hijoIds.has(l.hijo_id)).map((l) => l.id)
      if (idsFinales.length === 0) return
      copiarAlPortapapeles({
        tipo: 'componentes_descompuesto',
        origenEntidad,
        ids: idsFinales,
        origenEtiqueta: `${codigo} · ${resumen}`,
      })
      notificar(idsFinales.length === 1 ? 'Componente copiado' : `${idsFinales.length} componentes copiados`)
      return
    }
    copiarAlPortapapeles({
      tipo: 'componentes_descompuesto',
      origenEntidad,
      ids: reales,
      origenEtiqueta: `${codigo} · ${resumen}`,
    })
    notificar(reales.length === 1 ? 'Componente copiado' : `${reales.length} componentes copiados`)
  }

  function pegar() {
    const contenido = leerPortapapeles()
    if (!contenido) {
      notificar('No hay nada copiado')
      return
    }
    if (contenido.origenEntidad !== origenEntidad) {
      notificar('Lo copiado es de otro tipo de documento y no se puede pegar aquí')
      return
    }
    if (contenido.tipo !== 'componentes_descompuesto') {
      notificar('Lo copiado no se puede pegar aquí')
      return
    }
    setPegando({ ids: contenido.ids, origenEtiqueta: contenido.origenEtiqueta })
  }

  async function confirmarPegado(alcance: AlcancePegado) {
    if (!pegando) return
    try {
      const resultado = await pegarComponentes({ linea_ids: pegando.ids, alcance })
      setPegando(null)
      await cargar()
      onCambio()
      notificar(
        resultado.pegadas === 1 ? 'Componente pegado' : `${resultado.pegadas} componentes pegados`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setPegando(null)
    }
  }

  function empezarAlta() {
    if (anadiendo) return
    setConceptoNuevo(null)
    setBorradorNuevo(null)
    setAnadiendo(true)
  }

  function cancelarAlta() {
    setAnadiendo(false)
    setConceptoNuevo(null)
    setBorradorNuevo(null)
  }

  function elegirConcepto(opcion?: OpcionCelda) {
    if (!opcion) {
      cancelarAlta()
      return
    }
    if (opcion.esAccion) {
      setBorradorNuevo({ resumen: opcion.valor })
      return
    }
    void elegirConceptoExistente(opcion.valor)
  }

  async function elegirConceptoExistente(conceptoId: string) {
    try {
      setConceptoNuevo(await api.conceptos.get(conceptoId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      cancelarAlta()
    }
  }

  function elegirTipoLinea(opcion?: OpcionCelda) {
    if (!opcion) return
    setBorradorNuevo((actual) => (actual ? { ...actual, tipoLinea: opcion.valor as TipoLinea } : actual))
  }

  async function confirmarCreacion(unidadNueva: string) {
    if (!borradorNuevo?.tipoLinea) return
    const esUnitario = borradorNuevo.tipoLinea === 'unitario'
    try {
      const concepto = await api.conceptos.create({
        resumen: borradorNuevo.resumen,
        unidad: unidadNueva,
        precio: '0',
        tipo: esUnitario ? 'unitario' : 'basico',
        naturaleza: esUnitario ? 'sin_clasificar' : (borradorNuevo.tipoLinea as NaturalezaConcepto),
      })
      notificar(`«${borradorNuevo.resumen}» dado de alta en el banco de precios`)
      setBorradorNuevo(null)
      setConceptoNuevo(concepto)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      cancelarAlta()
    }
  }

  async function confirmarRendimiento(valor: string) {
    if (!conceptoNuevo) return
    const limpio = valor.replace(',', '.')
    if (limpio === '' || Number.isNaN(Number(limpio)) || Number(limpio) <= 0) {
      setError('El rendimiento tiene que ser un número mayor que cero')
      return
    }
    try {
      setDatos(await anadirComponente({ hijo_id: conceptoNuevo.id, rendimiento: limpio }))
      cancelarAlta()
      onCambio()
      notificar('Componente añadido al descompuesto')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      cancelarAlta()
    }
  }

  async function cambiarRendimiento(linea: LineaDescomposicion, valor: string) {
    if (!linea.hijo_id) return
    const limpio = valor.replace(',', '.')
    if (limpio === '' || Number.isNaN(Number(limpio)) || Number(limpio) <= 0) {
      setError('El rendimiento tiene que ser un número mayor que cero')
      return
    }
    if (Number(limpio) === Number(linea.rendimiento)) return
    try {
      setDatos(await cambiarRendimientoComponente({ hijo_id: linea.hijo_id, rendimiento: limpio }))
      onCambio()
      notificar('Rendimiento actualizado')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function cambiarResumen(linea: LineaDescomposicion, valor: string) {
    if (!linea.hijo_id) return
    const limpio = valor.trim()
    if (limpio === '' || limpio === linea.resumen) return
    try {
      setDatos(await cambiarResumenComponente({ hijo_id: linea.hijo_id, resumen: limpio }))
      onCambio()
      notificar('Descripción actualizada')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function cambiarUnidad(linea: LineaDescomposicion, opcion?: OpcionCelda) {
    if (!linea.hijo_id || !opcion || opcion.valor === linea.unidad) return
    try {
      setDatos(await cambiarUnidadComponente({ hijo_id: linea.hijo_id, unidad: opcion.valor }))
      onCambio()
      notificar('Unidad actualizada')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function cambiarNaturaleza(linea: LineaDescomposicion, opcion?: OpcionCelda) {
    if (!linea.hijo_id || !opcion || opcion.valor === linea.naturaleza) return
    try {
      setDatos(
        await cambiarNaturalezaComponente({ hijo_id: linea.hijo_id, naturaleza: opcion.valor as NaturalezaConcepto }),
      )
      onCambio()
      notificar('Tipo de línea actualizado')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function independizar() {
    try {
      setDatos(await independizarDescomposicion())
      onCambio()
      notificar('Descompuesto independizado del banco de precios')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const lineaBorrador: LineaDescomposicion = conceptoNuevo
    ? {
        id: ID_BORRADOR,
        hijo_id: conceptoNuevo.id,
        codigo: conceptoNuevo.codigo,
        resumen: conceptoNuevo.resumen,
        unidad: conceptoNuevo.unidad,
        naturaleza: conceptoNuevo.naturaleza,
        rendimiento: '1',
        factor: '1',
        precio: conceptoNuevo.precio,
        importe: conceptoNuevo.precio,
      }
    : {
        id: ID_BORRADOR,
        hijo_id: null,
        codigo: borradorNuevo ? '(nuevo)' : '',
        resumen: borradorNuevo?.resumen ?? '',
        unidad: '',
        naturaleza: null,
        rendimiento: '1',
        factor: '1',
        precio: '0',
        importe: '0',
      }

  const total = (datos?.lineas ?? []).reduce((suma, l) => suma + Number(l.importe), 0)

  const columnas: ColumnaRejilla<LineaDescomposicion>[] = [
    { id: 'codigo', etiqueta: 'Código', ancho: '140px', valor: (l) => l.codigo },
    {
      id: 'resumen',
      etiqueta: 'Descripción',
      ancho: '220px',
      valor: (l) => l.resumen,
      editable: (l) => (l.id === ID_BORRADOR ? !conceptoNuevo && !borradorNuevo : l.hijo_id !== null),
      tipo: 'autocompletado',
      buscar: async (q, fila) => {
        if (fila.id !== ID_BORRADOR) return []
        if (q.trim().length < 2) return []
        const pagina = await api.conceptos.list({ q, activo: true, limit: 8 })
        const sugerencias: OpcionCelda[] = pagina.items.map((c) => ({
          valor: c.id,
          etiqueta: `${c.codigo} · ${c.resumen}`,
          detalle: `${formatoImporte(c.precio)} €/${c.unidad}`,
        }))
        sugerencias.push({
          valor: q,
          etiqueta: `Crear «${q}» en el banco de precios`,
          esAccion: true,
        })
        return sugerencias
      },
    },
    {
      id: 'tipoLinea',
      etiqueta: 'Tipo',
      ancho: '170px',
      tipo: 'select',
      valor: (l) => {
        if (l.id !== ID_BORRADOR) return l.naturaleza ? ETIQUETA_NATURALEZA[l.naturaleza] : ''
        const elegido = OPCIONES_TIPO_LINEA.find((o) => o.valor === borradorNuevo?.tipoLinea)
        return elegido?.etiqueta ?? ''
      },
      editable: (l) =>
        l.id === ID_BORRADOR ? Boolean(borradorNuevo) && !borradorNuevo?.tipoLinea : l.hijo_id !== null,
      opciones: (l) => (l.id === ID_BORRADOR ? OPCIONES_TIPO_LINEA : OPCIONES_NATURALEZA_EXISTENTE),
    },
    {
      id: 'unidad',
      etiqueta: 'Ud.',
      ancho: '110px',
      tipo: 'select',
      valor: (l) => l.unidad,
      editable: (l) => (l.id === ID_BORRADOR ? Boolean(borradorNuevo?.tipoLinea) : l.hijo_id !== null),
      opciones: () => unidadesMedida.map((u) => ({ valor: u.clave, etiqueta: u.etiqueta })),
    },
    {
      id: 'rendimiento',
      etiqueta: 'Rendim.',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => formatoImporte(l.rendimiento, 3),
      editable: (l) => (l.id === ID_BORRADOR ? Boolean(conceptoNuevo) : l.hijo_id !== null),
    },
    {
      id: 'precio',
      etiqueta: 'Precio',
      ancho: '110px',
      tipo: 'numero',
      valor: (l) => formatoImporte(l.precio),
      editable: (l) => l.hijo_id !== null && l.id !== ID_BORRADOR,
    },
    {
      id: 'importe',
      etiqueta: 'Importe',
      ancho: '110px',
      tipo: 'numero',
      valor: (l) => formatoImporte(l.importe),
      total: `${formatoImporte(String(total))} €`,
    },
  ]

  const filas = anadiendo ? [...(datos?.lineas ?? []), lineaBorrador] : (datos?.lineas ?? [])

  const filtrosActivos = Object.entries(filtros).filter(([, v]) => v.trim() !== '')
  const filasVisibles =
    filtrosActivos.length === 0
      ? filas
      : filas.filter(
          (f) =>
            f.id === ID_BORRADOR ||
            filtrosActivos.every(([colId, q]) => {
              const col = columnas.find((c) => c.id === colId)
              return (col?.valor(f) ?? '').toLowerCase().includes(q.trim().toLowerCase())
            }),
        )

  return (
    <>
      <div className="rejilla-barra">
        <BotonAtajos conAutocompletado />
        <Tooltip texto="Buscar en el banco de precios, o crear uno nuevo">
          <button className="btn btn--sm" onClick={empezarAlta} disabled={anadiendo}>
            <Plus size={14} aria-hidden="true" />
            Línea
          </button>
        </Tooltip>
        {anadiendo && (
          <button className="btn btn--sm" onClick={cancelarAlta}>
            <X size={14} aria-hidden="true" />
            Cancelar
          </button>
        )}
        {(() => {
          const contenido = leerPortapapeles()
          if (!contenido || contenido.origenEntidad !== origenEntidad || contenido.tipo !== 'componentes_descompuesto')
            return null
          return (
            <Tooltip texto={`Pegar componente(s) de «${contenido.origenEtiqueta}»`}>
              <button className="btn btn--sm" onClick={pegar}>
                <Clipboard size={14} aria-hidden="true" />
                Pegar
              </button>
            </Tooltip>
          )
        })()}
        <span className="rejilla-barra__ayuda muted">
          {codigo} · {resumen}
        </span>
        <span className="rejilla-barra__estado">
          {datos?.propia ? (
            <span className="chip chip--preferente">descompuesto propio</span>
          ) : (
            <>
              <span className="chip">del banco de precios</span>{' '}
              <button className="btn btn--sm" onClick={() => void independizar()}>
                <Unlink size={14} aria-hidden="true" />
                Independizar
              </button>
            </>
          )}
        </span>
      </div>

      <ErrorNotice error={error} />

      <RejillaEditable
        filas={filasVisibles}
        columnas={columnas}
        idDe={(l) => l.id}
        onNuevaFila={empezarAlta}
        onCopiar={(ids) => void copiarComponentes(ids)}
        onPegar={pegar}
        filtros={filtros}
        onFiltrar={(columnaId, valor) => setFiltros((f) => ({ ...f, [columnaId]: valor }))}
        filaAEditarId={anadiendo ? ID_BORRADOR : null}
        columnaAEditarId={
          anadiendo
            ? conceptoNuevo
              ? 'rendimiento'
              : borradorNuevo?.tipoLinea
                ? 'unidad'
                : borradorNuevo
                  ? 'tipoLinea'
                  : 'resumen'
            : null
        }
        onEditar={(linea, columnaId, valor, opcion) => {
          if (linea.id === ID_BORRADOR) {
            if (columnaId === 'resumen') elegirConcepto(opcion)
            else if (columnaId === 'tipoLinea') elegirTipoLinea(opcion)
            else if (columnaId === 'unidad') void confirmarCreacion(valor)
            else if (columnaId === 'rendimiento') void confirmarRendimiento(valor)
            return
          }
          if (columnaId === 'resumen') return void cambiarResumen(linea, valor)
          if (columnaId === 'tipoLinea') return void cambiarNaturaleza(linea, opcion)
          if (columnaId === 'unidad') return void cambiarUnidad(linea, opcion)
          if (columnaId === 'rendimiento') return void cambiarRendimiento(linea, valor)
          if (columnaId !== 'precio') return
          const limpio = valor.replace(',', '.')
          if (limpio === '' || Number.isNaN(Number(limpio))) return
          if (Number(limpio) === Number(linea.precio)) return
          setPendiente({ linea, precio: limpio })
        }}
        acciones={(l) =>
          l.id === ID_BORRADOR ? null : (
            <Tooltip texto="Quitar este componente del descompuesto">
              <button
                className="btn btn--sm btn--danger btn--solo-icono"
                aria-label={`Quitar ${l.resumen}`}
                onClick={() => void quitar(l)}
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </Tooltip>
          )
        }
        vacia={
          filtrosActivos.length > 0 ? (
            <EmptyState title="Sin resultados">Nada coincide con los filtros.</EmptyState>
          ) : (
            <EmptyState title="Sin descomponer">
              Esta partida no tiene descompuesto: su precio va a mano.
              <div style={{ marginTop: 'var(--sp-3)' }}>
                <button className="btn btn--primary" onClick={empezarAlta}>
                  <Plus size={16} aria-hidden="true" />
                  Añadir el primer componente
                </button>
              </div>
            </EmptyState>
          )
        }
      />

      {(datos?.lineas.length ?? 0) > 0 && (
        <div className="resumen-totales" style={{ marginTop: 'var(--sp-3)' }}>
          <div className="resumen-totales__fila is-total">
            <span>Coste directo</span>
            <span className="resumen-totales__valor">{formatoImporte(String(total))} €</span>
          </div>
          {costesIndirectos && (
            <div className="resumen-totales__fila is-suave">
              <span>Costes indirectos {formatoImporte(costesIndirectos)} %</span>
              <span className="resumen-totales__valor">
                {formatoImporte(String(Number(precio) - total))} €
              </span>
            </div>
          )}
          <div className="resumen-totales__fila is-total">
            <span>Precio por {unidad}</span>
            <span className="resumen-totales__valor">{formatoImporte(precio)} €</span>
          </div>
        </div>
      )}

      {pendiente && (
        <Modal title="¿Hasta dónde llega este cambio?" onClose={() => setPendiente(null)}>
          <div className="form-section">
            <p className="form-section__note">
              Vas a poner <strong>«{pendiente.linea.resumen}»</strong> a{' '}
              <strong>
                {formatoImporte(pendiente.precio)} €/{pendiente.linea.unidad}
              </strong>{' '}
              (antes {formatoImporte(pendiente.linea.precio)} €). El banco de precios no se modifica
              en ninguno de los dos casos: la partida se independiza de él.
            </p>
            <div className="field__label">Alcance</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
              <button className="btn" onClick={() => void aplicar('partida')}>
                <Unlink size={16} aria-hidden="true" />
                Solo en esta partida
              </button>
              <button className="btn btn--primary" onClick={() => void aplicar('amplio')}>
                <Save size={16} aria-hidden="true" />
                {etiquetaAlcanceAmplio}
              </button>
            </div>
          </div>
          <div className="form-actions">
            <button className="btn" onClick={() => setPendiente(null)}>
              <X size={16} aria-hidden="true" />
              Cancelar
            </button>
          </div>
        </Modal>
      )}

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
