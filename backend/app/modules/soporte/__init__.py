from app.core.modules import ModuleSpec, NavItem
from app.modules.soporte.router import router

SPEC = ModuleSpec(
    code="soporte",
    name="Soporte y ayuda",
    description=(
        "Tickets para que cualquiera pida ayuda y una wiki con la "
        "documentación de la casa. La wiki se indexa por significado "
        "(pgvector + embeddings de Gemini) para que el asistente pueda "
        "responder citándola."
    ),
    icon="life-buoy",
    router=router,
    depends_on=("core",),
    nav=(
        NavItem(label="Ayuda y tickets", path="/soporte", icon="life-buoy",
                section="Organización"),
    ),
)
