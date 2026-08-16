import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { ErrorNotice } from '../components/ui'
import { aplanar } from '../i18n/aplanar'
import { aplicarOverridesTraduccion } from '../i18n'
import { es } from '../i18n/es'
import { api } from '../lib/api'
import { useToast } from '../toast'

const BASE = aplanar(es)
const CLAVES = Object.keys(BASE).sort()

/** Autoservicio de personalización de textos (Fase 19) — el admin de
 *  organización reescribe cualquier clave de la interfaz para su cuenta.
 *  Lo que no se toca aquí se sigue viendo con el valor de fábrica de
 *  `i18n/es.ts`. */
export function AjustesTraduccion() {
  const { t } = useTranslation()
  const [overrides, setOverrides] = useState<Record<string, string>>({})
  const [busqueda, setBusqueda] = useState('')
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      const lista = await api.ajustes.traduccion.list()
      setOverrides(Object.fromEntries(lista.map((o) => [o.clave, o.texto])))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const filtro = busqueda.trim().toLowerCase()
  const clavesFiltradas = useMemo(
    () =>
      filtro
        ? CLAVES.filter(
            (c) =>
              c.toLowerCase().includes(filtro) ||
              BASE[c].toLowerCase().includes(filtro) ||
              (overrides[c] ?? '').toLowerCase().includes(filtro),
          )
        : CLAVES,
    [filtro, overrides],
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{t('ajustes.traduccion.titulo')}</h1>
          <p className="page-lead">{t('ajustes.traduccion.descripcionPantalla')}</p>
        </div>
        <Link className="btn" to="/ajustes">
          {t('ajustes.modulos.volverAAjustes')}
        </Link>
      </div>

      <div className="toolbar">
        <div className="toolbar__search">
          <input
            className="input"
            placeholder={t('ajustes.traduccion.buscar')}
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
          />
        </div>
      </div>

      <ErrorNotice error={error} />

      <div className="card">
        {clavesFiltradas.length === 0 ? (
          <div className="dicc-fila">
            <div className="module-row__desc">{t('comun.sinResultados')}.</div>
          </div>
        ) : (
          clavesFiltradas.map((clave) => (
            <FilaTraduccion
              key={clave}
              clave={clave}
              valorPorDefecto={BASE[clave]}
              override={overrides[clave]}
              onGuardado={(texto) => setOverrides((actual) => ({ ...actual, [clave]: texto }))}
              onRestablecido={() =>
                setOverrides((actual) => {
                  const { [clave]: _omitido, ...resto } = actual
                  return resto
                })
              }
            />
          ))
        )}
      </div>
    </>
  )
}

function FilaTraduccion({
  clave,
  valorPorDefecto,
  override,
  onGuardado,
  onRestablecido,
}: {
  clave: string
  valorPorDefecto: string
  override: string | undefined
  onGuardado: (texto: string) => void
  onRestablecido: () => void
}) {
  const { t } = useTranslation()
  const { notificar } = useToast()
  const [texto, setTexto] = useState(override ?? valorPorDefecto)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setTexto(override ?? valorPorDefecto)
  }, [override, valorPorDefecto])

  const tienePersonalizacion = override !== undefined
  const cambiado = texto !== (override ?? valorPorDefecto)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.ajustes.traduccion.establecer(clave, texto)
      onGuardado(texto)
      aplicarOverridesTraduccion({ [clave]: texto })
      notificar(t('ajustes.traduccion.guardadoToast'))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    } finally {
      setGuardando(false)
    }
  }

  async function restablecer() {
    setGuardando(true)
    setError(null)
    try {
      await api.ajustes.traduccion.eliminar(clave)
      onRestablecido()
      aplicarOverridesTraduccion({ [clave]: valorPorDefecto })
      notificar(t('ajustes.traduccion.restablecidoToast'))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="dicc-fila">
      <ErrorNotice error={error} />
      <span className="table__code dicc-fila__clave" style={{ minWidth: '16em' }} title={clave}>
        {clave}
      </span>
      <input
        className="input dicc-fila__etiqueta"
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
      />
      {tienePersonalizacion && <span className="badge">{t('ajustes.traduccion.personalizado')}</span>}
      <button className="btn btn--sm" disabled={!cambiado || guardando} onClick={() => void guardar()}>
        {guardando ? t('comun.guardando') : t('comun.guardar')}
      </button>
      {tienePersonalizacion && (
        <button className="btn btn--sm" disabled={guardando} onClick={() => void restablecer()}>
          {t('ajustes.traduccion.restablecer')}
        </button>
      )}
    </div>
  )
}
