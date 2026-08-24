import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Boxes,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Copy,
  ExternalLink,
  FolderPlus,
  Plus,
  Sparkles,
  Tags,
  Search,
  Trash2,
  Upload,
} from 'lucide-react'

import { BotonAtajos } from './AtajosTeclado'
import { AyudaIAModalBanco } from './AyudaIAModalBanco'
import { DocumentoIAModal } from './DocumentoIAModal'
import { ImportarBancoModal } from './ImportarBancoModal'
import type { ColumnaRejilla, ItemMenuContextual } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Modal, Tooltip, formatoImporte } from './ui'
import { ETIQUETA_NATURALEZA, api } from '../lib/api'
import type {
  ArbolBanco,
  CapituloBanco,
  ConceptoEnBanco,
  Familia,
  NaturalezaConcepto,
  TipoConcepto,
} from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'
import { copiarAlPortapapeles, leerPortapapeles } from '../lib/portapapeles'
import { useToast } from '../toast'
import { useWorkspace } from '../workspace'

/** Fila de la rejilla del banco: capítulos y fichas aplanados en una sola
 *  lista, igual que en un presupuesto. El árbol se reconstruye por `nivel`.
 *
 *  Recordatorio de la distinción que gobierna todo este fichero:
 *  `capituloId` = dónde está la ficha (estructura, se arrastra) y
 *  `familiaId` = qué es (clasificación, se asigna en masa). */
export interface FilaBanco {
  id: string
  tipo: 'capitulo' | 'ficha'
  nivel: number
  codigo: string
  resumen: string
  texto: string | null
  unidad: string
  precio: string
  precioVenta: string | null
  naturaleza: NaturalezaConcepto | null
  tipoConcepto: TipoConcepto | null
  familiaId: string | null
  padreId: string | null
  orden: number
  tieneDescompuesto: boolean
  activo: boolean
  concepto?: ConceptoEnBanco
  capitulo?: CapituloBanco
}

/** Fila sintética que representa el banco entero: sirve de destino para
 *  pegar o soltar "en la raíz" sin ningún caso especial. */
export const ID_RAIZ = '__raiz__'

