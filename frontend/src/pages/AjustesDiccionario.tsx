import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { Checkbox, ErrorNotice, Field } from '../components/ui'
import { api } from '../lib/api'
import type { EntradaDiccionario, TipoDiccionario } from '../lib/api'
import { useToast } from '../toast'

const TIPOS_CON_VALOR: TipoDiccionario[] = ['iva', 'recargo_equivalencia', 'retencion']

/** Autoservicio del diccionario de referencia (Fase 18) — el admin de
 *  organización edita las entradas de su propia cuenta. `forma_pago`
 *  comparte claves con el enum del backend (ver `diccionario_models.py`):
 *  una clave nueva que nunca se use en un tercero no rompe nada, pero si se
 *  intenta usar y no coincide con el enum, la rechaza la base de datos. */
export function AjustesDiccionario() {
  const { t } = useTranslation()
  const etiquetaTipo: Record<TipoDiccionario, string> = {
    pais: t('ajustes.diccionario.paises'),
    forma_pago: t('ajustes.diccionario.formasDePago'),
    provincia: t('ajustes.diccionario.provincias'),
    unidad_medida: t('ajustes.diccionario.unidadesMedida'),
    forma_juridica: t('ajustes.diccionario.formasJuridicas'),
    tratamiento: t('ajustes.diccionario.tratamientos'),
    cargo: t('ajustes.diccionario.cargos'),
    iva: t('ajustes.diccionario.iva'),
    recargo_equivalencia: t('ajustes.diccionario.recargoEquivalencia'),
    retencion: t('ajustes.diccionario.retenciones'),
  }
  const NOTA_TIPO: Partial<Record<TipoDiccionario, string>> = {
    iva: t('ajustes.diccionario.notaIva'),
    recargo_equivalencia: t('ajustes.diccionario.notaRecargo'),
    retencion: t('ajustes.diccionario.notaRetencion'),
  }
  const [tipo, setTipo] = useState<TipoDiccionario>('pais')
  const [busqueda, setBusqueda] = useState('')
  const [entradas, setEntradas] = useState<EntradaDiccionario[]>([])
  const [error, setError] = useState<string | null>(null)
  const [creando, setCreando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setEntradas(await api.ajustes.diccionario.list(tipo))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tipo])

  useEffect(() => {
    setBusqueda('')
    void cargar()
  }, [cargar])

  const filtro = busqueda.trim().toLowerCase()
  const filtradas = filtro
    ? entradas.filter(
        (e) => e.clave.toLowerCase().includes(filtro) || e.etiqueta.toLowerCase().includes(filtro),
      )
    : entradas

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{t('ajustes.diccionario.titulo')}</h1>
          <p className="page-lead">{t('ajustes.diccionario.descripcionPantalla')}</p>
        </div>
        <Link className="btn" to="/ajustes">
          {t('ajustes.modulos.volverAAjustes')}
        </Link>
      </div>

      <div className="pestanas">
        {(Object.keys(etiquetaTipo) as TipoDiccionario[]).map((tipoTab) => (
          <button
            key={tipoTab}
            className={tipoTab === tipo ? 'pestanas__item is-activa' : 'pestanas__item'}
            onClick={() => setTipo(tipoTab)}
          >
            {etiquetaTipo[tipoTab]}
          </button>
        ))}
      </div>

      <div className="toolbar">
        <div className="toolbar__search">
          <input
            className="input"
            placeholder={t('ajustes.diccionario.buscar')}
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
          />
        </div>
        <button className="btn btn--primary" onClick={() => setCreando(true)}>
          {t('ajustes.diccionario.nuevaEntrada')}
        </button>
      </div>

      {NOTA_TIPO[tipo] && <div className="notice notice--aviso">{NOTA_TIPO[tipo]}</div>}

      <ErrorNotice error={error} />

      {creando && (
        <NuevaEntrada
          tipo={tipo}
          onCancelar={() => setCreando(false)}
          onCreada={(entrada) => {
            setCreando(false)
            setEntradas((actual) => [...actual, entrada])
          }}
        />
      )}

      <div className="card" style={{ marginTop: 'var(--sp-3)' }}>
        {filtradas.length === 0 ? (
          <div className="dicc-fila">
            <div className="module-row__desc">{t('comun.sinResultados')}.</div>
          </div>
        ) : (
          filtradas.map((entrada) => (
            <FilaEntrada
              key={entrada.id}
              tipo={tipo}
              entrada={entrada}
              onGuardada={(actualizada) =>
                setEntradas((actual) => actual.map((e) => (e.id === actualizada.id ? actualizada : e)))
              }
              onEliminada={() => setEntradas((actual) => actual.filter((e) => e.id !== entrada.id))}
            />
          ))
        )}
      </div>
    </>
  )
}

