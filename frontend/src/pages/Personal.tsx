import { useCallback, useEffect, useState } from 'react'
import { Pencil, Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal, Pager, Tooltip, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type { Personal as PersonalT } from '../lib/api'

const LIMITE = 25

export function Personal() {
  const [items, setItems] = useState<PersonalT[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [soloActivos, setSoloActivos] = useState(true)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creando, setCreando] = useState(false)
  const [editando, setEditando] = useState<PersonalT | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.personal.list({
        activo: soloActivos ? true : undefined,
        limit: LIMITE,
        offset,
      })
      setItems(page.items)
      setTotal(page.total)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [soloActivos, offset])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Personal</h1>
          <p className="page-lead">
            Plantilla propia de la organización. El coste/hora es lo que cuesta a la empresa
            (salario más cargas sociales), y se congela en cada asignación a obra.
          </p>
        </div>
        <Tooltip texto="Dar de alta un trabajador">
          <button className="btn btn--primary" onClick={() => setCreando(true)}>
            <Plus size={16} aria-hidden="true" />
            Nuevo trabajador
          </button>
        </Tooltip>
      </div>

      <div className="toolbar">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={soloActivos}
            onChange={(e) => {
              setOffset(0)
              setSoloActivos(e.target.checked)
            }}
          />
          <span>Solo activos</span>
        </label>
      </div>

      <ErrorNotice error={error} />

      <div className="table-wrap">
        {items.length === 0 && !cargando ? (
          <EmptyState title="Sin trabajadores">Crea el primero para empezar.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Categoría</th>
                <th className="table__num">Coste/hora</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id}>
                  <td className="table__code">{p.codigo}</td>
                  <td>
                    {p.nombre} {p.apellidos ?? ''}
                    {!p.activo && <span className="chip chip--inactivo"> baja</span>}
                  </td>
                  <td>{p.categoria ?? <span className="muted">—</span>}</td>
                  <td className="table__num">{formatoImporte(p.coste_hora)} €</td>
                  <td className="table__actions">
                    <button className="btn btn--sm" onClick={() => setEditando(p)}>
                      <Pencil size={14} aria-hidden="true" />
                      Editar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Pager total={total} limit={LIMITE} offset={offset} onChange={setOffset} />

      {creando && (
        <FormularioPersonal
          onClose={() => setCreando(false)}
          onGuardado={() => {
            setCreando(false)
            void cargar()
          }}
        />
      )}
      {editando && (
        <FormularioPersonal
          persona={editando}
          onClose={() => setEditando(null)}
          onGuardado={() => {
            setEditando(null)
            void cargar()
          }}
        />
      )}
    </>
  )
}

function FormularioPersonal({
  persona,
  onClose,
  onGuardado,
}: {
  persona?: PersonalT
  onClose: () => void
  onGuardado: () => void
}) {
  const [nombre, setNombre] = useState(persona?.nombre ?? '')
  const [apellidos, setApellidos] = useState(persona?.apellidos ?? '')
  const [categoria, setCategoria] = useState(persona?.categoria ?? '')
  const [costeHora, setCosteHora] = useState(persona?.coste_hora ?? '0.00')
  const [activo, setActivo] = useState(persona?.activo ?? true)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const datos = {
        nombre,
        apellidos: apellidos || null,
        categoria: categoria || null,
        coste_hora: costeHora,
        activo,
      }
      if (persona) {
        await api.personal.update(persona.id, datos)
      } else {
        await api.personal.create(datos)
      }
      onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal title={persona ? 'Editar trabajador' : 'Nuevo trabajador'} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
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
          <Field label="Categoría" hint="Oficial 1ª, peón, encargado…">
            <input
              className="input"
              value={categoria}
              onChange={(e) => setCategoria(e.target.value)}
            />
          </Field>
          <Field label="Coste por hora" hint="Coste para la empresa, no lo que cobra en mano">
            <input
              className="input"
              type="number"
              step="0.01"
              value={costeHora}
              onChange={(e) => setCosteHora(e.target.value)}
            />
          </Field>
        </div>
        {persona && (
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={activo}
                onChange={(e) => setActivo(e.target.checked)}
              />
              <span>Activo</span>
            </label>
          </div>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={guardando || nombre.trim() === ''}
          onClick={() => void guardar()}
        >
          {!guardando && <Plus size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : persona ? 'Guardar cambios' : 'Crear'}
        </button>
      </div>
    </Modal>
  )
}
