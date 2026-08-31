import { useCallback, useEffect, useRef, useState } from 'react'

import logoClaro from '../assets/logo.png'
import logoOscuro from '../assets/logo-sobre-oscuro-recorte.png'
import './LandingNueva.css'

/** Dirección de contacto pública. Vive aquí y no repartida por el JSX para
 *  que cambiarla sea una sola línea. */
const CORREO = 'info@flexometro.online'

const asunto = (texto: string) => `mailto:${CORREO}?subject=${encodeURIComponent(texto)}`

interface Props {
  onEntrar: () => void
}

export function LandingNueva({ onEntrar }: Props) {
  return (
    <>
      <AvisoDesarrollo />
      <div className="flx">
        <div className="pagina">
          <CintaMetrica />
          <div className="lienzo">
            <Cabecera onEntrar={onEntrar} />
            <Hero onEntrar={onEntrar} />
            <Problema />
            <Cadena />
            <CosteReal />
            <Bc3 />
            <Ia />
            <Red />
            <Prl />
            <PorQue />
            <Planes />
            <Confianza />
            <Cierre />
            <Pie />
          </div>
        </div>
      </div>
      <Cookies />
    </>
  )
}

function AvisoDesarrollo() {
  return (
    <div className="flx-aviso" role="status">
      <span className="punto" aria-hidden="true" />
      <span>
        <b>En desarrollo</b> · Flexómetro se está construyendo ahora mismo. Esta web y el producto
        cambian cada semana, y algunas funciones todavía no están disponibles para todo el mundo.
      </span>
    </div>
  )
}

/** La regla graduada del margen izquierdo. Mide la página de verdad: las
 *  marcas se calculan sobre la altura real del documento, no sobre un valor
 *  fijo, así que siguen cuadrando cuando el contenido crece o el texto se
 *  reajusta al cargar las tipografías. */
function CintaMetrica() {
  const ref = useRef<HTMLDivElement>(null)
  const [marcas, setMarcas] = useState<number[]>([])

  const graduar = useCallback(() => {
    const alto = ref.current?.offsetHeight ?? 0
    const nuevas: number[] = []
    for (let y = 100; y < alto - 40; y += 100) nuevas.push(y)
    setMarcas(nuevas)
  }, [])

  useEffect(() => {
    graduar()
    const observador = new ResizeObserver(graduar)
    if (ref.current) observador.observe(ref.current)
    // Las tipografías cambian la altura al cargar, después del primer pintado.
    void document.fonts?.ready.then(graduar)
    return () => observador.disconnect()
  }, [graduar])

  return (
    <div className="cinta" ref={ref} aria-hidden="true">
      {marcas.map((y) => (
        <b key={y} style={{ top: `${y}px` }}>
          {(y / 100).toFixed(2).replace('.', ',')}
        </b>
      ))}
    </div>
  )
}

function Cabecera({ onEntrar }: Props) {
  return (
    <div className="barra">
      <picture>
        <source srcSet={logoOscuro} media="(prefers-color-scheme: dark)" />
        <img src={logoClaro} alt="Flexómetro" />
      </picture>
      <button type="button" className="boton secundario compacto" onClick={onEntrar}>
        Iniciar sesión
      </button>
    </div>
  )
}

function Hero({ onEntrar }: Props) {
  return (
    <section className="hero">
      <span className="aviso">Veri*Factu · obligatorio en 2026</span>
      <h1>El presupuesto y la obra, por fin en el mismo sitio.</h1>
      <p className="guia">
        Flexómetro presupuesta como se presupuesta en España —descompuesto, medición,
        certificación— y además lleva la obra: pedidos, albaranes, coste real y factura.{' '}
        <strong>Sin volver a teclear nada.</strong>
      </p>
      <div className="acciones">
        <a className="boton principal" href={asunto('Demo de Flexómetro')}>
          Pedir una demo
        </a>
        <button type="button" className="boton secundario" onClick={onEntrar}>
          Ya tengo cuenta
        </button>
      </div>
      <p className="apunte">Sin instalar nada · Funciona en el móvil, en obra</p>
    </section>
  )
}

