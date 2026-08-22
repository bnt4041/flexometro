"""Descubrimiento y registro de los módulos de negocio.

Un módulo nuevo se añade importándolo aquí y exponiendo un `SPEC`. Los modelos
se importan explícitamente para que estén todos en `Base.metadata` cuando
Alembic autogenere migraciones.

Grafo de dependencias:

    terceros     (base)
    presupuestos -> terceros
    obras        -> presupuestos
    compras      -> obras
    facturacion  -> obras, terceros
    ia           -> presupuestos

El módulo `catalogo` (Producto, Familia, PrecioSuministro) existió hasta la
Fase 25, cuando se fusionó en `presupuestos.Concepto` bajo el nombre "banco de
precios": un producto/servicio y una partida unitaria son la misma ficha.
"""

from app.core.modules import registry
from app.modules.campos_libres import SPEC as CAMPOS_LIBRES
from app.modules.compras import SPEC as COMPRAS
from app.modules.core import SPEC as CORE
from app.modules.crm import SPEC as CRM
from app.modules.documentos import SPEC as DOCUMENTOS
from app.modules.facturacion import SPEC as FACTURACION
from app.modules.ia import SPEC as IA
from app.modules.obras import SPEC as OBRAS
from app.modules.presupuestos import SPEC as PRESUPUESTOS
from app.modules.terceros import SPEC as TERCEROS

ALL_SPECS = (
    CORE, CAMPOS_LIBRES, CRM, DOCUMENTOS, TERCEROS, PRESUPUESTOS, OBRAS, COMPRAS, FACTURACION, IA,
)


def register_all() -> None:
    for spec in ALL_SPECS:
        registry.register(spec)
    registry.validate_dependencies()


def import_models() -> None:
    """Puebla Base.metadata. Lo usa el env.py de Alembic."""
    from app.modules.campos_libres import models as _campos_libres_models  # noqa: F401
    from app.modules.compras import models as _compras_models  # noqa: F401
    from app.modules.crm import models as _crm_models  # noqa: F401
    from app.modules.documentos import models as _documentos_models  # noqa: F401
    from app.modules.core import auditoria_models as _core_auditoria_models  # noqa: F401
    from app.modules.core import billing_models as _core_billing_models  # noqa: F401
    from app.modules.core import diccionario_models as _core_diccionario_models  # noqa: F401
    from app.modules.core import models as _core_models  # noqa: F401
    from app.modules.core import moneda_models as _core_moneda_models  # noqa: F401
    from app.modules.core import numeracion_models as _core_numeracion_models  # noqa: F401
    from app.modules.core import traduccion_models as _core_traduccion_models  # noqa: F401
    from app.modules.core import permisos_models as _core_permisos_models  # noqa: F401
    from app.modules.core import settings_models as _core_settings_models  # noqa: F401
    from app.modules.facturacion import models as _facturacion_models  # noqa: F401
    from app.modules.ia import models as _ia_models  # noqa: F401
    from app.modules.obras import models as _obras_models  # noqa: F401
    from app.modules.presupuestos import models as _presupuestos_models  # noqa: F401
    from app.modules.presupuestos import (  # noqa: F401
        models_presupuesto as _presupuesto_models,
    )
    from app.modules.presupuestos import (  # noqa: F401
        plantilla_docx_models as _presupuesto_plantilla_docx_models,
    )
    from app.modules.terceros import models as _terceros_models  # noqa: F401
