import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Sparkles, Trash2 } from 'lucide-react'

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
import { EmptyState, ErrorNotice, ModalPantalla, Tooltip } from '../components/ui'
import { WidgetGrid } from '../components/WidgetGrid'
import { ETIQUETA_ESTADO_PEDIDO, ETIQUETA_TIPO_PEDIDO, api } from '../lib/api'
import type { EstadoPedido, PedidoCapituloConPartidas, PedidoDetalle as Detalle } from '../lib/api'
import { useContextoPedidos } from './Pedidos'

export function PedidoDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoPedidos()
  const [pedido, setPedido] = useState<Detalle | null>(null)
  const [capitulos, setCapitulos] = useState<PedidoCapituloConPartidas[]>([])
  const [error, setError] = useState<string | null>(null)
  const [errorCapitulos, setErrorCapitulos] = useState<string | null>(null)
  const [seleccionId, setSeleccionId] = useState<string | null>(null)
  const [ayudaIAAbierta, setAyudaIAAbierta] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setPedido(await api.pedidos.get(id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  const cargarCapitulos = useCallback(async () => {
    try {
      setCapitulos(await api.pedidos.capitulos(id))
      setErrorCapitulos(null)
    } catch (err) {
      setErrorCapitulos(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
    void cargarCapitulos()
  }, [cargar, cargarCapitulos])

  function cerrar() {
    navigate('/pedidos')
  }

  if (error && !pedido) {
    return (
      <ModalPantalla title="Pedido" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!pedido) return null

  async function cambiarEstado(estado: EstadoPedido) {
    try {
      await api.pedidos.update(id, { estado })
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar el pedido ${pedido!.codigo}?`)) return
    try {
      await api.pedidos.remove(id)
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const partidaSeleccionada = seleccionId ? buscarPartida(capitulos, seleccionId) : null
  const permiteDescompuesto = pedido.tipo === 'cliente'

  const pestanaDatos = (
    <>
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          {pedido.fecha}
          {pedido.fecha_entrega_prevista && <> · entrega prevista {pedido.fecha_entrega_prevista}</>}
          {pedido.origen_oferta_presupuesto_id && (
            <>
              {' '}
              ·{' '}
              <Link to={`/presupuestos/${pedido.origen_oferta_presupuesto_id}`}>
                {pedido.tipo === 'proveedor' ? 'desde oferta' : 'desde presupuesto'}
              </Link>
            </>
          )}
        </p>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <select
            className="select"
            style={{ width: 'auto' }}
            value={pedido.estado}
            onChange={(e) => void cambiarEstado(e.target.value as EstadoPedido)}
          >
            {Object.entries(ETIQUETA_ESTADO_PEDIDO).map(([clave, etiqueta]) => (
              <option key={clave} value={clave}>
                {etiqueta}
              </option>
            ))}
          </select>
          <Tooltip texto="Eliminar este pedido">
            <button className="btn btn--danger" onClick={() => void eliminar()}>
              <Trash2 size={16} aria-hidden="true" />
              Eliminar
            </button>
          </Tooltip>
        </div>
      </div>

      <ErrorNotice error={error} />
      <ErrorNotice error={errorCapitulos} />

      <WidgetGrid
        id="pedido-datos"
        widgets={[
          {
            id: 'lineas',
            titulo: 'Capítulos y partidas',
            x: 0,
            y: 0,
            w: 8,
            h: 12,
            minW: 4,
            minH: 6,
            contenido: (
              <RejillaDocumento
                capitulos={capitulos}
                permiteDescompuesto={permiteDescompuesto}
                onCrearCapitulo={() => api.pedidos.addCapitulo(id, { resumen: 'Nuevo capítulo' })}
                onActualizarCapitulo={(capId, cambios) => api.pedidosCapitulos.update(capId, cambios)}
                onEliminarCapitulo={(capId) => api.pedidosCapitulos.remove(capId)}
                onCrearPartida={(capId) =>
                  api.pedidosCapitulos.addPartida(capId, { resumen: 'Nueva partida' })
                }
                onActualizarPartida={(partId, cambios) => api.pedidosPartidas.update(partId, cambios)}
                onEliminarPartida={(partId) => api.pedidosPartidas.remove(partId)}
                onSeleccionarPartida={setSeleccionId}
                seleccionadaId={seleccionId}
                onCambio={cargarCapitulos}
                origenEntidad="pedido"
                etiquetaDocumento={pedido.codigo}
                onPegarCapitulos={(datos) => api.pedidos.pegarCapitulos(id, datos)}
                onPegarPartidas={(capituloId, datos) => api.pedidosCapitulos.pegarPartidas(capituloId, datos)}
              />
            ),
          },
          {
            id: 'mediciones',
            titulo: 'Mediciones',
            x: 8,
            y: 0,
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
                onCrear={() => api.pedidosPartidas.addMedicion(partidaSeleccionada.id, { uds: '1' })}
                onActualizar={(medId, campos) => api.pedidosMediciones.update(medId, campos)}
                onEliminar={(medId) => api.pedidosMediciones.remove(medId)}
                onCambio={cargarCapitulos}
                origenEntidad="pedido"
                origenEtiqueta={`${partidaSeleccionada.codigo} · ${partidaSeleccionada.resumen}`}
                onPegar={(datos) => api.pedidosPartidas.pegarMediciones(partidaSeleccionada.id, datos)}
              />
            ),
          },
          ...(permiteDescompuesto
            ? [
                {
                  id: 'descompuesto',
                  titulo: 'Descompuesto',
                  x: 0,
                  y: 12,
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
                      etiquetaAlcanceAmplio="En todo el pedido donde aparezca"
                      cargar={() => api.pedidosPartidas.descomposicion(partidaSeleccionada.id)}
                      anadirComponente={(datos) =>
                        api.pedidosPartidas.anadirComponente(partidaSeleccionada.id, datos)
                      }
                      quitarComponente={(lineaId) =>
                        api.pedidosPartidas.quitarComponente(partidaSeleccionada.id, lineaId)
                      }
                      independizarDescomposicion={() =>
                        api.pedidosPartidas.independizarDescomposicion(partidaSeleccionada.id)
                      }
                      cambiarPrecioComponente={(datos) =>
                        api.pedidosPartidas.cambiarPrecioComponente(partidaSeleccionada.id, {
                          hijo_id: datos.hijo_id,
                          precio: datos.precio,
                          alcance: datos.alcance === 'amplio' ? 'pedido' : 'partida',
                        })
                      }
                      cambiarRendimientoComponente={(datos) =>
                        api.pedidosPartidas.cambiarRendimientoComponente(partidaSeleccionada.id, datos)
                      }
                      cambiarResumenComponente={(datos) =>
                        api.pedidosPartidas.cambiarResumenComponente(partidaSeleccionada.id, datos)
                      }
                      cambiarNaturalezaComponente={(datos) =>
                        api.pedidosPartidas.cambiarNaturalezaComponente(partidaSeleccionada.id, datos)
                      }
                      cambiarUnidadComponente={(datos) =>
                        api.pedidosPartidas.cambiarUnidadComponente(partidaSeleccionada.id, datos)
                      }
                      onCambio={cargarCapitulos}
                      origenEntidad="pedido"
                      pegarComponentes={(datos) =>
                        api.pedidosPartidas.pegarComponentes(partidaSeleccionada.id, datos)
                      }
                    />
                  ),
                },
                {
                  // Solo pedidos de cliente: uno de proveedor no tiene
                  // descompuesto que montar y el backend responde 409 si se
                  // llama aquí (ver `pedido_ia_router._pedido_cliente_propio`).
                  id: 'ayuda-ia',
                  titulo: 'Ayuda con IA',
                  x: 0,
                  y: 22,
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
              ]
            : []),
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
            api.pedidos.iaConversar(id, {
              contexto: { ...datos.contexto, pedido_id: id, pedido_codigo: pedido.codigo },
              mensajes: datos.mensajes,
            })
          }
          aplicarCapitulo={(datos) => api.pedidos.iaAplicarCapitulo(id, datos)}
          pegarPartida={(capituloId, datos) => api.pedidosCapitulos.pegarPartidas(capituloId, datos)}
          crearPartida={(capituloId, datos) => api.pedidosCapitulos.addPartida(capituloId, datos)}
          anadirComponente={(partidaId, datos) => api.pedidosPartidas.anadirComponente(partidaId, datos)}
          onCambio={cargarCapitulos}
          onClose={() => setAyudaIAAbierta(false)}
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
      contenido: <ContactosAsociados entidad="pedido" entidadId={id} />,
    },
    {
      id: 'crm',
      etiqueta: 'CRM',
      icono: 'crm',
      contenido: <NotasCrm entidad="pedido" entidadId={id} />,
    },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="pedido" entidadId={id} />,
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
              etiqueta: pedido.tercero_razon_social,
              ruta: `/terceros/${pedido.cliente_id ?? pedido.proveedor_id}`,
              estadoEtiqueta: ETIQUETA_TIPO_PEDIDO[pedido.tipo],
            },
            ...(pedido.origen_oferta_presupuesto_id
              ? [
                  {
                    tipo: 'presupuesto' as const,
                    etiqueta: pedido.tipo === 'proveedor' ? 'Oferta ganadora' : 'Presupuesto de origen',
                    ruta: `/presupuestos/${pedido.origen_oferta_presupuesto_id}`,
                  },
                ]
              : []),
          ]}
          cargarAsociados={() => cargarAsociadosDeObra(pedido.obra_id, { tipo: 'pedido', id })}
        />
      ),
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.pedidos.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {pedido.tercero_razon_social} <span className="table__code">{pedido.codigo}</span>
        </>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}

/** Busca una partida por id en el árbol de capítulos ya cargado — la
 *  selección se guarda solo como id para no arrastrar una copia que quede
 *  desactualizada tras la siguiente recarga (mismo criterio que
 *  `PresupuestoDetalle.buscarPartida`). */
function buscarPartida(capitulos: PedidoCapituloConPartidas[], id: string) {
  for (const capitulo of capitulos) {
    const encontrada = capitulo.partidas.find((p) => p.id === id)
    if (encontrada) return encontrada
  }
  return null
}
