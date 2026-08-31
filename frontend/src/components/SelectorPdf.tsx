import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, FileText, Search, Upload, X } from 'lucide-react'

import { api } from '../lib/api'
import type { Documento, DocumentoBusqueda, EntidadDocumento, FichaConDocumentos } from '../lib/api'

/** Nombre legible de cada tipo de ficha, para las ramas del árbol. Sin esto
 *  saldrían los valores crudos del enum (`factura_recibida`, `solicitud_precios`). */
const ETIQUETA_ENTIDAD: Record<EntidadDocumento, string> = {
  tercero: 'Terceros',
  contacto: 'Contactos',
  concepto: 'Banco de precios',
  presupuesto: 'Presupuestos',
  obra: 'Obras',
  certificacion: 'Certificaciones',
  factura: 'Facturas',
  solicitud_precios: 'Solicitudes de precios',
  pedido: 'Pedidos',
  contrato: 'Contratos',
  albaran: 'Albaranes',
  factura_recibida: 'Facturas recibidas',
  personal: 'Personal',
  recurso: 'Recursos',
  prl_empresa: 'PRL de empresa',
  solicitud_firma: 'Documentos firmados',
}

function tamano(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Zona de arrastrar y soltar un PDF.
 *
 *  Mantiene el `<input type="file">` por debajo en vez de sustituirlo: es lo
 *  que hace que se pueda seguir eligiendo con el teclado y con el diálogo del
 *  sistema. Arrastrar es un atajo encima, no el único camino. */
export function ZonaSoltarPdf({
  fichero,
  onFichero,
}: {
  fichero: File | null
  onFichero: (fichero: File | null) => void
}) {
  const entradaRef = useRef<HTMLInputElement>(null)
  const [encima, setEncima] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function aceptar(elegido: File | undefined) {
    if (!elegido) return
    if (elegido.type !== 'application/pdf') {
      setError(`«${elegido.name}» no es un PDF.`)
      return
    }
    setError(null)
    onFichero(elegido)
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setEncima(true)
        }}
        onDragLeave={() => setEncima(false)}
        onDrop={(e) => {
          e.preventDefault()
          setEncima(false)
          aceptar(e.dataTransfer.files?.[0])
        }}
        onClick={() => entradaRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            entradaRef.current?.click()
          }
        }}
        style={{
          border: `2px dashed ${encima ? 'var(--c-accent-strong)' : 'var(--c-border-strong)'}`,
          borderRadius: 'var(--radius)',
          padding: 'var(--sp-5)',
          textAlign: 'center',
          cursor: 'pointer',
          background: encima ? 'var(--c-surface-2)' : 'var(--c-surface)',
          transition: 'border-color 120ms ease, background 120ms ease',
        }}
      >
        {fichero ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--sp-3)' }}>
            <FileText size={20} aria-hidden="true" />
            <span>
              <strong>{fichero.name}</strong>{' '}
              <span className="muted">({tamano(fichero.size)})</span>
            </span>
            <button
              type="button"
              className="btn btn--sm"
              onClick={(e) => {
                e.stopPropagation()
                onFichero(null)
                if (entradaRef.current) entradaRef.current.value = ''
              }}
            >
              <X size={14} aria-hidden="true" /> Quitar
            </button>
          </div>
        ) : (
          <>
            <Upload size={24} aria-hidden="true" style={{ opacity: 0.6 }} />
            <div style={{ marginTop: 'var(--sp-2)' }}>
              <strong>Arrastra aquí el PDF</strong>
            </div>
            <div className="muted" style={{ fontSize: '0.9em' }}>
              o pulsa para elegirlo
            </div>
          </>
        )}
      </div>
      <input
        ref={entradaRef}
        type="file"
        accept="application/pdf"
        onChange={(e) => aceptar(e.target.files?.[0])}
        style={{ display: 'none' }}
      />
      {error && (
        <p className="notice notice--error" style={{ marginTop: 'var(--sp-2)' }}>
          {error}
        </p>
      )}
    </div>
  )
}

/** Biblioteca de documentos: árbol por ficha de origen + buscador.
 *
 *  Los dos, y no uno u otro, porque resuelven cosas distintas: el buscador
 *  vale cuando ya sabes cómo se llama el fichero, y el árbol cuando lo que
 *  sabes es de qué obra o de qué pedido venía — que es lo habitual al buscar
 *  algo que subió otra persona. */
