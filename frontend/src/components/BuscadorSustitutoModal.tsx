import { useEffect, useRef, useState } from 'react'
import { Check, Search, Sparkles, X } from 'lucide-react'

import { ErrorNotice, Modal, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { SustitutoCandidato } from '../lib/api'

const ETIQUETA_ORIGEN: Record<SustitutoCandidato['origen'], string> = {
  banco: 'Banco de precios',
  presupuesto: 'Presupuesto anterior',
  certificacion: 'Certificación',
}

/** «Cambiar por banco de precios» (Fase 52): buscador de sustitutos para una
 *  partida o un componente de un descompuesto, con tres fuentes posibles —
 *  banco de precios propio, partidas de presupuestos anteriores, y líneas ya
 *  certificadas (para un componente, solo el banco tiene sentido: un
 *  componente siempre es un `Concepto`, no algo que se certifique aparte).
 *
 *  La IA sugiere 2-3 candidatos en cuanto se abre (marcados arriba, con su
 *  razón), pero nunca aplica nada por su cuenta: el usuario siempre elige de
 *  la lista, con el buscador libre debajo para cualquier otro caso. Aplicar
 *  la elección lo hace quien abre este modal (`onAplicar`), porque el gesto
 *  real difiere según el contexto: la partida llama a un único endpoint,
 *  mientras que un componente quita+añade contra su propio descompuesto
 *  (de una partida o de una ficha del banco, según desde dónde se abra). */
export function BuscadorSustitutoModal({
  resumenActual,
  unidadActual,
  modo,
  excluirPartidaId,
  onAplicar,
  onClose,
}: {
  resumenActual: string
  unidadActual: string
  modo: 'partida' | 'componente'
  excluirPartidaId?: string | null
  onAplicar: (candidato: SustitutoCandidato, copiarDescompuesto: boolean) => Promise<void>
  onClose: () => void
}) {
  const [texto, setTexto] = useState('')
  const [candidatos, setCandidatos] = useState<SustitutoCandidato[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [elegido, setElegido] = useState<SustitutoCandidato | null>(null)
  const [copiarDescompuesto, setCopiarDescompuesto] = useState(true)
  const [aplicando, setAplicando] = useState(false)
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null)

  async function buscar(q: string, conIa: boolean) {
    setCargando(true)
    setError(null)
    try {
      const resultado = await api.presupuestos.buscarSustitutos({
        texto: q || null,
        resumen_actual: resumenActual,
        unidad_actual: unidadActual,
        modo,
        excluir_partida_id: modo === 'partida' ? excluirPartidaId : null,
        con_ia: conIa,
      })
      setCandidatos(resultado)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }

  // Carga inicial: busca con el resumen actual y pide sugerencia de la IA.
  useEffect(() => {
    void buscar('', true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Búsqueda a mano: sin IA (ya se pidió una vez al abrir), con debounce.
  function onCambiarTexto(valor: string) {
    setTexto(valor)
    if (temporizador.current) clearTimeout(temporizador.current)
    temporizador.current = setTimeout(() => void buscar(valor, false), 300)
  }

  async function confirmar() {
    if (!elegido || aplicando) return
    setAplicando(true)
    setError(null)
    try {
      await onAplicar(elegido, elegido.origen === 'banco' ? true : copiarDescompuesto)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setAplicando(false)
    }
  }

  const sugeridos = candidatos.filter((c) => c.sugerido)
  const resto = candidatos.filter((c) => !c.sugerido)

  function fila(c: SustitutoCandidato, i: number) {
    const activo = elegido === c
    return (
      <button
        key={`${c.origen}-${c.concepto_id ?? c.partida_id}-${i}`}
        type="button"
        className={activo ? 'sustituto-fila is-elegida' : 'sustituto-fila'}
        onClick={() => setElegido(c)}
      >
        <div className="sustituto-fila__cabecera">
          <span className="chip">{ETIQUETA_ORIGEN[c.origen]}</span>
          {c.codigo && <span className="muted">{c.codigo}</span>}
          <strong>{formatoImporte(c.precio)} €</strong>
        </div>
        <div className="sustituto-fila__resumen">{c.resumen}</div>
        <div className="muted">
          {c.unidad} · {c.origen_detalle}
        </div>
        {c.razon_sugerencia && (
          <div className="sustituto-fila__razon">
            <Sparkles size={12} aria-hidden="true" /> {c.razon_sugerencia}
          </div>
        )}
      </button>
    )
  }

  return (
    <Modal title="Cambiar por banco de precios" onClose={onClose}>
      <div className="form-section">
        <p className="form-section__note">
          Sustituyendo «{resumenActual}». Elige un candidato de la lista, o busca a mano.
        </p>
        <label className="field">
          <span className="field__label">Buscar</span>
          <span className="rejilla-barra__buscador">
            <Search size={14} aria-hidden="true" />
            <input
              className="input"
              type="search"
              placeholder="Código o descripción…"
              value={texto}
              onChange={(e) => onCambiarTexto(e.target.value)}
              autoFocus
            />
          </span>
        </label>

        <ErrorNotice error={error} />

        {cargando && <p className="muted">Buscando…</p>}

        {!cargando && candidatos.length === 0 && (
          <p className="muted">Sin resultados. Prueba con otro texto.</p>
        )}

        {!cargando && sugeridos.length > 0 && (
          <>
            <p className="sustituto-grupo__titulo">
              <Sparkles size={13} aria-hidden="true" /> Sugerido por la IA
            </p>
            <div className="sustituto-lista">{sugeridos.map(fila)}</div>
          </>
        )}

        {!cargando && resto.length > 0 && (
          <>
            {sugeridos.length > 0 && <p className="sustituto-grupo__titulo">Todos los resultados</p>}
            <div className="sustituto-lista">{resto.map(fila)}</div>
          </>
        )}

        {elegido && modo === 'partida' && elegido.origen !== 'banco' && (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={copiarDescompuesto}
              onChange={(e) => setCopiarDescompuesto(e.target.checked)}
            />
            <span>Copiar también el descompuesto de «{elegido.resumen}»</span>
          </label>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={!elegido || aplicando}
          onClick={() => void confirmar()}
        >
          {!aplicando && <Check size={16} aria-hidden="true" />}
          {aplicando ? 'Aplicando…' : 'Aplicar'}
        </button>
      </div>
    </Modal>
  )
}
