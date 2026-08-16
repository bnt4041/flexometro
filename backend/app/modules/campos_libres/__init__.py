from app.core.modules import ModuleSpec
from app.modules.campos_libres.router import router

SPEC = ModuleSpec(
    code="campos_libres",
    name="Campos libres",
    description=(
        "Campos definidos por el propio tenant sobre terceros, productos, obras, "
        "presupuestos y sus líneas — al estilo Dolibarr. Su edición vive dentro de "
        "Ajustes, no tiene navegación propia."
    ),
    icon="list-plus",
    router=router,
    always_active=True,
)
