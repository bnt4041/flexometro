import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, Check, Send } from 'lucide-react'

import { Tooltip } from './ui'
import { api } from '../lib/api'
import type { Notificacion } from '../lib/api'
import { useToast } from '../toast'

/** Cada cuánto se pregunta por avisos nuevos. No hay WebSocket ni SSE en el
 *  proyecto y no compensa estrenarlos para esto: es un COUNT barato. */
const CADA_MS = 60_000

function haceCuanto(iso: string): string {
  const minutos = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutos < 1) return 'ahora mismo'
  if (minutos < 60) return `hace ${minutos} min`
  const horas = Math.round(minutos / 60)
  if (horas < 24) return `hace ${horas} h`
  return `hace ${Math.round(horas / 24)} d`
}

/** La bandeja de avisos de la barra superior.
 *
 *  Es la vía por la que a un proveedor que ya tiene Flexómetro le llega una
 *  solicitud de precios dentro de su propia aplicación, en vez de por un
 *  enlace de correo: al aceptarla se convierte en un presupuesto suyo. */
export function Campana() {
  const navegar = useNavigate()
  const { notificar } = useToast()
  const [pendientes, setPendientes] = useState(0)
  const [abierta, setAbierta] = useState(false)
  const [items, setItems] = useState<Notificacion[] | null>(null)
  const [aceptando, setAceptando] = useState<string | null>(null)
  const caja = useRef<HTMLDivElement>(null)

  const contar = useCallback(async () => {
    try {
      const { pendientes } = await api.notificaciones.contador()
      setPendientes(pendientes)
    } catch {
      // Un fallo de red no debe romper la barra superior: se reintenta al
      // siguiente sondeo.
    }
  }, [])

  useEffect(() => {
    void contar()
    const id = setInterval(() => void contar(), CADA_MS)
    return () => clearInterval(id)
  }, [contar])

  const cargar = useCallback(async () => {
    try {
      const lista = await api.notificaciones.list()
      setItems(lista)
      const sinLeer = lista.filter((n) => n.leida_en === null).map((n) => n.id)
      if (sinLeer.length > 0) {
        const { pendientes } = await api.notificaciones.marcarLeidas(sinLeer)
        setPendientes(pendientes)
      }
    } catch {
      setItems([])
    }
  }, [])

  function alternar() {
    const siguiente = !abierta
    setAbierta(siguiente)
    if (siguiente) void cargar()
  }

  // Cerrar al pulsar fuera, como el resto de menús de la aplicación.
  useEffect(() => {
    if (!abierta) return
    function fuera(e: MouseEvent) {
      if (caja.current && !caja.current.contains(e.target as Node)) setAbierta(false)
    }
    document.addEventListener('mousedown', fuera)
    return () => document.removeEventListener('mousedown', fuera)
  }, [abierta])

  async function devolver(n: Notificacion) {
    if (
      !window.confirm(
        'Se enviarán los precios de tu presupuesto a quien te los pidió, para que entren en ' +
          'su comparativo. ¿Continuar?',
      )
    ) {
      return
    }
    setAceptando(n.id)
    try {
      const { mensaje } = await api.notificaciones.devolver(n.id)
      notificar(mensaje)
      await cargar()
    } catch (err) {
      notificar(err instanceof Error ? err.message : 'Error desconocido', 'error')
    } finally {
      setAceptando(null)
    }
  }

  async function aceptar(n: Notificacion) {
    setAceptando(n.id)
    try {
      const { presupuesto_id, mensaje } = await api.notificaciones.aceptar(n.id)
      notificar(mensaje)
      setAbierta(false)
      await cargar()
      navegar(`/presupuestos/${presupuesto_id}`)
    } catch (err) {
      notificar(err instanceof Error ? err.message : 'Error desconocido', 'error')
    } finally {
      setAceptando(null)
    }
  }

  return (
    <div className="campana" ref={caja}>
      <Tooltip texto="Avisos">
        <button
          className="campana__boton"
          onClick={alternar}
          aria-label={pendientes > 0 ? `Avisos (${pendientes} sin leer)` : 'Avisos'}
          aria-expanded={abierta}
        >
          <Bell size={16} aria-hidden="true" />
          {pendientes > 0 && <span className="campana__contador">{pendientes}</span>}
        </button>
      </Tooltip>

      {abierta && (
        <div className="campana__panel" role="dialog" aria-label="Avisos">
          {items === null && <p className="muted">Cargando…</p>}
          {items?.length === 0 && <p className="muted">No hay avisos.</p>}
          {items?.map((n) => (
            <article key={n.id} className="campana__item">
              <p className="campana__titulo">
                {n.importante && <span className="badge badge--info">importante</span>}{' '}
                {n.titulo}
              </p>
              {n.cuerpo && <p className="muted">{n.cuerpo}</p>}
              <p className="muted campana__fecha">{haceCuanto(n.created_at)}</p>

              {n.tipo === 'solicitud_precios' &&
                (n.resuelta_en ? (
                  <div className="campana__acciones">
                    <button
                      className="btn btn--sm"
                      onClick={() => {
                        setAbierta(false)
                        if (n.presupuesto_id) navegar(`/presupuestos/${n.presupuesto_id}`)
                      }}
                    >
                      <Check size={14} aria-hidden="true" />
                      Ver el presupuesto
                    </button>
                    {n.enviada_en ? (
                      <span className="badge badge--success">oferta enviada</span>
                    ) : (
                      <button
                        className="btn btn--sm btn--primary"
                        disabled={aceptando === n.id}
                        onClick={() => void devolver(n)}
                      >
                        <Send size={14} aria-hidden="true" />
                        {aceptando === n.id ? 'Enviando…' : 'Enviar mi oferta'}
                      </button>
                    )}
                  </div>
                ) : (
                  <button
                    className="btn btn--sm btn--primary"
                    disabled={aceptando === n.id}
                    onClick={() => void aceptar(n)}
                  >
                    {aceptando === n.id ? 'Aceptando…' : 'Aceptar y crear presupuesto'}
                  </button>
                ))}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
