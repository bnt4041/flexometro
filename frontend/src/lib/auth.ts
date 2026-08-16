/**
 * Autenticación contra Keycloak con el flujo de código y PKCE.
 *
 * Sin librería: son unas líneas de `crypto.subtle` y dos peticiones. Una
 * dependencia más para esto no se paga sola, y así se ve exactamente qué se
 * envía.
 *
 * Los tokens se guardan en `sessionStorage`, no en `localStorage`: se borran al
 * cerrar la pestaña y no quedan a mano de otra pestaña del mismo origen. Sigue
 * siendo accesible desde JavaScript, así que la protección real frente a XSS es
 * no tener XSS; para un despliegue autoalojado es un equilibrio razonable.
 */

const CLAVE_TOKENS = 'obras.tokens'
const CLAVE_VERIFICADOR = 'obras.pkce.verificador'
const CLAVE_ESTADO = 'obras.pkce.estado'
const CLAVE_DESTINO = 'obras.destino'

export interface ConfigAuth {
  auth: 'keycloak' | 'stub'
  url: string | null
  realm: string | null
  client_id: string | null
}

interface Tokens {
  access_token: string
  refresh_token?: string
  /** Momento (ms) en que caduca el access token, con margen. */
  expira_en: number
}

let config: ConfigAuth | null = null
let tokens: Tokens | null = null
let refrescoEnCurso: Promise<boolean> | null = null

// --- Utilidades PKCE ---

function aleatorio(longitud: number): string {
  const bytes = new Uint8Array(longitud)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(36).padStart(2, '0')).join('').slice(0, longitud)
}

function base64url(datos: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(datos)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

async function reto(verificador: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verificador))
  return base64url(digest)
}

// --- Puntos finales del realm ---

function base(): string {
  return `${config!.url!.replace(/\/$/, '')}/realms/${config!.realm}/protocol/openid-connect`
}

function redireccion(): string {
  return `${window.location.origin}/`
}

// --- Estado ---

function guardar(t: Tokens): void {
  tokens = t
  sessionStorage.setItem(CLAVE_TOKENS, JSON.stringify(t))
}

function recuperar(): Tokens | null {
  const crudo = sessionStorage.getItem(CLAVE_TOKENS)
  if (!crudo) return null
  try {
    return JSON.parse(crudo) as Tokens
  } catch {
    return null
  }
}

function desdeRespuesta(datos: Record<string, unknown>): Tokens {
  // Se descuentan 30 s para no llegar con el token justo de caducado.
  const segundos = Number(datos.expires_in ?? 300)
  return {
    access_token: String(datos.access_token),
    refresh_token: datos.refresh_token ? String(datos.refresh_token) : undefined,
    expira_en: Date.now() + Math.max(0, segundos - 30) * 1000,
  }
}

// --- Flujo ---

export async function cargarConfig(): Promise<ConfigAuth> {
  if (config) return config
  const respuesta = await fetch('/api/config')
  if (!respuesta.ok) throw new Error('No se pudo leer la configuración de la API')
  config = (await respuesta.json()) as ConfigAuth
  return config
}

export function requiereLogin(): boolean {
  return config?.auth === 'keycloak'
}

export async function iniciarSesion(): Promise<void> {
  const verificador = aleatorio(64)
  const estado = aleatorio(24)
  sessionStorage.setItem(CLAVE_VERIFICADOR, verificador)
  sessionStorage.setItem(CLAVE_ESTADO, estado)
  // Se recuerda dónde estaba el usuario para devolverlo ahí tras entrar.
  sessionStorage.setItem(CLAVE_DESTINO, window.location.pathname + window.location.search)

  const parametros = new URLSearchParams({
    client_id: config!.client_id!,
    redirect_uri: redireccion(),
    response_type: 'code',
    scope: 'openid profile email',
    state: estado,
    code_challenge: await reto(verificador),
    code_challenge_method: 'S256',
  })
  window.location.assign(`${base()}/auth?${parametros}`)
}

