import pytest

from app.core.modules import ModuleRegistry, ModuleSpec


def spec(code: str, *, depends_on: tuple[str, ...] = (), always_active: bool = False):
    return ModuleSpec(
        code=code,
        name=code.title(),
        description="",
        depends_on=depends_on,
        always_active=always_active,
    )


def test_no_admite_codigos_duplicados():
    registry = ModuleRegistry()
    registry.register(spec("compras"))
    with pytest.raises(ValueError, match="ya está registrado"):
        registry.register(spec("compras"))


def test_dependencia_inexistente_falla_al_validar():
    registry = ModuleRegistry()
    registry.register(spec("compras", depends_on=("obras",)))
    with pytest.raises(ValueError, match="no está registrado"):
        registry.validate_dependencies()


def test_detecta_ciclos():
    registry = ModuleRegistry()
    registry.register(spec("a", depends_on=("b",)))
    registry.register(spec("b", depends_on=("a",)))
    with pytest.raises(ValueError, match="Ciclo de dependencias"):
        registry.validate_dependencies()


def test_activar_arrastra_dependencias_transitivas():
    registry = ModuleRegistry()
    registry.register(spec("core", always_active=True))
    registry.register(spec("presupuestos"))
    registry.register(spec("obras", depends_on=("presupuestos",)))
    registry.register(spec("compras", depends_on=("obras",)))
    registry.validate_dependencies()

    assert registry.resolve_activation(["compras"]) == {
        "compras",
        "obras",
        "presupuestos",
        "core",
    }


def test_los_modulos_always_active_siempre_entran():
    registry = ModuleRegistry()
    registry.register(spec("core", always_active=True))
    registry.register(spec("presupuestos"))
    registry.validate_dependencies()

    assert registry.resolve_activation([]) == {"core"}


def test_el_grafo_real_de_la_aplicacion_es_valido():
    """Falla si alguien añade un módulo con una dependencia rota."""
    from app.core.modules import registry as app_registry
    from app.modules import register_all

    if not app_registry.codes():
        register_all()
    app_registry.validate_dependencies()
    assert "presupuestos" in app_registry.codes()
