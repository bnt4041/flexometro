/** Captura de fotogramas de la cámara DENTRO de una sesión WebXR inmersiva.
 *
 *  Hace falta porque en `immersive-ar` no hay ningún `<video>` del que tirar:
 *  ARCore se queda la cámara en exclusiva y un `getUserMedia` paralelo falla.
 *  La vía soportada es la característica `camera-access` de WebXR (Chrome
 *  Android 107+, sin flag), que da la imagen como textura de WebGL.
 *  https://immersive-web.github.io/raw-camera-access/
 *
 *  Tres trampas que este módulo resuelve, y que si no se ven en las pruebas
 *  hasta que ya es tarde:
 *
 *  1. **La textura solo vale dentro del `requestAnimationFrame` en el que se
 *     pidió** (es una «textura opaca»): hay que leerla en ese mismo frame.
 *  2. **Hay que volver a dejar puesto el framebuffer de la capa base** al
 *     terminar la lectura. Si no, la escena se pinta en negro a partir del
 *     siguiente frame — el clásico «la primera foto sale y las demás no».
 *  3. **La imagen viene con el origen abajo a la izquierda**, al revés que un
 *     canvas 2D, así que se voltea en vertical al pasarla al lienzo.
 */

// `@types/webxr` (0.5.x) todavía no trae `camera-access`, así que hay que
// declarar la parte de la API que usamos.
declare global {
  interface XRCamera {
    readonly width: number
    readonly height: number
  }
  interface XRView {
    readonly camera?: XRCamera
  }
  interface XRWebGLBinding {
    getCameraImage(camera: XRCamera): WebGLTexture | null
  }
}

export const CARACTERISTICA_CAMARA_XR = 'camera-access'

/** Captura el fotograma actual de la cámara del pase-through como JPEG.
 *
 *  Debe llamarse DENTRO del callback de animación de la sesión, con el
 *  `XRFrame` de ese frame — fuera de ahí la textura ya no es válida.
 *  Devuelve `null` si la sesión no concedió `camera-access` o si el
 *  dispositivo no expone la cámara en este frame. */
export async function capturarFotogramaXR(
  frame: XRFrame,
  binding: XRWebGLBinding,
  gl: WebGL2RenderingContext | WebGLRenderingContext,
  espacio: XRReferenceSpace,
  framebufferLectura: WebGLFramebuffer,
): Promise<Blob | null> {
  const pose = frame.getViewerPose(espacio)
  const vista = pose?.views.find((v) => v.camera)
  if (!vista?.camera) return null

  const camara = vista.camera
  const textura = binding.getCameraImage(camara)
  if (!textura) return null

  const { width, height } = camara
  const pixeles = new Uint8Array(width * height * 4)

  // Se guarda lo que hubiera enlazado para restaurarlo después (trampa 2).
  const texturaPrevia = gl.getParameter(gl.TEXTURE_BINDING_2D) as WebGLTexture | null

  gl.bindTexture(gl.TEXTURE_2D, textura)
  gl.bindFramebuffer(gl.FRAMEBUFFER, framebufferLectura)
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, textura, 0)

  let leido = false
  if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE) {
    gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixeles)
    leido = true
  }

  // Restaurar SIEMPRE, aunque la lectura haya fallado: si la capa base se
  // queda sin su framebuffer, la sesión deja de pintar.
  const capaBase = frame.session.renderState.baseLayer
  gl.bindFramebuffer(gl.FRAMEBUFFER, capaBase ? capaBase.framebuffer : null)
  gl.bindTexture(gl.TEXTURE_2D, texturaPrevia)
  if (!leido) return null

  const lienzo = document.createElement('canvas')
  lienzo.width = width
  lienzo.height = height
  const ctx = lienzo.getContext('2d')
  if (!ctx) return null
  ctx.putImageData(new ImageData(new Uint8ClampedArray(pixeles), width, height), 0, 0)

  // Voltear en vertical (trampa 3): se vuelca sobre un segundo lienzo con la
  // escala invertida en Y.
  const derecho = document.createElement('canvas')
  derecho.width = width
  derecho.height = height
  const ctx2 = derecho.getContext('2d')
  if (!ctx2) return null
  ctx2.translate(0, height)
  ctx2.scale(1, -1)
  ctx2.drawImage(lienzo, 0, 0)

  return new Promise<Blob | null>((resolver) =>
    derecho.toBlob(resolver, 'image/jpeg', 0.85),
  )
}
