import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Save, X } from 'lucide-react'

import { ErrorNotice, Field, ModalPantalla } from '../components/ui'
import { api } from '../lib/api'
import type { Module, TarifaDetalle as Detalle, TarifaModulo } from '../lib/api'
import { FormularioModulos, useContextoTarifas } from './AdminTarifas'

export function AdminTarifaDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoTarifas()
  const [modulos, setModulos] = useState<Module[]>([])
  const [tarifa, setTarifa] = useState<Detalle | null>(null)
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [precioDeepseek, setPrecioDeepseek] = useState('0.0000')
  const [precioGemini, setPrecioGemini] = useState('0.0000')
  const [valorCredito, setValorCredito] = useState('0.001000')
  const [creditosIncluidos, setCreditosIncluidos] = useState('0')
  const [activa, setActiva] = useState(true)
  const [filasModulos, setFilasModulos] = useState<TarifaModulo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const datos = await api.admin.tarifas.get(id)
      setTarifa(datos)
      setNombre(datos.nombre)
      setDescripcion(datos.descripcion ?? '')
      setPrecioDeepseek(datos.precio_1000_tokens_deepseek)
      setPrecioGemini(datos.precio_1000_tokens_gemini)
      setValorCredito(datos.valor_credito_euros)
      setCreditosIncluidos(String(datos.creditos_ia_incluidos_mes))
      setActiva(datos.activa)
      setFilasModulos(datos.modulos)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  useEffect(() => {
    void api.modules().then(setModulos)
  }, [])

  function cerrar() {
    navigate('/admin/tarifas')
  }

  if (error && !tarifa) {
    return (
      <ModalPantalla title="Tarifa" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!tarifa) return null

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.tarifas.update(id, {
        nombre,
        descripcion: descripcion || null,
        activa,
        precio_1000_tokens_deepseek: precioDeepseek,
        precio_1000_tokens_gemini: precioGemini,
        valor_credito_euros: valorCredito,
        creditos_ia_incluidos_mes: Number(creditosIncluidos) || 0,
        modulos: filasModulos,
      })
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title={`Editar tarifa · ${tarifa.nombre}`} onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <div className="form-grid">
            <Field ancho="doble" label="Nombre">
              <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus />
            </Field>
            <Field ancho="doble" label="Descripción" hint="Opcional">
              <input
                className="input"
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
              />
            </Field>
            <Field label="€ por 1000 tokens DeepSeek">
              <input
                className="input"
                value={precioDeepseek}
                onChange={(e) => setPrecioDeepseek(e.target.value)}
              />
            </Field>
            <Field label="€ por 1000 tokens Gemini">
              <input
                className="input"
                value={precioGemini}
                onChange={(e) => setPrecioGemini(e.target.value)}
              />
            </Field>
            <Field label="€ por crédito IA" hint="Unidad propia que ve el usuario final en vez de tokens">
              <input
                className="input"
                value={valorCredito}
                onChange={(e) => setValorCredito(e.target.value)}
              />
            </Field>
            <Field label="Créditos IA incluidos al mes">
              <input
                className="input"
                type="number"
                min="0"
                value={creditosIncluidos}
                onChange={(e) => setCreditosIncluidos(e.target.value)}
              />
            </Field>
            <Field label="Estado">
              <select
                className="select"
                value={activa ? 'activa' : 'inactiva'}
                onChange={(e) => setActiva(e.target.value === 'activa')}
              >
                <option value="activa">Activa</option>
                <option value="inactiva">Inactiva</option>
              </select>
            </Field>
          </div>
          <FormularioModulos modulos={modulos} filas={filasModulos} onCambiar={setFilasModulos} />
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            <X size={16} aria-hidden="true" />
            Cerrar
          </button>
          <button
            className="btn btn--primary"
            disabled={guardando || nombre.trim() === ''}
            onClick={() => void guardar()}
          >
            {!guardando && <Save size={16} aria-hidden="true" />}
            {guardando ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
