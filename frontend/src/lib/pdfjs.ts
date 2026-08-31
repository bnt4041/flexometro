import * as pdfjs from 'pdfjs-dist'

// El "worker" de pdf.js se carga desde el propio paquete con la URL que
// resuelve Vite en el build — no desde un CDN, que la política de contenido
// bloquearía y que además dejaría la aplicación dependiendo de un tercero.
//
// Vive aquí y no en cada componente porque `workerSrc` es una variable global
// del módulo: configurarla en dos sitios es pedir que un día discrepen.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

export { pdfjs }