function NuevaEntrada({
  tipo,
  onCancelar,
  onCreada,
}: {
  tipo: TipoDiccionario
  onCancelar: () => void
  onCreada: (entrada: EntradaDiccionario) => void
}) {
  const { t } = useTranslation()
  const [clave, setClave] = useState('')
  const [etiqueta, setEtiqueta] = useState('')
  const [valor, setValor] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const conValor = TIPOS_CON_VALOR.includes(tipo)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const entrada = await api.ajustes.diccionario.create(tipo, {
        clave,
        etiqueta,
        valor: conValor && valor !== '' ? valor : null,
      })
      onCreada(entrada)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="card" style={{ padding: 'var(--sp-4)', marginTop: 'var(--sp-3)' }}>
      <ErrorNotice error={error} />
      <div className="form-grid">
        <Field label={t('ajustes.diccionario.clave')} hint={t('ajustes.diccionario.claveHint')}>
          <input className="input" value={clave} onChange={(e) => setClave(e.target.value)} autoFocus />
        </Field>
        <Field label={t('ajustes.diccionario.etiqueta')}>
          <input className="input" value={etiqueta} onChange={(e) => setEtiqueta(e.target.value)} />
        </Field>
        {conValor && (
          <Field label={t('ajustes.diccionario.valor')}>
            <input
              className="input"
              type="number"
              step="0.001"
              min="0"
              max="100"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
            />
          </Field>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onCancelar}>
          {t('comun.cancelar')}
        </button>
        <button
          className="btn btn--primary"
          disabled={guardando || clave.trim() === '' || etiqueta.trim() === ''}
          onClick={() => void guardar()}
        >
          {guardando ? t('comun.creando') : t('comun.crear')}
        </button>
      </div>
    </div>
  )
}

function FilaEntrada({
  tipo,
  entrada,
  onGuardada,
  onEliminada,
}: {
  tipo: TipoDiccionario
  entrada: EntradaDiccionario
  onGuardada: (actualizada: EntradaDiccionario) => void
  onEliminada: () => void
}) {
  const { t } = useTranslation()
  const { notificar } = useToast()
  const [etiqueta, setEtiqueta] = useState(entrada.etiqueta)
  const [valor, setValor] = useState(entrada.valor ?? '')
  const [activo, setActivo] = useState(entrada.activo)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const conValor = TIPOS_CON_VALOR.includes(tipo)

  const cambiado =
    etiqueta !== entrada.etiqueta || activo !== entrada.activo || (conValor && valor !== (entrada.valor ?? ''))

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const actualizada = await api.ajustes.diccionario.update(tipo, entrada.id, {
        etiqueta,
        activo,
        ...(conValor ? { valor: valor !== '' ? valor : null } : {}),
      })
      onGuardada(actualizada)
      notificar(t('ajustes.diccionario.guardadoToast', { etiqueta: actualizada.etiqueta }))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar() {
    if (!window.confirm(t('ajustes.diccionario.confirmarEliminar', { etiqueta: entrada.etiqueta }))) return
    try {
      await api.ajustes.diccionario.eliminar(tipo, entrada.id)
      onEliminada()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    }
  }

  return (
    <div className="dicc-fila">
      <ErrorNotice error={error} />
      <span className="table__code dicc-fila__clave">{entrada.clave}</span>
      <input
        className="input dicc-fila__etiqueta"
        value={etiqueta}
        onChange={(e) => setEtiqueta(e.target.value)}
      />
      {conValor && (
        <input
          className="input"
          style={{ maxWidth: '7em' }}
          type="number"
          step="0.001"
          min="0"
          max="100"
          value={valor}
          onChange={(e) => setValor(e.target.value)}
        />
      )}
      <Checkbox label={t('comun.activo')} checked={activo} onChange={setActivo} />
      <button
        className="btn btn--sm"
        disabled={!cambiado || guardando}
        onClick={() => void guardar()}
      >
        {guardando ? t('comun.guardando') : t('comun.guardar')}
      </button>
      <button className="btn btn--sm btn--danger" onClick={() => void eliminar()}>
        {t('comun.eliminar')}
      </button>
    </div>
  )
}
