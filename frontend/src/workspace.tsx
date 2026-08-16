import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { aplicarOverridesTraduccion } from './i18n'
import { api } from './lib/api'
import type { Module, Principal } from './lib/api'
import {
  cargarConfig,
  cerrarSesion,
  fijarOrganizacion,
  iniciarSesion,
  procesarRetorno,
  requiereLogin,
  restaurarSesion,
} from './lib/auth'

type Estado = 'arrancando' | 'sin-sesion' | 'listo' | 'error'

interface Workspace {
  estado: Estado
  principal: Principal | null
  modules: Module[]
  error: string | null
  reload: () => Promise<void>
  entrar: () => Promise<void>
  salir: () => void
  cambiarOrganizacion: (slug: string) => Promise<void>
}

const WorkspaceContext = createContext<Workspace | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<Estado>('arrancando')
  const [principal, setPrincipal] = useState<Principal | null>(null)
  const [modules, setModules] = useState<Module[]>([])
  const [error, setError] = useState<string | null>(null)

  const cargarDatos = useCallback(async () => {
    const [me, mods, overrides] = await Promise.all([
      api.me(),
      api.modules(),
      api.traducciones.list(),
    ])
    aplicarOverridesTraduccion(overrides)
    setPrincipal(me)
    setModules(mods)
    setError(null)
    setEstado('listo')
  }, [])

  const reload = useCallback(async () => {
    try {
      await cargarDatos()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setEstado('error')
    }
  }, [cargarDatos])

  useEffect(() => {
    let cancelado = false

    async function arrancar() {
      try {
        await cargarConfig()

        // Primero el retorno de Keycloak: si venimos con un código, hay que
        // canjearlo antes de decidir si hay sesión.
        const destino = await procesarRetorno()
        if (destino) window.history.replaceState({}, '', destino)

        if (requiereLogin() && !(await restaurarSesion())) {
          if (!cancelado) setEstado('sin-sesion')
          return
        }

        await cargarDatos()
      } catch (err) {
        if (cancelado) return
        setError(err instanceof Error ? err.message : 'Error desconocido')
        setEstado('error')
      }
    }

    void arrancar()
    return () => {
      cancelado = true
    }
  }, [cargarDatos])

  const cambiarOrganizacion = useCallback(
    async (slug: string) => {
      fijarOrganizacion(slug)
      await reload()
    },
    [reload],
  )

  return (
    <WorkspaceContext.Provider
      value={{
        estado,
        principal,
        modules,
        error,
        reload,
        entrar: iniciarSesion,
        salir: cerrarSesion,
        cambiarOrganizacion,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace(): Workspace {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) throw new Error('useWorkspace fuera de WorkspaceProvider')
  return ctx
}
