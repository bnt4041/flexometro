from app.core.modules import ModuleSpec
from app.modules.documentos.router import router

SPEC = ModuleSpec(
    code="documentos",
    name="Documentos",
    description=(
        "Ficheros subidos sobre terceros, presupuestos, obras, certificaciones y "
        "facturas, guardados en MinIO. Su única vista es la pestaña 'Documentos' de "
        "cada ficha, no tiene navegación propia."
    ),
    icon="file-text",
    router=router,
    always_active=True,
)
