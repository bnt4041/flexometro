from app.core.modules import ModuleSpec, NavItem
from app.modules.plexo.router import router

SPEC = ModuleSpec(
    code="plexo",
    name="Universo Plexo",
    description=(
        "Punto de unión entre organizaciones de cuentas distintas: buscarse, "
        "invitarse y conectar. Es la base sobre la que se construirá el "
        "intercambio de documentos, el directorio para colaborar en "
        "proyectos y el resto del universo Plexo — este primer paso solo "
        "establece el vínculo, todavía no mueve ningún dato de negocio."
    ),
    icon="globe",
    router=router,
    depends_on=("core",),
    nav=(NavItem(label="Universo Plexo", path="/plexo", icon="globe", section="Organización"),),
)