function Problema() {
  return (
    <section>
      <p className="eyebrow">El problema</p>
      <h2>Presupuestas en un sitio, compras en otro, y el coste real lo sabes tarde</h2>
      <p className="guia">
        El presupuesto vive en un programa de escritorio. Los pedidos, en el correo. Los albaranes,
        en una carpeta. Y la pregunta que de verdad importa —¿cuánto llevo gastado en esta
        partida?— se contesta con una hoja de cálculo hecha a mano tres semanas tarde, cuando ya no
        puedes hacer nada al respecto.
      </p>
      <div className="rejilla tres">
        <div className="tarjeta">
          <span className="sello">Hoy</span>
          <h3>Se teclea tres veces</h3>
          <p>
            La misma partida se copia al pedido, del pedido al albarán y del albarán a la factura.
            Cada copia es un error esperando.
          </p>
        </div>
        <div className="tarjeta">
          <span className="sello">Hoy</span>
          <h3>La obra va a ciegas</h3>
          <p>
            Sabes lo que presupuestaste y lo que has pagado, pero no lo mismo y al mismo tiempo. El
            desvío aparece al cerrar.
          </p>
        </div>
        <div className="tarjeta">
          <span className="sello">Hoy</span>
          <h3>Cuatro suscripciones</h3>
          <p>
            Mediciones, facturación, coordinación documental de PRL y firma electrónica. Cuatro
            proveedores, cuatro facturas, cero conexión.
          </p>
        </div>
      </div>
    </section>
  )
}

const CADENA = [
  { n: 'Presupuesto', q: 'Partida', d: 'Descompuesto en cascada, con su medición' },
  { n: 'Compras', q: 'Pedido', d: 'Sale de la partida, con sus cantidades' },
  { n: 'Obra', q: 'Albarán', d: 'Se recibe y se imputa solo' },
  { n: 'Control', q: 'Coste real', d: 'Frente a presupuesto, partida a partida' },
  { n: 'Cobro', q: 'Certificación', d: 'Por medición acumulada a fecha' },
  { n: 'Cobro', q: 'Factura', d: 'Numeración legal y Veri*Factu' },
]

