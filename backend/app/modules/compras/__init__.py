from app.core.modules import ModuleSpec, NavItem
from app.modules.compras.router import router

SPEC = ModuleSpec(
    code="compras",
    name="Compras",
    description="Proveedores, pedidos y albaranes de material.",
    icon="truck",
    router=router,
    depends_on=("obras", "catalogo"),
    tipo_documento_numeracion="albaran",
    # Los proveedores ya se gestionan en Terceros (filtrando por rol); aquí
    # solo hace falta navegación a lo que es propio de este módulo.
    nav=(NavItem(label="Albaranes", path="/albaranes", icon="truck"),),
)
