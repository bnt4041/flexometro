import { useEffect, useRef, useState } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'

import { pdfjs } from '../lib/pdfjs'

/** Lo mínimo que necesitamos de una tarea de render, sin arrastrar el tipo
 *  interno de pdf.js (que cambia de nombre entre versiones). */
type TareaRender = { promise: Promise<unknown>; cancel: () => void }

function PaginaPdf({
  documento,
  numero,
  ancho,
}: {
  documento: PDFDocumentProxy
  numero: number
  ancho: number
}) {
  const lienzoRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    let cancelado = false
    let tarea: TareaRender | null = null

    void (async () => {
      const pagina = await documento.getPage(numero)
      const canvas = lienzoRef.current
      if (cancelado || !canvas) return

      const base = pagina.getViewport({ scale: 1 })
      // Se pinta por encima de la densidad de pantalla (con tope, que si no
      // un A4 en un móvil moderno se va a decenas de megapíxeles) para que el
      // texto siga leyéndose al ampliar con los dedos.
      const densidad = Math.min(window.devicePixelRatio || 1, 2)
      const vista = pagina.getViewport({ scale: (ancho / base.width) * densidad })

      canvas.width = vista.width
      canvas.height = vista.height
      // El tamaño en CSS es el del contenedor: los píxeles de más son solo
      // resolución, no ocupan sitio en la página.
      canvas.style.width = `${ancho}px`
      canvas.style.height = `${ancho * (base.height / base.width)}px`

      const ctx = canvas.getContext('2d')
      if (!ctx) return
      tarea = pagina.render({ canvasContext: ctx, viewport: vista }) as TareaRender
      // Cancelar una tarea hace que su promesa reviente: es lo esperado al
      // desmontar o al cambiar de ancho, no un error que haya que enseñar.
      await tarea.promise.catch(() => undefined)
    })()

    return () => {
      cancelado = true
      tarea?.cancel()
    }
  }, [documento, numero, ancho])

  return (
    <canvas
      ref={lienzoRef}
      style={{ display: 'block', margin: '0 auto var(--sp-2)', borderRadius: 4 }}
    />
  )
}

/** Muestra un PDF pintándolo con pdf.js, en vez de delegar en el visor del
 *  navegador con `<object type="application/pdf">`.
 *
 *  La diferencia importa justo donde más duele: el navegador incrustado de
 *  Android (el que abre Gmail al pulsar un enlace de un correo) NO trae visor
 *  de PDF, así que con `<object>` el documento sale en blanco. En una pantalla
 *  de firma eso no es un fallo estético — significa que alguien puede acabar
 *  firmando algo que no ha llegado a ver, y la evidencia de «se le mostró el
 *  documento» sería falsa. Pintado a mano se ve igual en todas partes. */
export function VistaPdf({ url, alto = '60vh' }: { url: string; alto?: string }) {
  const contenedorRef = useRef<HTMLDivElement>(null)
  const [documento, setDocumento] = useState<PDFDocumentProxy | null>(null)
  const [error, setError] = useState(false)
  const [ancho, setAncho] = useState(0)

  useEffect(() => {
    let cancelado = false
    setError(false)
    setDocumento(null)
    const tarea = pdfjs.getDocument(url)
    tarea.promise
      .then((doc) => {
        if (cancelado) {
          void doc.destroy()
          return
        }
        setDocumento(doc)
      })
      .catch(() => {
        if (!cancelado) setError(true)
      })
    return () => {
      cancelado = true
      void tarea.destroy()
    }
  }, [url])

  // El ancho se mide del contenedor y se repinta al girar el móvil: pdf.js
  // pinta a un tamaño fijo, así que sin esto la página se quedaría a la
  // escala de la orientación anterior.
  useEffect(() => {
    const medir = () => setAncho(contenedorRef.current?.clientWidth ?? 0)
    medir()
    window.addEventListener('resize', medir)
    window.addEventListener('orientationchange', medir)
    return () => {
      window.removeEventListener('resize', medir)
      window.removeEventListener('orientationchange', medir)
    }
  }, [])

  return (
    <div
      style={{
        border: '1px solid var(--c-border)',
        borderRadius: 8,
        background: 'var(--c-surface-2)',
        maxHeight: alto,
        overflow: 'auto',
        padding: 'var(--sp-2)',
      }}
    >
      <div ref={contenedorRef}>
        {error ? (
          <p className="muted" style={{ padding: 'var(--sp-4)', textAlign: 'center' }}>
            No se ha podido cargar el documento. Prueba a recargar la página.
          </p>
        ) : !documento ? (
          <p className="muted" style={{ padding: 'var(--sp-4)', textAlign: 'center' }}>
            Cargando el documento…
          </p>
        ) : (
          ancho > 0 &&
          Array.from({ length: documento.numPages }, (_, i) => (
            <PaginaPdf key={i} documento={documento} numero={i + 1} ancho={ancho} />
          ))
        )}
      </div>
    </div>
  )
}
