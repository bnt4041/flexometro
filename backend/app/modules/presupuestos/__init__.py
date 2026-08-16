from app.core.modules import ModuleSpec, NavItem
from app.modules.presupuestos import hooks
from app.modules.presupuestos.router import router

# El módulo se suscribe al importarse: a partir de aquí, un cambio de tarifa en
# catalogo dispara el recálculo en cascada sin que catalogo sepa que existimos.
hooks.registrar()

SPEC = ModuleSpec(
    code="presupuestos",
    name="Presupuestos",
    description=(
        "Precios descompuestos, mediciones y presupuestos por capítulos. "
        "Núcleo del negocio."
    ),
    icon="calculator",
    router=router,
    depends_on=("catalogo",),
    tipo_documento_numeracion="presupuesto",
    nav=(
        NavItem(label="Cuadro de precios", path="/precios", icon="layers"),
        NavItem(label="Presupuestos", path="/presupuestos", icon="calculator"),
        NavItem(label="Importar BC3", path="/importar-bc3", icon="upload"),
    ),
)
