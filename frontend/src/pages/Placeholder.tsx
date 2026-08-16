interface Props {
  title: string
  phase: string
}

/** Cada pantalla real llega en su fase; esto marca el hueco y qué lo llenará. */
export function Placeholder({ title, phase }: Props) {
  return (
    <>
      <h1 className="page-title">{title}</h1>
      <p className="page-lead">Andamiaje listo. La pantalla se construye en su fase.</p>
      <div className="placeholder">
        <div>Pendiente de implementación</div>
        <div className="placeholder__phase">{phase}</div>
      </div>
    </>
  )
}
