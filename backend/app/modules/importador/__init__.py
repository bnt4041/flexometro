from app.core.modules import ModuleSpec, NavItem
from app.modules.importador.router import router

SPEC = ModuleSpec(
    code="importador",
    name="Importador",
    description=(
        "Trae datos de otro sistema desde una hoja de CSV o Excel: terceros, "
        "contactos y personal. Propone el mapeo de columnas solo, avisa de "
        "los problemas antes de escribir nada, e importa fila a fila — si "
        "una falla, las demás entran igual."
    ),
    icon="upload",
    router=router,
    depends_on=("core", "terceros"),
    nav=(
        NavItem(label="Importador", path="/importador", icon="upload", section="Organización"),
    ),
)
