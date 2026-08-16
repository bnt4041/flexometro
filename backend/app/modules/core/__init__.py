from app.core.modules import ModuleSpec, NavItem
from app.modules.core.router import router

SPEC = ModuleSpec(
    code="core",
    name="Núcleo",
    description="Organizaciones, activación de módulos e identidad.",
    icon="settings",
    router=router,
    always_active=True,
    nav=(NavItem(label="Ajustes", path="/ajustes", icon="settings"),),
)
