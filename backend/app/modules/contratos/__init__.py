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
    # Un contrato puede ser de cliente o de proveedor (`Contrato.tipo`) —
    # mismo listado, con atajo desde las dos secciones donde alguien puede
    # buscarlo primero (mismo criterio ya usado con `Pedido`/`Albaran` en
    # `compras/__init__.py`), en vez de tener su propia sección de un solo
    # enlace.
    nav=(
        NavItem(label="Contratos", path="/contratos", icon="file-text", section="Clientes"),
        NavItem(label="Contratos", path="/contratos", icon="file-text", section="Compras"),
    ),
)
