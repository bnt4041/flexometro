import { useCallback, useEffect, useState } from 'react'
import { ArrowLeftRight, Plus, Save, Send, Trash2, Unlink, X } from 'lucide-react'

import { BotonAtajos } from './AtajosTeclado'
import { BuscadorSustitutoModal } from './BuscadorSustitutoModal'
import { PegarModal } from './PegarModal'
import { SolicitarPreciosModal } from './SolicitarPreciosModal'
import type { ColumnaRejilla, ItemMenuContextual, OpcionCelda } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Modal, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type {
  AlcancePegado,
  AlcancePrecio,
  ConceptoDetalle,
  DescomposicionPartida,
  LineaDescomposicion,
  NaturalezaConcepto,
  Partida,
} from '../lib/api'
import { ETIQUETA_NATURALEZA } from '../lib/api'
import { copiarAlPortapapeles, leerPortapapeles } from '../lib/portapapeles'
import { useDiccionario } from '../lib/useDiccionario'
import { useToast } from '../toast'

/** Fila que solo vive en el navegador mientras se está montando un componente
 *  nuevo — nunca llega a `datos.lineas`, que es lo que devuelve el backend. */
const ID_BORRADOR = '__nuevo__'

/** "Tipo de línea" al crear un componente nuevo: las cuatro naturalezas
 *  normales (Fase 38) más la opción de anidar un unitario entero como
 *  auxiliar de esta partida — un caso raro, de ahí la coletilla. */
type TipoLinea = 'material' | 'mano_obra' | 'maquinaria' | 'servicio' | 'unitario'

const OPCIONES_TIPO_LINEA: OpcionCelda[] = [
  { valor: 'material', etiqueta: 'Material' },
  { valor: 'mano_obra', etiqueta: 'Mano de obra' },
  { valor: 'maquinaria', etiqueta: 'Maquinaria' },
  { valor: 'servicio', etiqueta: 'Servicio' },
  { valor: 'unitario', etiqueta: 'Auxiliar (unitario) — poco uso' },
]

/** Para reclasificar una línea ya guardada: sin "Auxiliar (unitario)", que
 *  no es una naturaleza sino el tipo del concepto en sí —no se puede
 *  convertir un componente básico ya puesto en uno unitario desde aquí. */
const OPCIONES_NATURALEZA_EXISTENTE: OpcionCelda[] = [
  { valor: 'sin_clasificar', etiqueta: 'Sin clasificar' },
  { valor: 'material', etiqueta: 'Material' },
  { valor: 'mano_obra', etiqueta: 'Mano de obra' },
  { valor: 'maquinaria', etiqueta: 'Maquinaria' },
  { valor: 'servicio', etiqueta: 'Servicio' },
]

/** Descompuesto de la partida seleccionada (Fase 34).
 *
 *  Mientras la partida hereda el descompuesto del banco de precios se enseña
 *  igual, pero al cambiar el precio de un componente hay que decidir hasta
 *  dónde llega el cambio: solo esta partida, o todas las del presupuesto que
 *  lleven ese componente. En ambos casos la partida (o partidas) se
 *  independizan del banco — el banco no se toca nunca desde aquí. */
