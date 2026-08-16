import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {children}
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}

export function Checkbox({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="checkbox">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  )
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  // Escape cierra el diálogo: en una pantalla de alta densidad, obligar a
  // apuntar a la equis para descartar un formulario molesta.
  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal__head">
          <span className="modal__title">{title}</span>
          <button className="modal__close" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

/** El modal "gigante" de alta/detalle: cubre el área principal entera (todo
 *  menos la barra lateral, que sigue navegable), a diferencia de `Modal`
 *  (diálogo pequeño centrado, para confirmaciones y subformularios cortos).
 *  Cada pantalla de lista lo monta sobre su propia ruta hija (`:id`,
 *  `nuevo`) vía `<Outlet/>`, así que tiene URL propia: se puede recargar o
 *  compartir el enlace y el modal reaparece solo. */
export function ModalPantalla({
  title,
  onClose,
  children,
}: {
  title: ReactNode
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [onClose])

  return (
    <div className="modal-pantalla-backdrop" onClick={onClose}>
      <div
        className="modal-pantalla"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-pantalla__head">
          <span className="modal-pantalla__title">{title}</span>
          <button className="modal-pantalla__close" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>
        <div className="modal-pantalla__body">
          <div className="content__inner">{children}</div>
        </div>
      </div>
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty__title">{title}</div>
      {children}
    </div>
  )
}

export function ErrorNotice({ error }: { error: string | null }) {
  if (!error) return null
  return <div className="notice notice--error">{error}</div>
}

export function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
}) {
  if (total <= limit) return null
  const desde = total === 0 ? 0 : offset + 1
  const hasta = Math.min(offset + limit, total)
  return (
    <div className="pager">
      <span>
        {desde}–{hasta} de {total}
      </span>
      <div className="pager__buttons">
        <button
          className="btn btn--sm"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Anterior
        </button>
        <button
          className="btn btn--sm"
          disabled={hasta >= total}
          onClick={() => onChange(offset + limit)}
        >
          Siguiente
        </button>
      </div>
    </div>
  )
}

/** Botón + campo de destinatario para probar una configuración SMTP YA
 *  GUARDADA (plataforma u organización, según qué `onProbar` se le pase) —
 *  enseña el error real del servidor si el envío falla, en vez de dejar
 *  que el primer aviso de eso sea un usuario real sin poder entrar. */
export function PruebaSmtpCard({
  onProbar,
}: {
  onProbar: (destinatario: string) => Promise<{ enviado: boolean; error: string | null }>
}) {
  const [destinatario, setDestinatario] = useState('')
  const [probando, setProbando] = useState(false)
  const [resultado, setResultado] = useState<{ enviado: boolean; error: string | null } | null>(
    null,
  )

  async function probar() {
    setProbando(true)
    setResultado(null)
    try {
      setResultado(await onProbar(destinatario))
    } catch (err) {
      setResultado({
        enviado: false,
        error: err instanceof Error ? err.message : 'Error desconocido',
      })
    } finally {
      setProbando(false)
    }
  }

  return (
    <div style={{ marginTop: 'var(--sp-4)' }}>
      <div className="form-section__title">Enviar correo de prueba</div>
      <p className="form-section__note">
        Prueba la configuración ya guardada — si acabas de cambiarla, guárdala antes de probar.
      </p>
      <div style={{ display: 'flex', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)' }}>
        <input
          className="input"
          type="email"
          placeholder="destinatario@ejemplo.com"
          value={destinatario}
          onChange={(e) => setDestinatario(e.target.value)}
        />
        <button
          className="btn"
          disabled={probando || destinatario.trim() === ''}
          onClick={() => void probar()}
        >
          {probando ? 'Enviando…' : 'Enviar prueba'}
        </button>
      </div>
      {resultado && (
        <div
          className={`notice ${resultado.enviado ? 'notice--ok' : 'notice--error'}`}
          style={{ marginTop: 'var(--sp-2)' }}
        >
          {resultado.enviado ? 'Correo de prueba enviado correctamente.' : resultado.error}
        </div>
      )}
    </div>
  )
}

/** Importe en formato español, con los decimales que se le pidan. */
export function formatoImporte(valor: string | number | null, decimales = 2): string {
  if (valor === null || valor === '') return '—'
  const numero = typeof valor === 'string' ? Number(valor) : valor
  if (Number.isNaN(numero)) return '—'
  return numero.toLocaleString('es-ES', {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  })
}
