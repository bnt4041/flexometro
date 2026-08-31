import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Ban, FileDown, Plus, RefreshCw, Send, Sparkles, Trash2, X } from 'lucide-react'

import { AyudaIADocumentoModal } from '../components/AyudaIADocumentoModal'
import { ContactosAsociados } from '../components/ContactosAsociados'
import { DescompuestoDocumento } from '../components/DescompuestoDocumento'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { MedicionesDocumento } from '../components/MedicionesDocumento'
import { NotasCrm } from '../components/NotasCrm'
import { RejillaDocumento } from '../components/RejillaDocumento'
import { Trazabilidad, cargarAsociadosDeObra } from '../components/Trazabilidad'
import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { WidgetGrid } from '../components/WidgetGrid'
import { ETIQUETA_ESTADO_FACTURA, ETIQUETA_SITUACION_COBRO, api, descargar } from '../lib/api'
import type { CuentaFinanciera, FacturaCapituloConPartidas, FacturaDetalle as Detalle } from '../lib/api'
import { useContextoFacturas } from './Facturas'

export function FacturaDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoFacturas()
  const [factura, setFactura] = useState<Detalle | null>(null)
  const [capitulos, setCapitulos] = useState<FacturaCapituloConPartidas[]>([])
  const [error, setError] = useState<string | null>(null)
  const [errorCapitulos, setErrorCapitulos] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const [anulando, setAnulando] = useState(false)
  const [cobrando, setCobrando] = useState(false)
  const [seleccionId, setSeleccionId] = useState<string | null>(null)
  const [ayudaIAAbierta, setAyudaIAAbierta] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setFactura(await api.facturas.get(id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  const cargarCapitulos = useCallback(async () => {
    try {
      setCapitulos(await api.facturas.capitulos(id))
      setErrorCapitulos(null)
    } catch (err) {
      setErrorCapitulos(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
    void cargarCapitulos()
  }, [cargar, cargarCapitulos])

  async function recargarTodo() {
    await Promise.all([cargar(), cargarCapitulos()])
  }

  function cerrar() {
    navigate('/facturas')
  }

  if (error && !factura) {
    return (
      <ModalPantalla title="Factura" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!factura) return null

  async function emitir() {
    try {
      await api.facturas.emitir(id)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function reintentarNotificacion() {
    try {
      const actualizada = await api.facturas.notificar(id)
      await cargar()
      setAviso(
        actualizada.notificado_n8n_en
          ? 'Notificada a n8n correctamente.'
          : 'n8n no ha respondido; sigue pendiente de enviar.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminarCobro(cobroId: string) {
    await api.cobros.remove(cobroId)
    await cargar()
  }

  const numeroFiscal = factura.numero
    ? `${factura.serie}/${String(factura.numero).padStart(5, '0')}`
    : `${factura.serie} · borrador`

  const partidaSeleccionada = seleccionId ? buscarPartida(capitulos, seleccionId) : null

  const pestanaDatos = (
    <>
      <ErrorNotice error={error} />
      {aviso && <div className="notice notice--ok">{aviso}</div>}

      <div className="page-head" style={{ marginBottom: 'var(--sp-2)' }}>
        <span className={`chip chip--estado-${factura.estado}`}>
          {ETIQUETA_ESTADO_FACTURA[factura.estado]}
        </span>
        {factura.estado === 'emitida' && (
          <span className={`chip chip--cobro-${factura.situacion_cobro}`}>
            {ETIQUETA_SITUACION_COBRO[factura.situacion_cobro]}
            {factura.vencida && ' · vencida'}
          </span>
        )}
      </div>

      {factura.estado === 'anulada' && factura.motivo_anulacion && (
        <div className="notice notice--error">Anulada: {factura.motivo_anulacion}</div>
      )}

      {factura.estado === 'emitida' && !factura.notificado_n8n_en && (
        <div className="notice notice--aviso">
          Todavía no se ha notificado a n8n para el circuito Veri*Factu/Facturae.{' '}
          <button className="btn btn--sm" onClick={() => void reintentarNotificacion()}>
            <RefreshCw size={14} aria-hidden="true" />
            Reintentar envío
          </button>
        </div>
      )}

      <WidgetGrid
        id="factura-datos"
        widgets={[
          ...(factura.estado === 'emitida'
            ? [
                {
                  id: 'cobros',
                  titulo: 'Cobros',
                  x: 0,
                  y: 0,
                  w: 8,
                  h: 10,
                  minW: 4,
                  minH: 5,
                  contenido: (
                    <>
                      {factura.situacion_cobro !== 'cobrada' && (
                        <div className="form-actions" style={{ justifyContent: 'flex-end' }}>
                          <Tooltip texto="Registrar un cobro para esta factura">
                            <button className="btn btn--sm" onClick={() => setCobrando(true)}>
                              <Plus size={14} aria-hidden="true" />
                              Registrar cobro
                            </button>
                          </Tooltip>
                        </div>
                      )}
                      <div className="table-wrap">
                        {factura.cobros.length === 0 ? (
                          <EmptyState title="Sin cobros registrados" />
                        ) : (
                          <table className="table">
                            <thead>
                              <tr>
                                <th>Fecha</th>
                                <th>Forma de pago</th>
                                <th>Entra en</th>
                                <th className="table__num">Importe</th>
                                <th className="table__actions" />
                              </tr>
                            </thead>
                            <tbody>
                              {factura.cobros.map((c) => (
                                <tr key={c.id}>
                                  <td>{c.fecha}</td>
                                  <td>{c.forma_pago ?? <span className="muted">—</span>}</td>
                                  <td className="muted">{c.cuenta_financiera_nombre ?? '—'}</td>
                                  <td className="table__num">{formatoImporte(c.importe)}</td>
                                  <td className="table__actions">
                                    <Tooltip texto="Eliminar este cobro">
                                      <button
                                        className="btn btn--sm btn--danger btn--solo-icono"
                                        onClick={() => void eliminarCobro(c.id)}
                                      >
                                        <Trash2 size={14} aria-hidden="true" />
                                      </button>
                                    </Tooltip>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                            <tfoot>
                              <tr className="fila-total">
                                <td colSpan={3} className="table__num total-label">
                                  Pendiente
                                </td>
                                <td className="table__num">
                                  <strong>{formatoImporte(factura.pendiente)}</strong>
                                </td>
                                <td />
                              </tr>
                            </tfoot>
                          </table>
                        )}
                      </div>
                    </>
                  ),
                },
              ]
            : []),
          {
            id: 'resumen',
            titulo: 'Resumen',
            x: 8,
            y: 0,
            w: 4,
            h: 10,
            minW: 3,
            minH: 5,
            contenido: (
              <div className="resumen-totales">
                <div className="resumen-totales__fila">
                  <span>Base imponible</span>
                  <span className="resumen-totales__valor">{formatoImporte(factura.base_imponible)} €</span>
                </div>
                <div className="resumen-totales__fila is-suave">
                  <span>{factura.inversion_sujeto_pasivo ? 'IVA — inversión del sujeto pasivo' : 'IVA'}</span>
                  <span className="resumen-totales__valor">{formatoImporte(factura.cuota_iva)} €</span>
                </div>
                <div className="resumen-totales__fila is-total">
                  <span>Total</span>
                  <span className="resumen-totales__valor">{formatoImporte(factura.total)} €</span>
                </div>
              </div>
            ),
          },
          {
            id: 'lineas',
            titulo: 'Capítulos y partidas',
            x: 0,
            y: 10,
            w: 8,
            h: 12,
            minW: 4,
            minH: 6,
            contenido: (
              <RejillaDocumento
                capitulos={capitulos}
                permiteDescompuesto
                onCrearCapitulo={() => api.facturas.addCapitulo(id, { resumen: 'Nuevo capítulo' })}
                onActualizarCapitulo={(capId, cambios) => api.facturasCapitulos.update(capId, cambios)}
                onEliminarCapitulo={(capId) => api.facturasCapitulos.remove(capId)}
                onCrearPartida={(capId) =>
                  api.facturasCapitulos.addPartida(capId, { resumen: 'Nueva partida' })
                }
                onActualizarPartida={(partId, cambios) => api.facturasPartidas.update(partId, cambios)}
                onEliminarPartida={(partId) => api.facturasPartidas.remove(partId)}
                onSeleccionarPartida={setSeleccionId}
                seleccionadaId={seleccionId}
                onCambio={() => void recargarTodo()}
                origenEntidad="factura"
                etiquetaDocumento={numeroFiscal}
                onPegarCapitulos={(datos) => api.facturas.pegarCapitulos(id, datos)}
                onPegarPartidas={(capituloId, datos) => api.facturasCapitulos.pegarPartidas(capituloId, datos)}
              />
            ),
          },
          {
            id: 'mediciones',
            titulo: 'Mediciones',
            x: 8,
            y: 10,
            w: 4,
            h: 12,
            minW: 3,
            minH: 6,
            contenido: !partidaSeleccionada ? (
              <EmptyState title="Nada seleccionado">
                Selecciona una partida en el listado para ver y editar su medición aquí.
              </EmptyState>
            ) : (
              <MedicionesDocumento
                key={partidaSeleccionada.id}
                mediciones={partidaSeleccionada.mediciones}
                unidad={partidaSeleccionada.unidad}
                medicionTotal={partidaSeleccionada.medicion}
                precio={partidaSeleccionada.precio}
                importe={partidaSeleccionada.importe}
                onCrear={() => api.facturasPartidas.addMedicion(partidaSeleccionada.id, { uds: '1' })}
                onActualizar={(medId, campos) => api.facturasMediciones.update(medId, campos)}
                onEliminar={(medId) => api.facturasMediciones.remove(medId)}
                onCambio={() => void recargarTodo()}
                origenEntidad="factura"
                origenEtiqueta={`${partidaSeleccionada.codigo} · ${partidaSeleccionada.resumen}`}
                onPegar={(datos) => api.facturasPartidas.pegarMediciones(partidaSeleccionada.id, datos)}
              />
            ),
          },
          {
            id: 'descompuesto',
            titulo: 'Descompuesto',
            x: 0,
            y: 22,
            w: 12,
            h: 10,
            minW: 5,
            minH: 5,
            contenido: !partidaSeleccionada ? (
              <EmptyState title="Ninguna partida seleccionada">
                Selecciona una partida en el listado para ver de qué se compone su precio.
              </EmptyState>
            ) : (
              <DescompuestoDocumento
                key={partidaSeleccionada.id}
                codigo={partidaSeleccionada.codigo}
                resumen={partidaSeleccionada.resumen}
                unidad={partidaSeleccionada.unidad}
                precio={partidaSeleccionada.precio}
                costesIndirectos={partidaSeleccionada.costes_indirectos}
                etiquetaAlcanceAmplio="En toda la factura donde aparezca"
                cargar={() => api.facturasPartidas.descomposicion(partidaSeleccionada.id)}
                anadirComponente={(datos) =>
                  api.facturasPartidas.anadirComponente(partidaSeleccionada.id, datos)
                }
                quitarComponente={(lineaId) =>
                  api.facturasPartidas.quitarComponente(partidaSeleccionada.id, lineaId)
                }
                independizarDescomposicion={() =>
                  api.facturasPartidas.independizarDescomposicion(partidaSeleccionada.id)
                }
                cambiarPrecioComponente={(datos) =>
                  api.facturasPartidas.cambiarPrecioComponente(partidaSeleccionada.id, {
                    hijo_id: datos.hijo_id,
                    precio: datos.precio,
                    alcance: datos.alcance === 'amplio' ? 'factura' : 'partida',
                  })
                }
                cambiarRendimientoComponente={(datos) =>
                  api.facturasPartidas.cambiarRendimientoComponente(partidaSeleccionada.id, datos)
                }
                cambiarResumenComponente={(datos) =>
                  api.facturasPartidas.cambiarResumenComponente(partidaSeleccionada.id, datos)
                }
                cambiarNaturalezaComponente={(datos) =>
                  api.facturasPartidas.cambiarNaturalezaComponente(partidaSeleccionada.id, datos)
                }
                cambiarUnidadComponente={(datos) =>
                  api.facturasPartidas.cambiarUnidadComponente(partidaSeleccionada.id, datos)
                }
                onCambio={() => void recargarTodo()}
                origenEntidad="factura"
                pegarComponentes={(datos) =>
                  api.facturasPartidas.pegarComponentes(partidaSeleccionada.id, datos)
                }
              />
            ),
          },
          {
            // Factura de venta: siempre de cliente, así que a diferencia de
            // Pedido este widget no depende de ningún tipo.
            id: 'ayuda-ia',
            titulo: 'Ayuda con IA',
            x: 0,
            y: 32,
            w: 12,
            h: 3,
            minW: 4,
            minH: 3,
            contenido: !partidaSeleccionada ? (
              <EmptyState title="Ninguna partida seleccionada">
                Selecciona una partida en el listado para pedir ayuda a la IA sobre ella.
              </EmptyState>
            ) : (
              <div className="form-actions" style={{ justifyContent: 'flex-start' }}>
                <button className="btn btn--sm" onClick={() => setAyudaIAAbierta(true)}>
                  <Sparkles size={14} aria-hidden="true" />
                  Ayuda con IA sobre «{partidaSeleccionada.resumen}»
                </button>
              </div>
            ),
          },
        ]}
      />

      {ayudaIAAbierta && partidaSeleccionada && (
        <AyudaIADocumentoModal
          contexto={{
            tipo: 'partida',
            codigo: partidaSeleccionada.codigo,
            resumen: partidaSeleccionada.resumen,
            unidad: partidaSeleccionada.unidad,
            precio: partidaSeleccionada.precio,
          }}
          destinoCapituloId={partidaSeleccionada.capitulo_id}
          conversar={(datos) =>
            api.facturas.iaConversar(id, {
              contexto: { ...datos.contexto, factura_id: id, factura_codigo: factura.codigo },
              mensajes: datos.mensajes,
            })
          }
          aplicarCapitulo={(datos) => api.facturas.iaAplicarCapitulo(id, datos)}
          pegarPartida={(capituloId, datos) => api.facturasCapitulos.pegarPartidas(capituloId, datos)}
          crearPartida={(capituloId, datos) => api.facturasCapitulos.addPartida(capituloId, datos)}
          anadirComponente={(partidaId, datos) => api.facturasPartidas.anadirComponente(partidaId, datos)}
          onCambio={() => void recargarTodo()}
          onClose={() => setAyudaIAAbierta(false)}
        />
      )}
      <ErrorNotice error={errorCapitulos} />

      <div className="card" style={{ marginTop: 'var(--sp-4)' }}>
        <div className="form-actions form-actions--separadas">
          {factura!.estado === 'emitida' ? (
            <Tooltip texto="Anular esta factura (conserva su número)">
              <button className="btn btn--danger" onClick={() => setAnulando(true)}>
                <Ban size={16} aria-hidden="true" />
                Anular
              </button>
            </Tooltip>
          ) : (
            <span />
          )}
          <span className="form-actions__grupo">
            <Tooltip texto="Descargar el PDF de esta factura">
              <button
                className="btn"
                onClick={() =>
                  void descargar(api.facturas.pdfUrl(id), `${numeroFiscal.replace('/', '-')}.pdf`, {
                    abrir: true,
                  }).catch((err) => setError(err instanceof Error ? err.message : String(err)))
                }
              >
                <FileDown size={16} aria-hidden="true" />
                PDF
              </button>
            </Tooltip>
            {factura!.estado === 'borrador' && (
              <Tooltip texto="Emitir: asigna número fiscal definitivo">
                <button className="btn btn--primary" onClick={() => void emitir()}>
                  <Send size={16} aria-hidden="true" />
                  Emitir
                </button>
              </Tooltip>
            )}
          </span>
        </div>
      </div>

      {anulando && (
        <AnularModal
          onClose={() => setAnulando(false)}
          onAnulada={() => {
            setAnulando(false)
            void cargar()
            onCambio()
          }}
          facturaId={id}
        />
      )}

      {cobrando && (
        <CobroModal
          facturaId={id}
          onClose={() => setCobrando(false)}
          onRegistrado={() => {
            setCobrando(false)
            void cargar()
            onCambio()
          }}
        />
      )}
    </>
  )

  const pestanas: PestanaFicha[] = [
    { id: 'datos', etiqueta: 'Datos', icono: 'datos', contenido: pestanaDatos },
    {
      id: 'contactos',
      etiqueta: 'Contactos',
      icono: 'contactos',
      contenido: <ContactosAsociados entidad="factura" entidadId={id} />,
    },
    {
      id: 'crm',
      etiqueta: 'CRM',
      icono: 'crm',
      contenido: <NotasCrm entidad="factura" entidadId={id} />,
    },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="factura" entidadId={id} />,
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
              etiqueta: factura.cliente_razon_social,
              ruta: `/terceros/${factura.cliente_id}`,
              estadoEtiqueta: 'Cliente',
            },
            ...(factura.certificacion_id
              ? [
                  {
                    tipo: 'certificacion' as const,
                    etiqueta: 'Certificación de origen',
                    ruta: `/certificaciones/${factura.certificacion_id}`,
                  },
                ]
              : []),
          ]}
          cargarAsociados={() =>
            cargarAsociadosDeObra(factura.obra_id, { tipo: 'factura', id })
          }
        />
      ),
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.facturas.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {factura.cliente_razon_social} <span className="table__code">{numeroFiscal}</span>
        </>
      }
      subtitulo={
        <p className="page-lead" style={{ marginBottom: 0 }}>
          {factura.concepto}
          {factura.fecha_emision && <> · emitida {factura.fecha_emision}</>}
        </p>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}

function AnularModal({
  facturaId,
  onClose,
  onAnulada,
}: {
  facturaId: string
  onClose: () => void
  onAnulada: () => void
}) {
  const [motivo, setMotivo] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function confirmar() {
    setError(null)
    try {
      await api.facturas.anular(facturaId, motivo)
      onAnulada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Anular factura" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          La factura conserva su número: una factura emitida no se borra nunca, para no dejar
          huecos en la serie.
        </p>
        <Field label="Motivo de la anulación">
          <textarea
            className="input"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            autoFocus
          />
        </Field>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--danger"
          disabled={motivo.trim() === ''}
          onClick={() => void confirmar()}
        >
          <Ban size={16} aria-hidden="true" />
          Anular
        </button>
      </div>
    </Modal>
  )
}

function CobroModal({
  facturaId,
  onClose,
  onRegistrado,
}: {
  facturaId: string
  onClose: () => void
  onRegistrado: () => void
}) {
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [importe, setImporte] = useState('')
  const [formaPago, setFormaPago] = useState('transferencia')
  const [cuentas, setCuentas] = useState<CuentaFinanciera[]>([])
  const [cuentaId, setCuentaId] = useState('')
  const [error, setError] = useState<string | null>(null)

  // La predeterminada viene la primera (lo ordena el backend), así que sale
  // ya elegida sin tener que buscarla aquí.
  useEffect(() => {
    void api.cuentasFinancieras
      .list()
      .then((lista) => {
        setCuentas(lista)
        setCuentaId(lista.find((c) => c.es_predeterminada)?.id ?? '')
      })
      .catch(() => setCuentas([]))
  }, [])

  async function guardar() {
    setError(null)
    try {
      await api.facturas.addCobro(facturaId, {
        fecha,
        importe,
        forma_pago: formaPago,
        cuenta_financiera_id: cuentaId || null,
      })
      onRegistrado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Registrar cobro" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field label="Fecha">
            <input
              className="input"
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </Field>
          <Field label="Importe">
            <input
              className="input"
              type="number"
              step="0.01"
              value={importe}
              onChange={(e) => setImporte(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Forma de pago">
            <select className="select" value={formaPago} onChange={(e) => setFormaPago(e.target.value)}>
              <option value="transferencia">Transferencia</option>
              <option value="domiciliado">Domiciliado</option>
              <option value="pagare">Pagaré</option>
              <option value="confirming">Confirming</option>
              <option value="efectivo">Efectivo</option>
              <option value="tarjeta">Tarjeta</option>
            </select>
          </Field>
          {cuentas.length > 0 && (
            <Field ancho="doble" label="Entra en" hint="Banco o caja donde se ingresa">
              <select className="select" value={cuentaId} onChange={(e) => setCuentaId(e.target.value)}>
                <option value="">Sin especificar</option>
                {cuentas.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nombre}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={importe === ''} onClick={() => void guardar()}>
          <Plus size={16} aria-hidden="true" />
          Registrar
        </button>
      </div>
    </Modal>
  )
}

/** Busca una partida por id en el árbol de capítulos ya cargado — igual que
 *  `PresupuestoDetalle.buscarPartida`: la selección se guarda solo como id
 *  para no arrastrar una copia que quede desactualizada tras la siguiente
 *  recarga. */
function buscarPartida(capitulos: FacturaCapituloConPartidas[], id: string) {
  for (const capitulo of capitulos) {
    const encontrada = capitulo.partidas.find((p) => p.id === id)
    if (encontrada) return encontrada
  }
  return null
}
