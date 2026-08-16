from app.core.modules import ModuleSpec, NavItem
from app.modules.catalogo.router import router

SPEC = ModuleSpec(
    code="catalogo",
    name="Catálogo",
    description=(
        "Productos y servicios, familias y tarifas de proveedor. "
        "El precio de suministro es el primer eslabón de la cadena de precios."
    ),
    icon="package",
    router=router,
    depends_on=("terceros",),
    nav=(NavItem(label="Productos", path="/productos", icon="package"),),
)
