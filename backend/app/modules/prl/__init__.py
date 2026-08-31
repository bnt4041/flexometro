from app.core.modules import ModuleSpec, NavItem
from app.modules.prl.router import router

SPEC = ModuleSpec(
    code="prl",
    name="PRL y recursos",
    description=(
        "Prevención de riesgos laborales y recursos de la empresa: vehículos "
        "y maquinaria con su documentación, control de caducidades de todos "
        "los documentos PRL (empresa, personal, obra y proveedores), "
        "plantillas de documento y envío a firma a terceros."
    ),
    icon="shield-check",
    router=router,
    # `obras` por `Personal` y `Obra` (los documentos PRL cuelgan de ellos);
    # `terceros` por el proveedor al que se le pide la firma.
    depends_on=("obras", "terceros"),
    nav=(
        NavItem(label="PRL", path="/prl", icon="shield-check", section="Organización"),
        NavItem(label="Recursos", path="/recursos", icon="truck", section="Organización"),
        NavItem(
            label="Documentos a firmar", path="/firmas", icon="file-signature", section="Organización"
        ),
    ),
)
