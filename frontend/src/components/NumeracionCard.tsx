import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Save } from 'lucide-react'

import { Checkbox, ErrorNotice, Field } from './ui'
import { useToast } from '../toast'
import type { PatronNumeracion, TipoDocumentoNumeracion } from '../lib/api'

function useEtiquetaTipoDocumento() {
  const { t } = useTranslation()
  const etiquetas: Record<TipoDocumentoNumeracion, string> = {
    presupuesto: t('ajustes.numeracion.tipoPresupuesto'),
    albaran: t('ajustes.numeracion.tipoAlbaran'),
    factura: t('ajustes.numeracion.tipoFactura'),
  }
  return etiquetas
}

function Seccion({ titulo, nota, children }: { titulo: string; nota?: string; children: ReactNode }) {
  return (
    <>
      <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, margin: 'var(--sp-6) 0 var(--sp-3)' }}>
        {titulo}
      </h2>
      {nota && <p className="page-lead">{nota}</p>}
      {children}
    </>
  )
}

/** Editor del patrón de numeración del `codigo` interno de presupuestos,
 *  albaranes y facturas — nunca la serie/número fiscal de la factura, que
 *  sigue siempre las reglas legales de Veri*Factu. Reutilizado tanto por la
 *  ficha de cuenta del superadmin (`AdminCuentaDetalle`, todos los tipos)
 *  como por el autoservicio de ajustes de módulo (`AjustesModulo`, un solo
 *  tipo vía `soloTipos`) — cada uno inyecta sus propias llamadas a la API,
 *  ya que una vive bajo `/admin/cuentas/{id}/...` y la otra bajo
 *  `/ajustes/...` resuelta del lado del servidor. */
export function NumeracionCard({
  cifsDistintos,
  soloTipos,
  listar,
  actualizar,
  incluirTitulo = true,
}: {
  cifsDistintos: boolean
  /** Si se da, solo se muestran (y cargan) estos tipos de documento — para
   *  la pantalla de ajustes de un módulo concreto. */
  soloTipos?: TipoDocumentoNumeracion[]
  listar: () => Promise<PatronNumeracion[]>
  actualizar: (
    tipo: TipoDocumentoNumeracion,
    datos: { patron: string; secuencia_compartida: boolean },
  ) => Promise<PatronNumeracion>
  incluirTitulo?: boolean
}) {
  const { t } = useTranslation()
  const etiquetas = useEtiquetaTipoDocumento()
  const { notificar } = useToast()
  const [patrones, setPatrones] = useState<PatronNumeracion[]>([])
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      const todos = await listar()
      setPatrones(soloTipos ? todos.filter((p) => soloTipos.includes(p.tipo_documento)) : todos)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listar, soloTipos?.join(',')])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const contenido = (
    <>
      <ErrorNotice error={error} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
        {patrones.map((p) => (
          <FilaPatron
            key={p.tipo_documento}
            patron={p}
            cifsDistintos={cifsDistintos}
            actualizar={actualizar}
            onGuardado={async (actualizado) => {
              setPatrones((actual) =>
                actual.map((x) => (x.tipo_documento === actualizado.tipo_documento ? actualizado : x)),
              )
              notificar(
                t('ajustes.numeracion.guardado', {
                  tipo: etiquetas[actualizado.tipo_documento].toLowerCase(),
                }),
              )
            }}
          />
        ))}
      </div>
    </>
  )

  if (!incluirTitulo) return contenido

  return (
    <Seccion
      titulo={t('ajustes.numeracion.titulo')}
      nota={t('ajustes.numeracion.nota', { seq: '{SEQ:05d}', fecha: '{YYYY}/{YY}/{MM}/{DD}', org: '{ORG}' })}
    >
      {contenido}
    </Seccion>
  )
}

function FilaPatron({
  patron,
  cifsDistintos,
  actualizar,
  onGuardado,
}: {
  patron: PatronNumeracion
  cifsDistintos: boolean
  actualizar: (
    tipo: TipoDocumentoNumeracion,
    datos: { patron: string; secuencia_compartida: boolean },
  ) => Promise<PatronNumeracion>
  onGuardado: (actualizado: PatronNumeracion) => Promise<void>
}) {
  const { t } = useTranslation()
  const etiquetas = useEtiquetaTipoDocumento()
  const [valor, setValor] = useState(patron.patron)
  const [compartida, setCompartida] = useState(patron.secuencia_compartida)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cambiado = valor !== patron.patron || compartida !== patron.secuencia_compartida

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const actualizado = await actualizar(patron.tipo_documento, {
        patron: valor,
        secuencia_compartida: compartida,
      })
      await onGuardado(actualizado)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="card" style={{ padding: 'var(--sp-4)' }}>
      <ErrorNotice error={error} />
      <div className="form-grid">
        <Field ancho="doble" label={etiquetas[patron.tipo_documento]}>
          <input className="input" value={valor} onChange={(e) => setValor(e.target.value)} />
        </Field>
      </div>
      <div style={{ marginTop: 'var(--sp-3)' }}>
        <Checkbox
          label={t('ajustes.numeracion.secuenciaCompartida')}
          checked={compartida}
          onChange={setCompartida}
        />
      </div>
      {compartida && cifsDistintos && (
        <div className="notice notice--aviso" style={{ marginTop: 'var(--sp-2)' }}>
          {t('ajustes.numeracion.avisoCifsDistintos')}
        </div>
      )}
      <div className="form-actions">
        <button
          className="btn btn--primary"
          disabled={guardando || !cambiado || valor.trim() === ''}
          onClick={() => void guardar()}
        >
          {!guardando && <Save size={16} aria-hidden="true" />}
          {guardando ? t('comun.guardando') : t('comun.guardar')}
        </button>
      </div>
    </div>
  )
}
