/** Exportación de listados — CSV en el navegador (sin dependencias nuevas;
 *  Excel lo abre igual de bien que un .xlsx real) y PDF a través del
 *  backend (mismo motor que ya usan facturas/presupuestos). Ambas mandan
 *  exactamente lo que el usuario tiene en pantalla: columnas visibles,
 *  filtradas y en el orden que haya elegido — nunca vuelven a pedir datos
 *  aparte. */

import { api } from './api'

function descargarBlob(blob: Blob, nombreArchivo: string) {
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombreArchivo
  enlace.click()
  URL.revokeObjectURL(url)
}

/** CSV con las convenciones de Excel en español: `;` como separador (la
 *  coma la usa el propio decimal), BOM UTF-8 para que las tildes no salgan
 *  mal al abrirlo directamente con doble clic. */
export function exportarCsv(nombreArchivo: string, columnas: string[], filas: string[][]) {
  const escapar = (celda: string) => `"${celda.replace(/"/g, '""')}"`
  const lineas = [columnas, ...filas].map((fila) => fila.map(escapar).join(';'))
  const contenido = '﻿' + lineas.join('\r\n')
  descargarBlob(new Blob([contenido], { type: 'text/csv;charset=utf-8;' }), `${nombreArchivo}.csv`)
}

export async function exportarPdf(nombreArchivo: string, titulo: string, columnas: string[], filas: string[][]) {
  const blob = await api.exportarPdf({ titulo, columnas, filas })
  descargarBlob(blob, `${nombreArchivo}.pdf`)
}