export function BibliotecaPdf({
  elegido,
  onElegir,
}: {
  elegido: Documento | DocumentoBusqueda | null
  onElegir: (documento: Documento | DocumentoBusqueda | null) => void
}) {
  const [arbol, setArbol] = useState<FichaConDocumentos[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [abiertos, setAbiertos] = useState<Set<string>>(new Set())
  const [busqueda, setBusqueda] = useState('')
  const [resultados, setResultados] = useState<DocumentoBusqueda[] | null>(null)
  const [buscando, setBuscando] = useState(false)

  useEffect(() => {
    api.documentos
      .arbol({ content_type: 'application/pdf' })
      .then(setArbol)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
      .finally(() => setCargando(false))
  }, [])

  const buscar = useCallback(async () => {
    if (busqueda.trim().length < 2) {
      setResultados(null)
      return
    }
    setBuscando(true)
    try {
      const encontrados = await api.documentos.buscar(busqueda.trim())
      setResultados(encontrados.filter((d) => d.content_type === 'application/pdf'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBuscando(false)
    }
  }, [busqueda])

  // Agrupa las fichas por tipo, que es el primer nivel del árbol.
  const porTipo = new Map<EntidadDocumento, FichaConDocumentos[]>()
  for (const ficha of arbol) {
    const lista = porTipo.get(ficha.entidad) ?? []
    lista.push(ficha)
    porTipo.set(ficha.entidad, lista)
  }

  function alternar(clave: string) {
    setAbiertos((previo) => {
      const siguiente = new Set(previo)
      if (siguiente.has(clave)) siguiente.delete(clave)
      else siguiente.add(clave)
      return siguiente
    })
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
        <input
          className="input"
          value={busqueda}
          placeholder="Buscar por nombre de fichero…"
          onChange={(e) => {
            setBusqueda(e.target.value)
            if (e.target.value.trim().length < 2) setResultados(null)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              void buscar()
            }
          }}
        />
        <button type="button" className="btn" onClick={() => void buscar()} disabled={buscando}>
          <Search size={16} aria-hidden="true" /> {buscando ? 'Buscando…' : 'Buscar'}
        </button>
      </div>

      {elegido && (
        <p className="notice notice--ok" style={{ marginBottom: 'var(--sp-3)' }}>
          Elegido: <strong>{elegido.nombre_archivo}</strong>{' '}
          <button type="button" className="btn btn--sm" onClick={() => onElegir(null)}>
            <X size={14} aria-hidden="true" /> Quitar
          </button>
        </p>
      )}

      {error && <p className="notice notice--error">{error}</p>}

      <div
        style={{
          maxHeight: 260,
          overflowY: 'auto',
          border: '1px solid var(--c-border)',
          borderRadius: 'var(--radius)',
          padding: 'var(--sp-2)',
        }}
      >
        {resultados !== null ? (
          resultados.length === 0 ? (
            <p className="muted" style={{ margin: 'var(--sp-2)' }}>
              Ningún PDF con ese nombre.
            </p>
          ) : (
            resultados.map((documento) => (
              <FilaDocumento
                key={documento.id}
                nombre={documento.nombre_archivo}
                detalle={`${ETIQUETA_ENTIDAD[documento.entidad] ?? documento.entidad}${
                  documento.entidad_codigo ? ` · ${documento.entidad_codigo}` : ''
                }`}
                tam={documento.tamano_bytes}
                activo={elegido?.id === documento.id}
                onClick={() => onElegir(documento)}
              />
            ))
          )
        ) : cargando ? (
          <p className="muted" style={{ margin: 'var(--sp-2)' }}>
            Cargando la biblioteca…
          </p>
        ) : porTipo.size === 0 ? (
          <p className="muted" style={{ margin: 'var(--sp-2)' }}>
            No hay ningún PDF en la biblioteca todavía.
          </p>
        ) : (
          [...porTipo.entries()].map(([entidad, fichas]) => {
            const claveTipo = `tipo:${entidad}`
            const abiertoTipo = abiertos.has(claveTipo)
            const total = fichas.reduce((suma, f) => suma + f.documentos.length, 0)
            return (
              <div key={entidad}>
                <Rama
                  abierto={abiertoTipo}
                  etiqueta={ETIQUETA_ENTIDAD[entidad] ?? entidad}
                  contador={total}
                  nivel={0}
                  onClick={() => alternar(claveTipo)}
                />
                {abiertoTipo &&
                  fichas.map((ficha) => {
                    const claveFicha = `ficha:${ficha.entidad}:${ficha.entidad_id}`
                    const abiertaFicha = abiertos.has(claveFicha)
                    return (
                      <div key={ficha.entidad_id}>
                        <Rama
                          abierto={abiertaFicha}
                          etiqueta={ficha.entidad_codigo ?? 'Sin ficha asociada'}
                          contador={ficha.documentos.length}
                          nivel={1}
                          onClick={() => alternar(claveFicha)}
                        />
                        {abiertaFicha &&
                          ficha.documentos.map((documento) => (
                            <FilaDocumento
                              key={documento.id}
                              nombre={documento.nombre_archivo}
                              tam={documento.tamano_bytes}
                              nivel={2}
                              activo={elegido?.id === documento.id}
                              onClick={() => onElegir(documento)}
                            />
                          ))}
                      </div>
                    )
                  })}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

function Rama({
  abierto,
  etiqueta,
  contador,
  nivel,
  onClick,
}: {
  abierto: boolean
  etiqueta: string
  contador: number
  nivel: number
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--sp-2)',
        width: '100%',
        padding: '4px var(--sp-2)',
        paddingLeft: `calc(var(--sp-2) + ${nivel * 16}px)`,
        background: 'none',
        border: 'none',
        textAlign: 'left',
        cursor: 'pointer',
        color: 'var(--c-text)',
        fontWeight: nivel === 0 ? 600 : 400,
      }}
    >
      {abierto ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
      {etiqueta}
      <span className="muted" style={{ fontSize: '0.85em' }}>
        ({contador})
      </span>
    </button>
  )
}

function FilaDocumento({
  nombre,
  detalle,
  tam,
  nivel = 0,
  activo,
  onClick,
}: {
  nombre: string
  detalle?: string
  tam: number
  nivel?: number
  activo: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--sp-2)',
        width: '100%',
        padding: '4px var(--sp-2)',
        paddingLeft: `calc(var(--sp-2) + ${nivel * 16}px)`,
        background: activo ? 'var(--c-surface-2)' : 'none',
        border: 'none',
        borderRadius: 'var(--radius)',
        textAlign: 'left',
        cursor: 'pointer',
        color: 'var(--c-text)',
      }}
    >
      <FileText size={14} aria-hidden="true" style={{ flexShrink: 0, opacity: 0.7 }} />
      <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {nombre}
        {detalle && (
          <span className="muted" style={{ fontSize: '0.85em' }}>
            {' '}
            · {detalle}
          </span>
        )}
      </span>
      <span className="muted" style={{ fontSize: '0.8em', flexShrink: 0 }}>
        {tamano(tam)}
      </span>
    </button>
  )
}
