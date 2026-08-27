import { useCallback, useEffect, useState } from 'react'
import { Send } from 'lucide-react'

import { api } from '../lib/api'
import type { Notificacion } from '../lib/api'
import { useToast } from '../toast'

/** Aviso y botón para devolverle la oferta a quien pidió el precio.
 *
 *  Va en la propia ficha del presupuesto —y no solo en la campana— porque es
 *  aquí donde se trabaja: obligar a volver a buscar el aviso para mandarlo
 *  sería absurdo. No se pinta nada si el presupuesto no salió de una
 *  solicitud de otra empresa. */
export function DevolverOferta({ presupuestoId }: { presupuestoId: string }) {
  const { notificar } = useToast()
  const [aviso, setAviso] = useState<Notificacion | null>(null)
  const [enviando, setEnviando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setAviso(await api.notificaciones.porPresupuesto(presupuestoId))
    } catch {
      // Es un extra: si falla, la ficha sigue funcionando igual.
      setAviso(null)
    }
  }, [presupuestoId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  if (!aviso) return null

  async function enviar() {
    if (
      !window.confirm(
        'Se enviarán los precios de este presupuesto a quien te los pidió, para que entren ' +
          'en su comparativo. ¿Continuar?',
      )
    ) {
      return
    }
    setEnviando(true)
    try {
      const { mensaje } = await api.notificaciones.devolver(aviso!.id)
      notificar(mensaje)
      await cargar()
    } catch (err) {
      notificar(err instanceof Error ? err.message : 'Error desconocido', 'error')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="devolver-oferta">
      <div>
        <strong>{aviso.titulo}</strong>
        <div className="muted">
          {aviso.enviada_en
            ? 'Ya le enviaste tu oferta. Si cambias precios, puedes volver a enviarla.'
            : 'Cuando lo tengas valorado, envíaselo y entrará en su comparativo.'}
        </div>
      </div>
      <button className="btn btn--primary" disabled={enviando} onClick={() => void enviar()}>
        <Send size={16} aria-hidden="true" />
        {enviando ? 'Enviando…' : aviso.enviada_en ? 'Volver a enviar' : 'Enviar mi oferta'}
      </button>
    </div>
  )
}
