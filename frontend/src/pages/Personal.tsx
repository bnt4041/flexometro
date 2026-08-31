import { useCallback, useEffect, useState } from 'react'
import { Pencil, Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal, Pager, Tooltip, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type { AptitudMedica, Personal as PersonalT, TipoContratoLaboral } from '../lib/api'

const LIMITE = 25

export function Personal() {
  const [items, setItems] = useState<PersonalT[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [soloActivos, setSoloActivos] = useState(true)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creando, setCreando] = useState(false)
  const [editando, setEditando] = useState<PersonalT | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.personal.list({
        activo: soloActivos ? true : undefined,
        limit: LIMITE,
        offset,
      })
      setItems(page.items)
      setTotal(page.total)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [soloActivos, offset])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Personal</h1>
          <p className="page-lead">
            Plantilla propia de la organización. El coste/hora es lo que cuesta a la empresa
            (salario más cargas sociales), y se congela en cada asignación a obra.
          </p>
        </div>
        <Tooltip texto="Dar de alta un trabajador">
          <button className="btn btn--primary" onClick={() => setCreando(true)}>
            <Plus size={16} aria-hidden="true" />
            Nuevo trabajador
          </button>
        </Tooltip>
      </div>

      <div className="toolbar">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={soloActivos}
            onChange={(e) => {
              setOffset(0)
              setSoloActivos(e.target.checked)
            }}
          />
          <span>Solo activos</span>
        </label>
      </div>

      <ErrorNotice error={error} />

      <div className="table-wrap">
        {items.length === 0 && !cargando ? (
          <EmptyState title="Sin trabajadores">Crea el primero para empezar.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Categoría</th>
                <th className="table__num">Coste/hora</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id}>
                  <td className="table__code">{p.codigo}</td>
                  <td>
                    {p.nombre} {p.apellidos ?? ''}
                    {!p.activo && <span className="chip chip--inactivo"> baja</span>}
                  </td>
                  <td>{p.categoria ?? <span className="muted">—</span>}</td>
                  <td className="table__num">{formatoImporte(p.coste_hora)} €</td>
                  <td className="table__actions">
                    <button className="btn btn--sm" onClick={() => setEditando(p)}>
                      <Pencil size={14} aria-hidden="true" />
                      Editar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Pager total={total} limit={LIMITE} offset={offset} onChange={setOffset} />

      {creando && (
        <FormularioPersonal
          onClose={() => setCreando(false)}
          onGuardado={() => {
            setCreando(false)
            void cargar()
          }}
        />
      )}
      {editando && (
        <FormularioPersonal
          persona={editando}
          onClose={() => setEditando(null)}
          onGuardado={() => {
            setEditando(null)
            void cargar()
          }}
        />
      )}
    </>
  )
}

const TIPOS_CONTRATO: { valor: TipoContratoLaboral; etiqueta: string }[] = [
  { valor: 'indefinido', etiqueta: 'Indefinido' },
  { valor: 'temporal', etiqueta: 'Temporal' },
  { valor: 'fijo_discontinuo', etiqueta: 'Fijo discontinuo' },
  { valor: 'obra_y_servicio', etiqueta: 'Obra y servicio' },
  { valor: 'formacion', etiqueta: 'Formación' },
  { valor: 'practicas', etiqueta: 'Prácticas' },
  { valor: 'autonomo', etiqueta: 'Autónomo' },
  { valor: 'otro', etiqueta: 'Otro' },
]

const APTITUDES: { valor: AptitudMedica; etiqueta: string }[] = [
  { valor: 'apto', etiqueta: 'Apto' },
  { valor: 'apto_con_restricciones', etiqueta: 'Apto con restricciones' },
  { valor: 'no_apto', etiqueta: 'No apto' },
  { valor: 'pendiente', etiqueta: 'Pendiente' },
]

type SeccionFicha = 'basicos' | 'identificacion' | 'laboral' | 'prl'

/** La ficha pasó de cuatro campos a casi treinta al entrar el HRM y la PRL,
 *  así que se reparte en secciones dentro del mismo modal: en una sola lista
 *  no se encuentra nada, y separarla en pantallas distintas obligaría a
 *  guardar varias veces lo que conceptualmente es una sola ficha. */
