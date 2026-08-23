import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Plus, Save, Trash2, Upload } from 'lucide-react'

import { EditorHtml } from '../components/EditorHtml'
import { ErrorNotice, Field } from '../components/ui'
import { api, urlBlob } from '../lib/api'
import type { Empresa, EmpresasCuenta } from '../lib/api'
import { useToast } from '../toast'

const ESTILO_SUBTITULO: CSSProperties = {
  fontSize: 'var(--fs-sm)',
  fontWeight: 650,
  textTransform: 'uppercase',
  letterSpacing: '0.03em',
  color: 'var(--c-text-muted)',
  margin: '0 0 var(--sp-3)',
  paddingTop: 'var(--sp-5)',
  borderTop: '1px solid var(--c-border)',
}

/** Datos básicos, logo y política de privacidad de cada empresa (CIF) de la
 *  cuenta (Fase 40/41) — hasta 2, en pestañas: cualquiera de las dos se edita
 *  aquí mismo, sin depender del selector de organización de la barra
 *  superior. Disponibles como claves (`organizacion.*`) en las plantillas
 *  Word de presupuesto. */
export function AjustesEmpresa() {
  const { notificar } = useToast()
  const [empresas, setEmpresas] = useState<EmpresasCuenta | null>(null)
  const [pestanaId, setPestanaId] = useState<string | null>(null)
  const [empresa, setEmpresa] = useState<Empresa | null>(null)
  const [logoUrl, setLogoUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [subiendoLogo, setSubiendoLogo] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const [nuevoNombre, setNuevoNombre] = useState('')
  const [nuevoCif, setNuevoCif] = useState('')
  const [creandoEmpresa, setCreandoEmpresa] = useState(false)

  const cargarLista = useCallback(async () => {
    try {
      const listado = await api.ajustes.empresas.list()
      setEmpresas(listado)
      setPestanaId((actual) => actual ?? listado.empresas.find((e) => e.es_la_actual)?.id ?? listado.empresas[0]?.id ?? null)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargarLista()
  }, [cargarLista])

  useEffect(() => {
    if (!pestanaId) {
      setEmpresa(null)
      return
    }
    let cancelado = false
    void api.ajustes.empresas
      .get(pestanaId)
      .then((datos) => {
        if (!cancelado) setEmpresa(datos)
      })
      .catch((err) => {
        if (!cancelado) setError(err instanceof Error ? err.message : 'Error desconocido')
      })
    return () => {
      cancelado = true
    }
  }, [pestanaId])

  useEffect(() => {
    if (!empresa?.tiene_logo || !pestanaId) {
      setLogoUrl(null)
      return
    }
    let cancelado = false
    let url: string | null = null
    void urlBlob(api.ajustes.empresas.logoUrl(pestanaId)).then((u) => {
      if (cancelado) {
        URL.revokeObjectURL(u)
        return
      }
      url = u
      setLogoUrl(u)
    })
    return () => {
      cancelado = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [empresa?.tiene_logo, pestanaId])

  function campo<K extends keyof Empresa>(clave: K, valor: Empresa[K]) {
    setEmpresa((actual) => (actual ? { ...actual, [clave]: valor } : actual))
  }

  async function guardar() {
    if (!empresa || !pestanaId) return
    setGuardando(true)
    setError(null)
    try {
      const actualizada = await api.ajustes.empresas.actualizar(pestanaId, {
        name: empresa.name,
        cif: empresa.cif,
        direccion: empresa.direccion,
        codigo_postal: empresa.codigo_postal,
        ciudad: empresa.ciudad,
        provincia: empresa.provincia,
        telefono: empresa.telefono,
        email: empresa.email,
        web: empresa.web,
        linkedin: empresa.linkedin,
        instagram: empresa.instagram,
        facebook: empresa.facebook,
        twitter: empresa.twitter,
        politica_privacidad: empresa.politica_privacidad,
      })
      setEmpresa(actualizada)
      setEmpresas((actual) =>
        actual
          ? { ...actual, empresas: actual.empresas.map((e) => (e.id === pestanaId ? { ...e, name: actualizada.name, cif: actualizada.cif } : e)) }
          : actual,
      )
      notificar('Datos de la empresa guardados')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function subirLogo(archivo: File | null) {
    if (!archivo || !pestanaId) return
    setSubiendoLogo(true)
    setError(null)
    try {
      setEmpresa(await api.ajustes.empresas.subirLogo(pestanaId, archivo))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setSubiendoLogo(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function eliminarLogo() {
    if (!pestanaId) return
    try {
      setEmpresa(await api.ajustes.empresas.eliminarLogo(pestanaId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function crearEmpresa() {
    if (!nuevoNombre.trim()) {
      setError('El nombre es obligatorio')
      return
    }
    setCreandoEmpresa(true)
    setError(null)
    try {
      const creada = await api.ajustes.empresas.crear({
        name: nuevoNombre.trim(),
        cif: nuevoCif.trim() || null,
      })
      await cargarLista()
      setPestanaId(creada.id)
      setNuevoNombre('')
      setNuevoCif('')
      notificar('Empresa creada — ya puedes cambiar a ella desde el selector de la barra superior')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCreandoEmpresa(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Empresa</h1>
          <p className="page-lead">
            Datos básicos, logo y política de privacidad de cada empresa de la cuenta — se usan en
            cabeceras de documentos y están disponibles como claves (<code>organizacion.*</code>) en
            las plantillas Word de presupuesto.
          </p>
        </div>
        <Link className="btn" to="/ajustes">
          <ArrowLeft size={16} aria-hidden="true" />
          Volver a Ajustes
        </Link>
      </div>

      <ErrorNotice error={error} />

      {empresas && empresas.empresas.length > 1 && (
        <div className="ficha-pestanas" role="tablist" style={{ marginBottom: 'var(--sp-4)' }}>
          {empresas.empresas.map((e) => (
            <button
              key={e.id}
              type="button"
              role="tab"
              aria-selected={e.id === pestanaId}
              className={e.id === pestanaId ? 'ficha-pestana ficha-pestana--activa' : 'ficha-pestana'}
              onClick={() => setPestanaId(e.id)}
            >
              {e.name}
              {e.es_la_actual && <span className="badge badge--info" style={{ marginLeft: 'var(--sp-2)' }}>Actual</span>}
            </button>
          ))}
        </div>
      )}

      {empresa && (
        <>
          <div className="card" style={{ padding: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', fontWeight: 650, margin: '0 0 var(--sp-4)' }}>Logo</h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-4)' }}>
              <div
                style={{
                  width: 160,
                  height: 80,
                  border: '1px dashed var(--c-border)',
                  borderRadius: 'var(--radius)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                  background: 'var(--c-surface-2)',
                }}
              >
                {logoUrl ? (
                  <img src={logoUrl} alt="Logo de la empresa" style={{ maxWidth: '100%', maxHeight: '100%' }} />
                ) : (
                  <span className="muted" style={{ fontSize: 'var(--fs-xs)' }}>
                    Sin logo
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                <button className="btn btn--sm" disabled={subiendoLogo} onClick={() => inputRef.current?.click()}>
                  <Upload size={14} aria-hidden="true" />
                  {subiendoLogo ? 'Subiendo…' : empresa.tiene_logo ? 'Cambiar logo' : 'Subir logo'}
                </button>
                {empresa.tiene_logo && (
                  <button className="btn btn--sm btn--danger" onClick={() => void eliminarLogo()}>
                    <Trash2 size={14} aria-hidden="true" />
                    Quitar
                  </button>
                )}
                <input
                  ref={inputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/svg+xml"
                  style={{ display: 'none' }}
                  onChange={(e) => void subirLogo(e.target.files?.[0] ?? null)}
                />
              </div>
            </div>
          </div>

          <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', fontWeight: 650, margin: '0 0 var(--sp-4)' }}>Identidad</h2>
            <div className="form-grid" style={{ marginBottom: 'var(--sp-6)' }}>
              <Field ancho="doble" label="Nombre">
                <input className="input" value={empresa.name} onChange={(e) => campo('name', e.target.value)} />
              </Field>
              <Field label="CIF">
                <input className="input" value={empresa.cif ?? ''} onChange={(e) => campo('cif', e.target.value)} />
              </Field>
            </div>

            <h3 style={ESTILO_SUBTITULO}>Dirección</h3>
            <div className="form-grid" style={{ marginBottom: 'var(--sp-6)' }}>
              <Field ancho="doble" label="Dirección">
                <input
                  className="input"
                  value={empresa.direccion ?? ''}
                  onChange={(e) => campo('direccion', e.target.value)}
                />
              </Field>
              <Field label="Código postal">
                <input
                  className="input"
                  value={empresa.codigo_postal ?? ''}
                  onChange={(e) => campo('codigo_postal', e.target.value)}
                />
              </Field>
              <Field label="Ciudad">
                <input className="input" value={empresa.ciudad ?? ''} onChange={(e) => campo('ciudad', e.target.value)} />
              </Field>
              <Field label="Provincia">
                <input
                  className="input"
                  value={empresa.provincia ?? ''}
                  onChange={(e) => campo('provincia', e.target.value)}
                />
              </Field>
            </div>

            <h3 style={ESTILO_SUBTITULO}>Contacto</h3>
            <div className="form-grid" style={{ marginBottom: 'var(--sp-6)' }}>
              <Field label="Teléfono">
                <input
                  className="input"
                  value={empresa.telefono ?? ''}
                  onChange={(e) => campo('telefono', e.target.value)}
                />
              </Field>
              <Field ancho="doble" label="Email">
                <input className="input" value={empresa.email ?? ''} onChange={(e) => campo('email', e.target.value)} />
              </Field>
              <Field ancho="doble" label="Web">
                <input
                  className="input"
                  value={empresa.web ?? ''}
                  onChange={(e) => campo('web', e.target.value)}
                  placeholder="https://"
                />
              </Field>
            </div>

            <h3 style={ESTILO_SUBTITULO}>Redes sociales</h3>
            <div className="form-grid">
              <Field ancho="doble" label="LinkedIn">
                <input
                  className="input"
                  value={empresa.linkedin ?? ''}
                  onChange={(e) => campo('linkedin', e.target.value)}
                  placeholder="https://linkedin.com/company/…"
                />
              </Field>
              <Field ancho="doble" label="Instagram">
                <input
                  className="input"
                  value={empresa.instagram ?? ''}
                  onChange={(e) => campo('instagram', e.target.value)}
                  placeholder="https://instagram.com/…"
                />
              </Field>
              <Field ancho="doble" label="Facebook">
                <input
                  className="input"
                  value={empresa.facebook ?? ''}
                  onChange={(e) => campo('facebook', e.target.value)}
                  placeholder="https://facebook.com/…"
                />
              </Field>
              <Field ancho="doble" label="X / Twitter">
                <input
                  className="input"
                  value={empresa.twitter ?? ''}
                  onChange={(e) => campo('twitter', e.target.value)}
                  placeholder="https://x.com/…"
                />
              </Field>
            </div>
          </div>

          <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', fontWeight: 650, margin: '0 0 var(--sp-4)' }}>
              Política de privacidad
            </h2>
            <div style={{ height: 320 }}>
              <EditorHtml
                value={empresa.politica_privacidad ?? ''}
                onChange={(html) => campo('politica_privacidad', html)}
                placeholder="Sin política de privacidad todavía — escribe aquí…"
              />
            </div>
          </div>

          {/* Una sola barra para las tres tarjetas de arriba (logo, datos y
              política): todas se guardan con el mismo botón. */}
          <div className="card" style={{ marginTop: 'var(--sp-4)' }}>
            <div className="form-actions">
              <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
                <Save size={16} aria-hidden="true" />
                {guardando ? 'Guardando…' : 'Guardar'}
              </button>
            </div>
          </div>
        </>
      )}

      {empresas?.puede_crear && (
        <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-5)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', fontWeight: 650, margin: '0 0 var(--sp-4)' }}>Crear otra empresa</h2>
          <div className="form-grid">
            <Field ancho="doble" label="Nombre">
              <input className="input" value={nuevoNombre} onChange={(e) => setNuevoNombre(e.target.value)} />
            </Field>
            <Field label="CIF">
              <input className="input" value={nuevoCif} onChange={(e) => setNuevoCif(e.target.value)} />
            </Field>
          </div>
          {/* Fila simple, no `.form-actions`: esta tarjeta ya lleva su propio
              padding, y esa clase trae el suyo más un borde superior — se
              vería una caja dentro de otra. */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--sp-4)' }}>
            <button className="btn btn--primary" disabled={creandoEmpresa} onClick={() => void crearEmpresa()}>
              <Plus size={16} aria-hidden="true" />
              {creandoEmpresa ? 'Creando…' : 'Crear empresa'}
            </button>
          </div>
        </div>
      )}
    </>
  )
}
