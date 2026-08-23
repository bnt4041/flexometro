import type { ReactNode } from 'react'
import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Icon } from './Icon'
import type { NombreIcono } from './Icon'
import { useSidebarColapsada } from '../lib/sidebarColapsada'

/** Pila de capas superpuestas (fichas y modales) para repartir el Escape.
 *
 *  Sin esto, una ficha y el modal que ella misma abre escuchan los dos el
 *  Escape en `window` y actúan a la vez: cierras el modal y de paso te echa de
 *  la ficha. Aquí solo responde la capa de arriba, y al cerrarse le devuelve el
 *  turno a la de debajo. */
const capas: object[] = []

export function useEscapeCierra(onClose: () => void): void {
  // El callback se guarda en una referencia para poder registrar la capa una
  // sola vez por montaje: si el efecto dependiera de `onClose`, un simple
  // repintado del padre reordenaría la pila y la capa de abajo robaría el turno.
  const alCerrar = useRef(onClose)
  alCerrar.current = onClose

  useEffect(() => {
    const capa = {}
    capas.push(capa)
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (capas[capas.length - 1] !== capa) return
      alCerrar.current()
    }
    window.addEventListener('keydown', alPulsar)
    return () => {
      window.removeEventListener('keydown', alPulsar)
      const i = capas.lastIndexOf(capa)
      if (i >= 0) capas.splice(i, 1)
    }
  }, [])
}

export function Field({
  label,
  hint,
  ancho,
  children,
}: {
  label: string
  hint?: string
  /** Cuánto ocupa dentro de un `.form-grid` (cuyas columnas son todas
   *  iguales): `doble` para lo que se teclea largo —un email, una dirección,
   *  un IBAN, una URL—, `completo` para un textarea que necesita la fila
   *  entera. Sin esto, un campo de una palabra y uno de sesenta caracteres
   *  salen del mismo ancho. */
  ancho?: 'doble' | 'completo'
  children: ReactNode
}) {
  const clase = ancho ? `field field--${ancho}` : 'field'
  return (
    <label className={clase}>
      <span className="field__label">{label}</span>
      {children}
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}

/** Popover explicativo al pasar el ratón (o el foco, por teclado) — Fase 26.
 *  Envuelve el elemento que lo dispara; no captura clics, solo hover/focus,
 *  así que no interfiere con el botón que rodea. */
export function Tooltip({
  texto,
  posicion = 'arriba',
  children,
}: {
  texto: string
  posicion?: 'arriba' | 'abajo'
  children: ReactNode
}) {
  const [visible, setVisible] = useState(false)
  const id = useId()

  return (
    <span
      className="tooltip-envoltorio"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span role="tooltip" id={id} className={`tooltip-globo tooltip-globo--${posicion}`}>
          {texto}
        </span>
      )}
    </span>
  )
}

/** Botón con icono + texto, y un tooltip que explica la acción al pasar el
 *  ratón por encima — Fase 26. `soloIcono` lo reduce a un botón cuadrado
 *  (para filas de tabla muy densas), pero el tooltip sigue dando el texto
 *  completo: un icono sin más nunca es autoexplicativo del todo. */