function Cadena() {
  return (
    <section>
      <p className="eyebrow">Cómo funciona</p>
      <h2>Una sola cadena, de la partida al cobro</h2>
      <p className="guia">
        De la partida sale el pedido. Del pedido, el albarán. Del albarán, el coste real. De la
        medición ejecutada, la certificación. Y de la certificación, la factura. Cada eslabón
        conoce al anterior.
      </p>
      <div className="cadena-envoltorio">
        <div className="cadena">
          {CADENA.map((paso) => (
            <div className="paso" key={paso.q}>
              <span className="n">{paso.n}</span>
              <span className="q">{paso.q}</span>
              <span className="d">{paso.d}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const PARTIDAS = [
  {
    codigo: '1.01',
    nombre: 'Reparación de zonas afogaradas',
    ancho: 71,
    mal: false,
    presupuestado: '4.940,00',
    real: '3.512,00',
    desvio: '−28,9 %',
  },
  {
    codigo: '1.03',
    nombre: 'Rehabilitación y pintura de fachadas',
    ancho: 100,
    mal: true,
    presupuestado: '24.700,00',
    real: '27.184,50',
    desvio: '+10,1 %',
  },
  {
    codigo: '1.04',
    nombre: 'Limpieza de cubierta de tejas',
    ancho: 46,
    mal: false,
    presupuestado: '3.060,00',
    real: '1.407,60',
    desvio: '−54,0 %',
  },
]

function CosteReal() {
  return (
    <section>
      <p className="eyebrow">La pantalla que importa</p>
      <h2>Cuánto llevas gastado en esta partida. Ahora, no al cerrar.</h2>
      <p className="guia">
        Es la única pregunta que se hace un jefe de obra, y en Flexómetro se contesta sola: lo
        presupuestado, lo pedido, lo recibido y lo facturado, en la misma línea. Si una partida se
        está yendo, lo ves mientras todavía puedes hacer algo.
      </p>
      <div className="panel">
        <div className="panel-cab">
          <span>Control de coste · Obra 2607</span>
          <span>
            Presupuesto <b>71.427,43 €</b>
          </span>
        </div>
        <div className="panel-tabla">
          <table>
            <thead>
              <tr>
                <th scope="col">Partida</th>
                <th scope="col">Presupuestado</th>
                <th scope="col">Coste real</th>
                <th scope="col">Desvío</th>
              </tr>
            </thead>
            <tbody>
              {PARTIDAS.map((p) => (
                <tr key={p.codigo}>
                  <td>
                    <b>{p.codigo}</b>
                    {p.nombre}
                    <span className="barra-medida">
                      <i className={p.mal ? 'mal' : undefined} style={{ width: `${p.ancho}%` }} />
                    </span>
                  </td>
                  <td className="num">{p.presupuestado}</td>
                  <td className="num">{p.real}</td>
                  <td className="num">
                    <span className={p.mal ? 'delta mal' : 'delta bien'}>{p.desvio}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel-pie">
          Ejemplo ilustrativo · En Flexómetro estas cifras se actualizan solas al registrar cada
          albarán
        </div>
      </div>
    </section>
  )
}

function Bc3() {
  return (
    <section>
      <p className="eyebrow">Empezar no duele</p>
      <h2>Trae lo que ya tienes. No abandonas nada.</h2>
      <p className="guia">
        Flexómetro importa y exporta <strong>FIEBDC-3 (BC3)</strong>, el formato en el que viajan
        los bancos de precios y los presupuestos en España. Sueltas el fichero sobre un capítulo y
        las partidas se colocan solas, con su descompuesto y sus mediciones.
      </p>
      <div className="nota">
        <strong>Probado contra exportaciones reales de Presto.</strong> Codificación, textos largos,
        mediciones con longitud, anchura y altura, y las desviaciones que los programas de verdad
        emiten y la norma no contempla. Si algo no cuadra, se avisa: no se traga en silencio.
      </div>
      <ul className="lista">
        <li>Sigue usando tu programa de siempre mientras pruebas</li>
        <li>Banco de precios propio, compartido entre las empresas del grupo</li>
        <li>Exporta de vuelta cuando lo necesites</li>
        <li>Importación de datos desde CSV y Excel</li>
      </ul>
    </section>
  )
}

const IA = [
  {
    t: 'Redacta partidas y descompuestos',
    d: 'Describes lo que hay que hacer y te devuelve la partida escrita, con su descomposición y sus rendimientos, siguiendo el patrón de tus presupuestos anteriores.',
  },
  {
    t: 'Lee planos acotados',
    d: 'Subes el plano y saca las mediciones. No como un fichero suelto: directamente sobre el capítulo del presupuesto.',
  },
  {
    t: 'Ayuda en pedidos y facturas',
    d: 'Reconoce las partidas de una factura recibida y las propone contra el pedido correspondiente. Casar facturas deja de ser una tarde.',
  },
  {
    t: 'Responde sobre tu documentación',
    d: 'Sueltas los PDF de la obra —proyecto, pliegos, contratos— y preguntas en lenguaje llano. Sin salir del expediente.',
  },
]

function Ia() {
  return (
    <section>
      <p className="eyebrow">Inteligencia artificial</p>
      <h2>No está anunciada. Está trabajando.</h2>
      <p className="guia">
        La diferencia no es usar un modelo: es que el modelo vea tu descompuesto, tu banco de
        precios y tu histórico de obra. Un asistente genérico lee un fichero. El de Flexómetro sabe
        cómo presupuestas.
      </p>
      <div className="rejilla dos">
        {IA.map((c) => (
          <div className="tarjeta" key={c.t}>
            <h3>{c.t}</h3>
            <p>{c.d}</p>
          </div>
        ))}
      </div>
      <p className="apunte">
        El consumo de IA se mide y se factura por uso, con el detalle a la vista. Sin sorpresas al
        final de mes.
      </p>
    </section>
  )
}

const RED = [
  {
    estado: 'vivo' as const,
    etiqueta: 'Funcionando',
    t: 'Solicitud de precios a varios proveedores',
    d: 'Separata pública por enlace, sin registro para quien la recibe, y comparativa automática de las ofertas que entran.',
  },
  {
    estado: 'vivo' as const,
    etiqueta: 'Funcionando',
    t: 'Firma electrónica a terceros',
    d: 'Multifirma con verificación en dos pasos por un canal distinto, sello en el PDF y hoja de evidencias por firmante.',
  },
  {
    estado: 'camino' as const,
    etiqueta: 'En camino',
    t: 'Documentos que entran solos',
    d: 'La factura que emite un Flexómetro aterriza en el otro ya casada contra el pedido. Sin PDF, sin teclear, sin conciliar.',
  },
  {
    estado: 'camino' as const,
    etiqueta: 'En camino',
    t: 'Colaborar en proyectos',
    d: 'Aparecer, si quieres, en los listados donde otras empresas buscan con quién presupuestar o a quién subcontratar.',
  },
]

function Red() {
  return (
    <section>
      <p className="eyebrow">La red Flexómetro</p>
      <h2>Tus proveedores ya están al otro lado</h2>
      <p className="guia">
        Pides precio a cinco proveedores y les llega un enlace: entran sin cuenta, rellenan y
        comparas las ofertas en una tabla. Y si ese proveedor ya usa Flexómetro, la solicitud no le
        llega por correo: le aparece dentro de su propia aplicación. Un Flexómetro hablando con
        otro.
      </p>
      <div className="rejilla dos">
        {RED.map((c) => (
          <div className="tarjeta" key={c.t}>
            <span className={`estado ${c.estado}`}>{c.etiqueta}</span>
            <h3>{c.t}</h3>
            <p>{c.d}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function Prl() {
  return (
    <section>
      <p className="eyebrow">PRL y documentación</p>
      <h2>Y te quitas la suscripción de coordinación documental</h2>
      <p className="guia">
        Caducidades de toda la documentación de prevención —empresa, personal, recursos, obra y
        proveedores— con vehículos y maquinaria y sus documentos. Lo que hoy pagas aparte, aquí
        viene dentro.
      </p>
      <ul className="lista">
        <li>Avisos antes de que caduque, no después</li>
        <li>Documentación de subcontratistas y proveedores</li>
        <li>Plantillas de documento por tipo</li>
        <li>Notificaciones por campana, correo o WhatsApp</li>
      </ul>
    </section>
  )
}

const PORQUE = [
  {
    t: 'Se entra desde la obra',
    d: 'Desde el móvil, sin instalar nada, con la misma información que tiene la oficina. Incluso levantando una planta con la cámara.',
  },
  {
    t: 'El grupo de empresas, en un sitio',
    d: 'Varias sociedades bajo una misma cuenta, con el banco de precios y los terceros compartidos, y los datos de cada una aislados de verdad.',
  },
  {
    t: 'Se conecta con lo tuyo',
    d: 'Claves de API con permisos, avisos automáticos a otros sistemas y automatizaciones que se montan sin programar.',
  },
  {
    t: 'Mejora sin migraciones',
    d: 'Las novedades aparecen y ya está. Ni versión nueva, ni instalador, ni un fin de semana perdido.',
  },
]

function PorQue() {
  return (
    <section>
      <p className="eyebrow">Por qué se nota</p>
      <h2>Construido ahora, no actualizado desde los noventa</h2>
      <p className="guia">
        No te vamos a hablar de tecnología. Te contamos lo que la tecnología permite y que en un
        programa de escritorio, sencillamente, no se puede hacer.
      </p>
      <div className="rejilla dos">
        {PORQUE.map((c) => (
          <div className="tarjeta" key={c.t}>
            <h3>{c.t}</h3>
            <p>{c.d}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

const PLANES = [
  {
    nombre: 'Presupuesto',
    para: 'Para estudios y quien solo mide y presupuesta',
    destacado: false,
    incluye: [
      'Banco de precios y descompuesto',
      'Mediciones, capítulos y versiones',
      'Importación y exportación BC3',
      'Informes en PDF',
    ],
  },
  {
    nombre: 'Obra',
    para: 'Para constructoras y empresas de reforma',
    destacado: true,
    incluye: [
      'Todo lo de Presupuesto',
      'Pedidos, albaranes y coste real',
      'Certificaciones y facturación Veri*Factu',
      'Solicitud de precios a proveedores',
      'IA de presupuesto y de planos',
    ],
  },
  {
    nombre: 'Grupo',
    para: 'Para varias sociedades bajo una misma cuenta',
    destacado: false,
    incluye: [
      'Todo lo de Obra',
      'PRL, firma electrónica y documental',
      'Maestros compartidos entre empresas',
      'API, avisos automáticos y automatizaciones',
    ],
  },
]

function Planes() {
  return (
    <section>
      <p className="eyebrow">Precios</p>
      <h2>Tres formas de empezar</h2>
      <p className="guia">
        Se factura por empresa y por módulos activos, no por puesto. Puedes activar y desactivar
        módulos cuando quieras, y dentro de la aplicación cada cuenta ve su tarifa y su consumo al
        detalle.
      </p>
      <div className="planes">
        {PLANES.map((plan) => (
          <div className={plan.destacado ? 'plan destacado' : 'plan'} key={plan.nombre}>
            <span className="nombre">{plan.nombre}</span>
            <span className="para">{plan.para}</span>
            <ul>
              {plan.incluye.map((linea) => (
                <li key={linea}>{linea}</li>
              ))}
            </ul>
            <a
              className={plan.destacado ? 'boton principal' : 'boton secundario'}
              href={asunto(`Precio del plan ${plan.nombre}`)}
            >
              Pedir precio
            </a>
          </div>
        ))}
      </div>
    </section>
  )
}

function Confianza() {
  return (
    <section>
      <p className="eyebrow">Quiénes estamos detrás</p>
      <h2>Un solo producto, el mismo para todos</h2>
      <p className="guia">
        Flexómetro no lleva treinta años en el mercado y no vamos a fingir que sí. Lo que sí tenemos
        es velocidad. Pero no hacemos versiones a medida ni desarrollos particulares:{' '}
        <strong>escuchamos lo que pides y, si le sirve al resto, entra en la hoja de ruta.</strong>{' '}
        Un programa hecho solo para ti sería un programa que envejece solo, sin ninguna de las
        mejoras que reciben los demás.
      </p>
      <div className="rejilla tres">
        <div className="tarjeta">
          <h3>Tus datos son tuyos</h3>
          <p>Exportas cuando quieras, en BC3 y en CSV. Entrar no te ata.</p>
        </div>
        <div className="tarjeta">
          <h3>Aislamiento real</h3>
          <p>
            Cada empresa ve solo lo suyo, garantizado en la propia base de datos, no en el código de
            la pantalla.
          </p>
        </div>
        <div className="tarjeta">
          <h3>Puesta en marcha incluida</h3>
          <p>
            Importamos tu banco de precios y tus terceros desde BC3, CSV o Excel. No te dejamos
            delante de un formulario vacío.
          </p>
        </div>
      </div>
    </section>
  )
}

function Cierre() {
  return (
    <section className="sinlinea">
      <div className="cierre">
        <h2>Veinte minutos, tu propio presupuesto dentro</h2>
        <p>
          Tráete un BC3 de una obra real. Lo importamos en la llamada y sales viendo tu presupuesto
          y tu control de coste montados. Si no te convence, te llevas el fichero y no ha pasado
          nada.
        </p>
        <div className="acciones">
          <a className="boton principal" href={asunto('Demo de Flexómetro')}>
            Pedir la demo
          </a>
          <a className="boton secundario" href={asunto('Consulta')}>
            Escribir un correo
          </a>
        </div>
        <p className="apunte">Sin compromiso · Sin tarjeta · Sin instalar nada</p>
      </div>
    </section>
  )
}

function Pie() {
  return (
    <footer>
      <div>
        Flexómetro · ERP de construcción · <a href={`mailto:${CORREO}`}>{CORREO}</a>
      </div>
      <div>
        Presupuestación, ejecución y cobro de obra. Hecho en España, para cómo se trabaja en España.
      </div>
      <div className="firma">
        Un producto de <a href="/pirueta">PIRUETA</a> — startups, SaaS, integraciones y
        automatizaciones.
      </div>
    </footer>
  )
}

const CLAVE_COOKIES = 'flexometro:cookies'

/** Aviso de cookies. La elección solo vive en el navegador de quien visita: no
 *  viaja al servidor. El `try/catch` no es decorativo — en navegación privada
 *  y con las cookies de sitio bloqueadas, `localStorage` lanza al leerlo. */
function Cookies() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    let guardado: string | null = null
    try {
      guardado = localStorage.getItem(CLAVE_COOKIES)
    } catch {
      guardado = null
    }
    if (!guardado) setVisible(true)
  }, [])

  const responder = (valor: string) => {
    try {
      localStorage.setItem(CLAVE_COOKIES, valor)
    } catch {
      /* sin almacenamiento: el aviso volverá a salir, que es lo correcto */
    }
    setVisible(false)
  }

  if (!visible) return null

  return (
    <div className="flx-cookies">
      <h3>Cookies</h3>
      <p>
        Esta web no usa cookies de publicidad ni de seguimiento. Solo guardamos en tu navegador esta
        misma elección, para no volver a preguntártelo.
      </p>
      <div className="botones">
        <button type="button" className="aceptar" onClick={() => responder('todo')}>
          Aceptar
        </button>
        <button type="button" className="rechazar" onClick={() => responder('minimo')}>
          Solo lo necesario
        </button>
      </div>
      <details>
        <summary>Qué guardamos exactamente</summary>
        <p>
          <strong>Necesario:</strong> tu respuesta a este aviso, en el almacenamiento local de tu
          navegador. No sale de tu equipo.
        </p>
        <p>
          <strong>Terceros:</strong> las tipografías se cargan desde Google Fonts, que recibe tu
          dirección IP al servirlas. No hay analítica, ni píxeles, ni redes sociales.
        </p>
      </details>
    </div>
  )
}
