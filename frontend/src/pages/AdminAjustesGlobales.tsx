import { useCallback, useEffect, useState } from 'react'
import { Save } from 'lucide-react'

import { ErrorNotice, Field, PruebaSmtpCard } from '../components/ui'
import { api } from '../lib/api'
import type { ConfiguracionIA, ConfiguracionPasarela, ConfiguracionSmtp } from '../lib/api'
import { useToast } from '../toast'

export function AdminAjustesGlobales() {
  return (
    <>
      <h1 className="page-title">Ajustes de la plataforma</h1>
      <p className="page-lead">
        Configuración global, no de una organización concreta: las claves de IA con las que
        paga la plataforma, el SMTP con el que envía su propio correo, y la pasarela de pago.
      </p>

      <AjustesIA />
      <AjustesSmtp />
      <AjustesPasarela />
    </>
  )
}

function AjustesIA() {
  const { notificar } = useToast()
  const [config, setConfig] = useState<ConfiguracionIA | null>(null)
  const [deepseekKey, setDeepseekKey] = useState('')
  const [deepseekModel, setDeepseekModel] = useState('')
  const [deepseekUrl, setDeepseekUrl] = useState('')
  const [geminiKey, setGeminiKey] = useState('')
  const [geminiModel, setGeminiModel] = useState('')
  const [geminiUrl, setGeminiUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const datos = await api.admin.ajustesIA.get()
      setConfig(datos)
      setDeepseekModel(datos.deepseek_model)
      setDeepseekUrl(datos.deepseek_base_url)
      setGeminiModel(datos.gemini_model)
      setGeminiUrl(datos.gemini_base_url)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.ajustesIA.update({
        deepseek_api_key: deepseekKey || undefined,
        deepseek_model: deepseekModel,
        deepseek_base_url: deepseekUrl,
        gemini_api_key: geminiKey || undefined,
        gemini_model: geminiModel,
        gemini_base_url: geminiUrl,
      })
      setDeepseekKey('')
      setGeminiKey('')
      await cargar()
      notificar('Ajustes de IA guardados')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  if (!config) return null

  return (
    <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-5)' }}>
      <div className="form-section__title">Ajustes IA</div>
      <ErrorNotice error={error} />
      <div className="form-grid" style={{ marginTop: 'var(--sp-3)' }}>
        <Field ancho="doble"
          label="DeepSeek — clave de API"
          hint={config.deepseek_configurada ? 'Configurada (deja en blanco para no cambiarla)' : 'Sin configurar'}
        >
          <input
            className="input"
            type="password"
            value={deepseekKey}
            onChange={(e) => setDeepseekKey(e.target.value)}
            placeholder={config.deepseek_configurada ? '••••••••' : 'sk-…'}
          />
        </Field>
        <Field label="DeepSeek — modelo">
          <input className="input" value={deepseekModel} onChange={(e) => setDeepseekModel(e.target.value)} />
        </Field>
        <Field ancho="doble" label="DeepSeek — base URL">
          <input className="input" value={deepseekUrl} onChange={(e) => setDeepseekUrl(e.target.value)} />
        </Field>
        <Field ancho="doble"
          label="Gemini — clave de API"
          hint={config.gemini_configurada ? 'Configurada (deja en blanco para no cambiarla)' : 'Sin configurar'}
        >
          <input
            className="input"
            type="password"
            value={geminiKey}
            onChange={(e) => setGeminiKey(e.target.value)}
            placeholder={config.gemini_configurada ? '••••••••' : 'AQ.…'}
          />
        </Field>
        <Field label="Gemini — modelo">
          <input className="input" value={geminiModel} onChange={(e) => setGeminiModel(e.target.value)} />
        </Field>
        <Field ancho="doble" label="Gemini — base URL">
          <input className="input" value={geminiUrl} onChange={(e) => setGeminiUrl(e.target.value)} />
        </Field>
      </div>
      <div className="form-actions">
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          {!guardando && <Save size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </div>
  )
}

function AjustesSmtp() {
  const { notificar } = useToast()
  const [config, setConfig] = useState<ConfiguracionSmtp | null>(null)
  const [host, setHost] = useState('')
  const [puerto, setPuerto] = useState('587')
  const [usuario, setUsuario] = useState('')
  const [password, setPassword] = useState('')
  const [remitente, setRemitente] = useState('')
  const [usaTls, setUsaTls] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const datos = await api.admin.ajustesSmtp.get()
      setConfig(datos)
      setHost(datos.host ?? '')
      setPuerto(String(datos.puerto))
      setUsuario(datos.usuario ?? '')
      setRemitente(datos.remitente ?? '')
      setUsaTls(datos.usa_tls)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.ajustesSmtp.update({
        host,
        puerto: Number(puerto),
        usuario,
        password: password || undefined,
        remitente,
        usa_tls: usaTls,
      })
      setPassword('')
      await cargar()
      notificar('SMTP de la plataforma guardado')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  if (!config) return null

  return (
    <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-5)' }}>
      <div className="form-section__title">SMTP de ERP Flexómetro</div>
      <p className="form-section__note">
        Con este SMTP se envían los correos de la propia plataforma — por ejemplo, la
        bienvenida al crear el administrador de una organización nueva.
      </p>
      <ErrorNotice error={error} />
      <div className="form-grid" style={{ marginTop: 'var(--sp-3)' }}>
        <Field label="Host">
          <input className="input" value={host} onChange={(e) => setHost(e.target.value)} />
        </Field>
        <Field label="Puerto">
          <input className="input" value={puerto} onChange={(e) => setPuerto(e.target.value)} />
        </Field>
        <Field label="Usuario">
          <input className="input" value={usuario} onChange={(e) => setUsuario(e.target.value)} />
        </Field>
        <Field
          label="Contraseña"
          hint={config.tiene_password ? 'Configurada (deja en blanco para no cambiarla)' : 'Sin configurar'}
        >
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={config.tiene_password ? '••••••••' : ''}
          />
        </Field>
        <Field ancho="doble" label="Remitente">
          <input className="input" value={remitente} onChange={(e) => setRemitente(e.target.value)} />
        </Field>
        <Field label="Usa TLS">
          <select className="select" value={usaTls ? 'si' : 'no'} onChange={(e) => setUsaTls(e.target.value === 'si')}>
            <option value="si">Sí</option>
            <option value="no">No</option>
          </select>
        </Field>
      </div>
      <div className="form-actions">
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          {!guardando && <Save size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
      <PruebaSmtpCard onProbar={(destinatario) => api.admin.ajustesSmtp.probar(destinatario)} />
    </div>
  )
}

function AjustesPasarela() {
  const { notificar } = useToast()
  const [config, setConfig] = useState<ConfiguracionPasarela | null>(null)
  const [vendorId, setVendorId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [activa, setActiva] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const datos = await api.admin.pasarelaPago.get()
      setConfig(datos)
      setVendorId(datos.vendor_id ?? '')
      setActiva(datos.activa)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.pasarelaPago.update({
        vendor_id: vendorId,
        api_key: apiKey || undefined,
        activa,
      })
      setApiKey('')
      await cargar()
      notificar('Pasarela de pago guardada')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  if (!config) return null

  return (
    <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-5)' }}>
      <div className="form-section__title">Pasarela de pago (Paddle)</div>
      <p className="form-section__note">
        Preparado para cuando se conecte de verdad: hoy solo se guardan las credenciales, sin
        llamar todavía a la API real de Paddle.
      </p>
      <ErrorNotice error={error} />
      <div className="form-grid" style={{ marginTop: 'var(--sp-3)' }}>
        <Field label="Vendor ID">
          <input className="input" value={vendorId} onChange={(e) => setVendorId(e.target.value)} />
        </Field>
        <Field ancho="doble"
          label="API key"
          hint={config.tiene_api_key ? 'Configurada (deja en blanco para no cambiarla)' : 'Sin configurar'}
        >
          <input
            className="input"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={config.tiene_api_key ? '••••••••' : ''}
          />
        </Field>
        <Field label="Activa">
          <select className="select" value={activa ? 'si' : 'no'} onChange={(e) => setActiva(e.target.value === 'si')}>
            <option value="no">No</option>
            <option value="si">Sí</option>
          </select>
        </Field>
      </div>
      <div className="form-actions">
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          {!guardando && <Save size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </div>
  )
}
