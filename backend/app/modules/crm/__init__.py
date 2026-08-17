from app.core.modules import ModuleSpec
from app.modules.crm.router import router

SPEC = ModuleSpec(
    code="crm",
    name="CRM",
    description=(
        "Notas de seguimiento sobre terceros, presupuestos, obras, certificaciones y "
        "facturas. Su única vista es la pestaña 'CRM' de cada ficha, no tiene navegación propia."
    ),
    icon="sticky-note",
    router=router,
    always_active=True,
)
