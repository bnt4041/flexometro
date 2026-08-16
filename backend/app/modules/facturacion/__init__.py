from app.core.modules import ModuleSpec, NavItem
from app.modules.facturacion.router import router

SPEC = ModuleSpec(
    code="facturacion",
    name="Facturación",
    description=(
        "Certificaciones de obra, facturas y cobros. "
        "Veri*Factu/Facturae se integran vía n8n."
    ),
    icon="receipt",
    router=router,
    depends_on=("obras", "terceros"),
    tipo_documento_numeracion="factura",
    nav=(
        NavItem(label="Certificaciones", path="/certificaciones", icon="clipboard-check"),
        NavItem(label="Facturas", path="/facturas", icon="receipt"),
    ),
)
