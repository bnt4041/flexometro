import { useCallback, useEffect, useRef, useState } from 'react'
import { FunctionSquare, Plus, Scan, Trash2 } from 'lucide-react'

import { BotonAtajos } from './AtajosTeclado'
import { FormulasModal } from './FormulasModal'
import { PegarModal } from './PegarModal'
import type { ColumnaRejilla } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { AlcancePegado, FormulaMedicion, LineaMedicion, Partida, PartidaDetalle } from '../lib/api'
import { copiarAlPortapapeles, leerPortapapeles } from '../lib/portapapeles'
import { useToast } from '../toast'
import { useWorkspace } from '../workspace'

const RETARDO_GUARDADO = 700

/** Estado de mediciones de una partida, editable por teclado (Fase 37).
 *
 *  Una línea se mide de una de dos formas: por el producto clásico de
 *  uds × longitud × anchura × altura (registro ~M de FIEBDC-3), o por una
 *  fórmula del catálogo, y entonces son sus variables las que se rellenan.
 *  Las dos conviven en la misma tabla porque en una medición real conviven. */
export function MedicionesPartida({
  partida,
  onCambio,
  onLeerPlano,
}: {
  partida: Partida
  onCambio: () => void
  onLeerPlano?: () => void
}) {
  const { modules } = useWorkspace()
  const { notificar } = useToast()
  const iaActiva = modules.some((m) => m.code === 'ia' && m.is_active)
  const [detalle, setDetalle] = useState<PartidaDetalle | null>(null)
  const [formulas, setFormulas] = useState<FormulaMedicion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [pendiente, setPendiente] = useState(false)
  const [gestionandoFormulas, setGestionandoFormulas] = useState(false)
  const [pegando, setPegando] = useState<{ ids: string[]; origenEtiqueta: string } | null>(null)
  const [filtros, setFiltros] = useState<Record<string, string>>({})
  const cambios = useRef<Map<string, Record<string, string | null>>>(new Map())
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cargar = useCallback(async () => {
    try {
      setDetalle(await api.partidas.get(partida.id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [partida.id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  useEffect(() => {
    void api.formulasMedicion
      .list()
      .then(setFormulas)
      .catch(() => setFormulas([]))
  }, [])

  const volcar = useCallback(async () => {
    if (cambios.current.size === 0) return
    const tanda = [...cambios.current.entries()]
    cambios.current.clear()
    setPendiente(false)
    try {
      // No hay endpoint de lote para mediciones: son unas pocas líneas por
      // partida, no cientos como en el listado del presupuesto.
      for (const [id, campos] of tanda) await api.mediciones.update(id, campos)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [cargar, onCambio])

  useEffect(() => {
    return () => {
      if (temporizador.current) clearTimeout(temporizador.current)
      void volcar()
    }
  }, [volcar])

  function encolar(linea: LineaMedicion, campo: string, valor: string | null) {
    const previo = cambios.current.get(linea.id) ?? {}
    cambios.current.set(linea.id, { ...previo, [campo]: valor })
    setPendiente(true)
    if (temporizador.current) clearTimeout(temporizador.current)
    temporizador.current = setTimeout(() => void volcar(), RETARDO_GUARDADO)
  }

  function editarLocal(id: string, cambio: Partial<LineaMedicion>) {
    setDetalle((d) =>
      d ? { ...d, lineas: d.lineas.map((l) => (l.id === id ? { ...l, ...cambio } : l)) } : d,
    )
  }

  async function anadir(formulaId?: string) {
    setError(null)
    try {
      // Sin `orden` explícito, el backend la crea con 0 — empataba con
      // cualquier otra línea ya a 0 y el orden de desempate de la consulta no
      // garantiza que la nueva quede al final. Va siempre después de la que
      // más alto tenga.
      const siguienteOrden =
        (detalle?.lineas ?? []).reduce((maximo, l) => Math.max(maximo, l.orden), -1) + 1
      await api.partidas.addLinea(
        partida.id,
        formulaId
          ? { formula_id: formulaId, orden: siguienteOrden }
          : { uds: '1', orden: siguienteOrden },
      )
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar(linea: LineaMedicion) {
    try {
      await api.mediciones.remove(linea.id)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  function copiarLineas(ids: string[]) {
    if (ids.length === 0) return
    copiarAlPortapapeles({
      tipo: 'lineas_medicion',
      ids,
      origenEtiqueta: partida.resumen,
    })
    notificar(ids.length === 1 ? 'Línea copiada' : `${ids.length} líneas copiadas`)
  }

  function pegar() {
    const contenido = leerPortapapeles()
    if (!contenido) {
      notificar('No hay nada copiado')
      return
    }
    if (contenido.tipo !== 'lineas_medicion') {
      notificar('Lo copiado no se puede pegar aquí')
      return
    }
    setPegando({ ids: contenido.ids, origenEtiqueta: contenido.origenEtiqueta })
  }

  async function confirmarPegado(alcance: AlcancePegado) {
    if (!pegando) return
    try {
      const resultado = await api.partidas.pegarLineas(partida.id, {
        linea_ids: pegando.ids,
        alcance,
      })
      setPegando(null)
      await cargar()
      onCambio()
      notificar(resultado.pegadas === 1 ? 'Línea pegada' : `${resultado.pegadas} líneas pegadas`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setPegando(null)
    }
  }

  /** Nombre de la fórmula de una línea, si la tiene. */
  function formulaDe(linea: LineaMedicion): FormulaMedicion | undefined {
    return formulas.find((f) => f.id === linea.formula_id)
  }

  /** Variables de la fórmula congelada en la línea. Se leen de los valores ya
   *  guardados y del catálogo, para que una fórmula borrada del catálogo siga
   *  dejando editar lo que esa línea tenía. */
  function variablesDe(linea: LineaMedicion): string[] {
    const delCatalogo = formulaDe(linea)?.variables ?? []
    const guardadas = Object.keys(linea.formula_valores ?? {})
    return [...new Set([...delCatalogo, ...guardadas])]
  }

  const conFormula = (l: LineaMedicion) => Boolean(l.formula_expresion)

  const columnas: ColumnaRejilla<LineaMedicion>[] = [
    {
      id: 'comentario',
      etiqueta: 'Comentario',
      // Sin ancho fijo, `table-layout: fixed` la aplastaba a lo que
      // sobrase tras repartir las demás columnas (a veces ~20px).
      ancho: '200px',
      valor: (l) => l.comentario ?? '',
      editable: () => true,
    },
    {
      id: 'uds',
      etiqueta: 'Uds',
      ancho: '90px',
      tipo: 'numero',
      valor: (l) => (l.uds ? formatoImporte(l.uds, 3) : ''),
      editable: () => true,
    },
    {
      id: 'formula',
      etiqueta: 'Fórmula / dimensiones',
      valor: (l) => {
        if (!conFormula(l)) return ''
        const nombre = formulaDe(l)?.nombre ?? 'Fórmula'
        const vars = variablesDe(l)
          .map((v) => `${v}=${l.formula_valores?.[v] ?? '0'}`)
          .join('  ')
        return `${nombre}: ${vars}`
      },
    },
    {
      id: 'longitud',
      etiqueta: 'Longitud',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => (conFormula(l) ? '' : l.longitud ? formatoImporte(l.longitud, 3) : ''),
      // Con fórmula manda la expresión: estas tres no intervienen en el parcial,
      // así que dejarlas editables sería invitar a teclear algo que no hace nada.
      editable: (l) => !conFormula(l),
    },
    {
      id: 'anchura',
      etiqueta: 'Anchura',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => (conFormula(l) ? '' : l.anchura ? formatoImporte(l.anchura, 3) : ''),
      editable: (l) => !conFormula(l),
    },
    {
      id: 'altura',
      etiqueta: 'Altura',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => (conFormula(l) ? '' : l.altura ? formatoImporte(l.altura, 3) : ''),
      editable: (l) => !conFormula(l),
    },
    {
      id: 'parcial',
      etiqueta: 'Parcial',
      ancho: '110px',
      tipo: 'numero',
      valor: (l) => formatoImporte(l.parcial, 3),
      // La medición ya recalculada del servidor, no una suma local: coincide
      // con lo que enseña el resumen de abajo aunque el redondeo del backend
      // difiera del de sumar aquí mismo.
      total: `${formatoImporte(detalle?.medicion ?? '0', 3)} ${partida.unidad}`,
    },
  ]

  const lineas = detalle?.lineas ?? []

  const filtrosActivos = Object.entries(filtros).filter(([, v]) => v.trim() !== '')
  const lineasVisibles =
    filtrosActivos.length === 0
      ? lineas
      : lineas.filter((l) =>
          filtrosActivos.every(([colId, q]) => {
            const col = columnas.find((c) => c.id === colId)
            return (col?.valor(l) ?? '').toLowerCase().includes(q.trim().toLowerCase())
          }),
        )

  return (
    <>
      <p className="form-section__note">
        {partida.resumen}. El parcial es el producto de lo que esté informado: una línea con solo
        unidades mide esas unidades. Un valor negativo deduce, que es como se descuentan los huecos.
      </p>

      {/* Las acciones van arriba, no debajo de la rejilla: en un widget bajito
          la rejilla se lleva todo el alto y los botones quedaban fuera de la
          vista, así que no había forma de empezar una medición. */}
      <div className="rejilla-barra">
        <BotonAtajos />
        <Tooltip texto="Añadir una línea de medición vacía">
          <button className="btn btn--sm" onClick={() => void anadir()}>
            <Plus size={14} aria-hidden="true" />
            Línea
          </button>
        </Tooltip>
        <select
          className="select select--sm"
          style={{ width: 'auto' }}
          aria-label="Añadir línea con fórmula"
          value=""
          onChange={(e) => {
            if (e.target.value) void anadir(e.target.value)
          }}
        >
          <option value="">Con fórmula…</option>
          {formulas.map((f) => (
            <option key={f.id} value={f.id}>
              {f.nombre}
            </option>
          ))}
        </select>
        <Tooltip texto="Crear, editar o borrar fórmulas de medición">
          <button
            className="btn btn--sm btn--solo-icono"
            aria-label="Gestionar fórmulas de medición"
            onClick={() => setGestionandoFormulas(true)}
          >
            <FunctionSquare size={14} aria-hidden="true" />
          </button>
        </Tooltip>
        {iaActiva && onLeerPlano && (
          <Tooltip texto="Extraer mediciones de un plano acotado con IA">
            <button className="btn btn--sm" onClick={onLeerPlano}>
              <Scan size={14} aria-hidden="true" />
              Leer plano
            </button>
          </Tooltip>
        )}
        <span className="rejilla-barra__estado">
          {pendiente ? <span className="muted">Sin guardar…</span> : <span className="muted">Guardado</span>}
        </span>
      </div>

      <ErrorNotice error={error} />

      <RejillaEditable
        filas={lineasVisibles}
        columnas={columnas}
        idDe={(l) => l.id}
        onEditar={(linea, columnaId, valor) => {
          // Las variables de la fórmula no se teclean en la rejilla: cada
          // fórmula tiene las suyas y no caben en columnas fijas.
          if (columnaId === 'formula' || columnaId === 'parcial') return
          const limpio = valor.trim() === '' ? null : valor.replace(',', '.')
          editarLocal(linea.id, { [columnaId]: limpio } as Partial<LineaMedicion>)
          encolar(linea, columnaId, limpio)
        }}
        onNuevaFila={() => anadir()}
        onEliminarFila={(l) => void eliminar(l)}
        onCopiar={copiarLineas}
        onPegar={pegar}
        onSoltarEn={() => pegar()}
        filtros={filtros}
        onFiltrar={(columnaId, valor) => setFiltros((f) => ({ ...f, [columnaId]: valor }))}
        vacia={
          filtrosActivos.length > 0 ? (
            <EmptyState title="Sin resultados">Nada coincide con los filtros.</EmptyState>
          ) : (
            <EmptyState title="Sin líneas de medición">
              Añade una línea, o mide con una fórmula.
            </EmptyState>
          )
        }
        acciones={(l) =>
          conFormula(l) ? (
            <>
              <VariablesFormula
                linea={l}
                variables={variablesDe(l)}
                onGuardar={async (valores) => {
                  await api.mediciones.update(l.id, { formula_valores: valores })
                  await cargar()
                  onCambio()
                }}
              />{' '}
              <Tooltip texto="Quitar la fórmula y medir por dimensiones">
                <button
                  className="btn btn--sm btn--solo-icono"
                  aria-label="Quitar la fórmula"
                  onClick={async () => {
                    await api.mediciones.update(l.id, { formula_id: null })
                    await cargar()
                    onCambio()
                  }}
                >
                  <FunctionSquare size={14} aria-hidden="true" />
                </button>
              </Tooltip>{' '}
              <Tooltip texto="Eliminar esta línea">
                <button
                  className="btn btn--sm btn--danger btn--solo-icono"
                  aria-label="Eliminar esta línea"
                  onClick={() => void eliminar(l)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            </>
          ) : (
            <Tooltip texto="Eliminar esta línea">
              <button
                className="btn btn--sm btn--danger btn--solo-icono"
                aria-label="Eliminar esta línea"
                onClick={() => void eliminar(l)}
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </Tooltip>
          )
        }
      />

      <div className="resumen-totales" style={{ marginTop: 'var(--sp-3)' }}>
        <div className="resumen-totales__fila is-total">
          <span>Medición total</span>
          <span className="resumen-totales__valor">
            {formatoImporte(detalle?.medicion ?? '0', 3)} {partida.unidad}
          </span>
        </div>
        <div className="resumen-totales__fila is-suave">
          <span>× {formatoImporte(detalle?.precio ?? '0')} €/{partida.unidad}</span>
          <span className="resumen-totales__valor">{formatoImporte(detalle?.importe ?? '0')} €</span>
        </div>
      </div>

      {gestionandoFormulas && (
        <FormulasModal
          onClose={() => setGestionandoFormulas(false)}
          onCambio={() => void api.formulasMedicion.list().then(setFormulas)}
        />
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

/** Botón que abre los valores de las variables de una línea con fórmula. */
function VariablesFormula({
  linea,
  variables,
  onGuardar,
}: {
  linea: LineaMedicion
  variables: string[]
  onGuardar: (valores: Record<string, string>) => Promise<void>
}) {
  const [abierto, setAbierto] = useState(false)
  const [valores, setValores] = useState<Record<string, string>>(() => {
    const iniciales: Record<string, string> = {}
    for (const v of variables) iniciales[v] = linea.formula_valores?.[v] ?? ''
    return iniciales
  })
  const [guardando, setGuardando] = useState(false)

  return (
    <span className="menu-acciones">
      <Tooltip texto="Valores de la fórmula">
        <button
          className="btn btn--sm"
          aria-label="Valores de la fórmula"
          onClick={() => setAbierto((v) => !v)}
        >
          <FunctionSquare size={14} aria-hidden="true" />
          Valores
        </button>
      </Tooltip>
      {abierto && (
        <div className="menu-acciones__lista" style={{ padding: 'var(--sp-3)', minWidth: 240 }}>
          <div className="field__label" style={{ marginBottom: 'var(--sp-2)' }}>
            {linea.formula_expresion}
          </div>
          {variables.map((v) => (
            <label key={v} className="field" style={{ marginBottom: 'var(--sp-2)' }}>
              <span className="field__label">{v}</span>
              <input
                className="input"
                type="number"
                step="any"
                value={valores[v] ?? ''}
                onChange={(e) => setValores((prev) => ({ ...prev, [v]: e.target.value }))}
              />
            </label>
          ))}
          <button
            className="btn btn--primary btn--sm"
            disabled={guardando}
            onClick={async () => {
              setGuardando(true)
              try {
                const limpios: Record<string, string> = {}
                for (const [k, val] of Object.entries(valores)) {
                  limpios[k] = val.trim() === '' ? '0' : val.replace(',', '.')
                }
                await onGuardar(limpios)
                setAbierto(false)
              } finally {
                setGuardando(false)
              }
            }}
          >
            {guardando ? 'Guardando…' : 'Aplicar'}
          </button>
        </div>
      )}
    </span>
  )
}
