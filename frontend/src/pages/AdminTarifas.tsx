import { useCallback, useEffect, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Pencil, Plus, Trash2, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, ModalPantalla, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type { Module, Tarifa, TarifaModulo } from '../lib/api'
import { DescuentosCard } from './DescuentosCard'

export type ContextoTarifas = { onCambio: () => void }

export function useContextoTarifas() {
  return useOutletContext<ContextoTarifas>()
}

export function AdminTarifas() {
  const [items, setItems] = useState<Tarifa[]>([])
  const [error, setError] = useState<string | null>(null)
  const [tarifaDescuentos, setTarifaDescuentos] = useState('')

  const cargar = useCallback(async () => {
    try {
      const tarifas = await api.admin.tarifas.list()
      setItems(tarifas)
      setTarifaDescuentos((actual) => actual || tarifas[0]?.id || '')
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Tarifas</h1>
          <p className="page-lead">
            Planes de precio: cuánto cuesta cada módulo al mes y cada 1000 tokens de IA
            consumidos. Se asignan a las organizaciones desde su ficha.
          </p>
        </div>
        <Link className="btn btn--primary" to="nueva">
          <Plus size={16} aria-hidden="true" />
          Nueva tarifa
        </Link>
      </div>

      <ErrorNotice error={error} />

      {items.length === 0 ? (
        <EmptyState title="No hay tarifas todavía" />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Descripción</th>
                <th className="table__num">€ / 1000 tok. DeepSeek</th>
                <th className="table__num">€ / 1000 tok. Gemini</th>
                <th>Estado</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id}>
                  <td>
                    <Link className="table__link" to={`${t.id}`}>
                      {t.nombre}
                    </Link>
                  </td>
                  <td className="muted">{t.descripcion ?? '—'}</td>
                  <td className="table__num">{formatoImporte(t.precio_1000_tokens_deepseek, 4)}</td>
                  <td className="table__num">{formatoImporte(t.precio_1000_tokens_gemini, 4)}</td>
                  <td>
                    <span className={`chip ${t.activa ? 'chip--proveedor' : 'chip--inactivo'}`}>
                      {t.activa ? 'activa' : 'inactiva'}
                    </span>
                  </td>
                  <td className="table__actions">
                    <Link className="btn btn--sm" to={`${t.id}`}>
                      <Pencil size={14} aria-hidden="true" />
                      Editar
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {items.length > 0 && (
        <>
          <h2
            style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, margin: 'var(--sp-6) 0 var(--sp-3)' }}
          >
            Descuentos
          </h2>
          <p className="page-lead">
            Promoción general de una tarifa: se aplica a cualquier organización que la tenga
            asignada. Para un trato particular de una organización concreta, se gestiona desde
            su propia ficha.
          </p>
          {items.length > 1 && (
            <div className="form-grid" style={{ marginBottom: 'var(--sp-3)' }}>
              <Field label="Tarifa">
                <select
                  className="select"
                  value={tarifaDescuentos}
                  onChange={(e) => setTarifaDescuentos(e.target.value)}
                >
                  {items.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.nombre}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          )}
          {tarifaDescuentos && <DescuentosCard tarifaId={tarifaDescuentos} />}
        </>
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoTarifas} />
    </>
  )
}

/** Formulario de módulos por precio, compartido entre alta y edición: la
 *  única diferencia entre crear y editar una tarifa es de dónde salen los
 *  valores iniciales y qué llamada a la API se dispara al guardar. */
export function FormularioModulos({
  modulos,
  filas,
  onCambiar,
}: {
  modulos: Module[]
  filas: TarifaModulo[]
  onCambiar: (filas: TarifaModulo[]) => void
}) {
  function anadirFila() {
    const disponible = modulos.find((m) => !filas.some((f) => f.module_code === m.code))
    if (!disponible) return
    onCambiar([...filas, { module_code: disponible.code, precio_mensual: '0.00' }])
  }

  function editarFila(indice: number, cambios: Partial<TarifaModulo>) {
    onCambiar(filas.map((f, i) => (i !== indice ? f : { ...f, ...cambios })))
  }

  function quitarFila(indice: number) {
    onCambiar(filas.filter((_, i) => i !== indice))
  }

  return (
    <>
      <div className="form-section__title" style={{ marginTop: 'var(--sp-4)' }}>
        Precio mensual por módulo
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Módulo</th>
              <th className="table__num">€ / mes</th>
              <th className="table__actions" />
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, i) => (
              <tr key={fila.module_code}>
                <td>
                  <select
                    className="select"
                    value={fila.module_code}
                    onChange={(e) => editarFila(i, { module_code: e.target.value })}
                  >
                    {modulos.map((m) => (
                      <option key={m.code} value={m.code}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    className="input"
                    value={fila.precio_mensual}
                    onChange={(e) => editarFila(i, { precio_mensual: e.target.value })}
                  />
                </td>
                <td className="table__actions">
                  <button
                    className="btn btn--sm btn--danger btn--solo-icono"
                    onClick={() => quitarFila(i)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button className="btn btn--sm" style={{ marginTop: 'var(--sp-2)' }} onClick={anadirFila}>
        <Plus size={14} aria-hidden="true" />
        Añadir módulo
      </button>
    </>
  )
}

export function TarifaCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoTarifas()
  const [modulos, setModulos] = useState<Module[]>([])
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [precioDeepseek, setPrecioDeepseek] = useState('0.0000')
  const [precioGemini, setPrecioGemini] = useState('0.0000')
  const [filasModulos, setFilasModulos] = useState<TarifaModulo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    void api.modules().then(setModulos)
  }, [])

  function cerrar() {
    navigate('/admin/tarifas')
  }

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.tarifas.create({
        nombre,
        descripcion: descripcion || null,
        precio_1000_tokens_deepseek: precioDeepseek,
        precio_1000_tokens_gemini: precioGemini,
        modulos: filasModulos,
      })
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title="Nueva tarifa" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <div className="form-grid">
            <Field label="Nombre">
              <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus />
            </Field>
            <Field label="Descripción" hint="Opcional">
              <input
                className="input"
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
              />
            </Field>
            <Field label="€ por 1000 tokens DeepSeek">
              <input
                className="input"
                value={precioDeepseek}
                onChange={(e) => setPrecioDeepseek(e.target.value)}
              />
            </Field>
            <Field label="€ por 1000 tokens Gemini">
              <input
                className="input"
                value={precioGemini}
                onChange={(e) => setPrecioGemini(e.target.value)}
              />
            </Field>
          </div>
          <FormularioModulos modulos={modulos} filas={filasModulos} onCambiar={setFilasModulos} />
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={guardando || nombre.trim() === ''}
            onClick={() => void guardar()}
          >
            {!guardando && <Plus size={16} aria-hidden="true" />}
            {guardando ? 'Creando…' : 'Crear tarifa'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
