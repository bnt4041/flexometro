import { useCallback, useEffect, useState } from 'react'
import { Send } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { DocumentosPRL } from './DocumentosPRL'
import { ErrorNotice, Field, IconButton, Modal } from './ui'
import { api } from '../lib/api'
import type { AvisoPersonal, PlantillaDocumento, SolicitudFirma } from '../lib/api'

const ETIQUETA_ESTADO: Record<string, string> = {
  borrador: 'Borrador',
  enviada: 'Enviada',
  vista: 'Abierta',
  firmada: 'Firmada',
  rechazada: 'Rechazada',
  cancelada: 'Cancelada',
}

/** Pestaña PRL de una obra: sus documentos, los avisos del personal asignado
 *  y los documentos mandados a firmar a subcontratas para esta obra.
 *
 *  Los tres bloques responden a la misma pregunta —¿está esta obra en regla
 *  hoy?— y por eso vienen en una sola llamada (`GET /api/prl/obras/{id}`) en
 *  vez de tres. */
export function PrlObra({ obraId }: { obraId: string }) {
  const navegar = useNavigate()
  const [avisos, setAvisos] = useState<AvisoPersonal[]>([])
  const [firmas, setFirmas] = useState<SolicitudFirma[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [modal, setModal] = useState(false)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const ficha = await api.prl.obra(obraId)
      setAvisos(ficha.personal_con_avisos)
      setFirmas(ficha.firmas)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [obraId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
      <ErrorNotice error={error} />

      <DocumentosPRL ambito="obra" entidadId={obraId} titulo="Documentación PRL de la obra" />

      <div>
        <div className="form-section__title">Personal asignado con avisos</div>
        {cargando ? (
          <p className="muted">Cargando…</p>
        ) : avisos.length === 0 ? (
          <p className="muted">
            Ningún trabajador asignado a esta obra tiene documentación pendiente o caducada.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Trabajador</th>
                  <th>Qué falta</th>
                </tr>
              </thead>
              <tbody>
                {avisos.map((aviso) => (
                  <tr key={aviso.personal_id}>
                    <td>{aviso.nombre}</td>
                    <td>
                      {aviso.motivos.map((motivo) => (
                        <span
                          key={motivo}
                          className="notice notice--aviso"
                          style={{ margin: '0 4px 4px 0', padding: '2px 8px', display: 'inline-block' }}
                        >
                          {motivo}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 'var(--sp-3)',
            gap: 'var(--sp-3)',
            flexWrap: 'wrap',
          }}
        >
          <div className="form-section__title" style={{ margin: 0 }}>
            Documentos a firmar de esta obra
          </div>
          <IconButton
            icono="nuevo"
            texto="Pedir firma"
            variante="primary"
            onClick={() => setModal(true)}
          />
        </div>
        {firmas.length === 0 ? (
          <p className="muted">
            Ningún documento pendiente de firma. Desde aquí puedes mandar un acta de coordinación o
            un acuse a una subcontrata.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Documento</th>
                  <th>Destinatario</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {firmas.map((firma) => (
                  <tr
                    key={firma.id}
                    onClick={() => navegar('/firmas')}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>
                      {firma.codigo} · {firma.titulo}
                    </td>
                    <td>{firma.firmantes.map((f) => f.nombre).join(', ')}</td>
                    <td>{ETIQUETA_ESTADO[firma.estado] ?? firma.estado}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modal && (
        <PedirFirma
          obraId={obraId}
          onCerrar={() => setModal(false)}
          onCreada={async () => {
            setModal(false)
            await cargar()
          }}
        />
      )}
    </div>
  )
}

function PedirFirma({
  obraId,
  onCerrar,
  onCreada,
}: {
  obraId: string
  onCerrar: () => void
  onCreada: () => void
}) {
  const [plantillas, setPlantillas] = useState<PlantillaDocumento[]>([])
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)
  const [titulo, setTitulo] = useState('')
  const [plantillaId, setPlantillaId] = useState('')
  const [nombre, setNombre] = useState('')
  const [email, setEmail] = useState('')

  useEffect(() => {
    api.prl.plantillas.list({ solo_activas: true }).then(setPlantillas).catch(() => setPlantillas([]))
  }, [])

  async function crearYEnviar() {
    if (!titulo.trim() || !nombre.trim() || !email.trim()) {
      setError('Hacen falta el título, el destinatario y su correo.')
      return
    }
    setEnviando(true)
    setError(null)
    try {
      const solicitud = await api.prl.firmas.create({
        titulo,
        plantilla_id: plantillaId || null,
        obra_id: obraId,
        firmantes: [{ nombre, email, guardar_como_contacto: true }],
      })
      const envios = await api.prl.firmas.enviar(solicitud.id)
      const fallido = envios.find((e) => !e.enviado)
      if (!fallido) onCreada()
      else {
        // El enlace vale igual: se enseña para poder mandarlo a mano en vez
        // de perder la solicitud por un fallo de correo.
        setAviso(`No se pudo enviar el correo. Enlace: ${fallido.enlace}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal title="Pedir firma de un documento" onClose={onCerrar}>
      <div className="form-section">
        <ErrorNotice error={error} />
        {aviso && (
          <p className="notice notice--aviso" style={{ wordBreak: 'break-all' }}>
            {aviso}
          </p>
        )}
        <div className="form-grid">
          <Field ancho="doble" label="Título del documento">
            <input className="input" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
          </Field>
          <Field ancho="doble" label="Plantilla" hint="Opcional">
            <select
              className="input"
              value={plantillaId}
              onChange={(e) => {
                setPlantillaId(e.target.value)
                const elegida = plantillas.find((p) => p.id === e.target.value)
                if (elegida && !titulo) setTitulo(elegida.nombre)
              }}
            >
              <option value="">Sin plantilla</option>
              {plantillas.map((plantilla) => (
                <option key={plantilla.id} value={plantilla.id}>
                  {plantilla.nombre}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Destinatario">
            <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Field>
          <Field label="Correo">
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
        </div>
      </div>
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button type="button" className="btn btn--primary" onClick={crearYEnviar} disabled={enviando}>
          <Send size={16} aria-hidden="true" /> {enviando ? 'Enviando…' : 'Crear y enviar'}
        </button>
      </div>
    </Modal>
  )
}
