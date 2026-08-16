from app.core.modules import ModuleSpec, NavItem
from app.modules.ia.router import router

SPEC = ModuleSpec(
    code="ia",
    name="IA — patrones de presupuesto",
    description=(
        "Sugerencia de estructura de presupuesto por tipo de obra a partir del "
        "histórico propio, vía DeepSeek. Módulo opt-in: solo se activa si la "
        "organización quiere que su vocabulario de partidas (nunca precios) "
        "salga hacia un proveedor de IA externo."
    ),
    icon="sparkles",
    router=router,
    depends_on=("presupuestos",),
    nav=(NavItem(label="Sugerir patrón", path="/ia/patrones", icon="sparkles"),),
)
