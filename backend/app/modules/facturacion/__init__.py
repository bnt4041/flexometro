from app.core.modules import ModuleSpec, NavItem
from app.modules.facturacion.router import router

SPEC = ModuleSpec(
    code="facturacion",
    # El código interno sigue siendo "facturacion" (numeración, permisos,
    # activación por organización no cambian), pero de cara al usuario esta
    # es la sección "todo lo del lado del cliente" — certificaciones,
    # facturas y, colgados desde otros módulos vía `NavItem.section`, sus
    # pedidos y contratos.
    name="Clientes",
    description=(
        "Certificaciones de obra, facturas y cobros. "
        "Veri*Factu/Facturae se integran vía n8n."
    ),
    icon="receipt",
    router=router,
    depends_on=("obras", "terceros", "ia"),
    tipo_documento_numeracion="factura",
    nav=(
        NavItem(label="Certificaciones", path="/certificaciones", icon="clipboard-check"),
        NavItem(label="Facturas", path="/facturas", icon="receipt"),
    ),
)
