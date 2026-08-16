import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Checkbox, ErrorNotice, Field } from '../components/ui'
import { api } from '../lib/api'
import type { CampoLibreDefinicion, EntidadCampoLibre, TipoCampoLibre } from '../lib/api'
import { useToast } from '../toast'

const ETIQUETA_ENTIDAD: Record<EntidadCampoLibre, string> = {
  tercero: 'Terceros',
  producto: 'Productos',
  obra: 'Obras',
  presupuesto: 'Presupuestos',
  capitulo: 'Capítulos',
  partida: 'Partidas',
  linea_medicion: 'Líneas de medición',
  asignacion: 'Asignaciones de personal',
  parte_trabajo: 'Partes de trabajo',
}

const ENTIDADES = Object.keys(ETIQUETA_ENTIDAD) as EntidadCampoLibre[]

const ETIQUETA_TIPO: Record<TipoCampoLibre, string> = {
  texto: 'Texto',
  numero: 'Número',
  fecha: 'Fecha',
  booleano: 'Sí / No',
  select: 'Lista de opciones',
}

/** Autoservicio de definición de campos libres (Fase 21-22) — el admin de
 *  organización decide qué campos existen para cada tipo de registro, al
 *  estilo Dolibarr. Los valores en sí se editan desde la propia ficha de
 *  cada registro (ver `components/CamposLibres.tsx`), no aquí. */
export function AjustesCamposLibres() {
  const [entidad, setEntidad] = useState<EntidadCampoLibre>('tercero')
  const [definiciones, setDefiniciones] = useState<CampoLibreDefinicion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [creando, setCreando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setDefiniciones(await api.ajustes.camposLibres.list(entidad))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [entidad])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Campos libres</h1>
          <p className="page-lead">
            Campos propios de la cuenta sobre terceros, productos, obras, presupuestos y sus
            líneas — al estilo Dolibarr.
          </p>
        </div>
        <Link className="btn" to="/ajustes">
          Volver a Ajustes
        </Link>
      </div>

      <div className="pestanas" style={{ flexWrap: 'wrap' }}>
        {ENTIDADES.map((e) => (
          <button
            key={e}
            className={e === entidad ? 'pestanas__item is-activa' : 'pestanas__item'}
            onClick={() => setEntidad(e)}
          >
            {ETIQUETA_ENTIDAD[e]}
          </button>
        ))}
      </div>

      <div className="toolbar">
        <button className="btn btn--primary" onClick={() => setCreando(true)}>
          Nuevo campo
        </button>
      </div>

      <ErrorNotice error={error} />

      {creando && (
        <NuevoCampo
          entidad={entidad}
          onCancelar={() => setCreando(false)}
          onCreado={(definicion) => {
            setCreando(false)
            setDefiniciones((actual) => [...actual, definicion])
          }}
        />
      )}

      <div className="card" style={{ marginTop: 'var(--sp-3)' }}>
        {definiciones.length === 0 ? (
          <div className="dicc-fila">
            <div className="module-row__desc">Sin campos definidos todavía.</div>
          </div>
        ) : (
          definiciones.map((d) => (
            <FilaCampo
              key={d.id}
              entidad={entidad}
              definicion={d}
              onGuardada={(actualizada) =>
                setDefiniciones((actual) => actual.map((x) => (x.id === actualizada.id ? actualizada : x)))
              }
              onEliminada={() => setDefiniciones((actual) => actual.filter((x) => x.id !== d.id))}
            />
          ))
        )}
      </div>
    </>
  )
}

