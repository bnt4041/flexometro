from app.core.modules import ModuleSpec, NavItem
from app.modules.terceros.router import router

SPEC = ModuleSpec(
    code="terceros",
    name="Terceros",
    description=(
        "Clientes, proveedores, subcontratistas y contactos. "
        "Una sola ficha con roles, no entidades separadas."
    ),
    icon="users",
    router=router,
    nav=(
        NavItem(label="Terceros", path="/terceros", icon="users"),
        NavItem(label="Contactos", path="/contactos", icon="user"),
    ),
)
