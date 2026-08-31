from app.core.modules import ModuleSpec, NavItem
from app.modules.desarrolladores.router import router

SPEC = ModuleSpec(
    code="desarrolladores",
    name="Desarrolladores",
    description=(
        "Claves de API con los mismos ámbitos que los permisos de una "
        "persona, y webhooks firmados con reintentos y registro de envíos. "
        "Es la puerta para integrar Flexómetro con otros sistemas."
    ),
    icon="code",
    router=router,
    depends_on=("core",),
    nav=(
        NavItem(
            label="Desarrolladores",
            path="/desarrolladores",
            icon="code",
            section="Organización",
        ),
    ),
)
