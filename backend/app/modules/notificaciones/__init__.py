from app.core.modules import ModuleSpec
from app.modules.notificaciones.router import router

SPEC = ModuleSpec(
    code="notificaciones",
    name="Notificaciones",
    description=(
        "Avisos configurables: qué recibe cada persona o grupo y por dónde "
        "(campana, correo o WhatsApp). Incluye vigilancias periódicas, como "
        "avisar de una obra que lleva demasiado tiempo sin cambiar de estado "
        "o de un documento a punto de caducar. Se configura desde la ficha "
        "de cada usuario y de cada grupo, no en una pantalla aparte."
    ),
    icon="bell",
    router=router,
    # `core` por los grupos a los que puede apuntar una regla. Los módulos de
    # los que se avisa NO son dependencia: el catálogo se filtra en caliente a
    # los que estén encendidos, así que esto funciona con los que haya.
    depends_on=("core",),
    # Sin entrada de menú a propósito: no hay nada que gestionar en una
    # pantalla propia. Qué recibe cada uno se decide en su ficha (Usuarios y
    # grupos), que es donde estás cuando te haces la pregunta.
    nav=(),
)
