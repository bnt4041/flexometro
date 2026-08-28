"""Registro de módulos de negocio.

Modularidad tipo Dolibarr: cada módulo se declara con un `ModuleSpec` (código,
metadatos, router propio, dependencias y entradas de navegación) y se activa o
desactiva por organización. Los routers se montan siempre, pero quedan detrás de
`require_module`, de modo que un módulo desactivado responde 404 en vez de
existir a medias.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session


@dataclass(frozen=True)
class NavItem:
    """Entrada de menú que el módulo publica al shell del frontend.

    `section` agrupa la entrada bajo un título de sección distinto del
    nombre de su propio módulo — por defecto (`None`) cada módulo pinta su
    propia sección con `ModuleSpec.name`; con `section` puesto, la entrada se
    cuelga de esa cabecera en su lugar (varias entradas de módulos distintos
    con el mismo `section` acaban en la misma sección del menú). Sirve para
    cuando el mismo objeto interesa desde dos ángulos del negocio (un pedido
    puede ser a proveedor o de cliente) sin duplicar el módulo entero."""

    label: str
    path: str
    icon: str = "square"
    section: str | None = None


@dataclass(frozen=True)
class ModuleSpec:
    code: str
    name: str
    description: str
    icon: str = "square"
    router: APIRouter | None = None
    depends_on: tuple[str, ...] = ()
    # El módulo core sostiene organizaciones y activación: no se puede apagar.
    always_active: bool = False
    nav: tuple[NavItem, ...] = field(default_factory=tuple)
    # Qué tipo de documento numera este módulo (ver `app.core.numeracion`), si
    # alguno — determina si el shell le pone un botón de ajustes (rueda
    # dentada) y qué patrón de numeración le muestra. `None` si el módulo no
    # tiene ajustes propios todavía.
    tipo_documento_numeracion: str | None = None


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, ModuleSpec] = {}

    def register(self, spec: ModuleSpec) -> None:
        if spec.code in self._modules:
            raise ValueError(f"El módulo '{spec.code}' ya está registrado")
        self._modules[spec.code] = spec

    def get(self, code: str) -> ModuleSpec:
        try:
            return self._modules[code]
        except KeyError:
            raise LookupError(f"Módulo desconocido: '{code}'") from None

    def all(self) -> list[ModuleSpec]:
        return list(self._modules.values())

    def codes(self) -> set[str]:
        return set(self._modules)

    def validate_dependencies(self) -> None:
        """Falla al arrancar, no en la primera request, si el grafo es inválido."""
        for spec in self._modules.values():
            for dep in spec.depends_on:
                if dep not in self._modules:
                    raise ValueError(
                        f"El módulo '{spec.code}' depende de '{dep}', que no está registrado"
                    )
        self._detect_cycles()

    def _detect_cycles(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(code: str, path: tuple[str, ...]) -> None:
            if code in visited:
                return
            if code in visiting:
                cycle = " -> ".join([*path, code])
                raise ValueError(f"Ciclo de dependencias entre módulos: {cycle}")
            visiting.add(code)
            for dep in self._modules[code].depends_on:
                walk(dep, (*path, code))
            visiting.discard(code)
            visited.add(code)

        for code in self._modules:
            walk(code, ())

    def resolve_activation(self, requested: Iterable[str]) -> set[str]:
        """Cierre transitivo: activar un módulo activa aquello de lo que depende."""
        resolved: set[str] = set()

        def pull(code: str) -> None:
            if code in resolved:
                return
            spec = self.get(code)
            resolved.add(code)
            for dep in spec.depends_on:
                pull(dep)

        for code in requested:
            pull(code)
        for spec in self._modules.values():
            if spec.always_active:
                resolved.add(spec.code)
        return resolved


registry = ModuleRegistry()


def require_module(code: str):
    """Dependencia de router: 404 si el módulo no está activo en esta organización."""

    async def _guard(
        principal: Principal = Depends(get_principal),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        from app.modules.core.service import is_module_active

        if not await is_module_active(session, principal.organization_id, code):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El módulo '{code}' no está activo en esta organización",
            )

    return _guard
