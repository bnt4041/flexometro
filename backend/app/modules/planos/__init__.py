from app.core.modules import ModuleSpec, NavItem
from app.modules.planos.router import router

SPEC = ModuleSpec(
    code="planos",
    name="Planos",
    description=(
        "Biblioteca de planos por obra o presupuesto. Cada hoja se calibra "
        "sobre una cota conocida y a partir de ahí se mide encima: "
        "longitudes, áreas y conteos, por capas, junto a anotaciones y "
        "líneas auxiliares. Lo medido se puede llevar a una partida como una "
        "línea de medición más."
    ),
    icon="layers",
    router=router,
    # `presupuestos` no es opcional: llevar una medición a una partida es la
    # razón de ser de medir sobre un plano.
    depends_on=("core", "presupuestos"),
    nav=(NavItem(label="Planos", path="/planos", icon="layers", section="Obras"),),
)
