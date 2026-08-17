import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Check,
  ChevronDown,
  Copy,
  Download,
  FileDown,
  Layers,
  Plus,
  RefreshCw,
  Save,
  Scan,
  Trash2,
  X,
} from 'lucide-react'

import { CamposLibres } from '../components/CamposLibres'
import { ContactosAsociados } from '../components/ContactosAsociados'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { NotasCrm } from '../components/NotasCrm'
import type { FilaPresupuesto } from '../components/RejillaPresupuesto'
import { RejillaPresupuesto } from '../components/RejillaPresupuesto'
import {
  Checkbox,
  EmptyState,
  ErrorNotice,
  Field,
  MenuAcciones,
  Modal,
  ModalPantalla,
  Tooltip,
  formatoImporte,
} from '../components/ui'
import { WidgetGrid } from '../components/WidgetGrid'
import { ETIQUETA_ESTADO, ETIQUETA_IVA, api, descargar } from '../lib/api'
import type {
  Concepto,
  EstadoPresupuesto,
  LecturaPlanoDetalle,
  LineaSugerida,
  Partida,
  PresupuestoDetalle as Detalle,
  RecursosPresupuesto,
  Tercero,
  TipoIVA,
  UsuarioKeycloak,
  Version,
} from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'
import { useContextoPresupuestos } from './Presupuestos'
import { useWorkspace } from '../workspace'

function formatoFecha(iso: string): string {
  return new Date(iso).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
}

