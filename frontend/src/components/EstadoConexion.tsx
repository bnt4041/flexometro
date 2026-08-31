import { useEffect, useState } from 'react'
import { RefreshCw, WifiOff } from 'lucide-react'

import { alHaberVersionNueva } from '../lib/pwa'

/** Dos avisos que solo aparecen cuando hacen falta: sin conexión y hay
 *  versión nueva.
 *
 *  El de conexión importa más de lo que parece en esta aplicación: se usa en
 *  obra, donde la cobertura va y viene. Sin él, la pantalla se queda con los
 *  datos de hace un rato y nadie sabe si lo que ve es de ahora. */
export function EstadoConexion() {
  const [conectado, setConectado] = useState(() => navigator.onLine)
  const [versionNueva, setVersionNueva] = useState(false)

  useEffect(() => {
    const arriba = () => setConectado(true)
    const abajo = () => setConectado(false)
    window.addEventListener('online', arriba)
    window.addEventListener('offline', abajo)
    alHaberVersionNueva(setVersionNueva)
    return () => {
      window.removeEventListener('online', arriba)
      window.removeEventListener('offline', abajo)
    }
  }, [])

  if (conectado && !versionNueva) return null

  return (
    <div
      role="status"
      style={{
        position: 'fixed',
        left: '50%',
        transform: 'translateX(-50%)',
        bottom: 'var(--sp-4)',
        zIndex: 200,
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--sp-2)',
        padding: '8px 14px',
        borderRadius: 999,
        fontSize: '0.9em',
        color: '#fff',
        background: conectado ? 'var(--c-accent-strong, #f59e0b)' : 'var(--c-danger, #dc2626)',
        boxShadow: '0 4px 14px rgba(0,0,0,.25)',
      }}
    >
      {!conectado ? (
        <>
          <WifiOff size={15} aria-hidden="true" />
          Sin conexión. Lo que veas puede no estar al día.
        </>
      ) : (
        <>
          <RefreshCw size={15} aria-hidden="true" />
          Hay una versión nueva.
          <button
            className="btn btn--sm"
            onClick={() => window.location.reload()}
            style={{ marginLeft: 4 }}
          >
            Recargar
          </button>
        </>
      )}
    </div>
  )
}
