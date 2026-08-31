from app.core.modules import ModuleSpec, NavItem
from app.modules.obras.router import router

SPEC = ModuleSpec(
    code="obras",
    name="Obras",
    description="Ejecución: personal asignado, coste real frente a presupuestado.",
    icon="hard-hat",
    router=router,
    depends_on=("presupuestos", "ia"),
    nav=(
        NavItem(label="Obras", path="/obras", icon="hard-hat"),
        # La plantilla es de la empresa, no de una obra concreta: vive con el
        # resto de lo que describe a la organización (banco de precios, PRL,
        # recursos) y no bajo "Obras", que es ejecución.
        NavItem(label="Personal", path="/personal", icon="users", section="Organización"),
    ),
)