function FormularioPersonal({
  persona,
  onClose,
  onGuardado,
}: {
  persona?: PersonalT
  onClose: () => void
  onGuardado: () => void
}) {
  const [seccion, setSeccion] = useState<SeccionFicha>('basicos')
  const [datos, setDatos] = useState<Partial<PersonalT>>(
    persona ?? { nombre: '', coste_hora: '0.00', activo: true, es_recurso_preventivo: false },
  )
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const set = <K extends keyof PersonalT>(campo: K, valor: PersonalT[K]) =>
    setDatos((previo) => ({ ...previo, [campo]: valor }))

  /** Los `<input>` no manejan `null`, así que se traduce a cadena vacía al
   *  pintar y de vuelta a `null` al guardar — si no, el campo se quedaría con
   *  el literal "null" escrito dentro. */
  const txt = (campo: keyof PersonalT): string => {
    const valor = datos[campo]
    return valor === null || valor === undefined ? '' : String(valor)
  }

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const limpio: Record<string, unknown> = {}
      for (const [clave, valor] of Object.entries(datos)) {
        // El servidor pone estos, no el formulario.
        if (['id', 'codigo', 'created_at', 'updated_at', 'creado_por_nombre'].includes(clave)) continue
        limpio[clave] = valor === '' ? null : valor
      }
      limpio.nombre = (datos.nombre ?? '').trim()
      if (persona) await api.personal.update(persona.id, limpio as Partial<PersonalT>)
      else await api.personal.create(limpio as Partial<PersonalT>)
      onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal title={persona ? 'Editar trabajador' : 'Nuevo trabajador'} onClose={onClose}>
      <div className="ficha-pestanas" role="tablist" style={{ marginBottom: 'var(--sp-4)' }}>
        {(
          [
            ['basicos', 'Datos básicos'],
            ['identificacion', 'Identificación'],
            ['laboral', 'Contrato'],
            ['prl', 'PRL'],
          ] as [SeccionFicha, string][]
        ).map(([id, etiqueta]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={seccion === id}
            className={seccion === id ? 'ficha-pestana ficha-pestana--activa' : 'ficha-pestana'}
            onClick={() => setSeccion(id)}
          >
            {etiqueta}
          </button>
        ))}
      </div>

      <div className="form-section">
        <ErrorNotice error={error} />

        {seccion === 'basicos' && (
          <div className="form-grid">
            <Field label="Nombre">
              <input className="input" value={txt('nombre')} onChange={(e) => set('nombre', e.target.value)} autoFocus />
            </Field>
            <Field label="Apellidos">
              <input className="input" value={txt('apellidos')} onChange={(e) => set('apellidos', e.target.value)} />
            </Field>
            <Field ancho="doble" label="Categoría" hint="Oficial 1ª, peón, encargado…">
              <input className="input" value={txt('categoria')} onChange={(e) => set('categoria', e.target.value)} />
            </Field>
            <Field label="Coste por hora" hint="Coste para la empresa, no lo que cobra en mano">
              <input className="input" type="number" step="0.01" value={txt('coste_hora')} onChange={(e) => set('coste_hora', e.target.value)} />
            </Field>
            <Field ancho="completo" label="Notas">
              <input className="input" value={txt('notas')} onChange={(e) => set('notas', e.target.value)} />
            </Field>
            {persona && (
              <Field ancho="completo" label="Estado">
                <label className="checkbox">
                  <input type="checkbox" checked={datos.activo ?? true} onChange={(e) => set('activo', e.target.checked)} />
                  <span>Activo</span>
                </label>
              </Field>
            )}
          </div>
        )}

        {seccion === 'identificacion' && (
          <div className="form-grid">
            <Field label="NIF / NIE">
              <input className="input" value={txt('nif')} onChange={(e) => set('nif', e.target.value)} />
            </Field>
            <Field label="Fecha de nacimiento">
              <input className="input" type="date" value={txt('fecha_nacimiento')} onChange={(e) => set('fecha_nacimiento', e.target.value)} />
            </Field>
            <Field label="Nacionalidad">
              <input className="input" value={txt('nacionalidad')} onChange={(e) => set('nacionalidad', e.target.value)} />
            </Field>
            <Field label="Teléfono">
              <input className="input" value={txt('telefono')} onChange={(e) => set('telefono', e.target.value)} />
            </Field>
            <Field ancho="doble" label="Correo">
              <input className="input" type="email" value={txt('email')} onChange={(e) => set('email', e.target.value)} />
            </Field>
            <Field ancho="doble" label="Dirección">
              <input className="input" value={txt('direccion')} onChange={(e) => set('direccion', e.target.value)} />
            </Field>
            <Field label="Código postal">
              <input className="input" value={txt('codigo_postal')} onChange={(e) => set('codigo_postal', e.target.value)} />
            </Field>
            <Field label="Población">
              <input className="input" value={txt('poblacion')} onChange={(e) => set('poblacion', e.target.value)} />
            </Field>
            <Field label="Provincia">
              <input className="input" value={txt('provincia')} onChange={(e) => set('provincia', e.target.value)} />
            </Field>
            <Field ancho="doble" label="Contacto de emergencia" hint="A quién avisar si hay un accidente en obra">
              <input className="input" value={txt('contacto_emergencia')} onChange={(e) => set('contacto_emergencia', e.target.value)} />
            </Field>
            <Field label="Teléfono de emergencia">
              <input className="input" value={txt('telefono_emergencia')} onChange={(e) => set('telefono_emergencia', e.target.value)} />
            </Field>
          </div>
        )}

        {seccion === 'laboral' && (
          <div className="form-grid">
            <Field label="NAF" hint="Nº de afiliación a la Seguridad Social">
              <input className="input" value={txt('naf')} onChange={(e) => set('naf', e.target.value)} />
            </Field>
            <Field label="Tipo de contrato">
              <select className="input" value={txt('tipo_contrato')} onChange={(e) => set('tipo_contrato', (e.target.value || null) as TipoContratoLaboral | null)}>
                <option value="">Sin especificar</option>
                {TIPOS_CONTRATO.map((t) => (
                  <option key={t.valor} value={t.valor}>{t.etiqueta}</option>
                ))}
              </select>
            </Field>
            <Field label="Fecha de alta">
              <input className="input" type="date" value={txt('fecha_alta')} onChange={(e) => set('fecha_alta', e.target.value)} />
            </Field>
            <Field label="Fin de contrato" hint="Solo en temporales">
              <input className="input" type="date" value={txt('fecha_fin_contrato')} onChange={(e) => set('fecha_fin_contrato', e.target.value)} />
            </Field>
            <Field label="Fecha de baja">
              <input className="input" type="date" value={txt('fecha_baja')} onChange={(e) => set('fecha_baja', e.target.value)} />
            </Field>
            <Field label="Grupo de cotización">
              <input className="input" value={txt('grupo_cotizacion')} onChange={(e) => set('grupo_cotizacion', e.target.value)} />
            </Field>
            <Field ancho="doble" label="Convenio">
              <input className="input" value={txt('convenio')} onChange={(e) => set('convenio', e.target.value)} />
            </Field>
            <Field label="Jornada (h/semana)">
              <input className="input" type="number" step="0.5" value={txt('jornada_horas_semana')} onChange={(e) => set('jornada_horas_semana', e.target.value)} />
            </Field>
            <Field label="Salario bruto anual">
              <input className="input" type="number" step="0.01" value={txt('salario_bruto_anual')} onChange={(e) => set('salario_bruto_anual', e.target.value)} />
            </Field>
            <Field ancho="doble" label="IBAN">
              <input className="input" value={txt('iban')} onChange={(e) => set('iban', e.target.value)} />
            </Field>
          </div>
        )}

        {seccion === 'prl' && (
          <div className="form-grid">
            <Field label="Nº de TPC" hint="Tarjeta Profesional de la Construcción">
              <input className="input" value={txt('tpc_numero')} onChange={(e) => set('tpc_numero', e.target.value)} />
            </Field>
            <Field label="Caducidad de la TPC">
              <input className="input" type="date" value={txt('tpc_caducidad')} onChange={(e) => set('tpc_caducidad', e.target.value)} />
            </Field>
            <Field label="Formación PRL (horas)" hint="20 h de oficio o 60 h de directivo">
              <input className="input" type="number" value={txt('formacion_prl_horas')} onChange={(e) => set('formacion_prl_horas', e.target.value === '' ? null : Number(e.target.value))} />
            </Field>
            <Field label="Fecha de la formación">
              <input className="input" type="date" value={txt('formacion_prl_fecha')} onChange={(e) => set('formacion_prl_fecha', e.target.value)} />
            </Field>
            <Field label="Aptitud médica" hint="Solo el veredicto: el dato clínico no se guarda">
              <select className="input" value={txt('aptitud_medica')} onChange={(e) => set('aptitud_medica', (e.target.value || null) as AptitudMedica | null)}>
                <option value="">Sin especificar</option>
                {APTITUDES.map((a) => (
                  <option key={a.valor} value={a.valor}>{a.etiqueta}</option>
                ))}
              </select>
            </Field>
            <Field label="Último reconocimiento">
              <input className="input" type="date" value={txt('fecha_reconocimiento_medico')} onChange={(e) => set('fecha_reconocimiento_medico', e.target.value)} />
            </Field>
            <Field label="Próximo reconocimiento">
              <input className="input" type="date" value={txt('proximo_reconocimiento')} onChange={(e) => set('proximo_reconocimiento', e.target.value)} />
            </Field>
            <Field label="Información de riesgos">
              <input className="input" type="date" value={txt('informacion_riesgos_fecha')} onChange={(e) => set('informacion_riesgos_fecha', e.target.value)} />
            </Field>
            <Field label="Entrega de EPIs">
              <input className="input" type="date" value={txt('fecha_entrega_epis')} onChange={(e) => set('fecha_entrega_epis', e.target.value)} />
            </Field>
            <Field ancho="completo" label="EPIs entregados">
              <input className="input" value={txt('epis_entregados')} onChange={(e) => set('epis_entregados', e.target.value)} placeholder="Casco, botas de seguridad, arnés…" />
            </Field>
            <Field ancho="completo" label="Recurso preventivo">
              <label className="checkbox">
                <input type="checkbox" checked={datos.es_recurso_preventivo ?? false} onChange={(e) => set('es_recurso_preventivo', e.target.checked)} />
                <span>Designado recurso preventivo para presencia en obra</span>
              </label>
            </Field>
          </div>
        )}
      </div>

      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={guardando || (datos.nombre ?? '').trim() === ''}
          onClick={() => void guardar()}
        >
          {!guardando && <Plus size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : persona ? 'Guardar cambios' : 'Crear'}
        </button>
      </div>
    </Modal>
  )
}
