from app.core.modules import ModuleSpec
from app.modules.testmeter.router import router

SPEC = ModuleSpec(
    code="testmeter",
    name="Medidor de prueba (cámara + IA)",
    description=(
        "Prueba de concepto en /testmeter: reconoce con IA los elementos de "
        "una foto de obra (puertas, huecos, enchufes...) y estima sus "
        "dimensiones reales. Página pública, sin sesión ni organización — no "
        "aparece en el menú ni en Administración."
    ),
    router=router,
    always_active=True,
)
