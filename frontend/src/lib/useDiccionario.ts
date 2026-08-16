import { useEffect, useState } from 'react'

import { api } from './api'
import type { EntradaDiccionario, TipoDiccionario } from './api'

/** Entradas activas de un tipo de diccionario, para poblar un `<select>` de
 *  un formulario de negocio (país, forma de pago...). Solo lectura — editar
 *  vive en Ajustes > Diccionario (`api.ajustes.diccionario`). */
export function useDiccionario(tipo: TipoDiccionario): EntradaDiccionario[] {
  const [entradas, setEntradas] = useState<EntradaDiccionario[]>([])

  useEffect(() => {
    let cancelado = false
    void api.diccionario.list(tipo).then((datos) => {
      if (!cancelado) setEntradas(datos)
    })
    return () => {
      cancelado = true
    }
  }, [tipo])

  return entradas
}
