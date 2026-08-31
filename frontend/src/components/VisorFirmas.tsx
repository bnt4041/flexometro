import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Trash2 } from 'lucide-react'
import type { PDFDocumentProxy } from 'pdfjs-dist'

import type { PosicionFirma } from '../lib/api'
import { pdfjs } from '../lib/pdfjs'

/** Proporción del recuadro de firma, en fracción del ancho/alto de página.
 *  Se coloca centrado en el punto donde se pulsa. */
const ANCHO_FIRMA = 0.26
const ALTO_FIRMA = 0.09

/** Visor de PDF para colocar dónde tiene que firmar el destinatario.
 *
 *  Las posiciones se guardan en FRACCIONES del tamaño de página (0 a 1), no
 *  en píxeles ni en puntos: el visor pinta a la escala que le quepa en
 *  pantalla, y el PDF final se sella en puntos reales. Guardar píxeles ataría
 *  la firma a la resolución con la que se colocó y la descuadraría en el
 *  documento definitivo. */
export function VisorFirmas({
  url,
  posiciones,
  onCambio,
}: {
  /** De dónde bajar el PDF. Puede ser un `blob:` de un fichero aún sin subir. */
  url: string
  posiciones: PosicionFirma[]
  onCambio: (posiciones: PosicionFirma[]) => void
}) {
  const lienzoRef = useRef<HTMLCanvasElement>(null)
  const contenedorRef = useRef<HTMLDivElement>(null)
  const documentoRef = useRef<PDFDocumentProxy | null>(null)
  /** El render de pdf.js es asíncrono: si se cambia de página dos veces
   *  seguidas, el render viejo puede terminar DESPUÉS y pintar la página que
   *  ya no toca. Este contador descarta los que llegan tarde. */
  const generacionRef = useRef(0)

  const [paginas, setPaginas] = useState(0)
  const [pagina, setPagina] = useState(0)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tamano, setTamano] = useState({ ancho: 0, alto: 0 })

  useEffect(() => {
    let cancelado = false
    setCargando(true)
    setError(null)
    const tarea = pdfjs.getDocument(url)
    tarea.promise
      .then((documento) => {
        if (cancelado) {
          void documento.destroy()
          return
        }
        documentoRef.current = documento
        setPaginas(documento.numPages)
        setPagina(0)
      })
      .catch(() => {
        if (!cancelado) setError('No se ha podido abrir el PDF para colocar las firmas.')
      })
      .finally(() => {
        if (!cancelado) setCargando(false)
      })
    return () => {
      cancelado = true
      void tarea.destroy()
      documentoRef.current = null
    }
  }, [url])

  const pintar = useCallback(async () => {
    const documento = documentoRef.current
    const canvas = lienzoRef.current
    const contenedor = contenedorRef.current
    if (!documento || !canvas || !contenedor) return

    const generacion = ++generacionRef.current
    const pag = await documento.getPage(pagina + 1)
    if (generacion !== generacionRef.current) return

    // Se escala para ocupar el ancho disponible, con tope para que una página
    // apaisada no se salga de la caja.
    const base = pag.getViewport({ scale: 1 })
    const escala = Math.min((contenedor.clientWidth || 600) / base.width, 1.6)
    const vista = pag.getViewport({ scale: escala })

    canvas.width = vista.width
    canvas.height = vista.height
    setTamano({ ancho: vista.width, alto: vista.height })

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    await pag.render({ canvasContext: ctx, viewport: vista }).promise
  }, [pagina])

  useEffect(() => {
    if (!cargando && paginas > 0) void pintar()
  }, [pintar, cargando, paginas])

  // Repintar al cambiar de tamaño la ventana: si no, el PDF se queda a la
  // escala vieja y las cajas de firma dejan de cuadrar con lo que se ve.
  useEffect(() => {
    const alRedimensionar = () => void pintar()
    window.addEventListener('resize', alRedimensionar)
    return () => window.removeEventListener('resize', alRedimensionar)
  }, [pintar])

  function colocar(e: React.MouseEvent<HTMLDivElement>) {
    if (tamano.ancho === 0) return
    const caja = e.currentTarget.getBoundingClientRect()
    // Centrada en el punto pulsado, y recortada para que no se salga.
    const x = Math.min(
      Math.max((e.clientX - caja.left) / caja.width - ANCHO_FIRMA / 2, 0),
      1 - ANCHO_FIRMA,
    )
    const y = Math.min(
      Math.max((e.clientY - caja.top) / caja.height - ALTO_FIRMA / 2, 0),
      1 - ALTO_FIRMA,
    )
    onCambio([...posiciones, { pagina, x, y, ancho: ANCHO_FIRMA, alto: ALTO_FIRMA }])
  }

  const deEstaPagina = posiciones
    .map((posicion, indice) => ({ posicion, indice }))
    .filter(({ posicion }) => posicion.pagina === pagina)

  if (error) return <p className="notice notice--error">{error}</p>
  if (cargando) return <p className="muted">Cargando el PDF…</p>

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 'var(--sp-2)',
          gap: 'var(--sp-3)',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => setPagina((p) => Math.max(0, p - 1))}
            disabled={pagina === 0}
          >
            <ChevronLeft size={14} aria-hidden="true" />
          </button>
          <span className="muted" style={{ fontSize: '0.9em' }}>
            Página {pagina + 1} de {paginas}
          </span>
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => setPagina((p) => Math.min(paginas - 1, p + 1))}
            disabled={pagina >= paginas - 1}
          >
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </div>
        <span className="muted" style={{ fontSize: '0.85em' }}>
          Pulsa donde tenga que firmar · {posiciones.length} firma(s) colocada(s)
        </span>
      </div>

      <div
        ref={contenedorRef}
        style={{
          border: '1px solid var(--c-border)',
          borderRadius: 'var(--radius)',
          overflow: 'auto',
          maxHeight: '55vh',
          background: 'var(--c-surface-2)',
          padding: 'var(--sp-2)',
        }}
      >
        <div
          onClick={colocar}
          style={{
            position: 'relative',
            width: tamano.ancho,
            height: tamano.alto,
            margin: '0 auto',
            cursor: 'crosshair',
          }}
        >
          <canvas ref={lienzoRef} style={{ display: 'block' }} />
          {deEstaPagina.map(({ posicion, indice }) => (
            <div
              key={indice}
              style={{
                position: 'absolute',
                left: `${posicion.x * 100}%`,
                top: `${posicion.y * 100}%`,
                width: `${posicion.ancho * 100}%`,
                height: `${posicion.alto * 100}%`,
                border: '2px dashed var(--c-accent-strong)',
                background: 'rgba(245,158,11,0.16)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.75em',
                color: 'var(--c-text)',
              }}
            >
              Firma
              <button
                type="button"
                aria-label="Quitar esta firma"
                onClick={(e) => {
                  // Sin esto, el clic llegaría al contenedor y colocaría otra
                  // firma justo encima de la que se acaba de quitar.
                  e.stopPropagation()
                  onCambio(posiciones.filter((_, i) => i !== indice))
                }}
                style={{
                  position: 'absolute',
                  top: -10,
                  right: -10,
                  width: 20,
                  height: 20,
                  borderRadius: '50%',
                  border: 'none',
                  background: 'var(--c-danger)',
                  color: '#fff',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: 0,
                }}
              >
                <Trash2 size={11} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {posiciones.length === 0 && (
        <p className="muted" style={{ fontSize: '0.85em', marginTop: 'var(--sp-2)' }}>
          Si no colocas ninguna, la firma irá solo en la hoja de evidencias del final.
        </p>
      )}
    </div>
  )
}