export function IconButton({
  icono,
  texto,
  tooltip,
  soloIcono = false,
  variante,
  tamano,
  onClick,
  disabled,
  type = 'button',
}: {
  icono: NombreIcono
  texto: string
  tooltip?: string
  soloIcono?: boolean
  variante?: 'primary' | 'danger'
  tamano?: 'sm'
  onClick?: () => void
  disabled?: boolean
  type?: 'button' | 'submit'
}) {
  const clases = [
    'btn',
    variante === 'primary' && 'btn--primary',
    variante === 'danger' && 'btn--danger',
    tamano === 'sm' && 'btn--sm',
    soloIcono && 'btn--solo-icono',
  ]
    .filter(Boolean)
    .join(' ')

  const boton = (
    <button
      type={type}
      className={clases}
      onClick={onClick}
      disabled={disabled}
      aria-label={soloIcono ? texto : undefined}
    >
      <Icon name={icono} />
      {!soloIcono && <span>{texto}</span>}
    </button>
  )

  return <Tooltip texto={tooltip ?? texto}>{boton}</Tooltip>
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

export interface AccionMenu {
  id: string
  etiqueta: string
  icono: NombreIcono
  onClick: () => void
  peligroso?: boolean
}

/** Botón "Acciones" con un desplegable de opciones — para agrupar
 *  editar/cambiar estado/eliminar (y lo que se añada después) en un solo
 *  sitio de la cabecera de una ficha, en vez de ir sumando botones sueltos.
 *  Se cierra al elegir una opción, al pulsar fuera o con Escape. */
export function MenuAcciones({
  acciones,
  etiqueta = 'Acciones',
  icono = 'mas-vertical',
}: {
  acciones: AccionMenu[]
  etiqueta?: string
  icono?: NombreIcono
}) {
  const [abierto, setAbierto] = useState(false)

  useEffect(() => {
    if (!abierto) return
    function alPulsarFuera(e: MouseEvent) {
      const nodo = e.target as Node
      if (!(nodo instanceof Element) || !nodo.closest('.menu-acciones')) setAbierto(false)
    }
    function alPulsarTecla(e: KeyboardEvent) {
      if (e.key === 'Escape') setAbierto(false)
    }
    document.addEventListener('mousedown', alPulsarFuera)
    document.addEventListener('keydown', alPulsarTecla)
    return () => {
      document.removeEventListener('mousedown', alPulsarFuera)
      document.removeEventListener('keydown', alPulsarTecla)
    }
  }, [abierto])

  return (
    <div className="menu-acciones">
      <button className="btn" onClick={() => setAbierto((v) => !v)} aria-haspopup="menu" aria-expanded={abierto}>
        <Icon name={icono} />
        {etiqueta}
      </button>
      {abierto && (
        <div className="menu-acciones__lista" role="menu">
          {acciones.map((a) => (
            <button
              key={a.id}
              role="menuitem"
              className={a.peligroso ? 'menu-acciones__item is-peligroso' : 'menu-acciones__item'}
              onClick={() => {
                setAbierto(false)
                a.onClick()
              }}
            >
              <Icon name={a.icono} size={16} />
              {a.etiqueta}
            </button>
          ))}
        </div>
      )}
    </div>
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
  // Ni Escape ni el clic fuera cierran esto: son formularios (alta/edición),
  // y perder lo escrito por un clic o una tecla sin querer es peor que la
  // incomodidad de tener que ir a la X o a "Cancelar" a propósito.

  // Portal a `document.body`: un widget con zoom (Fase 32) pone `transform:
  // scale()` en su contenido, y eso convierte a ese `div` en el "containing
  // block" de cualquier `position: fixed` de dentro — el backdrop deja de
  // cubrir la pantalla y el modal se recorta contra el borde del widget. El
  // portal saca el modal de esa jerarquía por completo.
  return createPortal(
    <div className="modal-backdrop">
      <div className="modal" role="dialog" aria-modal="true">
        <div className="modal__head">
          <span className="modal__title">{title}</span>
          <Tooltip texto="Cerrar">
            <button className="modal__close" onClick={onClose} aria-label="Cerrar">
              <Icon name="cerrar" />
            </button>
          </Tooltip>
        </div>
        {children}
      </div>
    </div>,
    document.body,
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
  useEscapeCierra(onClose)
  const [colapsada, alternarColapsada] = useSidebarColapsada()

  // Mismo motivo que en `Modal`: sacarlo de la jerarquía de un widget con
  // zoom (que pone `transform`) para que el `position: fixed` cubra la
  // pantalla entera y no se recorte contra el borde del widget.
  return createPortal(
    <div className="modal-pantalla-backdrop" onClick={onClose}>
      <div
        className="modal-pantalla"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-pantalla__head">
          <div className="modal-pantalla__head-izq">
            {/* La ficha tapa la topbar entera, así que su botón de recoger la
                barra lateral queda inalcanzable desde aquí dentro — este es
                el mismo interruptor (`sidebarColapsada.ts`), repetido en la
                cabecera de la ficha para que siga habiendo forma de llegar a
                él. */}
            <Tooltip texto={colapsada ? 'Mostrar el menú' : 'Ocultar el menú'} posicion="abajo">
              <button
                className="modal-pantalla__colapsar"
                onClick={alternarColapsada}
                aria-label={colapsada ? 'Mostrar el menú' : 'Ocultar el menú'}
                aria-expanded={!colapsada}
              >
                {colapsada ? (
                  <ChevronRight size={16} aria-hidden="true" />
                ) : (
                  <ChevronLeft size={16} aria-hidden="true" />
                )}
              </button>
            </Tooltip>
            <span className="modal-pantalla__title">{title}</span>
          </div>
          <Tooltip texto="Cerrar" posicion="abajo">
            <button className="modal-pantalla__close" onClick={onClose} aria-label="Cerrar">
              <Icon name="cerrar" />
            </button>
          </Tooltip>
        </div>
        <div className="modal-pantalla__body">{children}</div>
      </div>
    </div>,
    document.body,
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
          <ChevronLeft size={14} aria-hidden="true" />
          Anterior
        </button>
        <button
          className="btn btn--sm"
          disabled={hasta >= total}
          onClick={() => onChange(offset + limit)}
        >
          Siguiente
          <ChevronRight size={14} aria-hidden="true" />
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
