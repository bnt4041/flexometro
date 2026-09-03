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

  if (!id) return null

  return (
    <ModalPantalla title={titulo} onClose={() => navigate('/planos')}>
      <VisorPlano planoId={id} onCargado={(p) => setTitulo(`${p.codigo} · ${p.nombre}`)} />
    </ModalPantalla>
  )
}
