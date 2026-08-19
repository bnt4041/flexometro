import { useState } from 'react'
import { Keyboard } from 'lucide-react'

import { Modal, Tooltip } from './ui'

export interface Atajo {
  teclas: string
  hace: string
}

/** Atajos que trae la propia rejilla (`RejillaEditable`), así que valen para
 *  cualquier tabla que la use. Los que dependen de la pantalla concreta —
 *  sangrar capítulos, por ejemplo — se pasan por `extra`. */
const NAVEGACION: Atajo[] = [
  { teclas: '↑ ↓ ← →', hace: 'Moverse de celda' },
  { teclas: 'Tab / Mayús+Tab', hace: 'Celda siguiente / anterior' },
  { teclas: 'Inicio / Fin', hace: 'Primera / última columna de la fila' },
  { teclas: '↓ o Tab al final', hace: 'Crear una fila nueva y bajar a ella' },
  { teclas: 'Enter en Acciones', hace: 'Si la fila tiene botones, pulsa el primero' },
]

const EDICION: Atajo[] = [
  { teclas: 'Empezar a teclear', hace: 'Editar la celda reemplazando lo que había' },
  { teclas: 'F2', hace: 'Editar la celda con el texto ya seleccionado' },
  { teclas: 'Enter', hace: 'Editar; y estando dentro, confirmar y bajar' },
  { teclas: 'Tab', hace: 'Confirmar y pasar a la celda de la derecha' },
  { teclas: 'Esc', hace: 'Descartar lo escrito en la celda' },
  { teclas: 'Supr', hace: 'Vaciar la celda' },
]

const FILAS: Atajo[] = [
  { teclas: 'Ctrl+Enter', hace: 'Insertar una fila' },
  { teclas: 'Ctrl+Supr', hace: 'Borrar la fila' },
]

const AUTOCOMPLETADO: Atajo[] = [
  { teclas: '↑ ↓', hace: 'Moverse por las sugerencias' },
  { teclas: 'Enter', hace: 'Elegir la sugerencia marcada' },
]

function Grupo({ titulo, atajos }: { titulo: string; atajos: Atajo[] }) {
  if (atajos.length === 0) return null
  return (
    <div className="form-section">
      <div className="form-section__title">{titulo}</div>
      <table className="table tabla-atajos">
        <tbody>
          {atajos.map((a) => (
            <tr key={a.teclas + a.hace}>
              <td className="tabla-atajos__teclas">
                <kbd>{a.teclas}</kbd>
              </td>
              <td>{a.hace}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Icono de ayuda con el listado de atajos de la rejilla.
 *
 *  Antes esto era una línea de texto en la barra, que se quedaba corta en
 *  cuanto había más de tres o cuatro atajos y encima competía por el sitio con
 *  el indicador de guardado. */
export function BotonAtajos({
  extra = [],
  conAutocompletado = false,
}: {
  extra?: Atajo[]
  conAutocompletado?: boolean
}) {
  const [abierto, setAbierto] = useState(false)

  return (
    <>
      <Tooltip texto="Atajos de teclado">
        <button
          className="btn btn--sm btn--solo-icono"
          aria-label="Ver los atajos de teclado"
          onClick={() => setAbierto(true)}
        >
          <Keyboard size={14} aria-hidden="true" />
        </button>
      </Tooltip>

      {abierto && (
        <Modal title="Atajos de teclado" onClose={() => setAbierto(false)}>
          <Grupo titulo="Moverse" atajos={[...NAVEGACION, ...extra]} />
          <Grupo titulo="Editar" atajos={EDICION} />
          <Grupo titulo="Filas" atajos={FILAS} />
          {conAutocompletado && (
            <Grupo titulo="Buscando en el banco de precios" atajos={AUTOCOMPLETADO} />
          )}
          <div className="form-section">
            <p className="form-section__note">
              Con una celda abierta, <kbd>Esc</kbd> solo descarta esa celda. Fuera de la edición,
              cierra la ficha.
            </p>
          </div>
        </Modal>
      )}
    </>
  )
}
