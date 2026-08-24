import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Save, Trash2, X } from 'lucide-react'

import { Apariciones } from '../components/Apariciones'
import { CamposLibres } from '../components/CamposLibres'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { NotasCrm } from '../components/NotasCrm'
import { Checkbox, ErrorNotice, Field, ModalPantalla, Tooltip } from '../components/ui'
import { api } from '../lib/api'
import type { Contacto } from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'
import { useContextoContactos } from './Contactos'

/** Ficha propia de un contacto (Fase 49) — hasta ahora una persona solo se
 *  veía como una fila dentro de la ficha de su tercero, sin forma de
 *  editarla ni de verle nada más. Mismo esqueleto que `TerceroDetalle`:
 *  borrador/valor/cambiar para el formulario, campos libres embebidos al
 *  final de Datos, y CRM/Documentos/Apariciones/Historial como pestañas. */
export function ContactoDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoContactos()
  const [contacto, setContacto] = useState<Contacto | null>(null)
  const [borrador, setBorrador] = useState<Partial<Contacto>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const tratamientos = useDiccionario('tratamiento')
  const cargos = useDiccionario('cargo')

  const cargar = useCallback(async () => {
    try {
      const datos = await api.contactos.get(id)
      setContacto(datos)
      setBorrador({})
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/contactos')
  }

  if (error && !contacto) {
    return (
      <ModalPantalla title="Contacto" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!contacto) return null

  const valor = <K extends keyof Contacto>(campo: K): Contacto[K] =>
    (borrador[campo] ?? contacto[campo]) as Contacto[K]
  const cambiar = <K extends keyof Contacto>(campo: K, v: Contacto[K]) =>
    setBorrador((b) => ({ ...b, [campo]: v }))
  const hayCambios = Object.keys(borrador).length > 0

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.contactos.update(id, borrador)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar el contacto «${contacto!.nombre}»? No se puede deshacer.`)) return
    try {
      await api.contactos.remove(id)
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const pestanaDatos = (
    <>
      <ErrorNotice error={error} />

      <div className="card">
        <div className="form-section">
          <div className="form-section__title">Datos personales</div>
          <div className="form-grid">
            <Field label="Tratamiento">
              <select
                className="select"
                value={valor('tratamiento') ?? ''}
                onChange={(e) => cambiar('tratamiento', e.target.value || null)}
              >
                <option value="">Sin definir</option>
                {tratamientos.map((t) => (
                  <option key={t.clave} value={t.clave}>
                    {t.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Nombre">
              <input
                className="input"
                value={valor('nombre')}
                onChange={(e) => cambiar('nombre', e.target.value)}
              />
            </Field>
            <Field label="Apellidos">
              <input
                className="input"
                value={valor('apellidos') ?? ''}
                onChange={(e) => cambiar('apellidos', e.target.value || null)}
              />
            </Field>
            <Field label="Cargo">
              <select
                className="select"
                value={valor('cargo') ?? ''}
                onChange={(e) => cambiar('cargo', e.target.value || null)}
              >
                <option value="">Sin definir</option>
                {cargos.map((c) => (
                  <option key={c.clave} value={c.etiqueta}>
                    {c.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Empresa">
              {contacto.tercero_id ? (
                <Link className="btn btn--sm" to={`/terceros/${contacto.tercero_id}`}>
                  Ver ficha
                </Link>
              ) : (
                <span className="muted">Contacto suelto, sin empresa</span>
              )}
            </Field>
          </div>
          <div style={{ display: 'flex', gap: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
            <Checkbox
              label="Contacto principal"
              checked={valor('es_principal')}
              onChange={(v) => cambiar('es_principal', v)}
            />
            <Checkbox label="Activo" checked={valor('activo')} onChange={(v) => cambiar('activo', v)} />
          </div>
        </div>

        <div className="form-section">
          <div className="form-section__title">Contacto</div>
          <div className="form-grid">
            <Field ancho="doble" label="Email">
              <input
                className="input"
                value={valor('email') ?? ''}
                onChange={(e) => cambiar('email', e.target.value || null)}
              />
            </Field>
            <Field label="Teléfono">
              <input
                className="input"
                value={valor('telefono') ?? ''}
                onChange={(e) => cambiar('telefono', e.target.value || null)}
              />
            </Field>
            <Field label="Móvil">
              <input
                className="input"
                value={valor('movil') ?? ''}
                onChange={(e) => cambiar('movil', e.target.value || null)}
              />
            </Field>
            <Field ancho="completo" label="Notas">
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
          <Tooltip texto="Eliminar este contacto">
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

      <CamposLibres entidad="contacto" entidadId={id} />
    </>
  )

  const pestanas: PestanaFicha[] = [
    { id: 'datos', etiqueta: 'Datos', icono: 'datos', contenido: pestanaDatos },
    { id: 'crm', etiqueta: 'CRM', icono: 'crm', contenido: <NotasCrm entidad="contacto" entidadId={id} /> },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="contacto" entidadId={id} />,
    },
    {
      id: 'apariciones',
      etiqueta: 'Apariciones',
      icono: 'apariciones',
      contenido: <Apariciones cargar={() => api.contactos.apariciones(id)} />,
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.contactos.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {contacto.tratamiento && `${contacto.tratamiento} `}
          {contacto.nombre} {contacto.apellidos ?? ''}
        </>
      }
      subtitulo={
        contacto.cargo ? (
          <p className="page-lead" style={{ marginBottom: 0 }}>
            {contacto.cargo}
          </p>
        ) : undefined
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}
