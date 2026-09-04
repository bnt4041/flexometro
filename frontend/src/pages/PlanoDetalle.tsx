import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'

import { VisorPlano } from '../components/VisorPlano'
import { ModalPantalla } from '../components/ui'

/** Pantalla `/planos/:id` — el visor de un plano a página completa, para la
 *  biblioteca de planos. El visor en sí (calibrar/dibujar/medir) vive en
 *  `VisorPlano`, compartido con la pestaña de Mediciones de una partida
 *  (Fase 1k): aquí solo se le pone el chrome de `ModalPantalla` y se lee el
 *  id de la ruta. */
export function PlanoDetalle() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [titulo, setTitulo] = useState('Plano')
  // De qué presupuesto u obra es este plano, si es de alguno — para volver
  // ahí al cerrar en vez de a la biblioteca. Casi ningún plano se abre desde
  // la biblioteca sin más: la mayoría se llega buscándolo desde el
  // presupuesto o la obra a la que pertenece, así que cerrar y caer en la
  // lista general en vez de donde se estaba trabajando es peor que quedarse
  // sin cerrar.
  const [volverA, setVolverA] = useState<string | null>(null)

  if (!id) return null

  return (
    <ModalPantalla title={titulo} onClose={() => navigate(volverA ?? '/planos')}>
      <VisorPlano
        planoId={id}
        onCargado={(p) => {
          setTitulo(`${p.codigo} · ${p.nombre}`)
          setVolverA(
            p.presupuesto_id
              ? `/presupuestos/${p.presupuesto_id}`
              : p.obra_id
                ? `/obras/${p.obra_id}`
                : null,
          )
        }}
      />
    </ModalPantalla>
  )
}
