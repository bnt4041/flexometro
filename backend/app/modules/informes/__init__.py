from app.core.modules import ModuleSpec, NavItem
from app.modules.informes.router import router

SPEC = ModuleSpec(
    code="informes",
    name="Informes",
    description=(
        "Informes agregados sobre los datos de la organización: agrupar por "
        "lo que sea y contar o sumar. Cada informe se ejecuta con el alcance "
        "de permisos de quien lo abre, no con el de quien lo guardó."
    ),
    icon="file-text",
    router=router,
    depends_on=("core",),
    nav=(NavItem(label="Informes", path="/informes", icon="file-text", section="Organización"),),
)
