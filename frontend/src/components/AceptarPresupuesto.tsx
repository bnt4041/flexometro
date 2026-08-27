/** Aceptar un presupuesto no es solo cambiarle el estado: es ponerlo en
 *  ejecución, y eso exige decir dónde. O arranca una obra nueva, o entra como
 *  anexo en una que ya está en marcha.
 *
 *  El destino no se puede adivinar, así que se pregunta. Lo hace el endpoint
 *  `/api/presupuestos/{id}/aceptar`, que vive en el módulo de obras (es el
 *  único lado que ve las dos cosas) y deja el presupuesto aprobado con los
 *  precios congelados en un solo viaje: si algo falla, no se queda a medias.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Building2, Check, Plus, X } from 'lucide-react'

import { api } from '../lib/api'
import type { ObraResumen, PresupuestoAceptado } from '../lib/api'
import { ErrorNotice, Field, Modal } from './ui'

type Destino = 'nueva' | 'existente'

export function AceptarPresupuestoModal({
  presupuestoId,
  nombreSugerido,
  onClose,
  onAceptado,
}: {
  presupuestoId: string
  /** El nombre del presupuesto: casi siempre es también el de la obra. */
  nombreSugerido: string
  onClose: () => void
  /** Para que la ficha del presupuesto recargue: su estado ha cambiado. */
  onAceptado: (resultado: PresupuestoAceptado) => void
}) {
  const [hecho, setHecho] = useState<PresupuestoAceptado | null>(null)
  const [destino, setDestino] = useState<Destino>('nueva')
  const [nombre, setNombre] = useState(nombreSugerido)
  const [codigo, setCodigo] = useState('')
  const [obraId, setObraId] = useState('')
  const [obras, setObras] = useState<ObraResumen[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    let vigente = true
    api.obras
      .list({ limit: 200 })
      .then((pagina) => {
        if (!vigente) return
        setObras(pagina.items)
        // Sin obras en marcha, «añadir a una existente» no es una opción real:
        // se deja fuera en vez de ofrecer un desplegable vacío.
        if (pagina.items.length === 0) setDestino('nueva')
      })
      .catch((err: unknown) => {
        if (vigente) setError(err instanceof Error ? err.message : 'No se han podido cargar las obras')
      })
    return () => {
      vigente = false
    }
  }, [])

  const hayObras = obras !== null && obras.length > 0
  const listo =
    destino === 'nueva' ? nombre.trim().length > 0 : obraId.length > 0

  async function aceptar() {
    setGuardando(true)
    setError(null)
    try {
      const resultado = await api.presupuestos.aceptar(
        presupuestoId,
        destino === 'existente'
          ? { obra_id: obraId }
          : { obra_nombre: nombre.trim(), obra_codigo: codigo.trim() || null },
      )
      // El destino se enseña en vez de dar un salto de pantalla: aceptar es un
      // paso con consecuencias y conviene ver dónde ha ido.
      setHecho(resultado)
      setGuardando(false)
      onAceptado(resultado)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  if (hecho) {
    return (
      <Modal title="Presupuesto aceptado" onClose={onClose}>
        <div className="form-section">
          <p className="aceptar__hecho">
            <Check size={18} aria-hidden="true" />
            {hecho.mensaje}
          </p>
          {hecho.tipo === 'anexo' && (
            <p className="aceptar__intro">
              Queda marcado como anexo: en la obra se distingue de lo contratado al principio.
            </p>
          )}
        </div>
        <div className="form-actions">
          <button className="btn" onClick={onClose}>
            Seguir aquí
          </button>
          <Link className="btn btn--primary" to={`/obras/${hecho.obra_id}`}>
            Ir a {hecho.obra_codigo}
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title="Aceptar presupuesto" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="aceptar__intro">
          Al aceptarlo pasa a ejecutarse y sus precios quedan congelados. ¿En qué obra?
        </p>

        <div className="aceptar__destinos">
          <button
            type="button"
            className={`aceptar__destino${destino === 'nueva' ? ' aceptar__destino--activo' : ''}`}
            onClick={() => setDestino('nueva')}
          >
            <Plus size={18} aria-hidden="true" />
            <span className="aceptar__destino-titulo">Obra nueva</span>
            <span className="aceptar__destino-nota">Este presupuesto será el principal</span>
          </button>
          <button
            type="button"
            className={`aceptar__destino${destino === 'existente' ? ' aceptar__destino--activo' : ''}`}
            onClick={() => setDestino('existente')}
            disabled={!hayObras}
          >
            <Building2 size={18} aria-hidden="true" />
            <span className="aceptar__destino-titulo">Obra existente</span>
            <span className="aceptar__destino-nota">
              {hayObras ? 'Entrará como anexo o adenda' : 'Todavía no hay obras'}
            </span>
          </button>
        </div>

        {destino === 'nueva' ? (
          <>
            <Field label="Nombre de la obra">
              <input
                className="input"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                autoFocus
              />
            </Field>
            <Field label="Código" hint="Si lo dejas vacío se numera solo">
              <input
                className="input"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                placeholder="OBR00002"
              />
            </Field>
          </>
        ) : (
          <Field label="Obra" hint="El presupuesto se añade como anexo a lo ya contratado">
            <select
              className="select"
              value={obraId}
              onChange={(e) => setObraId(e.target.value)}
              autoFocus
            >
              <option value="">Elige una obra…</option>
              {(obras ?? []).map((obra) => (
                <option key={obra.id} value={obra.id}>
                  {obra.codigo} · {obra.nombre}
                </option>
              ))}
            </select>
          </Field>
        )}
      </div>

      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={!listo || guardando}
          onClick={() => void aceptar()}
        >
          {!guardando && <Check size={16} aria-hidden="true" />}
          {guardando ? 'Aceptando…' : 'Aceptar y poner en obra'}
        </button>
      </div>
    </Modal>
  )
}
