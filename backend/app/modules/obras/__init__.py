from app.core.modules import ModuleSpec, NavItem
from app.modules.obras.router import router

SPEC = ModuleSpec(
    code="obras",
    name="Obras",
    description="Ejecución: personal asignado, coste real frente a presupuestado.",
    icon="hard-hat",
    router=router,
    depends_on=("presupuestos",),
    nav=(
        NavItem(label="Obras", path="/obras", icon="hard-hat"),
        NavItem(label="Personal", path="/personal", icon="users"),
    ),
)