export function RejillaBancoPrecios({
  arbol,
  familias,
  onCambio,
  onSeleccionar,
  seleccionadaId,
}: {
  arbol: ArbolBanco
  familias: Familia[]
  onCambio: () => void
  onSeleccionar?: (fila: FilaBanco | null) => void
  seleccionadaId?: string | null
}) {
  const navigate = useNavigate()
  const { notificar } = useToast()
  const { modules } = useWorkspace()
  const iaActiva = modules.some((m) => m.code === 'ia' && m.is_active)
  const unidadesMedida = useDiccionario('unidad_medida')

  const [error, setError] = useState<string | null>(null)
  // Los capítulos nacen PLEGADOS y sus fichas se piden al abrirlos: con un
  // banco de 12.000 fichas, traerlas y pintarlas todas colgaba el navegador.
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set())
  const [fichasPorCapitulo, setFichasPorCapitulo] = useState<Map<string, ConceptoEnBanco[]>>(
    new Map(),
  )
  const [busqueda, setBusqueda] = useState('')
  const [resultados, setResultados] = useState<ConceptoEnBanco[] | null>(null)
  const [totalResultados, setTotalResultados] = useState(0)
  const [filtros, setFiltros] = useState<Record<string, string>>({})
  const [marcadas, setMarcadas] = useState<string[]>([])
  const [asignandoFamilia, setAsignandoFamilia] = useState<string[] | null>(null)
  const [importando, setImportando] = useState<{ ficheros: File[]; capituloId: string | null } | null>(
    null,
  )
  const [documentoIA, setDocumentoIA] = useState<File[] | null>(null)
  const [ayudaIA, setAyudaIA] = useState<FilaBanco | null>(null)
  const inputFicheroRef = useRef<HTMLInputElement>(null)
  const filaParaSubir = useRef<FilaBanco | null>(null)
  const filaActiva = useRef<FilaBanco | null>(null)

  const LIMITE_PAGINA = 200

  /** Trae las fichas de un capítulo (clave "" = las que no tienen capítulo).
   *  Se cachean: volver a plegar y desplegar no vuelve a pedirlas. */
  const cargarFichas = useCallback(async (clave: string) => {
    try {
      const pagina = await api.banco.fichas(
        clave === ''
          ? { sin_capitulo: true, limit: LIMITE_PAGINA }
          : { capitulo_id: clave, limit: LIMITE_PAGINA },
      )
      setFichasPorCapitulo((previo) => new Map(previo).set(clave, pagina.items))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  // Las fichas sueltas (sin capítulo) se ven siempre, así que se piden al
  // entrar; las de cada capítulo, solo al abrirlo.
  useEffect(() => {
    void cargarFichas('')
  }, [cargarFichas, arbol])

  // Búsqueda contra el servidor, con freno: en un banco de 12.000 fichas no
  // se puede filtrar en el navegador porque no están todas cargadas.
  useEffect(() => {
    const termino = busqueda.trim()
    if (termino.length < 2) {
      setResultados(null)
      return
    }
    const id = setTimeout(() => {
      void api.banco
        .fichas({ q: termino, limit: LIMITE_PAGINA })
        .then((pagina) => {
          setResultados(pagina.items)
          setTotalResultados(pagina.total)
        })
        .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
    }, 300)
    return () => clearTimeout(id)
  }, [busqueda])

  async function alternarExpandido(id: string) {
    const abierto = expandidos.has(id)
    setExpandidos((previos) => {
      const nuevos = new Set(previos)
      if (abierto) nuevos.delete(id)
      else nuevos.add(id)
      return nuevos
    })
    if (!abierto && !fichasPorCapitulo.has(id)) await cargarFichas(id)
  }

  const filas = useMemo(
    () => construirFilas(arbol, fichasPorCapitulo, expandidos, resultados),
    [arbol, fichasPorCapitulo, expandidos, resultados],
  )
  const porId = useMemo(() => new Map(filas.map((f) => [f.id, f])), [filas])
  const familiaPorId = useMemo(() => new Map(familias.map((f) => [f.id, f])), [familias])

  // Valor "en bruto" por columna, para filtrar sin depender de `columnas`
  // (que se define más abajo y necesita los diccionarios cargados).
  function valorCrudoDe(f: FilaBanco, columnaId: string): string {
    switch (columnaId) {
      case 'tipo':
        return f.tipo === 'capitulo' ? 'capitulo' : (f.tipoConcepto ?? '')
      case 'codigo':
        return f.codigo
      case 'resumen':
        return f.resumen
      case 'unidad':
        return f.tipo === 'ficha' ? f.unidad : ''
      case 'naturaleza':
        return f.naturaleza ? ETIQUETA_NATURALEZA[f.naturaleza] : ''
      case 'familia':
        return f.familiaId ? (familiaPorId.get(f.familiaId)?.nombre ?? '') : ''
      case 'precio':
        return f.tipo === 'ficha' ? f.precio : ''
      case 'precio_venta':
        return f.tipo === 'ficha' ? (f.precioVenta ?? '') : ''
      default:
        return ''
    }
  }

  // Los filtros de columna afinan SOLO lo que ya está en pantalla (el
  // capítulo abierto, o los resultados de la búsqueda). Para buscar en todo
  // el banco está la caja de arriba, que pregunta al servidor: aquí no
  // están las 12.000 fichas, y fingir que se filtra sobre todas sería
  // mentir. Los capítulos nunca se ocultan, para no perder el árbol.
  const filtrosActivos = Object.entries(filtros).filter(([, v]) => v.trim() !== '')
  const filtrando = filtrosActivos.length > 0
  const filasVisibles = useMemo(() => {
    if (!filtrando) return filas
    const activos = filtrosActivos.map(([id, v]) => [id, v.trim().toLowerCase()] as const)
    return filas.filter(
      (f) =>
        f.tipo === 'capitulo' ||
        activos.every(([id, q]) => valorCrudoDe(f, id).toLowerCase().includes(q)),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filas, filtrando, filtros, familiaPorId])

  /** El capítulo donde caería algo soltado sobre esta fila: el propio si es
   *  capítulo, y si no el que la contiene. `null` = la raíz del banco. */
  function contenedorDe(fila: FilaBanco | null): string | null {
    if (!fila || fila.id === ID_RAIZ) return null
    return fila.tipo === 'capitulo' ? fila.id : fila.padreId
  }

  async function conError(accion: () => Promise<unknown>) {
    setError(null)
    try {
      await accion()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function nuevoCapitulo(padre: FilaBanco | null) {
    const parentId = contenedorDe(padre)
    await conError(() =>
      api.banco.crearCapitulo({ resumen: 'Capítulo nuevo', parent_id: parentId }),
    )
  }

  async function nuevaFicha(filaActual: FilaBanco | null) {
    const capituloId = contenedorDe(filaActual ?? filaActiva.current)
    await conError(async () => {
      const ficha = await api.conceptos.create({
        tipo: 'unitario',
        resumen: 'Ficha nueva',
        unidad: 'ud',
      })
      if (capituloId) await api.banco.mover([ficha.id], capituloId)
    })
  }

  async function alEditar(fila: FilaBanco, columnaId: string, valor: string) {
    if (fila.id === ID_RAIZ) return

    if (fila.tipo === 'capitulo') {
      const campo = columnaId === 'resumen' ? 'resumen' : columnaId === 'codigo' ? 'codigo' : null
      if (!campo) return
      await conError(() => api.banco.actualizarCapitulo(fila.id, { [campo]: valor }))
      return
    }

    // Las fichas se guardan una a una (no hay endpoint de tanda como en el
    // presupuesto): son menos y cada una recalcula su cascada de precios.
    const cambios: Record<string, unknown> = {}
    switch (columnaId) {
      case 'codigo':
        // El código lo genera el sistema y lo referencian los presupuestos:
        // cambiarlo desde aquí rompería más de lo que arregla.
        return
      case 'resumen':
        cambios.resumen = valor
        break
      case 'unidad':
        cambios.unidad = valor
        break
      case 'tipo':
        cambios.tipo = valor
        break
      case 'naturaleza':
        cambios.naturaleza = valor
        break
      case 'familia':
        // Individual: el mismo camino que la asignación masiva, con una sola
        // ficha — así no hay dos formas distintas de hacer lo mismo.
        await conError(() => api.banco.asignarFamilia([fila.id], valor || null))
        return
      case 'precio':
        cambios.precio = valor.replace(',', '.')
        break
      case 'precio_venta':
        cambios.precio_venta = valor.replace(',', '.') || null
        break
      default:
        return
    }
    await conError(() => api.conceptos.update(fila.id, cambios))
  }

  async function eliminarFila(fila: FilaBanco) {
    if (fila.id === ID_RAIZ) return
    const que = fila.tipo === 'capitulo' ? 'el capítulo' : 'la ficha'
    if (!window.confirm(`¿Eliminar ${que} «${fila.resumen}»? No se puede deshacer.`)) return
    await conError(() =>
      fila.tipo === 'capitulo'
        ? api.banco.eliminarCapitulo(fila.id)
        : api.conceptos.remove(fila.id),
    )
  }

  function copiar(ids: string[]) {
    const fichas = ids.filter((id) => porId.get(id)?.tipo === 'ficha')
    if (fichas.length === 0) return
    copiarAlPortapapeles({
      tipo: 'fichas_banco',
      ids: fichas,
      origenEtiqueta: 'el banco de precios',
    })
  }

  /** Soltar sobre una fila = mover las fichas arrastradas a ese capítulo.
   *  No se reordena dentro del capítulo con el borde (como sí hace el
   *  presupuesto): en el banco el orden natural es el del código, y mover
   *  entre capítulos es la operación que de verdad se usa. */
  async function soltarEn(destino: FilaBanco | null) {
    const portapapeles = leerPortapapeles()
    if (!portapapeles || portapapeles.tipo !== 'fichas_banco') return
    const capituloId = contenedorDe(destino)
    await conError(() => api.banco.mover(portapapeles.ids, capituloId))
  }

  function manejarFicheros(fila: FilaBanco, archivos: File[]) {
    const bc3: File[] = []
    const docs: File[] = []
    const rechazados: string[] = []
    for (const archivo of archivos) {
      const nombre = archivo.name.toLowerCase()
      if (nombre.endsWith('.bc3')) bc3.push(archivo)
      else if (
        archivo.type === 'application/pdf' ||
        nombre.endsWith('.pdf') ||
        archivo.type.startsWith('image/') ||
        nombre.endsWith('.xlsx')
      ) {
        docs.push(archivo)
      } else rechazados.push(archivo.name)
    }

    if (bc3.length > 0) setImportando({ ficheros: bc3, capituloId: contenedorDe(fila) })
    if (docs.length > 0) setDocumentoIA(docs)
    if (rechazados.length > 0) {
      notificar(`No se puede soltar aquí: ${rechazados.join(', ')} (solo BC3, PDF, imagen o Excel)`)
    }
  }

  function pedirFichero(fila: FilaBanco) {
    filaParaSubir.current = fila
    inputFicheroRef.current?.click()
  }

  function menuContextualDe(f: FilaBanco): ItemMenuContextual[] {
    const esRaiz = f.id === ID_RAIZ
    // Si hay varias marcadas y esta es una de ellas, el menú actúa sobre
    // todas — `RejillaEditable` conserva el marcado al hacer clic derecho
    // sobre una fila ya marcada, justo para esto.
    const objetivo = marcadas.length > 1 && marcadas.includes(f.id) ? marcadas : [f.id]
    const fichasObjetivo = objetivo.filter((id) => porId.get(id)?.tipo === 'ficha')
    const sufijo = fichasObjetivo.length > 1 ? ` (${fichasObjetivo.length})` : ''

    const items: ItemMenuContextual[] = []

    if (!esRaiz) {
      items.push({
        id: 'abrir',
        etiqueta: 'Abrir ficha',
        icono: <ExternalLink size={14} aria-hidden="true" />,
        onClick: () => navigate(`/banco-precios/${f.id}`),
        disabled: f.tipo === 'capitulo',
      })
      if (f.tipo === 'ficha') {
        items.push({
          id: 'copiar',
          etiqueta: `Copiar ficha${sufijo}`,
          icono: <Copy size={14} aria-hidden="true" />,
          onClick: () => copiar(objetivo),
        })
      }
    }

    items.push({
      id: 'pegar',
      etiqueta: esRaiz ? 'Pegar en la raíz' : 'Mover aquí lo copiado',
      icono: <Clipboard size={14} aria-hidden="true" />,
      onClick: () => void soltarEn(f),
      disabled: leerPortapapeles()?.tipo !== 'fichas_banco',
    })

    if (fichasObjetivo.length > 0) {
      items.push({
        id: 'familia',
        etiqueta: `Asignar familia${sufijo}…`,
        icono: <Tags size={14} aria-hidden="true" />,
        onClick: () => setAsignandoFamilia(fichasObjetivo),
      })
    }

    items.push({
      id: 'nuevo-capitulo',
      etiqueta: 'Añadir capítulo aquí',
      icono: <FolderPlus size={14} aria-hidden="true" />,
      onClick: () => void nuevoCapitulo(f),
    })

    if (iaActiva && f.tipo === 'ficha') {
      items.push({
        id: 'ia',
        etiqueta: 'Ayuda con IA',
        icono: <Sparkles size={14} aria-hidden="true" />,
        onClick: () => setAyudaIA(f),
      })
    }
    items.push({
      id: 'subir-fichero',
      etiqueta: 'Importar fichero (BC3, PDF o imagen)…',
      icono: <Upload size={14} aria-hidden="true" />,
      onClick: () => pedirFichero(f),
    })
    return items
  }

  const columnas: ColumnaRejilla<FilaBanco>[] = [
    {
      id: 'tipo',
      etiqueta: 'Tipo',
      ancho: '110px',
      tipo: 'select',
      valor: (f) =>
        f.id === ID_RAIZ ? 'banco' : f.tipo === 'capitulo' ? 'capitulo' : (f.tipoConcepto ?? ''),
      editable: (f) => f.tipo === 'ficha',
      opciones: () => [
        { valor: 'basico', etiqueta: 'Básico' },
        { valor: 'auxiliar', etiqueta: 'Auxiliar' },
        { valor: 'unitario', etiqueta: 'Unitario' },
      ],
    },
    {
      id: 'codigo',
      etiqueta: 'Código',
      ancho: '150px',
      valor: (f) => f.codigo,
      editable: (f) => f.tipo === 'capitulo',
      sangrada: true,
      prefijo: (f) =>
        f.tipo === 'capitulo' && f.id !== ID_RAIZ ? (
          <button
            className="rejilla__plegar"
            aria-label={expandidos.has(f.id) ? `Replegar ${f.resumen}` : `Expandir ${f.resumen}`}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              void alternarExpandido(f.id)
            }}
          >
            {expandidos.has(f.id) ? (
              <ChevronDown size={14} aria-hidden="true" />
            ) : (
              <ChevronRight size={14} aria-hidden="true" />
            )}
          </button>
        ) : null,
    },
    {
      id: 'resumen',
      etiqueta: 'Descripción',
      ancho: '280px',
      valor: (f) =>
        f.tipo === 'capitulo' && f.id !== ID_RAIZ
          ? `${f.resumen}  (${arbol.fichas_por_capitulo[f.id] ?? 0})`
          : f.resumen,
      editable: (f) => f.id !== ID_RAIZ,
      prefijo: (f) =>
        f.tipo === 'ficha' && f.tieneDescompuesto ? (
          <span className="rejilla__avisos">
            <Tooltip texto="Tiene descompuesto">
              <Boxes size={12} aria-hidden="true" className="rejilla__aviso" />
            </Tooltip>
          </span>
        ) : null,
    },
    {
      id: 'unidad',
      etiqueta: 'Ud.',
      ancho: '90px',
      tipo: 'select',
      valor: (f) => (f.tipo === 'ficha' ? f.unidad : ''),
      editable: (f) => f.tipo === 'ficha',
      opciones: () => unidadesMedida.map((u) => ({ valor: u.clave, etiqueta: u.etiqueta })),
    },
    {
      id: 'naturaleza',
      etiqueta: 'Naturaleza',
      ancho: '130px',
      tipo: 'select',
      valor: (f) => (f.naturaleza ? ETIQUETA_NATURALEZA[f.naturaleza] : ''),
      editable: (f) => f.tipo === 'ficha',
      opciones: () =>
        Object.entries(ETIQUETA_NATURALEZA).map(([valor, etiqueta]) => ({ valor, etiqueta })),
    },
    {
      id: 'familia',
      etiqueta: 'Familia',
      ancho: '150px',
      tipo: 'select',
      valor: (f) => (f.familiaId ? (familiaPorId.get(f.familiaId)?.nombre ?? '') : ''),
      editable: (f) => f.tipo === 'ficha',
      opciones: () => [
        { valor: '', etiqueta: 'Sin familia' },
        ...familias.map((fa) => ({ valor: fa.id, etiqueta: fa.nombre })),
      ],
    },
    {
      id: 'precio',
      etiqueta: 'Coste',
      ancho: '110px',
      tipo: 'numero',
      valor: (f) => (f.tipo === 'ficha' ? formatoImporte(f.precio) : ''),
      // Con descompuesto el precio es la suma de sus componentes: se edita
      // en el panel de descompuesto, no aquí.
      editable: (f) => f.tipo === 'ficha' && !f.tieneDescompuesto,
    },
    {
      id: 'precio_venta',
      etiqueta: 'Venta',
      ancho: '110px',
      tipo: 'numero',
      valor: (f) => (f.tipo === 'ficha' ? formatoImporte(f.precioVenta ?? '0') : ''),
      editable: (f) => f.tipo === 'ficha',
    },
  ]

  return (
    <>
      <div className="rejilla-barra">
        <BotonAtajos
          extra={[
            { teclas: 'Ctrl+clic / May+clic', hace: 'Marcar varias fichas para asignarles familia' },
          ]}
        />
        <span className="rejilla-barra__buscador">
          <Search size={14} aria-hidden="true" />
          <input
            className="input input--sm"
            type="search"
            placeholder={`Buscar en las ${arbol.total_fichas.toLocaleString('es-ES')} fichas…`}
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
          />
        </span>
        {resultados && (
          <span className="muted">
            {totalResultados > resultados.length
              ? `${resultados.length} de ${totalResultados.toLocaleString('es-ES')} — afina la búsqueda`
              : `${totalResultados} resultado${totalResultados === 1 ? '' : 's'}`}
          </span>
        )}
        {marcadas.length > 1 && (
          <Tooltip texto={`Asignar familia a las ${marcadas.length} fichas marcadas`}>
            <button
              className="btn btn--sm"
              onClick={() =>
                setAsignandoFamilia(marcadas.filter((id) => porId.get(id)?.tipo === 'ficha'))
              }
            >
              <Tags size={14} aria-hidden="true" />
              Familia ({marcadas.length})
            </button>
          </Tooltip>
        )}
        <span className="rejilla-barra__estado" />
        <Tooltip texto="Añadir una ficha en la raíz del banco">
          <button className="btn btn--sm" onClick={() => void nuevaFicha(null)}>
            <Plus size={14} aria-hidden="true" />
            Ficha
          </button>
        </Tooltip>
        <Tooltip texto="Añadir un capítulo en la raíz del banco">
          <button className="btn btn--sm" onClick={() => void nuevoCapitulo(null)}>
            <FolderPlus size={14} aria-hidden="true" />
            Capítulo
          </button>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      <RejillaEditable
        filas={filasVisibles}
        columnas={columnas}
        idDe={(f) => f.id}
        nivelDe={(f) => f.nivel}
        claseDe={(f) =>
          f.id === ID_RAIZ
            ? 'fila-capitulo fila-raiz'
            : f.tipo === 'capitulo'
              ? 'fila-capitulo'
              : f.activo
                ? ''
                : 'fila-inactiva'
        }
        onEditar={(f, col, valor) => void alEditar(f, col, valor)}
        onNuevaFila={nuevaFicha}
        onEliminarFila={(f) => void eliminarFila(f)}
        onSeleccionar={(f) => {
          filaActiva.current = f
          onSeleccionar?.(f)
        }}
        seleccionadaId={seleccionadaId}
        onMarcarVarias={setMarcadas}
        onCopiar={copiar}
        onPegar={() => void soltarEn(filaActiva.current)}
        onSoltarEn={(f) => void soltarEn(f)}
        puedeArrastrar={(f) => f.tipo === 'ficha'}
        onSoltarFichero={manejarFicheros}
        menuContextual={menuContextualDe}
        menuVacio={() => [
          {
            id: 'nuevo-capitulo',
            etiqueta: 'Añadir capítulo',
            icono: <FolderPlus size={14} aria-hidden="true" />,
            onClick: () => void nuevoCapitulo(null),
          },
        ]}
        filtros={filtros}
        onFiltrar={(columnaId, valor) => setFiltros((f) => ({ ...f, [columnaId]: valor }))}
        vacia={
          filtrando ? (
            <EmptyState title="Sin resultados">Nada coincide con los filtros.</EmptyState>
          ) : (
            <EmptyState title="Banco de precios vacío">
              Empieza creando un capítulo; dentro irán las fichas con su precio.
              <div style={{ marginTop: 'var(--sp-3)' }}>
                <button className="btn" onClick={() => void nuevoCapitulo(null)}>
                  <FolderPlus size={16} aria-hidden="true" />
                  Añadir capítulo
                </button>
              </div>
            </EmptyState>
          )
        }
        acciones={(f) =>
          f.id === ID_RAIZ ? (
            <Tooltip texto="Añadir un capítulo">
              <button
                className="btn btn--sm btn--solo-icono"
                aria-label="Añadir capítulo"
                onClick={() => void nuevoCapitulo(null)}
              >
                <FolderPlus size={14} aria-hidden="true" />
              </button>
            </Tooltip>
          ) : (
            <>
              {f.tipo === 'ficha' && (
                <Tooltip texto="Abrir la ficha completa">
                  <Link
                    className="btn btn--sm btn--solo-icono"
                    aria-label="Abrir ficha"
                    to={`/banco-precios/${f.id}`}
                  >
                    <ExternalLink size={14} aria-hidden="true" />
                  </Link>
                </Tooltip>
              )}
              <Tooltip texto={f.tipo === 'capitulo' ? 'Eliminar capítulo' : 'Eliminar ficha'}>
                <button
                  className="btn btn--sm btn--danger btn--solo-icono"
                  aria-label="Eliminar"
                  onClick={() => void eliminarFila(f)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            </>
          )
        }
      />

      <input
        ref={inputFicheroRef}
        type="file"
        multiple
        accept=".bc3,.xlsx,application/pdf,image/png,image/jpeg,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          const archivos = Array.from(e.target.files ?? [])
          if (archivos.length > 0 && filaParaSubir.current) {
            manejarFicheros(filaParaSubir.current, archivos)
          }
          e.target.value = ''
        }}
      />

      {asignandoFamilia && (
        <AsignarFamiliaModal
          conceptoIds={asignandoFamilia}
          familias={familias}
          onClose={() => setAsignandoFamilia(null)}
          onAsignada={() => {
            setAsignandoFamilia(null)
            onCambio()
          }}
        />
      )}

      {importando && (
        <ImportarBancoModal
          ficheros={importando.ficheros}
          capituloId={importando.capituloId}
          onClose={() => setImportando(null)}
          onImportado={() => {
            setImportando(null)
            onCambio()
          }}
        />
      )}

      {documentoIA && (
        <DocumentoIAModal
          ficheros={documentoIA}
          entidad="concepto"
          entidadId={filaParaSubir.current?.id ?? ''}
          onClose={() => setDocumentoIA(null)}
          onCambio={onCambio}
        />
      )}

      {ayudaIA && (
        <AyudaIAModalBanco
          conceptoId={ayudaIA.id}
          contexto={{ codigo: ayudaIA.codigo, resumen: ayudaIA.resumen, unidad: ayudaIA.unidad, precio: ayudaIA.precio }}
          onClose={() => setAyudaIA(null)}
          onCambio={onCambio}
        />
      )}
    </>
  )
}

/** Aplana lo que hay CARGADO: la fila raíz, los capítulos (con sus fichas
 *  solo si están abiertos) y las fichas sueltas. Con una búsqueda activa se
 *  devuelve la lista plana de resultados, sin árbol — buscar en un banco de
 *  12.000 fichas es justo lo contrario de navegar por capítulos. */
function construirFilas(
  arbol: ArbolBanco,
  fichasPorCapitulo: Map<string, ConceptoEnBanco[]>,
  expandidos: Set<string>,
  resultados: ConceptoEnBanco[] | null,
): FilaBanco[] {
  const filaDeFicha = (c: ConceptoEnBanco, nivel: number, padreId: string | null): FilaBanco => ({
    id: c.id,
    tipo: 'ficha',
    nivel,
    codigo: c.codigo,
    resumen: c.resumen,
    texto: c.texto,
    unidad: c.unidad,
    precio: c.precio,
    precioVenta: c.precio_venta,
    naturaleza: c.naturaleza,
    tipoConcepto: c.tipo,
    familiaId: c.familia_id,
    padreId,
    orden: c.orden,
    tieneDescompuesto: c.tiene_descompuesto,
    activo: c.activo,
    concepto: c,
  })

  if (resultados) return resultados.map((c) => filaDeFicha(c, 1, null))

  const filas: FilaBanco[] = [
    {
      id: ID_RAIZ,
      tipo: 'capitulo',
      nivel: 0,
      codigo: '',
      resumen: 'Banco de precios',
      texto: null,
      unidad: '',
      precio: '0',
      precioVenta: null,
      naturaleza: null,
      tipoConcepto: null,
      familiaId: null,
      padreId: null,
      orden: 0,
      tieneDescompuesto: false,
      activo: true,
    },
  ]

  const hijosDeCapitulo = new Map<string | null, CapituloBanco[]>()
  for (const capitulo of arbol.capitulos) {
    const lista = hijosDeCapitulo.get(capitulo.parent_id)
    if (lista) lista.push(capitulo)
    else hijosDeCapitulo.set(capitulo.parent_id, [capitulo])
  }

  // Iterativo con `vistos` por si la tabla tuviera un ciclo: mejor pintar de
  // menos que colgar el navegador dando vueltas.
  const vistos = new Set<string>()
  const aplanar = (parentId: string | null, nivel: number) => {
    for (const capitulo of hijosDeCapitulo.get(parentId) ?? []) {
      if (vistos.has(capitulo.id)) continue
      vistos.add(capitulo.id)
      filas.push({
        id: capitulo.id,
        tipo: 'capitulo',
        nivel,
        codigo: capitulo.codigo,
        resumen: capitulo.resumen,
        texto: capitulo.texto,
        unidad: '',
        precio: '0',
        precioVenta: null,
        naturaleza: null,
        tipoConcepto: null,
        familiaId: null,
        padreId: parentId ?? ID_RAIZ,
        orden: capitulo.orden,
        tieneDescompuesto: false,
        activo: true,
        capitulo,
      })
      if (expandidos.has(capitulo.id)) {
        for (const ficha of fichasPorCapitulo.get(capitulo.id) ?? []) {
          filas.push(filaDeFicha(ficha, nivel + 1, capitulo.id))
        }
        aplanar(capitulo.id, nivel + 1)
      }
    }
  }
  aplanar(null, 1)

  for (const suelta of fichasPorCapitulo.get('') ?? []) {
    filas.push(filaDeFicha(suelta, 1, ID_RAIZ))
  }

  return filas
}

function AsignarFamiliaModal({
  conceptoIds,
  familias,
  onClose,
  onAsignada,
}: {
  conceptoIds: string[]
  familias: Familia[]
  onClose: () => void
  onAsignada: () => void
}) {
  const [familiaId, setFamiliaId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.banco.asignarFamilia(conceptoIds, familiaId || null)
      onAsignada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal
      title={conceptoIds.length === 1 ? 'Asignar familia' : `Asignar familia a ${conceptoIds.length} fichas`}
      onClose={onClose}
    >
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          La familia clasifica la ficha (qué es); el capítulo dice dónde está guardada. Son cosas
          distintas: cambiar la familia no la mueve de sitio.
        </p>
        <select className="select" value={familiaId} onChange={(e) => setFamiliaId(e.target.value)}>
          <option value="">Sin familia</option>
          {familias.map((f) => (
            <option key={f.id} value={f.id}>
              {f.nombre}
            </option>
          ))}
        </select>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          {guardando ? 'Asignando…' : 'Asignar'}
        </button>
      </div>
    </Modal>
  )
}