export function PresupuestoDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoPresupuestos()
  const [presupuesto, setPresupuesto] = useState<Detalle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const [nuevoCapituloEn, setNuevoCapituloEn] = useState<string | null | undefined>(undefined)
  const [nuevaPartidaEn, setNuevaPartidaEn] = useState<string | null>(null)
  const [midiendo, setMidiendo] = useState<Partida | null>(null)
  const [versiones, setVersiones] = useState<Version[]>([])
  const [recursos, setRecursos] = useState<RecursosPresupuesto | null>(null)
  const [cliente, setCliente] = useState<Tercero | null>(null)
  const [cabeceraExpandida, setCabeceraExpandida] = useState(false)
  const [guardandoPlantilla, setGuardandoPlantilla] = useState(false)
  const [editando, setEditando] = useState(false)
  const [cambiandoEstado, setCambiandoEstado] = useState(false)
  const [seleccion, setSeleccion] = useState<
    { tipo: 'partida'; partida: Partida } | { tipo: 'capitulo'; fila: FilaPresupuesto } | null
  >(null)

  const cargar = useCallback(async () => {
    try {
      const [detalle, lineaVersiones, datosRecursos] = await Promise.all([
        api.presupuestos.get(id),
        api.presupuestos.versiones(id),
        api.presupuestos.recursos(id),
      ])
      setPresupuesto(detalle)
      setVersiones(lineaVersiones)
      setRecursos(datosRecursos)
      setCliente(detalle.cliente_id ? await api.terceros.get(detalle.cliente_id) : null)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/presupuestos')
  }

  if (error && !presupuesto) {
    return (
      <ModalPantalla title="Presupuesto" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!presupuesto) return null

  async function sincronizar() {
    const { partidas_actualizadas } = await api.presupuestos.sincronizarPrecios(id)
    setAviso(
      partidas_actualizadas === 1
        ? '1 partida actualizada con el precio del cuadro.'
        : `${partidas_actualizadas} partidas actualizadas con el precio del cuadro.`,
    )
    await cargar()
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar «${presupuesto!.nombre}» y todo su contenido?`)) return
    await api.presupuestos.remove(id)
    onCambio()
    cerrar()
  }

  async function integrarBancoPrecios(partida: Partida) {
    if (
      !window.confirm(
        `¿Dar de alta «${partida.resumen}» como concepto nuevo del banco de precios? A partir de ` +
          'ahora esta partida seguirá su precio.',
      )
    ) {
      return
    }
    try {
      await api.partidas.integrarBancoPrecios(partida.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function crearVersion() {
    try {
      const nueva = await api.presupuestos.nuevaVersion(id)
      onCambio()
      navigate(`/presupuestos/${nueva.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const t = presupuesto.totales
  const seleccionId =
    seleccion?.tipo === 'partida'
      ? seleccion.partida.id
      : seleccion?.tipo === 'capitulo'
        ? seleccion.fila.id
        : null

  const pestanaDatos = (
    <>
      <div className="barra-acciones">
        <span className="barra-acciones__grupo">
          <span className="barra-acciones__etiqueta">Descargar</span>
          {[
            ['presupuesto', 'Presupuesto'],
            ['mediciones', 'Mediciones'],
            ['descompuestos', 'Descompuestos'],
          ].map(([documento, etiqueta]) => (
            <button
              key={documento}
              className="btn btn--sm"
              onClick={() =>
                void descargar(
                  api.presupuestos.pdfUrl(id, documento),
                  `${presupuesto!.codigo}-${documento}.pdf`,
                  { abrir: true },
                ).catch((err) => setError(err instanceof Error ? err.message : String(err)))
              }
            >
              <FileDown size={14} aria-hidden="true" />
              {etiqueta} PDF
            </button>
          ))}
          <button
            className="btn btn--sm"
            onClick={() =>
              void descargar(
                api.fiebdc.exportarUrl(id),
                `${presupuesto!.codigo}.bc3`,
              ).catch((err) => setError(err instanceof Error ? err.message : String(err)))
            }
          >
            <Download size={14} aria-hidden="true" />
            BC3
          </button>
        </span>
        <span className="barra-acciones__grupo">
          <Tooltip texto="Duplicar como versión siguiente, con precios libres otra vez">
            <button className="btn btn--sm" onClick={() => void crearVersion()}>
              <Copy size={14} aria-hidden="true" />
              Nueva versión
            </button>
          </Tooltip>
          <Tooltip texto="Guardar esta estructura como plantilla reutilizable">
            <button className="btn btn--sm" onClick={() => setGuardandoPlantilla(true)}>
              <Layers size={14} aria-hidden="true" />
              Guardar como plantilla
            </button>
          </Tooltip>
        </span>
      </div>

      {versiones.length > 1 && (
        <div className="versiones">
          <span className="barra-acciones__etiqueta">Versiones</span>
          {versiones.map((v) => (
            <span key={v.id} className="versiones__item">
              {v.id === id ? (
                <span className="chip chip--unitario">v{v.version}</span>
              ) : (
                <Link className="table__link" to={`/presupuestos/${v.id}`}>
                  v{v.version}
                </Link>
              )}
              {v.id !== id && (
                <Link className="versiones__comparar" to={`/presupuestos/${id}/comparar/${v.id}`}>
                  comparar
                </Link>
              )}
            </span>
          ))}
        </div>
      )}

      <ErrorNotice error={error} />
      {aviso && <div className="notice notice--ok">{aviso}</div>}

      {presupuesto.partidas_desactualizadas > 0 && (
        <div className="notice notice--aviso">
          <strong>{presupuesto.partidas_desactualizadas}</strong>{' '}
          {presupuesto.partidas_desactualizadas === 1 ? 'partida tiene' : 'partidas tienen'} un
          precio distinto del que hay ahora en el cuadro. Con los precios congelados no se
          actualizan solas.{' '}
          <button className="btn btn--sm" onClick={() => void sincronizar()}>
            <RefreshCw size={14} aria-hidden="true" />
            Traer precios del cuadro
          </button>
        </div>
      )}

      <CamposLibres entidad="presupuesto" entidadId={id} />

      <WidgetGrid
        id="presupuesto-datos"
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
              <RejillaPresupuesto
                presupuesto={presupuesto}
                onCambio={cargar}
                onMedir={setMidiendo}
                onIntegrarBanco={(partida) => void integrarBancoPrecios(partida)}
                seleccionadaId={seleccionId}
                onSeleccionar={(fila) => {
                  if (!fila) return setSeleccion(null)
                  if (fila.tipo === 'partida' && fila.partida) {
                    setSeleccion({ tipo: 'partida', partida: fila.partida })
                  } else {
                    setSeleccion({ tipo: 'capitulo', fila })
                  }
                }}
              />
            ),
          },
          {
            id: 'resumen',
            titulo: 'Resumen',
            x: 8,
            y: 0,
            w: 4,
            h: 12,
            minW: 3,
            minH: 6,
            contenido: (
              <div className="resumen-totales">
                <Fila etiqueta="Presupuesto de ejecución material (PEM)" valor={t.pem} />
                <Fila
                  etiqueta={`Gastos generales ${formatoImporte(presupuesto.gastos_generales)} %`}
                  valor={t.gastos_generales}
                  suave
                />
                <Fila
                  etiqueta={`Beneficio industrial ${formatoImporte(presupuesto.beneficio_industrial)} %`}
                  valor={t.beneficio_industrial}
                  suave
                />
                <Fila etiqueta="Presupuesto de ejecución por contrata (sin IVA)" valor={t.pec_sin_iva} />
                <Fila
                  etiqueta={
                    presupuesto.inversion_sujeto_pasivo
                      ? 'IVA — inversión del sujeto pasivo'
                      : `IVA ${formatoImporte(t.porcentaje_iva, 0)} %`
                  }
                  valor={t.iva}
                  suave
                />
                <Fila etiqueta="Total" valor={t.total} destacado />
              </div>
            ),
          },
          {
            id: 'mediciones',
            titulo: 'Mediciones',
            x: 0,
            y: 12,
            w: 12,
            h: 11,
            minW: 5,
            minH: 5,
            contenido:
              seleccion === null ? (
                <EmptyState title="Nada seleccionado">
                  Selecciona una partida en el listado para ver y editar su medición aquí.
                </EmptyState>
              ) : seleccion.tipo === 'capitulo' ? (
                <div className="ficha-datos">
                  <div>
                    <div className="barra-acciones__etiqueta">Capítulo</div>
                    <div className="ficha-datos__valor">
                      {seleccion.fila.codigo} — {seleccion.fila.resumen}
                    </div>
                    <p className="muted">
                      Un capítulo no se mide por sí mismo: selecciona una partida dentro de él
                      para ver su medición.
                    </p>
                  </div>
                  <div>
                    <div className="barra-acciones__etiqueta">Importe</div>
                    <div className="ficha-datos__valor">{formatoImporte(seleccion.fila.importe)} €</div>
                  </div>
                </div>
              ) : (
                <MedicionesPanel partida={seleccion.partida} onCambio={cargar} />
              ),
          },
          {
            id: 'materiales',
            titulo: 'Precios básicos',
            x: 0,
            y: 23,
            w: 8,
            h: 10,
            minW: 4,
            minH: 5,
            contenido: (
              <div className="table-wrap">
                {(recursos?.materiales.length ?? 0) === 0 ? (
                  <EmptyState title="Sin materiales">
                    Los materiales que compongan las partidas por descomposición aparecerán aquí.
                  </EmptyState>
                ) : (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Código</th>
                        <th>Descripción</th>
                        <th className="table__num">Cantidad</th>
                        <th className="table__num">Precio</th>
                        <th className="table__num">Importe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recursos?.materiales.map((m) => (
                        <tr key={m.concepto_id}>
                          <td className="table__code">{m.codigo}</td>
                          <td>{m.resumen}</td>
                          <td className="table__num">
                            {formatoImporte(m.cantidad, 3)} <span className="muted">{m.unidad}</span>
                          </td>
                          <td className="table__num">{formatoImporte(m.precio)}</td>
                          <td className="table__num">
                            <strong>{formatoImporte(m.importe)}</strong>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ),
          },
          {
            id: 'mano-obra',
            titulo: 'Recursos humanos',
            x: 8,
            y: 23,
            w: 4,
            h: 10,
            minW: 3,
            minH: 5,
            contenido: (
              <>
                <div className="ficha-datos" style={{ marginBottom: 'var(--sp-4)' }}>
                  <div>
                    <div className="barra-acciones__etiqueta">Horas presupuestadas</div>
                    <div className="ficha-datos__valor">
                      {formatoImporte(recursos?.horas_totales ?? '0', 1)} h
                    </div>
                  </div>
                </div>
                {(recursos?.mano_obra.length ?? 0) === 0 ? (
                  <EmptyState title="Sin mano de obra">
                    Los recursos de mano de obra que compongan las partidas aparecerán aquí.
                  </EmptyState>
                ) : (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Código</th>
                          <th>Descripción</th>
                          <th className="table__num">Cantidad</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recursos?.mano_obra.map((m) => (
                          <tr key={m.concepto_id}>
                            <td className="table__code">{m.codigo}</td>
                            <td>{m.resumen}</td>
                            <td className="table__num">
                              {formatoImporte(m.cantidad, 3)} <span className="muted">{m.unidad}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ),
          },
        ]}
      />

      {nuevoCapituloEn !== undefined && (
        <NuevoCapituloModal
          presupuestoId={id}
          parentId={nuevoCapituloEn}
          onClose={() => setNuevoCapituloEn(undefined)}
          onCreado={() => {
            setNuevoCapituloEn(undefined)
            void cargar()
          }}
        />
      )}

      {nuevaPartidaEn && (
        <NuevaPartidaModal
          capituloId={nuevaPartidaEn}
          onClose={() => setNuevaPartidaEn(null)}
          onCreada={() => {
            setNuevaPartidaEn(null)
            void cargar()
          }}
        />
      )}

      {midiendo && (
        <MedicionModal
          partida={midiendo}
          onClose={() => setMidiendo(null)}
          onCambio={cargar}
        />
      )}

      {guardandoPlantilla && (
        <GuardarPlantillaModal
          presupuestoId={id}
          nombreBase={presupuesto.nombre}
          onClose={() => setGuardandoPlantilla(false)}
          onGuardada={() => {
            setGuardandoPlantilla(false)
            setAviso('Plantilla creada. La tienes en la pestaña Plantillas.')
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
      contenido: <ContactosAsociados entidad="presupuesto" entidadId={id} />,
    },
    {
      id: 'crm',
      etiqueta: 'CRM',
      icono: 'crm',
      contenido: <NotasCrm entidad="presupuesto" entidadId={id} />,
    },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="presupuesto" entidadId={id} />,
    },
  ]

  return (
    <>
    <FichaDetalle
      titulo={
        <>
          {presupuesto.nombre} <span className="table__code">{presupuesto.codigo}</span>
        </>
      }
      subtitulo={
        <div className="ficha-cabecera-extra">
          <div className="ficha-cabecera-extra__resumen">
            <p className="page-lead" style={{ marginBottom: 0 }}>
              {presupuesto.emplazamiento && <>{presupuesto.emplazamiento} · </>}
              {presupuesto.fecha && <>{presupuesto.fecha} · </>}
              {presupuesto.precios_bloqueados && (
                <> <span className="badge">precios congelados</span></>
              )}
            </p>
            <Tooltip texto={cabeceraExpandida ? 'Mostrar menos' : 'Mostrar todos los datos'}>
              <button
                className="ficha-cabecera-extra__toggle"
                onClick={() => setCabeceraExpandida((v) => !v)}
              >
                <ChevronDown
                  size={16}
                  aria-hidden="true"
                  style={{
                    transition: 'transform 150ms ease',
                    transform: cabeceraExpandida ? 'rotate(180deg)' : undefined,
                  }}
                />
              </button>
            </Tooltip>
          </div>

          {cabeceraExpandida && (
            <div className="ficha-datos ficha-cabecera-extra__datos">
              <div>
                <div className="barra-acciones__etiqueta">Cliente</div>
                <div>{cliente?.razon_social ?? <span className="muted">Sin cliente</span>}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Tipo de obra</div>
                <div>{presupuesto.tipo_obra ?? <span className="muted">—</span>}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Validez</div>
                <div>
                  {presupuesto.validez_dias ? (
                    `${presupuesto.validez_dias} días`
                  ) : (
                    <span className="muted">—</span>
                  )}
                </div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Tipo de IVA</div>
                <div>{ETIQUETA_IVA[presupuesto.tipo_iva]}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Gastos generales</div>
                <div>{formatoImporte(presupuesto.gastos_generales)} %</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Beneficio industrial</div>
                <div>{formatoImporte(presupuesto.beneficio_industrial)} %</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Inversión del sujeto pasivo</div>
                <div>{presupuesto.inversion_sujeto_pasivo ? 'Sí' : 'No'}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Origen del dato</div>
                <div>{presupuesto.origen_dato}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Responsable</div>
                <div>{presupuesto.responsable_nombre ?? <span className="muted">Sin asignar</span>}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Creado</div>
                <div>
                  {formatoFecha(presupuesto.created_at)}
                  {presupuesto.creado_por_nombre && ` · ${presupuesto.creado_por_nombre}`}
                </div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Última modificación</div>
                <div>{formatoFecha(presupuesto.updated_at)}</div>
              </div>
              {presupuesto.descripcion && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <div className="barra-acciones__etiqueta">Descripción</div>
                  <div>{presupuesto.descripcion}</div>
                </div>
              )}
              {presupuesto.notas && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <div className="barra-acciones__etiqueta">Notas</div>
                  <div>{presupuesto.notas}</div>
                </div>
              )}
            </div>
          )}
        </div>
      }
      acciones={
        <>
          <span className={`chip chip--estado-${presupuesto.estado}`}>
            {ETIQUETA_ESTADO[presupuesto.estado]}
          </span>
          <MenuAcciones
            acciones={[
              { id: 'editar', etiqueta: 'Editar', icono: 'editar', onClick: () => setEditando(true) },
              {
                id: 'estado',
                etiqueta: 'Cambiar estado',
                icono: 'estado',
                onClick: () => setCambiandoEstado(true),
              },
              {
                id: 'eliminar',
                etiqueta: 'Eliminar',
                icono: 'eliminar',
                peligroso: true,
                onClick: () => void eliminar(),
              },
            ]}
          />
        </>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />

    {editando && (
      <EditarPresupuestoModal
        presupuesto={presupuesto}
        onClose={() => setEditando(false)}
        onGuardado={() => {
          setEditando(false)
          void cargar()
          onCambio()
        }}
      />
    )}

    {cambiandoEstado && (
      <CambiarEstadoModal
        presupuestoId={id}
        estadoActual={presupuesto.estado}
        onClose={() => setCambiandoEstado(false)}
        onGuardado={() => {
          setCambiandoEstado(false)
          void cargar()
          onCambio()
        }}
      />
    )}
    </>
  )
}

function EditarPresupuestoModal({
  presupuesto,
  onClose,
  onGuardado,
}: {
  presupuesto: Detalle
  onClose: () => void
  onGuardado: () => void
}) {
  const [nombre, setNombre] = useState(presupuesto.nombre)
  const [descripcion, setDescripcion] = useState(presupuesto.descripcion ?? '')
  const [clienteId, setClienteId] = useState(presupuesto.cliente_id ?? '')
  const [emplazamiento, setEmplazamiento] = useState(presupuesto.emplazamiento ?? '')
  const [fecha, setFecha] = useState(presupuesto.fecha ?? '')
  const [validezDias, setValidezDias] = useState(presupuesto.validez_dias?.toString() ?? '')
  const [tipoObra, setTipoObra] = useState(presupuesto.tipo_obra ?? '')
  const [tipoIva, setTipoIva] = useState(presupuesto.tipo_iva)
  const [gastosGenerales, setGastosGenerales] = useState(presupuesto.gastos_generales)
  const [beneficioIndustrial, setBeneficioIndustrial] = useState(presupuesto.beneficio_industrial)
  const [inversionSujetoPasivo, setInversionSujetoPasivo] = useState(
    presupuesto.inversion_sujeto_pasivo,
  )
  const [notas, setNotas] = useState(presupuesto.notas ?? '')
  const [responsableSubject, setResponsableSubject] = useState(
    presupuesto.responsable_subject ?? '',
  )
  const [responsableNombre, setResponsableNombre] = useState(presupuesto.responsable_nombre ?? '')
  const [clientes, setClientes] = useState<Tercero[]>([])
  const [usuarios, setUsuarios] = useState<UsuarioKeycloak[]>([])
  const [usuariosDisponibles, setUsuariosDisponibles] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    void api.terceros
      .list({ rol: 'cliente', activo: true, limit: 500 })
      .then((page) => setClientes(page.items))
      .catch(() => {
        /* si falla, el campo cliente simplemente se queda sin opciones nuevas */
      })
    // Listar usuarios de la organización exige ser administrador: para
    // cualquier otro perfil, el campo se muestra de solo lectura en vez de
    // romper el formulario entero.
    void api.usuariosYGrupos.usuarios
      .list()
      .then(setUsuarios)
      .catch(() => setUsuariosDisponibles(false))
  }, [])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.presupuestos.update(presupuesto.id, {
        nombre,
        descripcion: descripcion || null,
        cliente_id: clienteId || null,
        emplazamiento: emplazamiento || null,
        fecha: fecha || null,
        validez_dias: validezDias === '' ? null : Number(validezDias),
        tipo_obra: tipoObra || null,
        tipo_iva: tipoIva,
        gastos_generales: gastosGenerales,
        beneficio_industrial: beneficioIndustrial,
        inversion_sujeto_pasivo: inversionSujetoPasivo,
        notas: notas || null,
        responsable_subject: responsableSubject || null,
        responsable_nombre: responsableSubject ? responsableNombre : null,
      })
      onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <Modal title="Editar presupuesto" onClose={onClose}>
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
          <Field label="Cliente">
            <select className="select" value={clienteId} onChange={(e) => setClienteId(e.target.value)}>
              <option value="">Sin cliente</option>
              {clientes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.razon_social}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Emplazamiento">
            <input
              className="input"
              value={emplazamiento}
              onChange={(e) => setEmplazamiento(e.target.value)}
            />
          </Field>
          <Field label="Fecha">
            <input
              className="input"
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </Field>
          <Field label="Validez (días)">
            <input
              className="input"
              type="number"
              value={validezDias}
              onChange={(e) => setValidezDias(e.target.value)}
            />
          </Field>
          <Field label="Tipo de obra">
            <input className="input" value={tipoObra} onChange={(e) => setTipoObra(e.target.value)} />
          </Field>
          <Field label="Tipo de IVA">
            <select
              className="select"
              value={tipoIva}
              onChange={(e) => setTipoIva(e.target.value as TipoIVA)}
            >
              {Object.entries(ETIQUETA_IVA).map(([clave, etiqueta]) => (
                <option key={clave} value={clave}>
                  {etiqueta}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Gastos generales (%)">
            <input
              className="input"
              type="number"
              step="0.01"
              value={gastosGenerales}
              onChange={(e) => setGastosGenerales(e.target.value)}
            />
          </Field>
          <Field label="Beneficio industrial (%)">
            <input
              className="input"
              type="number"
              step="0.01"
              value={beneficioIndustrial}
              onChange={(e) => setBeneficioIndustrial(e.target.value)}
            />
          </Field>
          <Field label="Responsable">
            {usuariosDisponibles ? (
              <select
                className="select"
                value={responsableSubject}
                onChange={(e) => {
                  const usuario = usuarios.find((u) => u.id === e.target.value)
                  setResponsableSubject(e.target.value)
                  setResponsableNombre(
                    usuario
                      ? [usuario.firstName, usuario.lastName].filter(Boolean).join(' ') ||
                          usuario.username
                      : '',
                  )
                }}
              >
                <option value="">Sin asignar</option>
                {usuarios.map((u) => (
                  <option key={u.id} value={u.id}>
                    {[u.firstName, u.lastName].filter(Boolean).join(' ') || u.username}
                  </option>
                ))}
              </select>
            ) : (
              <p className="field__hint" style={{ marginTop: 0 }}>
                {responsableNombre || 'Sin asignar'} — hace falta ser administrador de la
                organización para reasignarlo.
              </p>
            )}
          </Field>
        </div>

        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Checkbox
            label="Inversión del sujeto pasivo"
            checked={inversionSujetoPasivo}
            onChange={setInversionSujetoPasivo}
          />
        </div>

        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Field label="Descripción">
            <textarea
              className="input"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
            />
          </Field>
        </div>

        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Field label="Notas">
            <textarea className="input" value={notas} onChange={(e) => setNotas(e.target.value)} />
          </Field>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={nombre.trim() === '' || guardando}
          onClick={() => void guardar()}
        >
          {!guardando && <Save size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : 'Guardar cambios'}
        </button>
      </div>
    </Modal>
  )
}

function CambiarEstadoModal({
  presupuestoId,
  estadoActual,
  onClose,
  onGuardado,
}: {
  presupuestoId: string
  estadoActual: EstadoPresupuesto
  onClose: () => void
  onGuardado: () => void
}) {
  const [estado, setEstado] = useState(estadoActual)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.presupuestos.update(presupuestoId, { estado })
      onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <Modal title="Cambiar estado" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Nuevo estado" hint="Salir de borrador congela los precios de las partidas">
          <select
            className="select"
            value={estado}
            onChange={(e) => setEstado(e.target.value as EstadoPresupuesto)}
            autoFocus
          >
            {Object.entries(ETIQUETA_ESTADO).map(([clave, etiqueta]) => (
              <option key={clave} value={clave}>
                {etiqueta}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={estado === estadoActual || guardando}
          onClick={() => void guardar()}
        >
          {!guardando && <Save size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </Modal>
  )
}

function GuardarPlantillaModal({
  presupuestoId,
  nombreBase,
  onClose,
  onGuardada,
}: {
  presupuestoId: string
  nombreBase: string
  onClose: () => void
  onGuardada: () => void
}) {
  const [nombre, setNombre] = useState(`${nombreBase} — tipo`)
  const [tipoObra, setTipoObra] = useState('')
  const [conMediciones, setConMediciones] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    try {
      await api.presupuestos.guardarComoPlantilla(presupuestoId, {
        nombre,
        tipo_obra: tipoObra || null,
        con_mediciones: conMediciones,
      })
      onGuardada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Guardar como plantilla" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          Se copian los capítulos y las partidas con sus precios. Lo reutilizable de un
          presupuesto es qué partidas lleva, no cuántos metros medía aquella obra.
        </p>
        <div className="form-grid">
          <Field label="Nombre de la plantilla">
            <input
              className="input"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Tipo de obra" hint="Sirve para agrupar y buscar plantillas">
            <input
              className="input"
              value={tipoObra}
              onChange={(e) => setTipoObra(e.target.value)}
              placeholder="rehabilitacion_fachada"
            />
          </Field>
        </div>
        <div style={{ marginTop: 'var(--sp-4)' }}>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={conMediciones}
              onChange={(e) => setConMediciones(e.target.checked)}
            />
            <span>Conservar también las mediciones</span>
          </label>
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
          <Save size={16} aria-hidden="true" />
          Guardar
        </button>
      </div>
    </Modal>
  )
}

function Fila({
  etiqueta,
  valor,
  suave,
  destacado,
}: {
  etiqueta: string
  valor: string
  suave?: boolean
  destacado?: boolean
}) {
  const clases = ['resumen-totales__fila']
  if (suave) clases.push('is-suave')
  if (destacado) clases.push('is-total')
  return (
    <div className={clases.join(' ')}>
      <span>{etiqueta}</span>
      <span className="resumen-totales__valor">{formatoImporte(valor)} €</span>
    </div>
  )
}

function NuevoCapituloModal({
  presupuestoId,
  parentId,
  onClose,
  onCreado,
}: {
  presupuestoId: string
  parentId: string | null
  onClose: () => void
  onCreado: () => void
}) {
  const [resumen, setResumen] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    try {
      await api.presupuestos.addCapitulo(presupuestoId, { resumen, parent_id: parentId })
      onCreado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title={parentId ? 'Nuevo subcapítulo' : 'Nuevo capítulo'} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Descripción" hint="El código se numera solo: 01, 01.01, 01.02…">
          <input
            className="input"
            value={resumen}
            onChange={(e) => setResumen(e.target.value)}
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
          className="btn btn--primary"
          disabled={resumen.trim() === ''}
          onClick={() => void guardar()}
        >
          <Plus size={16} aria-hidden="true" />
          Crear
        </button>
      </div>
    </Modal>
  )
}

function NuevaPartidaModal({
  capituloId,
  onClose,
  onCreada,
}: {
  capituloId: string
  onClose: () => void
  onCreada: () => void
}) {
  const [modo, setModo] = useState<'cuadro' | 'alzada'>('cuadro')
  const unidadesMedida = useDiccionario('unidad_medida')
  const [q, setQ] = useState('')
  const [candidatos, setCandidatos] = useState<Concepto[]>([])
  const [conceptoId, setConceptoId] = useState('')
  const [codigo, setCodigo] = useState('')
  const [resumen, setResumen] = useState('')
  const [unidad, setUnidad] = useState('ud')
  const [precio, setPrecio] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (modo !== 'cuadro') return
    const id = setTimeout(() => {
      void api.conceptos
        .list({ q: q || undefined, tipo: 'unitario', activo: true, limit: 50 })
        .then((page) => setCandidatos(page.items))
        .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
    }, 250)
    return () => clearTimeout(id)
  }, [q, modo])

  async function guardar() {
    setError(null)
    try {
      await api.capitulos.addPartida(
        capituloId,
        modo === 'cuadro'
          ? { concepto_id: conceptoId }
          : { codigo, resumen, unidad, precio: precio || '0' },
      )
      onCreada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const listo = modo === 'cuadro' ? conceptoId !== '' : resumen.trim() !== ''

  return (
    <Modal title="Nueva partida" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Origen">
          <select
            className="select"
            value={modo}
            onChange={(e) => setModo(e.target.value as 'cuadro' | 'alzada')}
          >
            <option value="cuadro">Del banco de precios</option>
            <option value="alzada">Partida alzada (sin concepto)</option>
          </select>
        </Field>

        {modo === 'cuadro' ? (
          <>
            <div style={{ marginTop: 'var(--sp-4)' }}>
              <Field label="Buscar unitario">
                <input
                  className="input"
                  placeholder="Código o descripción…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  autoFocus
                />
              </Field>
            </div>
            <div className="lista-seleccion">
              {candidatos.length === 0 ? (
                <div className="muted" style={{ padding: 'var(--sp-3)' }}>
                  No hay unitarios en el banco de precios
                </div>
              ) : (
                candidatos.map((c) => (
                  <button
                    key={c.id}
                    className={
                      conceptoId === c.id
                        ? 'lista-seleccion__item is-activo'
                        : 'lista-seleccion__item'
                    }
                    onClick={() => setConceptoId(c.id)}
                  >
                    <span className="table__code">{c.codigo}</span>
                    <span className="lista-seleccion__texto">{c.resumen}</span>
                    <span className="chip chip--unitario">unitario</span>
                    <span className="table__num">
                      {formatoImporte(c.precio)} €/{c.unidad}
                    </span>
                  </button>
                ))
              )}
            </div>
            <p className="field__hint" style={{ marginTop: 'var(--sp-2)' }}>
              Se copian código, descripción, unidad y precio. La partida conserva esa copia
              aunque el cuadro cambie después.
            </p>
          </>
        ) : (
          <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
            <Field label="Código">
              <input className="input" value={codigo} onChange={(e) => setCodigo(e.target.value)} />
            </Field>
            <Field label="Descripción">
              <input
                className="input"
                value={resumen}
                onChange={(e) => setResumen(e.target.value)}
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
            <Field label="Precio">
              <input
                className="input"
                type="number"
                step="0.01"
                value={precio}
                onChange={(e) => setPrecio(e.target.value)}
              />
            </Field>
          </div>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={!listo} onClick={() => void guardar()}>
          <Plus size={16} aria-hidden="true" />
          Añadir
        </button>
      </div>
    </Modal>
  )
}

function MedicionModal({
  partida,
  onClose,
  onCambio,
}: {
  partida: Partida
  onClose: () => void
  onCambio: () => void
}) {
  return (
    <Modal title={`Medición · ${partida.codigo}`} onClose={onClose}>
      <div className="form-section">
        <MedicionesPanel partida={partida} onCambio={onCambio} />
      </div>

      <div className="form-actions">
        <button className="btn btn--primary" onClick={onClose}>
          <Check size={16} aria-hidden="true" />
          Hecho
        </button>
      </div>
    </Modal>
  )
}

/** Tabla de mediciones de una partida + acciones (añadir línea, leer plano
 *  con IA, campos libres) — sin cabecera modal propia, para poder vivir
 *  tanto dentro de `MedicionModal` como del widget "Mediciones" (Fase 31),
 *  que la muestra inline según la fila seleccionada en el listado. */
function MedicionesPanel({
  partida,
  onCambio,
}: {
  partida: Partida
  onCambio: () => void
}) {
  const { modules } = useWorkspace()
  const iaActiva = modules.some((m) => m.code === 'ia' && m.is_active)
  const [detalle, setDetalle] = useState<Awaited<
    ReturnType<typeof api.partidas.get>
  > | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [leyendoPlano, setLeyendoPlano] = useState(false)

  const recargar = useCallback(async () => {
    try {
      setDetalle(await api.partidas.get(partida.id))
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [partida.id, onCambio])

  useEffect(() => {
    void api.partidas
      .get(partida.id)
      .then(setDetalle)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [partida.id])

  async function anadir() {
    await api.partidas.addLinea(partida.id, { comentario: '', uds: '1' })
    await recargar()
  }

  return (
    <>
      <p className="form-section__note">
        {partida.resumen}. El parcial es el producto de lo que esté informado: una línea con
        solo unidades mide esas unidades. Un valor negativo deduce, que es como se descuentan
        los huecos.
      </p>
      <ErrorNotice error={error} />

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Comentario</th>
              <th className="table__num">Uds</th>
              <th className="table__num">Longitud</th>
              <th className="table__num">Anchura</th>
              <th className="table__num">Altura</th>
              <th className="table__num">Parcial</th>
              <th className="table__actions" />
            </tr>
          </thead>
          <tbody>
            {(detalle?.lineas ?? []).map((linea) => (
              <FilaMedicion key={linea.id} linea={linea} onCambio={recargar} />
            ))}
          </tbody>
          <tfoot>
            <tr className="fila-total">
              <td colSpan={5} className="table__num total-label">
                Medición total
              </td>
              <td className="table__num">
                <strong>{formatoImporte(detalle?.medicion ?? '0', 3)}</strong>
              </td>
              <td />
            </tr>
            <tr>
              <td colSpan={5} className="table__num total-label">
                × {formatoImporte(detalle?.precio ?? '0')} €/{partida.unidad}
              </td>
              <td className="table__num">
                <strong>{formatoImporte(detalle?.importe ?? '0')} €</strong>
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      <div style={{ display: 'flex', gap: 'var(--sp-2)', marginTop: 'var(--sp-3)' }}>
        <button className="btn" onClick={() => void anadir()}>
          <Plus size={16} aria-hidden="true" />
          Añadir línea
        </button>
        {iaActiva && (
          <Tooltip texto="Extraer mediciones de un plano acotado con IA">
            <button className="btn" onClick={() => setLeyendoPlano(true)}>
              <Scan size={16} aria-hidden="true" />
              Leer plano (IA)
            </button>
          </Tooltip>
        )}
      </div>

      <div style={{ marginTop: 'var(--sp-4)' }}>
        <CamposLibres entidad="partida" entidadId={partida.id} />
      </div>

      {leyendoPlano && (
        <LeerPlanoModal
          partida={partida}
          onClose={() => setLeyendoPlano(false)}
          onAplicado={() => {
            setLeyendoPlano(false)
            void recargar()
          }}
        />
      )}
    </>
  )
}

function LeerPlanoModal({
  partida,
  onClose,
  onAplicado,
}: {
  partida: Partida
  onClose: () => void
  onAplicado: () => void
}) {
  const [lectura, setLectura] = useState<LecturaPlanoDetalle | null>(null)
  const [lineas, setLineas] = useState<(LineaSugerida & { incluir: boolean })[]>([])
  const [error, setError] = useState<string | null>(null)
  const [leyendo, setLeyendo] = useState(false)
  const [aplicando, setAplicando] = useState(false)

  async function elegir(elegido: File | null) {
    setLectura(null)
    setError(null)
    if (!elegido) return

    setLeyendo(true)
    try {
      const resultado = await api.ia.mediciones.leer(partida.id, elegido)
      setLectura(resultado)
      setLineas(resultado.lineas.map((l) => ({ ...l, incluir: true })))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLeyendo(false)
    }
  }

  function editarLinea(
    indice: number,
    cambios: Partial<LineaSugerida & { incluir: boolean }>,
  ) {
    setLineas((actual) => actual.map((l, i) => (i !== indice ? l : { ...l, ...cambios })))
  }

  async function aplicar() {
    if (!lectura) return
    setAplicando(true)
    setError(null)
    try {
      await api.ia.mediciones.aplicar(
        lectura.id,
        lineas
          .filter((l) => l.incluir)
          .map(({ comentario, uds, longitud, anchura, altura }) => ({
            comentario,
            uds,
            longitud,
            anchura,
            altura,
          })),
      )
      onAplicado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setAplicando(false)
    }
  }

  return (
    <Modal title={`Leer plano · ${partida.codigo}`} onClose={onClose}>
      <div className="form-section">
        <p className="form-section__note">
          Sube un plano acotado (PDF, PNG, JPEG o WebP) para la partida «{partida.resumen}».
          Gemini propone líneas de medición a partir de las cotas del plano; nada se escribe
          hasta que revises y confirmes abajo.
        </p>
        <ErrorNotice error={error} />

        {!lectura && (
          <Field label="Plano">
            <input
              className="input"
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              onChange={(e) => void elegir(e.target.files?.[0] ?? null)}
            />
          </Field>
        )}
        {leyendo && <p className="muted">Analizando el plano con Gemini…</p>}

        {lectura && (
          <>
            {lectura.observaciones && (
              <div className="notice notice--aviso">{lectura.observaciones}</div>
            )}
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th />
                    <th>Comentario</th>
                    <th className="table__num">Uds</th>
                    <th className="table__num">Longitud</th>
                    <th className="table__num">Anchura</th>
                    <th className="table__num">Altura</th>
                    <th className="table__num">Parcial</th>
                  </tr>
                </thead>
                <tbody>
                  {lineas.map((linea, i) => (
                    <tr key={i}>
                      <td>
                        <input
                          type="checkbox"
                          checked={linea.incluir}
                          onChange={(e) => editarLinea(i, { incluir: e.target.checked })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          value={linea.comentario ?? ''}
                          onChange={(e) => editarLinea(i, { comentario: e.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          style={{ width: '70px' }}
                          value={linea.uds ?? ''}
                          onChange={(e) => editarLinea(i, { uds: e.target.value || null })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          style={{ width: '70px' }}
                          value={linea.longitud ?? ''}
                          onChange={(e) => editarLinea(i, { longitud: e.target.value || null })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          style={{ width: '70px' }}
                          value={linea.anchura ?? ''}
                          onChange={(e) => editarLinea(i, { anchura: e.target.value || null })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          style={{ width: '70px' }}
                          value={linea.altura ?? ''}
                          onChange={(e) => editarLinea(i, { altura: e.target.value || null })}
                        />
                      </td>
                      <td className="table__num muted">{formatoImporte(linea.parcial, 3)}</td>
                    </tr>
                  ))}
                  {lineas.length === 0 && (
                    <tr>
                      <td colSpan={7} className="muted">
                        Gemini no ha propuesto ninguna línea para esta partida
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        {lectura && (
          <button
            className="btn btn--primary"
            disabled={aplicando || lineas.every((l) => !l.incluir)}
            onClick={() => void aplicar()}
          >
            {!aplicando && <Check size={16} aria-hidden="true" />}
            {aplicando ? 'Aplicando…' : 'Aplicar seleccionadas'}
          </button>
        )}
      </div>
    </Modal>
  )
}

function FilaMedicion({
  linea,
  onCambio,
}: {
  linea: import('../lib/api').LineaMedicion
  onCambio: () => void
}) {
  const [valores, setValores] = useState({
    comentario: linea.comentario ?? '',
    uds: linea.uds ?? '',
    longitud: linea.longitud ?? '',
    anchura: linea.anchura ?? '',
    altura: linea.altura ?? '',
  })

  // Se guarda al salir del campo: cada guardado recalcula la partida y, con
  // ella, todos los totales del presupuesto.
  async function guardar() {
    await api.mediciones.update(linea.id, {
      comentario: valores.comentario || null,
      uds: valores.uds === '' ? null : valores.uds,
      longitud: valores.longitud === '' ? null : valores.longitud,
      anchura: valores.anchura === '' ? null : valores.anchura,
      altura: valores.altura === '' ? null : valores.altura,
    })
    onCambio()
  }

  async function eliminar() {
    await api.mediciones.remove(linea.id)
    onCambio()
  }

  const campo = (clave: keyof typeof valores) => (
    <input
      className="input input--celda"
      type={clave === 'comentario' ? 'text' : 'number'}
      step="0.001"
      value={valores[clave]}
      onChange={(e) => setValores((v) => ({ ...v, [clave]: e.target.value }))}
      onBlur={() => void guardar()}
    />
  )

  return (
    <tr>
      <td>
        <input
          className="input input--celda input--texto"
          value={valores.comentario}
          onChange={(e) => setValores((v) => ({ ...v, comentario: e.target.value }))}
          onBlur={() => void guardar()}
          placeholder="—"
        />
      </td>
      <td className="table__num">{campo('uds')}</td>
      <td className="table__num">{campo('longitud')}</td>
      <td className="table__num">{campo('anchura')}</td>
      <td className="table__num">{campo('altura')}</td>
      <td className="table__num">
        <strong>{formatoImporte(linea.parcial, 3)}</strong>
      </td>
      <td className="table__actions">
        <Tooltip texto="Eliminar esta línea de medición">
          <button
            className="btn btn--sm btn--danger btn--solo-icono"
            onClick={() => void eliminar()}
          >
            <Trash2 size={14} aria-hidden="true" />
          </button>
        </Tooltip>
      </td>
    </tr>
  )
}
