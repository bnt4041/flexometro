import type { ReactNode } from 'react'

import logo from '../assets/logo-sobre-oscuro-recorte.png'

interface Beneficio {
  titulo: string
  texto: string
  icono: ReactNode
}

const BENEFICIOS: Beneficio[] = [
  {
    titulo: 'Presupuestación profesional',
    texto:
      'El sistema clásico español de mediciones y presupuestos: de precio de suministro a precio unitario, capítulos y partidas, con versionado y plantillas reutilizables.',
    icono: <IconoRegla />,
  },
  {
    titulo: 'Ejecución de obra',
    texto:
      'Compras y albaranes, personal y parte de trabajo, coste real frente a lo presupuestado — para saber en todo momento cómo va cada obra.',
    icono: <IconoObra />,
  },
  {
    titulo: 'Certificaciones y facturación',
    texto:
      'Certificaciones periódicas, facturas y cobros ligados a cada obra, con numeración configurable por cuenta.',
    icono: <IconoFactura />,
  },
  {
    titulo: 'IA que ayuda de verdad',
    texto:
      'Sugerencias de partidas a partir de tus propios presupuestos y lectura de mediciones directamente desde el plano acotado.',
    icono: <IconoIa />,
  },
  {
    titulo: 'Multiorganización y seguro',
    texto:
      'Cada organización aislada con Row-Level Security forzado en PostgreSQL, no solo en la aplicación: el aislamiento lo impone la base de datos.',
    icono: <IconoEscudo />,
  },
  {
    titulo: 'Importa lo que ya tienes',
    texto:
      'Bancos de precios y presupuestos en formato BC3 (FIEBDC-3), el estándar del sector, listos para reutilizar sin recapturar nada.',
    icono: <IconoImportar />,
  },
]

export function Landing({ onEntrar }: { onEntrar: () => void }) {
  return (
    <div className="landing">
      <header className="landing__header">
        <div className="landing__header-inner">
          <img src={logo} alt="Flexómetro" className="landing__logo" />
          <button className="btn btn--primary" onClick={onEntrar}>
            Iniciar sesión
          </button>
        </div>
      </header>

      <section className="landing__hero">
        <div className="landing__hero-inner">
          <p className="landing__eyebrow">ERP para empresas de construcción</p>
          <h1 className="landing__titulo">
            Presupuesta, ejecuta y cobra tu obra desde un solo sitio
          </h1>
          <p className="landing__lead">
            De la medición al cobro: presupuestos con el sistema clásico español,
            compras y personal en obra, certificaciones y facturación — con IA que
            redacta partidas y lee mediciones desde el plano.
          </p>
          <div className="landing__hero-cta">
            <button className="btn btn--primary btn--lg" onClick={onEntrar}>
              Iniciar sesión
            </button>
            <a className="landing__hero-link" href="#beneficios">
              Ver qué incluye ↓
            </a>
          </div>
        </div>
      </section>

      <section className="landing__beneficios" id="beneficios">
        <div className="landing__beneficios-inner">
          <h2 className="landing__seccion-titulo">Todo el ciclo de la obra, en un solo sistema</h2>
          <div className="landing__grid">
            {BENEFICIOS.map((b) => (
              <article className="landing__card" key={b.titulo}>
                <div className="landing__card-icono">{b.icono}</div>
                <h3>{b.titulo}</h3>
                <p>{b.texto}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="landing__cta-final">
        <div className="landing__cta-final-inner">
          <h2>Empieza a presupuestar hoy</h2>
          <p>Accede con tu cuenta para entrar al ERP.</p>
          <button className="btn btn--primary btn--lg" onClick={onEntrar}>
            Iniciar sesión
          </button>
        </div>
      </section>

      <footer className="landing__footer">
        <span>© {new Date().getFullYear()} Flexómetro — ERP de construcción</span>
      </footer>
    </div>
  )
}

function IconoRegla() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 16.5 16.5 3l4.5 4.5L7.5 21z" />
      <path d="m9 7.5 1.5 1.5" />
      <path d="m12 4.5 1.5 1.5" />
      <path d="m6 10.5 1.5 1.5" />
      <path d="m3 13.5 1.5 1.5" />
    </svg>
  )
}

function IconoObra() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 21h18" />
      <path d="M5 21V10l7-6 7 6v11" />
      <path d="M9 21v-6h6v6" />
      <path d="M9 12h.01" />
      <path d="M15 12h.01" />
    </svg>
  )
}

function IconoFactura() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 2h9l3 3v17H6z" />
      <path d="M15 2v3h3" />
      <path d="M9 12h6" />
      <path d="M9 16h6" />
      <path d="M9 8h3" />
    </svg>
  )
}

function IconoIa() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v3" />
      <path d="M12 18v3" />
      <path d="M3 12h3" />
      <path d="M18 12h3" />
      <rect x="6" y="6" width="12" height="12" rx="3" />
      <path d="M9.5 10h.01" />
      <path d="M14.5 10h.01" />
      <path d="M9 15c1 .8 5 .8 6 0" />
    </svg>
  )
}

function IconoEscudo() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3 4 6v6c0 5 3.5 7.9 8 9 4.5-1.1 8-4 8-9V6z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  )
}

function IconoImportar() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M12 11v6" />
      <path d="m9.5 14.5 2.5 2.5 2.5-2.5" />
    </svg>
  )
}
