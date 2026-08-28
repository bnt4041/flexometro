from app.core.modules import ModuleSpec, NavItem
from app.modules.presupuestos.router import router

SPEC = ModuleSpec(
    code="presupuestos",
    name="Presupuestos",
    description=(
        "Banco de precios, mediciones y presupuestos por capítulos. "
        "Núcleo del negocio."
    ),
    icon="calculator",
    router=router,
    # "terceros" por la FK de PrecioSuministro.proveedor_id: desde la fusión
    # de Producto en Concepto (Fase 25) ya no hace falta pasar por "catalogo",
    # que se disuelve.
    depends_on=("terceros",),
    tipo_documento_numeracion="presupuesto",
    nav=(
        # El banco de precios es un recurso de toda la cuenta, no de un
        # cliente o proveedor concreto — vive en la sección "Organización".
        NavItem(label="Banco de precios", path="/banco-precios", icon="layers", section="Organización"),
        # El presupuesto es lo que se le hace a un cliente — vive en
        # "Clientes" junto a sus pedidos, contratos, certificaciones y
        # facturas (ver `facturacion/__init__.py`, que es el módulo dueño de
        # esa sección).
        NavItem(label="Presupuestos", path="/presupuestos", icon="calculator", section="Clientes"),
    ),
)
