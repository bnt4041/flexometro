/** ¿Estamos dentro del navegador incrustado de una aplicación (Gmail, Outlook,
 *  Facebook…) en lugar de en un navegador de verdad?
 *
 *  Importa en la pantalla de firma porque quien llega a firmar viene SIEMPRE
 *  de un correo, y estas ventanas tienen dos pegas serias: el visor de PDF de
 *  Android no existe dentro de ellas, y al salir a la aplicación para leer el
 *  código de verificación la ventana puede destruirse y volver desde cero.
 *
 *  Que quede claro: NO hay forma de saltar de aquí al navegador del sistema
 *  por código. Ni `target="_blank"`, ni una cabecera, ni un `meta`. Lo único
 *  que se puede hacer es detectarlo, avisar y dar el enlace para copiarlo.
 *
 *  La detección es deliberadamente CONSERVADORA: es mejor no avisar que
 *  avisar de más. En particular, las pestañas de Chrome (Custom Tabs), que es
 *  lo que Gmail usa en buena parte de los Android, son Chrome de verdad —
 *  llevan su propio visor de PDF y su menú «Abrir en Chrome» — y no deben
 *  disparar el aviso. */
export function esNavegadorEmbebido(ua: string = navigator.userAgent): boolean {
  // Android marca su WebView con "; wv" desde la versión 4.4.
  if (/;\s*wv\b/.test(ua)) return true

  // Aplicaciones que traen navegador propio y lo anuncian en el user-agent.
  // GSA es la app de Google; FBAN/FBAV, Facebook.
  if (/\b(FBAN|FBAV|FB_IAB|Instagram|Line|MicroMessenger|GSA)\b/.test(ua)) return true

  // iOS no tiene marca equivalente: dentro de una WKWebView el user-agent es
  // el de Safari pero SIN el token "Safari/…" del final, que un Safari de
  // verdad (y también Chrome o Firefox de iOS) siempre lleva.
  if (/\b(iPhone|iPad|iPod)\b/.test(ua) && /AppleWebKit/.test(ua) && !/Safari\//.test(ua)) {
    return true
  }

  return false
}
