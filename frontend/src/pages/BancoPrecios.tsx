import { useCallback, useEffect, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { FolderTree, Pencil, Plus, Trash2, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla, Tooltip } from '../components/ui'
import { DescompuestoConcepto } from '../components/DescompuestoConcepto'
import { DescripcionEditor } from '../components/DescripcionEditor'
import type { FilaBanco } from '../components/RejillaBancoPrecios'
import { ID_RAIZ, RejillaBancoPrecios } from '../components/RejillaBancoPrecios'
import { WidgetGrid } from '../components/WidgetGrid'
import { ETIQUETA_NATURALEZA, ETIQUETA_TIPO_CONCEPTO, api } from '../lib/api'
import type { ArbolBanco, Familia, NaturalezaConcepto, TipoConcepto } from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'

export type ContextoBancoPrecios = { onCambio: () => void }

export function useContextoBancoPrecios() {
  return useOutletContext<ContextoBancoPrecios>()
}

export function BancoPrecios() {
  const [arbol, setArbol] = useState<ArbolBanco | null>(null)
  const [familias, setFamilias] = useState<Familia[]>([])
  const [error, setError] = useState<string | null>(null)
  const [mostrarFamilias, setMostrarFamilias] = useState(false)
  // La fila que siguen los widgets de la derecha y de abajo. Se guarda la
  // fila entera (no solo el id) para poder pintar el descompuesto y la
  // descripción sin volver a buscarla en el árbol.
  const [seleccion, setSeleccion] = useState<FilaBanco | null>(null)

  const cargar = useCallback(async () => {
    try {
      const [datos, listaFamilias] = await Promise.all([
        api.banco.arbol(),
        api.familias.list(),
      ])
      setArbol(datos)
      setFamilias(listaFamilias)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const fichaSeleccionada =
    seleccion && seleccion.tipo === 'ficha' && seleccion.id !== ID_RAIZ ? seleccion : null

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Banco de precios</h1>
          <p className="page-lead">
            Cada producto, servicio o precio descompuesto es la misma ficha: básicos, auxiliares
            y unitarios. Cambiar un precio propaga hacia arriba a todo lo que lo contiene.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <Tooltip texto="Crear, editar o borrar familias">
            <button className="btn" onClick={() => setMostrarFamilias(true)}>
              <FolderTree size={16} aria-hidden="true" />
              Familias
            </button>
          </Tooltip>
          <Tooltip texto="Dar de alta un producto, servicio o precio nuevo">
            <Link className="btn btn--primary" to="nuevo">
              <Plus size={16} aria-hidden="true" />
              Nueva ficha
            </Link>
          </Tooltip>
        </div>
      </div>

      <ErrorNotice error={error} />

      {arbol && (
        <WidgetGrid
          id="banco-precios"
          widgets={[
            {
              id: 'lineas',
              titulo: 'Capítulos y fichas',
              x: 0,
              y: 0,
              w: 12,
              h: 13,
              minW: 5,
              minH: 6,
              contenido: (
                <RejillaBancoPrecios
                  arbol={arbol}
                  familias={familias}
                  onCambio={cargar}
                  seleccionadaId={seleccion?.id ?? null}
                  onSeleccionar={setSeleccion}
                />
              ),
            },
            {
              id: 'descompuesto',
              titulo: 'Descompuesto',
              x: 0,
              y: 13,
              w: 12,
              h: 10,
              minW: 5,
              minH: 5,
              contenido: fichaSeleccionada ? (
                <DescompuestoConcepto
                  key={fichaSeleccionada.id}
                  conceptoId={fichaSeleccionada.id}
                  onCambio={cargar}
                />
              ) : (
                <EmptyState title="Ninguna ficha seleccionada">
                  Elige una ficha de la rejilla para ver y editar su descompuesto.
                </EmptyState>
              ),
            },
            {
              id: 'descripcion',
              titulo: 'Descripción ampliada',
              x: 0,
              y: 23,
              w: 12,
              h: 12,
              minW: 5,
              minH: 6,
              contenido: !seleccion || seleccion.id === ID_RAIZ ? (
                <EmptyState title="Nada seleccionado">
                  Selecciona un capítulo o una ficha para ver y editar su descripción aquí.
                </EmptyState>
              ) : seleccion.tipo === 'ficha' ? (
                <DescripcionEditor
                  key={seleccion.id}
                  id={seleccion.id}
                  html={seleccion.texto}
                  entidad="concepto"
                  entidadId={seleccion.id}
                  onGuardar={async (texto) => {
                    await api.conceptos.update(seleccion.id, { texto })
                  }}
                />
              ) : (
                <DescripcionEditor
                  key={seleccion.id}
                  id={seleccion.id}
                  html={seleccion.texto}
                  // Las imágenes de un capítulo del banco no cuelgan de una
                  // ficha concreta; se guardan en la primera que tenga a mano
                  // — aquí el propio capítulo no es una entidad documental.
                  entidad="concepto"
                  entidadId={seleccion.id}
                  onGuardar={async (texto) => {
                    await api.banco.actualizarCapitulo(seleccion.id, { texto })
                  }}
                />
              ),
            },
          ]}
        />
      )}

      {mostrarFamilias && (
        <FamiliasModal
          onClose={() => {
            setMostrarFamilias(false)
            void cargar()
          }}
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoBancoPrecios} />
    </>
  )
}


function FamiliasModal({ onClose }: { onClose: () => void }) {
  const [familias, setFamilias] = useState<Familia[]>([])
  const [editandoId, setEditandoId] = useState<string | null>(null)
  const [codigo, setCodigo] = useState('')
  const [nombre, setNombre] = useState('')
  const [parentId, setParentId] = useState('')
  const [orden, setOrden] = useState('0')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setFamilias(await api.familias.list())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function limpiarFormulario() {
    setEditandoId(null)
    setCodigo('')
    setNombre('')
    setParentId('')
    setOrden('0')
  }

  function editar(familia: Familia) {
    setEditandoId(familia.id)
    setCodigo(familia.codigo)
    setNombre(familia.nombre)
    setParentId(familia.parent_id ?? '')
    setOrden(String(familia.orden))
  }

  async function guardar() {
    setGuardando(true)
    setError(null)
    const datos = {
      codigo,
      nombre,
      parent_id: parentId || null,
      orden: Number(orden) || 0,
    }
    try {
      if (editandoId) {
        await api.familias.update(editandoId, datos)
      } else {
        await api.familias.create(datos)
      }
      limpiarFormulario()
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar(familia: Familia) {
    if (!window.confirm(`¿Eliminar la familia «${familia.nombre}»?`)) return
    try {
      await api.familias.remove(familia.id)
      if (editandoId === familia.id) limpiarFormulario()
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  // Profundidad de cada familia (para la sangría), siguiendo su parent_id.
  const profundidadDe = (familia: Familia): number => {
    let profundidad = 0
    let actual: Familia | undefined = familia
    const vistos = new Set<string>()
    while (actual?.parent_id && !vistos.has(actual.id)) {
      vistos.add(actual.id)
      actual = familias.find((f) => f.id === actual!.parent_id)
      profundidad += 1
    }
    return profundidad
  }

  const ordenadas = [...familias].sort((a, b) => a.orden - b.orden || a.codigo.localeCompare(b.codigo))

  return (
    <Modal title="Familias del banco de precios" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field label="Código">
            <input className="input" value={codigo} onChange={(e) => setCodigo(e.target.value)} />
          </Field>
          <Field ancho="doble" label="Nombre">
            <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Field>
          <Field label="Familia superior" hint="Vacío: raíz">
            <select className="select" value={parentId} onChange={(e) => setParentId(e.target.value)}>
              <option value="">Sin familia superior</option>
              {familias
                .filter((f) => f.id !== editandoId)
                .map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.nombre}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Orden">
            <input
              className="input"
              type="number"
              value={orden}
              onChange={(e) => setOrden(e.target.value)}
            />
          </Field>
        </div>
        <div className="form-actions" style={{ justifyContent: 'flex-end' }}>
          {editandoId && (
            <button className="btn" onClick={limpiarFormulario}>
              <X size={14} aria-hidden="true" />
              Cancelar edición
            </button>
          )}
          <button
            className="btn btn--primary"
            disabled={guardando || codigo.trim() === '' || nombre.trim() === ''}
            onClick={() => void guardar()}
          >
            {!guardando && <Plus size={16} aria-hidden="true" />}
            {guardando ? 'Guardando…' : editandoId ? 'Guardar cambios' : 'Añadir familia'}
          </button>
        </div>

        <div className="lista-seleccion" style={{ marginTop: 'var(--sp-4)' }}>
          {ordenadas.length === 0 ? (
            <div className="muted" style={{ padding: 'var(--sp-3)' }}>
              Sin familias todavía
            </div>
          ) : (
            ordenadas.map((f) => (
              <div key={f.id} className="lista-seleccion__item" style={{ cursor: 'default' }}>
                <span className="table__code" style={{ marginLeft: profundidadDe(f) * 16 }}>
                  {f.codigo}
                </span>
                <span className="lista-seleccion__texto">{f.nombre}</span>
                <button className="btn btn--sm" onClick={() => editar(f)}>
                  <Pencil size={14} aria-hidden="true" />
                  Editar
                </button>{' '}
                <button className="btn btn--sm btn--danger" onClick={() => void eliminar(f)}>
                  <Trash2 size={14} aria-hidden="true" />
                  Eliminar
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </Modal>
  )
}

export function ConceptoCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoBancoPrecios()
  const unidadesMedida = useDiccionario('unidad_medida')
  const [tipo, setTipo] = useState<TipoConcepto>('basico')
  const [resumen, setResumen] = useState('')
  const [unidad, setUnidad] = useState('ud')
  const [naturaleza, setNaturaleza] = useState<NaturalezaConcepto>('material')
  const [origenPrecio, setOrigenPrecio] = useState<'manual' | 'producto'>('manual')
  const [precio, setPrecio] = useState('0.00')
  const [precioVenta, setPrecioVenta] = useState('')
  const [ean, setEan] = useState('')
  const [costesIndirectos, setCostesIndirectos] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  function cerrar() {
    navigate('/banco-precios')
  }

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.conceptos.create({
        tipo,
        resumen,
        unidad,
        naturaleza,
        origen_precio: origenPrecio,
        precio: origenPrecio === 'manual' ? precio : '0.00',
        precio_venta: precioVenta || null,
        ean: ean || null,
        costes_indirectos: tipo === 'unitario' && costesIndirectos ? costesIndirectos : null,
      })
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title="Nueva ficha del banco de precios" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
        <div className="form-grid">
          <Field
            label="Nivel"
            hint={
              tipo === 'basico'
                ? 'Recurso elemental: mano de obra, material, maquinaria o servicio'
                : tipo === 'auxiliar'
                  ? 'Se compone de básicos y entra en los unitarios'
                  : 'La partida que se presupuesta'
            }
          >
            <select
              className="select"
              value={tipo}
              onChange={(e) => setTipo(e.target.value as TipoConcepto)}
            >
              {Object.entries(ETIQUETA_TIPO_CONCEPTO).map(([clave, etiqueta]) => (
                <option key={clave} value={clave}>
                  {etiqueta}
                </option>
              ))}
            </select>
          </Field>
          <Field ancho="doble" label="Descripción corta">
            <input
              className="input"
              value={resumen}
              onChange={(e) => setResumen(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Unidad">
            <select className="select" value={unidad} onChange={(e) => setUnidad(e.target.value)}>
              {unidadesMedida.map((u) => (
                <option key={u.clave} value={u.clave}>
                  {u.etiqueta}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Naturaleza" hint="Equivale al campo TIPO de FIEBDC-3">
            <select
              className="select"
              value={naturaleza}
              onChange={(e) => setNaturaleza(e.target.value as NaturalezaConcepto)}
            >
              {Object.entries(ETIQUETA_NATURALEZA).map(([clave, etiqueta]) => (
                <option key={clave} value={clave}>
                  {etiqueta}
                </option>
              ))}
            </select>
          </Field>
          <Field label="EAN" hint="Opcional">
            <input className="input" value={ean} onChange={(e) => setEan(e.target.value)} />
          </Field>
          <Field label="Precio de venta" hint="Opcional, distinto del precio de coste">
            <input
              className="input"
              type="number"
              step="0.01"
              value={precioVenta}
              onChange={(e) => setPrecioVenta(e.target.value)}
            />
          </Field>
        </div>

        <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
          <Field
            label="Precio de coste"
            hint="Si lo descompones después, pasa a calcularse solo"
          >
            <select
              className="select"
              value={origenPrecio}
              onChange={(e) => setOrigenPrecio(e.target.value as 'manual' | 'producto')}
            >
              <option value="manual">A mano</option>
              <option value="producto">Desde tarifa de proveedor (añádela después de crear)</option>
            </select>
          </Field>

          {origenPrecio === 'manual' && (
            <Field label="Importe">
              <input
                className="input"
                type="number"
                step="0.01"
                value={precio}
                onChange={(e) => setPrecio(e.target.value)}
              />
            </Field>
          )}

          {tipo === 'unitario' && (
            <Field label="Costes indirectos (%)" hint="Se aplica sobre el coste directo">
              <input
                className="input"
                type="number"
                step="0.01"
                value={costesIndirectos}
                onChange={(e) => setCostesIndirectos(e.target.value)}
              />
            </Field>
          )}
        </div>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={guardando || resumen.trim() === ''}
            onClick={() => void guardar()}
          >
            {guardando ? 'Guardando…' : 'Crear'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