function NuevoCampo({
  entidad,
  onCancelar,
  onCreado,
}: {
  entidad: EntidadCampoLibre
  onCancelar: () => void
  onCreado: (definicion: CampoLibreDefinicion) => void
}) {
  const [clave, setClave] = useState('')
  const [etiqueta, setEtiqueta] = useState('')
  const [tipo, setTipo] = useState<TipoCampoLibre>('texto')
  const [opcionesTexto, setOpcionesTexto] = useState('')
  const [requerido, setRequerido] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const opciones = opcionesTexto
        .split(',')
        .map((o) => o.trim())
        .filter(Boolean)
      const definicion = await api.ajustes.camposLibres.create(entidad, {
        clave,
        etiqueta,
        tipo,
        opciones: tipo === 'select' ? opciones : [],
        requerido,
      })
      onCreado(definicion)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="card" style={{ padding: 'var(--sp-4)', marginTop: 'var(--sp-3)' }}>
      <ErrorNotice error={error} />
      <div className="form-grid">
        <Field label="Clave" hint="Identificador interno, no se puede cambiar luego">
          <input className="input" value={clave} onChange={(e) => setClave(e.target.value)} autoFocus />
        </Field>
        <Field label="Etiqueta">
          <input className="input" value={etiqueta} onChange={(e) => setEtiqueta(e.target.value)} />
        </Field>
        <Field label="Tipo">
          <select className="select" value={tipo} onChange={(e) => setTipo(e.target.value as TipoCampoLibre)}>
            {Object.entries(ETIQUETA_TIPO).map(([clave, etiqueta]) => (
              <option key={clave} value={clave}>
                {etiqueta}
              </option>
            ))}
          </select>
        </Field>
        {tipo === 'select' && (
          <Field label="Opciones" hint="Separadas por comas">
            <input
              className="input"
              value={opcionesTexto}
              onChange={(e) => setOpcionesTexto(e.target.value)}
              placeholder="Opción A, Opción B, Opción C"
            />
          </Field>
        )}
      </div>
      <div style={{ marginTop: 'var(--sp-3)' }}>
        <Checkbox label="Obligatorio" checked={requerido} onChange={setRequerido} />
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onCancelar}>
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={guardando || clave.trim() === '' || etiqueta.trim() === ''}
          onClick={() => void guardar()}
        >
          {guardando ? 'Creando…' : 'Crear'}
        </button>
      </div>
    </div>
  )
}

function FilaCampo({
  entidad,
  definicion,
  onGuardada,
  onEliminada,
}: {
  entidad: EntidadCampoLibre
  definicion: CampoLibreDefinicion
  onGuardada: (actualizada: CampoLibreDefinicion) => void
  onEliminada: () => void
}) {
  const { notificar } = useToast()
  const [etiqueta, setEtiqueta] = useState(definicion.etiqueta)
  const [activo, setActivo] = useState(definicion.activo)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cambiado = etiqueta !== definicion.etiqueta || activo !== definicion.activo

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const actualizada = await api.ajustes.camposLibres.update(entidad, definicion.id, { etiqueta, activo })
      onGuardada(actualizada)
      notificar(`«${actualizada.etiqueta}» guardado`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar el campo «${definicion.etiqueta}»? También se borran sus valores guardados.`))
      return
    try {
      await api.ajustes.camposLibres.eliminar(entidad, definicion.id)
      onEliminada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <div className="dicc-fila">
      <ErrorNotice error={error} />
      <span className="table__code dicc-fila__clave" title={definicion.clave}>
        {definicion.clave}
      </span>
      <input
        className="input dicc-fila__etiqueta"
        value={etiqueta}
        onChange={(e) => setEtiqueta(e.target.value)}
      />
      <span className="badge">{ETIQUETA_TIPO[definicion.tipo]}</span>
      {definicion.requerido && <span className="badge">obligatorio</span>}
      <Checkbox label="Activo" checked={activo} onChange={setActivo} />
      <button className="btn btn--sm" disabled={!cambiado || guardando} onClick={() => void guardar()}>
        {guardando ? 'Guardando…' : 'Guardar'}
      </button>
      <button className="btn btn--sm btn--danger" onClick={() => void eliminar()}>
        Eliminar
      </button>
    </div>
  )
}
