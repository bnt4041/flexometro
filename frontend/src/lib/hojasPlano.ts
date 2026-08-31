import { pdfjs } from './pdfjs'

export interface HojaLeida {
  ancho: number
  alto: number
  nombre?: string | null
}

/** Las páginas de un fichero, leídas en el navegador.
 *
 *  Se hace aquí y no en el servidor a propósito: rasterizar o parsear PDF en
 *  la API traería una librería pesada y bastante memoria a cambio de un dato
 *  —el tamaño de cada página— que el navegador ya conoce porque va a pintar
 *  el plano de todas formas.
 *
 *  Y no abre ningún agujero: estas dimensiones solo definen el sistema de
 *  coordenadas en el que se dibuja encima, y la escala real se fija después
 *  calibrando DENTRO de ese mismo sistema. Una página declarada con el doble
 *  de tamaño da exactamente las mismas mediciones en metros. */
export async function leerHojas(archivo: File): Promise<HojaLeida[]> {
  // Un DXF lo lee el servidor: de su geometría salen las dimensiones, las
  // capas y hasta la escala. Aquí no hay nada que mirar, y mandar un tamaño
  // inventado sería descartar el dato bueno por el de oídas.
  if (esDxf(archivo)) return []
  if (archivo.type === 'application/pdf') return leerPdf(archivo)
  return [await leerImagen(archivo)]
}

/** Por la extensión y no por el tipo MIME: no hay ninguno acordado para DXF
 *  —unos navegadores mandan `image/vnd.dxf`, otros `application/dxf` y muchos
 *  `application/octet-stream`— así que la extensión es lo único fiable. */
export function esDxf(archivo: File): boolean {
  return archivo.name.toLowerCase().endsWith('.dxf')
}

async function leerPdf(archivo: File): Promise<HojaLeida[]> {
  const datos = new Uint8Array(await archivo.arrayBuffer())
  const documento = await pdfjs.getDocument({ data: datos }).promise
  try {
    const hojas: HojaLeida[] = []
    for (let numero = 1; numero <= documento.numPages; numero++) {
      const pagina = await documento.getPage(numero)
      // `getViewport({scale:1})` ya devuelve la página con su rotación
      // aplicada. Usar `pagina.view` en crudo daría un A3 apaisado como
      // vertical, y todo lo dibujado encima saldría girado.
      const vista = pagina.getViewport({ scale: 1 })
      hojas.push({ ancho: vista.width, alto: vista.height, nombre: null })
    }
    return hojas
  } finally {
    await documento.destroy()
  }
}

function leerImagen(archivo: File): Promise<HojaLeida> {
  return new Promise((resolver, rechazar) => {
    const url = URL.createObjectURL(archivo)
    const imagen = new Image()
    imagen.onload = () => {
      URL.revokeObjectURL(url)
      resolver({ ancho: imagen.naturalWidth, alto: imagen.naturalHeight, nombre: null })
    }
    imagen.onerror = () => {
      URL.revokeObjectURL(url)
      rechazar(new Error('No se ha podido leer la imagen'))
    }
    imagen.src = url
  })
}
