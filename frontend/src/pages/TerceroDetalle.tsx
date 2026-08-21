import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Plus, Save, Trash2, X } from 'lucide-react'

import { CamposLibres } from '../components/CamposLibres'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { NotasCrm } from '../components/NotasCrm'
import { Checkbox, ErrorNotice, Field, Modal, ModalPantalla, EmptyState, Tooltip } from '../components/ui'
import { api } from '../lib/api'
import type { Contacto, FormaPago, TerceroDetalle as Detalle } from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'
import { useContextoTerceros } from './Terceros'

export function TerceroDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoTerceros()
  const [tercero, setTercero] = useState<Detalle | null>(null)
  const [borrador, setBorrador] = useState<Partial<Detalle>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [nuevoContacto, setNuevoContacto] = useState(false)
  const paises = useDiccionario('pais')
  const formasPago = useDiccionario('forma_pago')
  const provincias = useDiccionario('provincia')
  const formasJuridicas = useDiccionario('forma_juridica')
  const retenciones = useDiccionario('retencion')

  const cargar = useCallback(async () => {
    try {
      const datos = await api.terceros.get(id)
      setTercero(datos)
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
    navigate('/terceros')
  }

  if (error && !tercero) {
    return (
      <ModalPantalla title="Tercero" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!tercero) return null

  const valor = <K extends keyof Detalle>(campo: K): Detalle[K] =>
    (borrador[campo] ?? tercero[campo]) as Detalle[K]
  const cambiar = <K extends keyof Detalle>(campo: K, v: Detalle[K]) =>
    setBorrador((b) => ({ ...b, [campo]: v }))
  const hayCambios = Object.keys(borrador).length > 0

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.terceros.update(id, borrador)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar «${tercero!.razon_social}»? No se puede deshacer.`)) return
    try {
      await api.terceros.remove(id)
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
          <div className="form-section__title">Identificación</div>
          <div className="form-grid">
            <Field label="Razón social">
              <input
                className="input"
                value={valor('razon_social')}
                onChange={(e) => cambiar('razon_social', e.target.value)}
              />
            </Field>
            <Field label="Nombre comercial">
              <input
                className="input"
                value={valor('nombre_comercial') ?? ''}
                onChange={(e) => cambiar('nombre_comercial', e.target.value || null)}
              />
            </Field>
            <Field label="NIF / CIF">
              <input
                className="input"
                value={valor('nif') ?? ''}
                onChange={(e) => cambiar('nif', e.target.value || null)}
              />
            </Field>
            <Field label="Tipo de persona">
              <select
                className="select"
                value={valor('tipo_persona')}
                onChange={(e) => cambiar('tipo_persona', e.target.value as Detalle['tipo_persona'])}
              >
                <option value="juridica">Jurídica</option>
                <option value="fisica">Física</option>
              </select>
            </Field>
            <Field label="Forma jurídica">
              <select
                className="select"
                value={valor('forma_juridica') ?? ''}
                onChange={(e) => cambiar('forma_juridica', e.target.value || null)}
              >
                <option value="">Sin definir</option>
                {formasJuridicas.map((f) => (
                  <option key={f.clave} value={f.clave}>
                    {f.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div style={{ display: 'flex', gap: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
            <Checkbox
              label="Cliente"
              checked={valor('es_cliente')}
              onChange={(v) => cambiar('es_cliente', v)}
            />
            <Checkbox
              label="Proveedor"
              checked={valor('es_proveedor')}
              onChange={(v) => cambiar('es_proveedor', v)}
            />
            <Checkbox
              label="Subcontratista"
              checked={valor('es_subcontratista')}
              onChange={(v) => cambiar('es_subcontratista', v)}
            />
            <Checkbox
              label="Activo"
              checked={valor('activo')}
              onChange={(v) => cambiar('activo', v)}
            />
          </div>
        </div>

        <div className="form-section">
          <div className="form-section__title">Contacto y domicilio</div>
          <div className="form-grid">
            <Field label="Email">
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
            <Field label="Dirección">
              <input
                className="input"
                value={valor('direccion') ?? ''}
                onChange={(e) => cambiar('direccion', e.target.value || null)}
              />
            </Field>
            <Field label="Código postal">
              <input
                className="input"
                value={valor('codigo_postal') ?? ''}
                onChange={(e) => cambiar('codigo_postal', e.target.value || null)}
              />
            </Field>
            <Field label="Población">
              <input
                className="input"
                value={valor('ciudad') ?? ''}
                onChange={(e) => cambiar('ciudad', e.target.value || null)}
              />
            </Field>
            <Field label="Provincia">
              <select
                className="select"
                value={valor('provincia') ?? ''}
                onChange={(e) => cambiar('provincia', e.target.value || null)}
              >
                <option value="">Sin definir</option>
                {provincias.map((p) => (
                  <option key={p.clave} value={p.etiqueta}>
                    {p.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="País">
              <select
                className="select"
                value={valor('pais')}
                onChange={(e) => cambiar('pais', e.target.value)}
              >
                {paises.map((p) => (
                  <option key={p.clave} value={p.clave}>
                    {p.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </div>

        <div className="form-section">
          <div className="form-section__title">Cobros y pagos</div>
          <div className="form-grid">
            <Field label="Forma de pago">
              <select
                className="select"
                value={valor('forma_pago') ?? ''}
                onChange={(e) =>
                  cambiar('forma_pago', (e.target.value || null) as FormaPago | null)
                }
              >
                <option value="">Sin definir</option>
                {formasPago.map((f) => (
                  <option key={f.clave} value={f.clave}>
                    {f.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Días de pago">
              <input
                className="input"
                type="number"
                value={valor('dias_pago') ?? ''}
                onChange={(e) =>
                  cambiar('dias_pago', e.target.value === '' ? null : Number(e.target.value))
                }
              />
            </Field>
            <Field label="IBAN">
              <input
                className="input"
                value={valor('iban') ?? ''}
                onChange={(e) => cambiar('iban', e.target.value || null)}
              />
            </Field>
          </div>
        </div>

        <div className="form-section">
          <div className="form-section__title">Régimen fiscal y acreditación</div>
          <p className="form-section__note">
            La inversión del sujeto pasivo (art. 84.Uno.2.º f LIVA) es lo habitual en ejecución
            de obra subcontratada: la factura va sin IVA. El REA (Ley 32/2006) es obligatorio
            para subcontratar en construcción y caduca.
          </p>
          <div className="form-grid">
            <Field label="Retención IRPF (%)" hint="Sugerencias en la lista, pero admite cualquier valor">
              <input
                className="input"
                type="number"
                step="0.01"
                list="retenciones-sugeridas"
                value={valor('irpf_retencion') ?? ''}
                onChange={(e) => cambiar('irpf_retencion', e.target.value || null)}
              />
              <datalist id="retenciones-sugeridas">
                {retenciones.map((r) => (
                  <option key={r.clave} value={r.valor ?? ''}>
                    {r.etiqueta}
                  </option>
                ))}
              </datalist>
            </Field>
            <Field label="Nº REA">
              <input
                className="input"
                value={valor('rea_numero') ?? ''}
                onChange={(e) => cambiar('rea_numero', e.target.value || null)}
              />
            </Field>
            <Field label="Caducidad del REA">
              <input
                className="input"
                type="date"
                value={valor('rea_caducidad') ?? ''}
                onChange={(e) => cambiar('rea_caducidad', e.target.value || null)}
              />
            </Field>
          </div>
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <Checkbox
              label="Inversión del sujeto pasivo"
              checked={valor('inversion_sujeto_pasivo')}
              onChange={(v) => cambiar('inversion_sujeto_pasivo', v)}
            />
          </div>
        </div>

        <div className="form-actions">
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
        </div>
      </div>

      <CamposLibres entidad="tercero" entidadId={id} />
    </>
  )

  const pestanaContactos = (
    <>
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          Personas con las que se trata en esta empresa.
        </p>
        <Tooltip texto="Añadir una persona de contacto">
          <button className="btn" onClick={() => setNuevoContacto(true)}>
            <Plus size={16} aria-hidden="true" />
            Añadir contacto
          </button>
        </Tooltip>
      </div>

      <div className="table-wrap">
        {tercero.contactos.length === 0 ? (
          <EmptyState title="Sin contactos">
            Añade las personas con las que tratas en esta empresa.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Cargo</th>
                <th>Email</th>
                <th>Teléfono</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {tercero.contactos.map((c) => (
                <FilaContacto key={c.id} contacto={c} onCambio={cargar} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {nuevoContacto && (
        <NuevoContactoModal
          terceroId={id}
          onClose={() => setNuevoContacto(false)}
          onCreado={() => {
            setNuevoContacto(false)
            void cargar()
          }}
        />
      )}
    </>
  )

  const pestanas: PestanaFicha[] = [
    { id: 'datos', etiqueta: 'Datos', icono: 'datos', contenido: pestanaDatos },
    { id: 'contactos', etiqueta: 'Contactos', icono: 'contactos', contenido: pestanaContactos },
    { id: 'crm', etiqueta: 'CRM', icono: 'crm', contenido: <NotasCrm entidad="tercero" entidadId={id} /> },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="tercero" entidadId={id} />,
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.terceros.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {tercero.razon_social} <span className="table__code">{tercero.codigo}</span>
        </>
      }
      subtitulo={
        <p className="page-lead" style={{ marginBottom: 0 }}>
          Origen del dato: {tercero.origen_dato}
        </p>
      }
      acciones={
        <Tooltip texto="Eliminar este tercero">
          <button className="btn btn--danger" onClick={() => void eliminar()}>
            <Trash2 size={16} aria-hidden="true" />
            Eliminar
          </button>
        </Tooltip>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}

function FilaContacto({ contacto, onCambio }: { contacto: Contacto; onCambio: () => void }) {
  async function eliminar() {
    if (!window.confirm(`¿Eliminar el contacto «${contacto.nombre}»?`)) return
    await api.contactos.remove(contacto.id)
    onCambio()
  }
  return (
    <tr>
      <td>
        {contacto.tratamiento && `${contacto.tratamiento} `}
        {contacto.nombre} {contacto.apellidos ?? ''}
        {contacto.es_principal && <span className="chip chip--cliente"> principal</span>}
      </td>
      <td>{contacto.cargo ?? <span className="muted">—</span>}</td>
      <td>{contacto.email ?? <span className="muted">—</span>}</td>
      <td>{contacto.telefono ?? contacto.movil ?? <span className="muted">—</span>}</td>
      <td className="table__actions">
        <button className="btn btn--sm btn--danger" onClick={() => void eliminar()}>
          <Trash2 size={14} aria-hidden="true" />
          Eliminar
        </button>
      </td>
    </tr>
  )
}

function NuevoContactoModal({
  terceroId,
  onClose,
  onCreado,
}: {
  terceroId: string
  onClose: () => void
  onCreado: () => void
}) {
  const tratamientos = useDiccionario('tratamiento')
  const cargos = useDiccionario('cargo')
  const [tratamiento, setTratamiento] = useState('')
  const [nombre, setNombre] = useState('')
  const [apellidos, setApellidos] = useState('')
  const [cargo, setCargo] = useState('')
  const [email, setEmail] = useState('')
  const [telefono, setTelefono] = useState('')
  const [esPrincipal, setEsPrincipal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    setError(null)
    try {
      await api.contactos.create({
        tercero_id: terceroId,
        tratamiento: tratamiento || null,
        nombre,
        apellidos: apellidos || null,
        cargo: cargo || null,
        email: email || null,
        telefono: telefono || null,
        es_principal: esPrincipal,
      })
      onCreado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Nuevo contacto" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field label="Tratamiento">
            <select className="select" value={tratamiento} onChange={(e) => setTratamiento(e.target.value)}>
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
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Apellidos">
            <input
              className="input"
              value={apellidos}
              onChange={(e) => setApellidos(e.target.value)}
            />
          </Field>
          <Field label="Cargo">
            <select className="select" value={cargo} onChange={(e) => setCargo(e.target.value)}>
              <option value="">Sin definir</option>
              {cargos.map((c) => (
                <option key={c.clave} value={c.etiqueta}>
                  {c.etiqueta}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Email">
            <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Teléfono">
            <input
              className="input"
              value={telefono}
              onChange={(e) => setTelefono(e.target.value)}
            />
          </Field>
        </div>
        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Checkbox label="Contacto principal" checked={esPrincipal} onChange={setEsPrincipal} />
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={nombre.trim() === ''}
          onClick={() => void guardar()}
        >
          <Plus size={16} aria-hidden="true" />
          Crear
        </button>
      </div>
    </Modal>
  )
}
