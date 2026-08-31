from app.core.modules import ModuleSpec, NavItem
from app.modules.automatizaciones.router import router

SPEC = ModuleSpec(
    code="automatizaciones",
    name="Automatizaciones",
    description=(
        "Flujos de nodos que se disparan solos: cuando pasa algo, cuando "
        "llaman a una URL o cada cierto tiempo. Cada nodo recibe lo que "
        "produjeron los anteriores, hace lo suyo y decide por qué rama "
        "sigue el flujo."
    ),
    icon="layers",
    router=router,
    depends_on=("core", "notificaciones"),
    nav=(
        NavItem(
            label="Automatizaciones",
            path="/automatizaciones",
            icon="layers",
            section="Organización",
        ),
    ),
)
