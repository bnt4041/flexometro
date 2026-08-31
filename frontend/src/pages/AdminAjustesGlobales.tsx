import { useCallback, useEffect, useState } from 'react'
import { Save } from 'lucide-react'

import { ErrorNotice, Field, PruebaSmtpCard } from '../components/ui'
import { api } from '../lib/api'
import type {
  ConfiguracionIA,
  ConfiguracionPasarela,
  ConfiguracionSmtp,
  ConfiguracionWhatsApp,
  ProveedorWhatsApp,
  QrVinculacion,
  VinculacionWhatsApp,
} from '../lib/api'
import { useToast } from '../toast'

export function AdminAjustesGlobales() {
  return (
    <>
      <h1 className="page-title">Ajustes de la plataforma</h1>
      <p className="page-lead">
        Configuración global, no de una organización concreta: las claves de IA con las que
        paga la plataforma, el SMTP y el WhatsApp con los que envía, y la pasarela de pago.
      </p>

      <AjustesIA />
      <AjustesSmtp />
      <AjustesWhatsapp />
      <AjustesPasarela />
    </>
  )
}

function AjustesIA() {
  const { notificar } = useToast()
  const [config, setConfig] = useState<ConfiguracionIA | null>(null)
  const [deepseekKey, setDeepseekKey] = useState('')
  const [deepseekModel, setDeepseekModel] = useState('')
  const [deepseekVisionModel, setDeepseekVisionModel] = useState('')
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
      setDeepseekVisionModel(datos.deepseek_vision_model)
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
        deepseek_vision_model: deepseekVisionModel,
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
        <Field label="DeepSeek — modelo de visión" hint="Misma clave y base URL que el de texto">
          <input
            className="input"
            value={deepseekVisionModel}
            onChange={(e) => setDeepseekVisionModel(e.target.value)}
          />
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

function AjustesWhatsapp() {
  const { notificar } = useToast()
  const [config, setConfig] = useState<ConfiguracionWhatsApp | null>(null)
  const [proveedor, setProveedor] = useState<ProveedorWhatsApp>('gowa')
  const [activa, setActiva] = useState(false)
  const [prefijo, setPrefijo] = useState('34')
  const [baseUrl, setBaseUrl] = useState('')
  const [usuario, setUsuario] = useState('')
  const [password, setPassword] = useState('')
  const [deviceId, setDeviceId] = useState('')
  const [phoneNumberId, setPhoneNumberId] = useState('')
  const [cloudToken, setCloudToken] = useState('')
  const [cloudVersion, setCloudVersion] = useState('v21.0')
  const [plantillaAviso, setPlantillaAviso] = useState('')
  const [plantillaCodigo, setPlantillaCodigo] = useState('')
  const [idiomaPlantilla, setIdiomaPlantilla] = useState('es')
  const [vinculacion, setVinculacion] = useState<VinculacionWhatsApp | null>(null)
  const [qr, setQr] = useState<QrVinculacion | null>(null)
  const [restan, setRestan] = useState(0)
  const [vinculando, setVinculando] = useState(false)
  const [telefonoPrueba, setTelefonoPrueba] = useState('')
  const [probando, setProbando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const datos = await api.admin.ajustesWhatsapp.get()
      setConfig(datos)
      setProveedor(datos.proveedor)
      setActiva(datos.activa)
      setPrefijo(datos.prefijo_pais)
      setBaseUrl(datos.base_url ?? '')
      setUsuario(datos.usuario ?? '')
      setDeviceId(datos.device_id ?? '')
      setPhoneNumberId(datos.cloud_phone_number_id ?? '')
      setCloudVersion(datos.cloud_version)
      setPlantillaAviso(datos.plantilla_aviso ?? '')
      setPlantillaCodigo(datos.plantilla_codigo ?? '')
      setIdiomaPlantilla(datos.idioma_plantilla)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  const cargarVinculacion = useCallback(async () => {
    try {
      setVinculacion(await api.admin.ajustesWhatsapp.vinculacion())
    } catch {
      // No poder preguntar por el emparejamiento no puede impedir tocar el
      // resto de ajustes: se queda sin dato y ya está.
      setVinculacion(null)
    }
  }, [])

  useEffect(() => {
    void cargar()
    void cargarVinculacion()
  }, [cargar, cargarVinculacion])

  const pedirQr = useCallback(async () => {
    setVinculando(true)
    setError(null)
    try {
      const nuevo = await api.admin.ajustesWhatsapp.vincular()
      setQr(nuevo)
      setRestan(nuevo.segundos)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setQr(null)
    } finally {
      setVinculando(false)
    }
  }, [])

  // Mientras el QR está en pantalla: cuenta atrás y comprobación de si ya lo
  // han escaneado. Sin el sondeo habría que recargar a mano para enterarse.
  useEffect(() => {
    if (!qr) return
    const tic = window.setInterval(() => setRestan((s) => s - 1), 1000)
    const sondeo = window.setInterval(() => {
      void api.admin.ajustesWhatsapp
        .vinculacion()
        .then((estado) => {
          if (!estado.vinculado) return
          setVinculacion(estado)
          setQr(null)
        })
        .catch(() => undefined)
    }, 3000)
    return () => {
      window.clearInterval(tic)
      window.clearInterval(sondeo)
    }
  }, [qr])

  // WhatsApp rota los códigos cada pocos segundos: cuando caduca se pide otro
  // solo, que es lo que espera quien está delante con el móvil en la mano.
  useEffect(() => {
    if (qr && restan <= 0) void pedirQr()
  }, [qr, restan, pedirQr])

  async function desvincular() {
    setError(null)
    try {
      setVinculacion(await api.admin.ajustesWhatsapp.desvincular())
      setQr(null)
      notificar('Móvil desvinculado')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.ajustesWhatsapp.update({
        proveedor,
        activa,
        prefijo_pais: prefijo,
        base_url: baseUrl,
        usuario,
        // Vacío = no tocar la que ya hay, igual que en el SMTP.
        password: password || undefined,
        device_id: deviceId,
        cloud_phone_number_id: phoneNumberId,
        cloud_token: cloudToken || undefined,
        cloud_version: cloudVersion,
        plantilla_aviso: plantillaAviso,
        plantilla_codigo: plantillaCodigo,
        idioma_plantilla: idiomaPlantilla,
      })
      setPassword('')
      setCloudToken('')
      await cargar()
      notificar('WhatsApp guardado')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function probar() {
    setProbando(true)
    setError(null)
    try {
      const r = await api.admin.ajustesWhatsapp.probar(telefonoPrueba)
      if (r.enviado) notificar('WhatsApp de prueba enviado')
      else setError(r.error ?? 'No se ha podido enviar')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setProbando(false)
    }
  }

  if (!config) return null

  return (
    <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-5)' }}>
      <div className="form-section__title">WhatsApp</div>
      <p className="form-section__note">
        Se usa para mandar enlaces de firma y el documento firmado. Cuando un firmante tiene
        móvil, el enlace le llega por WhatsApp y el código de verificación por correo: que
        vayan por canales distintos es lo que hace que el segundo factor signifique algo.
      </p>
      <ErrorNotice error={error} />

      <div className="form-grid" style={{ marginTop: 'var(--sp-3)' }}>
        <Field
          label="Proveedor"
          hint={
            proveedor === 'gowa'
              ? 'Puente contra WhatsApp Web: vale para enseñar el producto, no para producción'
              : 'API oficial de Meta: exige número de empresa y plantillas aprobadas'
          }
        >
          <select
            className="select"
            value={proveedor}
            onChange={(e) => setProveedor(e.target.value as ProveedorWhatsApp)}
          >
            <option value="gowa">Puente WhatsApp Web (GOWA)</option>
            <option value="cloud">API oficial (Cloud API)</option>
          </select>
        </Field>
        <Field label="Activo">
          <select
            className="select"
            value={activa ? 'si' : 'no'}
            onChange={(e) => setActiva(e.target.value === 'si')}
          >
            <option value="si">Sí</option>
            <option value="no">No</option>
          </select>
        </Field>
        <Field label="Prefijo de país" hint="Para los móviles escritos sin él">
          <input className="input" value={prefijo} onChange={(e) => setPrefijo(e.target.value)} />
        </Field>
      </div>

      {proveedor === 'gowa' ? (
        <>
          <p className="notice" style={{ marginTop: 'var(--sp-4)' }}>
            El puente se conecta como un WhatsApp Web más, así que detrás hay una cuenta
            normal: mandar automatismos desde ella puede acabar en cierre del número. Para
            funcionar de verdad como empresa hay que pasar a la API oficial.
          </p>
          <div className="form-grid" style={{ marginTop: 'var(--sp-3)' }}>
            <Field ancho="doble" label="Dirección del puente" hint="Dentro del stack: http://gowa:3000">
              <input className="input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
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
            <Field ancho="doble" label="Device ID" hint="Solo si el puente tiene varias cuentas vinculadas">
              <input className="input" value={deviceId} onChange={(e) => setDeviceId(e.target.value)} />
            </Field>
          </div>

          {/* Vincular el móvil. Solo aparece si el proveedor sabe hacerlo:
              la API oficial no se empareja escaneando nada. */}
          {!vinculacion?.soporta_qr && (
            <p className="muted" style={{ marginTop: 'var(--sp-3)', fontSize: '0.9em' }}>
              Guarda la dirección del puente y sus credenciales para poder vincular un móvil
              desde aquí.
            </p>
          )}

          {vinculacion?.soporta_qr && (
            <div className="form-section" style={{ marginTop: 'var(--sp-4)' }}>
              <div className="form-section__title">Móvil vinculado</div>
              <p className="form-section__note">
                El puente manda desde un WhatsApp de verdad, así que hay que emparejarle un
                móvil. Se hace una vez; la sesión queda guardada y aguanta los reinicios.
              </p>

              {vinculacion.error && <p className="notice notice--error">{vinculacion.error}</p>}

              {vinculacion.vinculado ? (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--sp-3)',
                    flexWrap: 'wrap',
                  }}
                >
                  <span className="badge badge--success">
                    Vinculado{vinculacion.descripcion ? ` · ${vinculacion.descripcion}` : ''}
                  </span>
                  <button className="btn btn--sm btn--danger" onClick={() => void desvincular()}>
                    Desvincular
                  </button>
                </div>
              ) : qr ? (
                <div style={{ textAlign: 'center' }}>
                  <img
                    src={qr.imagen}
                    alt="Código QR para vincular WhatsApp"
                    // Fondo blanco fijo: un QR sobre fondo oscuro no lo lee
                    // ningún móvil.
                    style={{
                      width: 240,
                      height: 240,
                      background: '#fff',
                      padding: 12,
                      borderRadius: 8,
                    }}
                  />
                  <p className="muted" style={{ fontSize: '0.9em', margin: 'var(--sp-2) 0 0' }}>
                    En el móvil: WhatsApp → Ajustes → Dispositivos vinculados → Vincular un
                    dispositivo.
                  </p>
                  <p className="muted" style={{ fontSize: '0.85em', margin: '4px 0 0' }}>
                    {restan > 0
                      ? `Caduca en ${restan}s; se renueva solo.`
                      : 'Renovando el código…'}
                  </p>
                  <button
                    className="btn btn--sm"
                    style={{ marginTop: 'var(--sp-2)' }}
                    onClick={() => setQr(null)}
                  >
                    Cancelar
                  </button>
                </div>
              ) : (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--sp-3)',
                    flexWrap: 'wrap',
                  }}
                >
                  <span className="badge">Sin vincular</span>
                  <button
                    className="btn"
                    disabled={vinculando}
                    onClick={() => void pedirQr()}
                  >
                    {vinculando ? 'Generando…' : 'Vincular un móvil'}
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <>
          <p className="notice" style={{ marginTop: 'var(--sp-4)' }}>
            Fuera de la ventana de 24 h desde que el usuario escribe —que es siempre nuestro
            caso— Meta no deja mandar texto libre: hacen falta plantillas aprobadas. Una de
            «utilidad» para los avisos y otra de «autenticación» para el código.
          </p>
          <div className="form-grid" style={{ marginTop: 'var(--sp-3)' }}>
            <Field label="Phone number ID">
              <input
                className="input"
                value={phoneNumberId}
                onChange={(e) => setPhoneNumberId(e.target.value)}
              />
            </Field>
            <Field
              label="Token"
              hint={config.tiene_cloud_token ? 'Configurado (deja en blanco para no cambiarlo)' : 'Sin configurar'}
            >
              <input
                className="input"
                type="password"
                value={cloudToken}
                onChange={(e) => setCloudToken(e.target.value)}
                placeholder={config.tiene_cloud_token ? '••••••••' : ''}
              />
            </Field>
            <Field label="Versión de la API">
              <input
                className="input"
                value={cloudVersion}
                onChange={(e) => setCloudVersion(e.target.value)}
              />
            </Field>
            <Field label="Plantilla de aviso" hint="Categoría «utilidad»">
              <input
                className="input"
                value={plantillaAviso}
                onChange={(e) => setPlantillaAviso(e.target.value)}
              />
            </Field>
            <Field label="Plantilla de código" hint="Categoría «autenticación»">
              <input
                className="input"
                value={plantillaCodigo}
                onChange={(e) => setPlantillaCodigo(e.target.value)}
              />
            </Field>
            <Field label="Idioma de las plantillas">
              <input
                className="input"
                value={idiomaPlantilla}
                onChange={(e) => setIdiomaPlantilla(e.target.value)}
              />
            </Field>
          </div>
        </>
      )}

      <div className="form-actions">
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          {!guardando && <Save size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>

      <div className="form-section" style={{ marginTop: 'var(--sp-4)' }}>
        <div className="form-section__title">Probar el envío</div>
        <p className="form-section__note">
          Manda un WhatsApp real con lo que está GUARDADO, no con lo que haya a medio
          escribir aquí arriba.
        </p>
        <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
          <input
            className="input"
            type="tel"
            value={telefonoPrueba}
            placeholder="+34 600 11 22 33"
            onChange={(e) => setTelefonoPrueba(e.target.value)}
            style={{ maxWidth: 240 }}
          />
          <button
            className="btn"
            disabled={probando || telefonoPrueba.trim().length < 6}
            onClick={() => void probar()}
          >
            {probando ? 'Enviando…' : 'Enviar prueba'}
          </button>
        </div>
      </div>
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
