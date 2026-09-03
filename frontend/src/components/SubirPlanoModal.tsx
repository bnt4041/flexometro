import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'

import { ErrorNotice, Field, Modal } from './ui'
import { api } from '../lib/api'
import type { Plano } from '../lib/api'
import { esDxf, leerHojas } from '../lib/hojasPlano'

const ADMITIDOS = '.pdf,.png,.jpg,.jpeg,.webp,.dxf'

/** Subir un plano nuevo — compartido entre la biblioteca (`Planos.tsx`) y la
 *  pestaña de Mediciones de una partida (`PlanosPartida.tsx`, Fase 1k), que
 *  lo sube ya con `presupuestoId` puesto para que salga listado ahí sin un
 *  paso aparte. */
export function SubirPlanoModal({
  presupuestoId,
  obraId,
  onCerrar,
  onSubido,
}: {
  presupuestoId?: string
  obraId?: string
  onCerrar: () => void
  onSubido: (p: Plano) => void
}) {
  const [archivo, setArchivo] = useState<File | null>(null)
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [hojas, setHojas] = useState<number | null>(null)
  const [vectorial, setVectorial] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [arrastrando, setArrastrando] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function elegir(fichero: File) {
    setArchivo(fichero)
    setError(null)
    setVectorial(esDxf(fichero))
    // El nombre se propone del fichero, sin extensión: casi siempre es el
    // bueno, y teclearlo otra vez es trabajo tonto.
    if (!nombre) setNombre(fichero.name.replace(/\.[^.]+$/, ''))
    try {
      setHojas((await leerHojas(fichero)).length)
    } catch (err) {
      setHojas(null)
      setError(err instanceof Error ? err.message : 'No se ha podido leer el fichero')
    }
  }

  async function subir() {
    if (!archivo) return
    setOcupado(true)
    setError(null)
    try {
      const leidas = await leerHojas(archivo)
      onSubido(
        await api.planos.subir(
          { nombre, descripcion, presupuesto_id: presupuestoId, obra_id: obraId },
          archivo,
          leidas,
        ),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  return (
    <Modal title="Subir plano" onClose={onCerrar}>
      <ErrorNotice error={error} />
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setArrastrando(true)
        }}
        onDragLeave={() => setArrastrando(false)}
        onDrop={(e) => {
          e.preventDefault()
          setArrastrando(false)
          const fichero = e.dataTransfer.files?.[0]
          if (fichero) void elegir(fichero)
        }}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `1px dashed ${arrastrando ? 'var(--c-accent-strong)' : 'var(--c-border)'}`,
          borderRadius: 'var(--radius)',
          background: arrastrando ? 'var(--c-accent-soft)' : 'var(--c-surface-2)',
          padding: 'var(--sp-4)',
          textAlign: 'center',
          cursor: 'pointer',
          marginBottom: 'var(--sp-3)',
        }}
      >
        <Upload size={18} aria-hidden="true" style={{ marginBottom: 'var(--sp-1)' }} />
        <p className="form-section__note" style={{ margin: 0 }}>
          {archivo ? archivo.name : 'Arrastra aquí el plano, o haz clic para elegirlo'}
        </p>
        <input
          ref={inputRef}
          type="file"
          className="input"
          accept={ADMITIDOS}
          style={{ display: 'none' }}
          onChange={(e) => e.target.files?.[0] && void elegir(e.target.files[0])}
        />
      </div>
      {vectorial ? (
        <p className="muted">
          DXF. Se lee en el servidor: sus capas se crean solas y, si el fichero
          declara sus unidades, ya viene calibrado y se puede medir sin pinchar
          ninguna cota.
        </p>
      ) : (
        hojas !== null && (
          <p className="muted">
            {hojas === 1 ? '1 hoja' : `${hojas} hojas`}. Cada una se calibra por separado.
          </p>
        )
      )}
      <Field label="Nombre">
        <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
      </Field>
      <Field label="Descripción">
        <textarea
          className="input"
          rows={3}
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
        />
      </Field>
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={ocupado || !archivo || !nombre.trim()}
          onClick={() => void subir()}
        >
          <Upload size={16} aria-hidden="true" /> Subir
        </button>
      </div>
    </Modal>
  )
}
