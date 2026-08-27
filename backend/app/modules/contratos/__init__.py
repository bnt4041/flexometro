from app.core.modules import ModuleSpec, NavItem
from app.modules.contratos.router import router

SPEC = ModuleSpec(
    code="contratos",
    name="Contratos",
    description="Formaliza el acuerdo de una obra: con el cliente o con un proveedor.",
    icon="file-text",
    router=router,
    # Necesita obra (a qué obra pertenece) y terceros (cliente/proveedor).
    # No cuelga de presupuestos aunque enlace uno: no comparte su esquema de
    # partidas/mediciones, y presupuestos ya es el nodo con más dependientes
    # del grafo — no hace falta arrastrar más.
    depends_on=("obras", "terceros"),
    tipo_documento_numeracion="contrato",
    nav=(NavItem(label="Contratos", path="/contratos", icon="file-text"),),
)
