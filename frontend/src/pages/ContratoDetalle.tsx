import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Save, Trash2, X } from 'lucide-react'

import { ContactosAsociados } from '../components/ContactosAsociados'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { NotasCrm } from '../components/NotasCrm'
import { Trazabilidad, cargarAsociadosDeObra } from '../components/Trazabilidad'
import { EmptyState, ErrorNotice, Field, ModalPantalla, Tooltip } from '../components/ui'
import { ETIQUETA_ESTADO_CONTRATO, ETIQUETA_TIPO_CONTRATO, api } from '../lib/api'
import type { ContratoResumen as Detalle, EstadoContrato } from '../lib/api'
import { useContextoContratos } from './Contratos'

export function ContratoDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoContratos()
  const [contrato, setContrato] = useState<Detalle | null>(null)
  const [borrador, setBorrador] = useState<Partial<Detalle>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setContrato(await api.contratos.get(id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/contratos')
  }

  if (error && !contrato) {
    return (
      <ModalPantalla title="Contrato" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!contrato) return null

  const valor = <K extends keyof Detalle>(campo: K): Detalle[K] =>
    (borrador[campo] ?? contrato[campo]) as Detalle[K]
  const cambiar = <K extends keyof Detalle>(campo: K, v: Detalle[K]) =>
    setBorrador((b) => ({ ...b, [campo]: v }))
  const hayCambios = Object.keys(borrador).length > 0

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.contratos.update(id, borrador)
      setBorrador({})
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar el contrato ${contrato!.codigo}?`)) return
    try {
      await api.contratos.remove(id)
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const pestanaDatos = (
    <div className="ficha-datos">
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <div className="form-grid">
            <Field label="Tipo">
              <input className="input" value={ETIQUETA_TIPO_CONTRATO[contrato.tipo]} disabled />
            </Field>
            <Field label="Obra">
              <Link to={`/obras/${contrato.obra_id}`}>Ver obra</Link>
            </Field>
            {contrato.presupuesto_id && (
              <Field label="Presupuesto que formaliza">
                <Link to={`/presupuestos/${contrato.presupuesto_id}`}>Ver presupuesto</Link>
              </Field>
            )}
            <Field label="Estado">
              <select
                className="select"
                value={valor('estado')}
                onChange={(e) => cambiar('estado', e.target.value as EstadoContrato)}
              >
                {Object.entries(ETIQUETA_ESTADO_CONTRATO).map(([clave, etiqueta]) => (
                  <option key={clave} value={clave}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Fecha de firma">
              <input
                className="input"
                type="date"
                value={valor('fecha_firma') ?? ''}
                onChange={(e) => cambiar('fecha_firma', e.target.value || null)}
              />
            </Field>
            <Field label="Fecha de inicio">
              <input
                className="input"
                type="date"
                value={valor('fecha_inicio') ?? ''}
                onChange={(e) => cambiar('fecha_inicio', e.target.value || null)}
              />
            </Field>
            <Field label="Fin previsto">
              <input
                className="input"
                type="date"
                value={valor('fecha_fin_prevista') ?? ''}
                onChange={(e) => cambiar('fecha_fin_prevista', e.target.value || null)}
              />
            </Field>
            <Field label="Importe" hint="Informativo, el desglose vive en el presupuesto">
              <input
                className="input"
                type="number"
                step="0.01"
                value={valor('importe') ?? ''}
                onChange={(e) => cambiar('importe', e.target.value || null)}
              />
            </Field>
            <Field label="Retención de garantía (%)">
              <input
                className="input"
                type="number"
                step="0.01"
                value={valor('retencion_garantia_pct')}
                onChange={(e) => cambiar('retencion_garantia_pct', e.target.value)}
              />
            </Field>
          </div>
          <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
            <Field ancho="doble" label="Notas">
              <textarea
                className="input"
                rows={3}
                value={valor('notas') ?? ''}
                onChange={(e) => cambiar('notas', e.target.value || null)}
              />
            </Field>
          </div>
        </div>

        <div className="form-actions form-actions--separadas">
          <Tooltip texto="Eliminar este contrato">
            <button className="btn btn--danger" onClick={() => void eliminar()}>
              <Trash2 size={16} aria-hidden="true" />
              Eliminar
            </button>
          </Tooltip>
          <span className="form-actions__grupo">
            <button className="btn" disabled={!hayCambios} onClick={() => setBorrador({})}>
              <X size={16} aria-hidden="true" />
              Descartar
            </button>
            <button
              className="btn btn--primary"
              disabled={!hayCambios || guardando}
              onClick={() => void guardar()}
            >
              {!guardando && <Save size={16} aria-hidden="true" />}
              {guardando ? 'Guardando…' : 'Guardar cambios'}
            </button>
          </span>
        </div>
      </div>

      {!contrato.presupuesto_id && (
        <EmptyState title="Sin presupuesto enlazado">
          Este contrato no tiene un presupuesto que lo formalice todavía.
        </EmptyState>
      )}
    </div>
  )

  const pestanas: PestanaFicha[] = [
    { id: 'datos', etiqueta: 'Datos', icono: 'datos', contenido: pestanaDatos },
    {
      id: 'contactos',
      etiqueta: 'Contactos',
      icono: 'contactos',
      contenido: <ContactosAsociados entidad="contrato" entidadId={id} />,
    },
    {
      id: 'crm',
      etiqueta: 'CRM',
      icono: 'crm',
      contenido: <NotasCrm entidad="contrato" entidadId={id} />,
    },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="contrato" entidadId={id} />,
    },
    {
      id: 'trazabilidad',
      etiqueta: 'Trazabilidad',
      icono: 'trazabilidad',
      contenido: (
        <Trazabilidad
          origen={[
            {
              tipo: 'tercero',
              etiqueta: contrato.tercero_razon_social,
              ruta: `/terceros/${contrato.cliente_id ?? contrato.proveedor_id}`,
              estadoEtiqueta: ETIQUETA_TIPO_CONTRATO[contrato.tipo],
            },
            ...(contrato.presupuesto_id
              ? [
                  {
                    tipo: 'presupuesto' as const,
                    etiqueta: 'Presupuesto que formaliza',
                    ruta: `/presupuestos/${contrato.presupuesto_id}`,
                  },
                ]
              : []),
          ]}
          cargarAsociados={() =>
            cargarAsociadosDeObra(contrato.obra_id, { tipo: 'contrato', id })
          }
        />
      ),
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.contratos.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {contrato.tercero_razon_social} <span className="table__code">{contrato.codigo}</span>
        </>
      }
      subtitulo={
        <p className="page-lead" style={{ marginBottom: 0 }}>
          Contrato de {ETIQUETA_TIPO_CONTRATO[contrato.tipo].toLowerCase()}
        </p>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}
