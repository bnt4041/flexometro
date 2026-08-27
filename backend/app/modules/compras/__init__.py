from app.core.modules import ModuleSpec, NavItem
from app.modules.compras.router import router

SPEC = ModuleSpec(
    code="compras",
    name="Compras",
    description="Proveedores, pedidos y albaranes de material.",
    icon="truck",
    router=router,
    # "obras" ya arrastra "presupuestos" transitivamente, de donde sale el
    # concepto que una línea de albarán puede referenciar.
    depends_on=("obras",),
    tipo_documento_numeracion="albaran",
    # Los proveedores ya se gestionan en Terceros (filtrando por rol); aquí
    # solo hace falta navegación a lo que es propio de este módulo.
    nav=(
        NavItem(label="Pedidos", path="/pedidos", icon="truck"),
        NavItem(label="Albaranes", path="/albaranes", icon="truck"),
        NavItem(label="Facturas recibidas", path="/facturas-recibidas", icon="receipt"),
        # Las ofertas que devuelven los proveedores al responder una
        # solicitud de precios (ver `compras/oferta_service.py`): mismo
        # paradigma de partidas y mediciones que un presupuesto de cliente,
        # solo que `tipo == 'proveedor'` — por eso reutiliza la ficha de
        # Presupuestos en vez de tener una propia.
        NavItem(label="Presupuestos de proveedor", path="/presupuestos-proveedor", icon="clipboard-check"),
    ),
)
