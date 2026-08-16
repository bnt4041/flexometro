import { createContext, useCallback, useContext, useRef, useState } from 'react'
import type { ReactNode } from 'react'

type TipoAviso = 'ok' | 'error'

interface Aviso {
  id: number
  mensaje: string
  tipo: TipoAviso
}

interface ToastContextValue {
  notificar: (mensaje: string, tipo?: TipoAviso) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const DURACION_MS = 4000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([])
  const siguienteId = useRef(0)

  const notificar = useCallback((mensaje: string, tipo: TipoAviso = 'ok') => {
    const id = siguienteId.current++
    setAvisos((actual) => [...actual, { id, mensaje, tipo }])
    setTimeout(() => {
      setAvisos((actual) => actual.filter((a) => a.id !== id))
    }, DURACION_MS)
  }, [])

  return (
    <ToastContext.Provider value={{ notificar }}>
      {children}
      <div className="toast-host">
        {avisos.map((a) => (
          <div key={a.id} className={`toast toast--${a.tipo}`} role="status">
            {a.mensaje}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

/** `notificar(mensaje)` — confirmación de que algo se ha guardado (fondo
 *  de la aplicación, no bloquea nada); `notificar(mensaje, 'error')` para
 *  un fallo que ya se explica en detalle en la propia pantalla (esto es
 *  solo el aviso de fondo, no sustituye a `ErrorNotice`). */
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast fuera de ToastProvider')
  return ctx
}