export function DescompuestoPartida({
  partida,
  presupuestoId,
  onCambio,
}: {
  partida: Partida
  presupuestoId: string
  onCambio: () => void
}) {
  const { notificar } = useToast()
  const [datos, setDatos] = useState<DescomposicionPartida | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pendiente, setPendiente] = useState<{ linea: LineaDescomposicion; precio: string } | null>(
    null,
  )
  // Búsqueda o alta: primero se busca o se crea el concepto (celda
  // "Descripción"). Elegir uno existente pasa directo a rendimiento; crear
  // uno nuevo pide antes su tipo de línea y su unidad —hasta entonces no hay
  // nada que enviar al backend, porque `anadir_componente` exige un
  // `hijo_id` real desde el principio, y el concepto en sí necesita tipo,
  // naturaleza y unidad antes de poder darlo de alta.
  const [conceptoNuevo, setConceptoNuevo] = useState<ConceptoDetalle | null>(null)
  const [borradorNuevo, setBorradorNuevo] = useState<{
    resumen: string
    tipoLinea?: TipoLinea
  } | null>(null)
  const [anadiendo, setAnadiendo] = useState(false)
  const [pegando, setPegando] = useState<{ ids: string[]; origenEtiqueta: string } | null>(null)
  const [filtros, setFiltros] = useState<Record<string, string>>({})
  // «Solicitar precios…» sobre componentes sueltos: pedir solo el material,
  // solo la mano de obra, o un elemento concreto. Con la marca múltiple de la
  // rejilla (y sus filtros por tipo de línea) sale casi solo: filtrar por
  // "Mano de obra", marcar, botón derecho.
  const [marcadas, setMarcadas] = useState<string[]>([])
  const [solicitando, setSolicitando] = useState<LineaDescomposicion[] | null>(null)
  const unidadesMedida = useDiccionario('unidad_medida')

  const cargar = useCallback(async () => {
    try {
      setDatos(await api.partidas.descomposicion(partida.id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [partida.id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  // «Cambiar por banco de precios» (Fase 52) sobre un componente: quita la
  // línea vieja y añade una nueva con el concepto elegido, mismo
  // rendimiento — no hay un endpoint de "sustituir componente" propio, es
  // la misma pareja de llamadas que ya usan el resto de acciones de esta
  // rejilla (independiza sola si aún heredaba del banco, ver `anadir_componente`).
  const [sustituyendoLinea, setSustituyendoLinea] = useState<LineaDescomposicion | null>(null)

  async function sustituirComponente(linea: LineaDescomposicion, conceptoId: string) {
    await api.partidas.quitarComponente(partida.id, linea.id)
    await api.partidas.anadirComponente(partida.id, {
      hijo_id: conceptoId,
      rendimiento: linea.rendimiento,
    })
    await cargar()
    onCambio()
  }

  async function aplicar(alcance: AlcancePrecio) {
    if (!pendiente?.linea.hijo_id) return
    try {
      // La respuesta ya trae el descompuesto recalculado: volver a pedirlo aquí
      // se cruzaría con el commit del servidor, que ocurre tras enviar la
      // respuesta, y devolvería el estado anterior.
      const { partidas_afectadas, descomposicion } = await api.partidas.cambiarPrecioComponente(
        partida.id,
        { hijo_id: pendiente.linea.hijo_id, precio: pendiente.precio, alcance },
      )
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
      // Igual que arriba: la respuesta trae el descompuesto ya recalculado.
      setDatos(await api.partidas.quitarComponente(partida.id, linea.id))
      onCambio()
      notificar('Componente quitado del descompuesto')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function copiarComponentes(ids: string[]) {
    const reales = ids.filter((id) => id !== ID_BORRADOR)
    if (reales.length === 0 || !datos) return
    // Mientras la partida solo hereda del banco, el id que se ve en pantalla
    // es el de la línea del banco (`Descomposicion.id`): no identifica a esta
    // partida y el backend no lo va a encontrar al pegar. Se independiza
    // primero —como ya hace cualquier otro toque a una línea— y se recupera
    // qué línea es cuál por `hijo_id`, lo único que no cambia al clonarlas.
    let base = datos
    if (!base.propia) {
      const hijoIds = new Set(
        reales
          .map((id) => base?.lineas.find((l) => l.id === id)?.hijo_id)
          .filter((x): x is string => Boolean(x)),
      )
      try {
        base = await api.partidas.independizarDescomposicion(partida.id)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido')
        return
      }
      setDatos(base)
      onCambio()
      const idsFinales = base.lineas
        .filter((l) => l.hijo_id && hijoIds.has(l.hijo_id))
        .map((l) => l.id)
      if (idsFinales.length === 0) return
      copiarAlPortapapeles({
        tipo: 'componentes_descompuesto',
        ids: idsFinales,
        origenEtiqueta: `${partida.codigo} · ${partida.resumen}`,
      })
      notificar(
        idsFinales.length === 1 ? 'Componente copiado' : `${idsFinales.length} componentes copiados`,
      )
      return
    }
    copiarAlPortapapeles({
      tipo: 'componentes_descompuesto',
      ids: reales,
      origenEtiqueta: `${partida.codigo} · ${partida.resumen}`,
    })
    notificar(reales.length === 1 ? 'Componente copiado' : `${reales.length} componentes copiados`)
  }

  function pegar() {
    const contenido = leerPortapapeles()
    if (!contenido) {
      notificar('No hay nada copiado')
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
      const resultado = await api.partidas.pegarComponentes(partida.id, {
        linea_ids: pegando.ids,
        alcance,
      })
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
      // Crear nuevo: todavía no hay concepto real, así que no se puede
      // llamar a la API — antes hacen falta su tipo de línea y su unidad.
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

  async function confirmarCreacion(unidad: string) {
    if (!borradorNuevo?.tipoLinea) return
    const esUnitario = borradorNuevo.tipoLinea === 'unitario'
    try {
      const concepto = await api.conceptos.create({
        resumen: borradorNuevo.resumen,
        unidad,
        precio: '0',
        tipo: esUnitario ? 'unitario' : 'basico',
        // Un unitario es un ítem compuesto en sí mismo (una partida
        // anidada): la clasificación material/mano de obra/etc. es de los
        // recursos básicos que lo componen, no del unitario en conjunto.
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
      setDatos(await api.partidas.anadirComponente(partida.id, { hijo_id: conceptoNuevo.id, rendimiento: limpio }))
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
      setDatos(
        await api.partidas.cambiarRendimientoComponente(partida.id, {
          hijo_id: linea.hijo_id,
          rendimiento: limpio,
        }),
      )
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
      setDatos(
        await api.partidas.cambiarResumenComponente(partida.id, { hijo_id: linea.hijo_id, resumen: limpio }),
      )
      onCambio()
      notificar('Descripción actualizada')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function cambiarUnidad(linea: LineaDescomposicion, opcion?: OpcionCelda) {
    if (!linea.hijo_id || !opcion || opcion.valor === linea.unidad) return
    try {
      setDatos(
        await api.partidas.cambiarUnidadComponente(partida.id, {
          hijo_id: linea.hijo_id,
          unidad: opcion.valor,
        }),
      )
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
        await api.partidas.cambiarNaturalezaComponente(partida.id, {
          hijo_id: linea.hijo_id,
          naturaleza: opcion.valor as NaturalezaConcepto,
        }),
      )
      onCambio()
      notificar('Tipo de línea actualizado')
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
      // Sin ancho fijo, `table-layout: fixed` la aplastaba a lo que
      // sobrase tras repartir las demás columnas (a veces ~20px).
      ancho: '220px',
      valor: (l) => l.resumen,
      // Con el borrador se busca o se crea en el banco; una línea ya
      // guardada solo permite retocar el texto (`buscar` no llega a
      // consultar nada para ella, ver más abajo) — el concepto en sí no
      // cambia, es la etiqueta que se ve en este descompuesto.
      editable: (l) => (l.id === ID_BORRADOR ? !conceptoNuevo && !borradorNuevo : l.hijo_id !== null),
      tipo: 'autocompletado',
      buscar: async (q, fila) => {
        if (fila.id !== ID_BORRADOR) return []
        if (q.trim().length < 2) return []
        const pagina = await api.conceptos.list({ q, activo: true, limit: 8 })
        const sugerencias: OpcionCelda[] = pagina.items
          .filter((c) => c.id !== partida.concepto_id)
          .map((c) => ({
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
        if (l.id !== ID_BORRADOR) {
          return l.naturaleza ? ETIQUETA_NATURALEZA[l.naturaleza] : ''
        }
        const elegido = OPCIONES_TIPO_LINEA.find((o) => o.valor === borradorNuevo?.tipoLinea)
        return elegido?.etiqueta ?? ''
      },
      // En el borrador, solo tras elegir "crear nuevo" (segundo paso). En
      // una línea ya guardada, reclasifica —para poder corregir las que se
      // quedaron "sin clasificar" antes de que hubiera dónde elegirlo.
      editable: (l) =>
        l.id === ID_BORRADOR
          ? Boolean(borradorNuevo) && !borradorNuevo?.tipoLinea
          : l.hijo_id !== null,
      opciones: (l) => (l.id === ID_BORRADOR ? OPCIONES_TIPO_LINEA : OPCIONES_NATURALEZA_EXISTENTE),
    },
    {
      id: 'unidad',
      etiqueta: 'Ud.',
      ancho: '110px',
      tipo: 'select',
      valor: (l) => l.unidad,
      // En el borrador, el último paso antes de dar de alta el concepto: en
      // cuanto se confirma, se llama a la API (ver `confirmarCreacion`). En
      // una línea ya guardada, corrige la unidad congelada —por ejemplo, una
      // mano de obra que se dio de alta en "ud" en vez de en "h", y que por
      // eso no contaba en las horas presupuestadas.
      editable: (l) =>
        l.id === ID_BORRADOR ? Boolean(borradorNuevo?.tipoLinea) : l.hijo_id !== null,
      opciones: () => unidadesMedida.map((u) => ({ valor: u.clave, etiqueta: u.etiqueta })),
    },
    {
      id: 'rendimiento',
      etiqueta: 'Rendim.',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => formatoImporte(l.rendimiento, 3),
      // En el borrador, solo tras elegir el concepto (segundo paso). En una
      // línea ya guardada, lo mismo que el precio: hace falta que el
      // concepto siga existiendo en el banco para saber a qué aplicarlo.
      editable: (l) => (l.id === ID_BORRADOR ? Boolean(conceptoNuevo) : l.hijo_id !== null),
    },
    {
      id: 'precio',
      etiqueta: 'Precio',
      ancho: '110px',
      tipo: 'numero',
      valor: (l) => formatoImporte(l.precio),
      // Solo se puede tocar el precio de un componente que siga existiendo en
      // el banco: sin `hijo_id` no hay a qué aplicar el cambio.
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

  // El borrador de un alta en marcha nunca se filtra: se está tecleando.
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
        <span className="rejilla-barra__ayuda muted">
          {partida.codigo} · {partida.resumen}
        </span>
        <span className="rejilla-barra__estado">
          {datos?.propia ? (
            <span className="chip chip--preferente">descompuesto propio</span>
          ) : (
            <span className="chip">del banco de precios</span>
          )}
        </span>
      </div>

      <ErrorNotice error={error} />

      <RejillaEditable
        filas={filasVisibles}
        columnas={columnas}
        idDe={(l) => l.id}
        // ↓ en la última fila, o Tab al final de la fila: empieza el mismo
        // alta que el botón "+ Línea" (no-op si ya hay una en marcha).
        onNuevaFila={empezarAlta}
        onCopiar={copiarComponentes}
        onPegar={pegar}
        onSoltarEn={() => pegar()}
        puedeArrastrar={(l) => l.id !== ID_BORRADOR}
        onMarcarVarias={setMarcadas}
        menuContextual={(l): ItemMenuContextual[] | null => {
          // Sin `hijo_id` la línea no apunta a ningún concepto del banco (se
          // borró): ni se puede sustituir ni se le puede pedir precio, porque
          // no hay nada estable a lo que referirse.
          if (l.id === ID_BORRADOR || l.hijo_id === null) return null

          const objetivo = marcadas.length > 1 && marcadas.includes(l.id) ? marcadas : [l.id]
          const lineas = (datos?.lineas ?? []).filter(
            (linea) => objetivo.includes(linea.id) && linea.hijo_id !== null,
          )
          const sufijo = lineas.length > 1 ? ` (${lineas.length})` : ''

          return [
            {
              id: 'sustituir',
              etiqueta: 'Cambiar por banco de precios…',
              icono: <ArrowLeftRight size={14} aria-hidden="true" />,
              onClick: () => setSustituyendoLinea(l),
            },
            {
              id: 'solicitar-precios',
              etiqueta: `Solicitar precios…${sufijo}`,
              icono: <Send size={14} aria-hidden="true" />,
              onClick: () => setSolicitando(lineas),
            },
          ]
        }}
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
          if (columnaId === 'resumen') {
            void cambiarResumen(linea, valor)
            return
          }
          if (columnaId === 'tipoLinea') {
            void cambiarNaturaleza(linea, opcion)
            return
          }
          if (columnaId === 'unidad') {
            void cambiarUnidad(linea, opcion)
            return
          }
          if (columnaId === 'rendimiento') {
            void cambiarRendimiento(linea, valor)
            return
          }
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
              Esta partida no tiene descompuesto: su precio va a mano o viene de una partida alzada.
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
          {partida.costes_indirectos && (
            <div className="resumen-totales__fila is-suave">
              <span>Costes indirectos {formatoImporte(partida.costes_indirectos)} %</span>
              <span className="resumen-totales__valor">
                {formatoImporte(String(Number(partida.precio) - total))} €
              </span>
            </div>
          )}
          <div className="resumen-totales__fila is-total">
            <span>Precio por {partida.unidad}</span>
            <span className="resumen-totales__valor">{formatoImporte(partida.precio)} €</span>
          </div>
        </div>
      )}

      {pendiente && (
        <Modal title="¿Hasta dónde llega este cambio?" onClose={() => setPendiente(null)}>
          <div className="form-section">
            <p className="form-section__note">
              Vas a poner <strong>«{pendiente.linea.resumen}»</strong> a{' '}
              <strong>{formatoImporte(pendiente.precio)} €/{pendiente.linea.unidad}</strong> (antes{' '}
              {formatoImporte(pendiente.linea.precio)} €). El banco de precios no se modifica en
              ninguno de los dos casos: la partida se independiza de él.
            </p>
            {/* Ojo: estos botones NO van dentro de `Field`, que envuelve en un
                `<label>`; un `<label>` es para etiquetar un control, y metiendo
                botones dentro se rompe su nombre accesible. */}
            <div className="field__label">Alcance</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
              <button className="btn" onClick={() => void aplicar('partida')}>
                <Unlink size={16} aria-hidden="true" />
                Solo en esta partida
              </button>
              <button className="btn btn--primary" onClick={() => void aplicar('presupuesto')}>
                <Save size={16} aria-hidden="true" />
                En todo el presupuesto donde aparezca
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

      {sustituyendoLinea && (
        <BuscadorSustitutoModal
          resumenActual={sustituyendoLinea.resumen}
          unidadActual={sustituyendoLinea.unidad}
          modo="componente"
          onAplicar={async (candidato) => {
            if (!candidato.concepto_id) return
            await sustituirComponente(sustituyendoLinea, candidato.concepto_id)
            notificar(`«${sustituyendoLinea.resumen}» sustituido por «${candidato.resumen}»`)
          }}
          onClose={() => setSustituyendoLinea(null)}
        />
      )}
      {solicitando && (
        <SolicitarPreciosModal
          presupuestoId={presupuestoId}
          items={solicitando.map((l) => ({
            clave: l.id,
            // La medición que verá el proveedor es la de verdad (rendimiento
            // × medición de la partida), y la calcula el backend al congelar
            // la línea; aquí basta con identificar qué se le pide.
            resumen: l.resumen,
            unidad: l.unidad,
          }))}
          seleccion={{
            componentes: solicitando
              .filter((l) => l.hijo_id !== null)
              .map((l) => ({ partida_id: partida.id, concepto_id: l.hijo_id as string })),
          }}
          onClose={() => setSolicitando(null)}
          onCreada={() => setSolicitando(null)}
        />
      )}
    </>
  )
}