/** ¿Venimos de vuelta de Keycloak? Si es así, canjea el código por tokens. */
export async function procesarRetorno(): Promise<string | null> {
  const parametros = new URLSearchParams(window.location.search)
  const codigo = parametros.get('code')
  const error = parametros.get('error')

  if (error) {
    limpiarUrl()
    throw new Error(parametros.get('error_description') || error)
  }
  if (!codigo) return null

  const estadoEsperado = sessionStorage.getItem(CLAVE_ESTADO)
  if (!estadoEsperado || parametros.get('state') !== estadoEsperado) {
    limpiarUrl()
    throw new Error('El estado de la respuesta no coincide; se descarta por seguridad')
  }

  const verificador = sessionStorage.getItem(CLAVE_VERIFICADOR)
  if (!verificador) {
    limpiarUrl()
    throw new Error('Falta el verificador PKCE de esta sesión')
  }

  const respuesta = await fetch(`${base()}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: config!.client_id!,
      redirect_uri: redireccion(),
      code: codigo,
      code_verifier: verificador,
    }),
  })

  sessionStorage.removeItem(CLAVE_VERIFICADOR)
  sessionStorage.removeItem(CLAVE_ESTADO)
  limpiarUrl()

  if (!respuesta.ok) {
    throw new Error(`Keycloak rechazó el canje del código (${respuesta.status})`)
  }
  guardar(desdeRespuesta(await respuesta.json()))

  const destino = sessionStorage.getItem(CLAVE_DESTINO)
  sessionStorage.removeItem(CLAVE_DESTINO)
  return destino && destino !== '/' ? destino : null
}

function limpiarUrl(): void {
  // Fuera el ?code= de la barra de direcciones: no aporta y recargar la página
  // con él daría un error de código ya usado.
  window.history.replaceState({}, '', window.location.pathname)
}

async function refrescar(): Promise<boolean> {
  if (!tokens?.refresh_token) return false
  // Varias peticiones que caducan a la vez no deben pedir cinco refrescos.
  if (refrescoEnCurso) return refrescoEnCurso

  refrescoEnCurso = (async () => {
    try {
      const respuesta = await fetch(`${base()}/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          grant_type: 'refresh_token',
          client_id: config!.client_id!,
          refresh_token: tokens!.refresh_token!,
        }),
      })
      if (!respuesta.ok) return false
      guardar(desdeRespuesta(await respuesta.json()))
      return true
    } catch {
      return false
    } finally {
      refrescoEnCurso = null
    }
  })()

  return refrescoEnCurso
}

export async function restaurarSesion(): Promise<boolean> {
  if (!requiereLogin()) return true
  tokens = recuperar()
  if (!tokens) return false
  if (Date.now() < tokens.expira_en) return true
  return refrescar()
}

/** Token válido para la siguiente llamada, refrescando si hace falta. */
export async function tokenValido(): Promise<string | null> {
  if (!requiereLogin()) return null
  if (!tokens) return null
  if (Date.now() >= tokens.expira_en && !(await refrescar())) {
    return null
  }
  return tokens.access_token
}

export function cerrarSesion(): void {
  const refresco = tokens?.refresh_token
  tokens = null
  sessionStorage.removeItem(CLAVE_TOKENS)

  if (!requiereLogin()) {
    window.location.assign('/')
    return
  }
  const parametros = new URLSearchParams({
    client_id: config!.client_id!,
    post_logout_redirect_uri: window.location.origin + '/',
  })
  if (refresco) parametros.set('refresh_token', refresco)
  window.location.assign(`${base()}/logout?${parametros}`)
}

// --- Organización activa ---

const CLAVE_ORG = 'obras.organizacion'

export function organizacionActiva(): string | null {
  return sessionStorage.getItem(CLAVE_ORG)
}

export function fijarOrganizacion(slug: string | null): void {
  if (slug) sessionStorage.setItem(CLAVE_ORG, slug)
  else sessionStorage.removeItem(CLAVE_ORG)
}
