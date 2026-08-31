"""prl: alta del módulo (recursos, documentos con caducidad y firma)

Cinco tablas y un catálogo sembrado:

- `recurso`: vehículos y maquinaria, que tienen documentación que caduca
  exactamente igual que la tiene una persona.
- `tipo_documento_prl`: catálogo editable de qué se exige y cuánto dura. Se
  siembra con los tipos habituales del sector de la construcción en España,
  pero es dato, no código: cada organización lo ajusta.
- `documento_prl`: el documento concreto, con su caducidad obligatoria.
- `plantilla_documento` y `solicitud_firma`: el circuito de mandar algo a
  firmar a un tercero y guardar la evidencia.
- `firma_token`: FUERA DE RLS a propósito, igual que `compras.acceso_token`
  — hay que resolver a qué organización pertenece un enlace ANTES de que
  exista contexto, y sin contexto RLS devuelve cero filas. Ver el docstring
  de `prl/models.py:FirmaToken`.

Revision ID: prl_0001
Revises:
Create Date: 2026-08-28
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.rls import (
    activar_rls,
    conceder_privilegios_app,
    desactivar_rls,
    revocar_privilegios_app,
)

revision: str = "prl_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("prl",)
depends_on: str | Sequence[str] | None = ("obras", "terceros", "documentos")

_AMBITOS = ("empresa", "personal", "recurso", "obra", "proveedor")

#: Catálogo inicial: (código, nombre, ámbito, meses de validez, obligatorio).
#: Los plazos son los habituales; la norma no fija todos, así que son un valor
#: de partida editable, no una verdad legal.
_TIPOS_INICIALES = [
    # Empresa — lo que pide una subcontrata antes de dejarte entrar en obra.
    ("concierto-spa", "Concierto con servicio de prevención ajeno", "empresa", 12, True),
    ("evaluacion-riesgos", "Evaluación de riesgos", "empresa", 36, True),
    ("plan-prevencion", "Plan de prevención de riesgos laborales", "empresa", 36, True),
    ("planificacion-preventiva", "Planificación de la actividad preventiva", "empresa", 12, True),
    ("seguro-rc", "Seguro de responsabilidad civil", "empresa", 12, True),
    ("certificado-ss", "Certificado corriente de pago con la Seguridad Social", "empresa", 6, True),
    ("certificado-aeat", "Certificado corriente de pago con Hacienda", "empresa", 6, True),
    ("rea", "Inscripción en el REA", "empresa", 36, False),
    # Personal — art. 19 y 22 de la Ley 31/1995 y convenio del sector.
    ("formacion-prl", "Formación en PRL del puesto", "personal", 48, True),
    ("reconocimiento-medico", "Certificado de aptitud médica", "personal", 12, True),
    ("tpc", "Tarjeta Profesional de la Construcción", "personal", 60, False),
    ("entrega-epis", "Justificante de entrega de EPIs", "personal", 24, True),
    ("informacion-riesgos", "Información de riesgos del puesto", "personal", 48, True),
    ("alta-ss", "Alta en la Seguridad Social (TA.2)", "personal", 120, True),
    ("autorizacion-maquinaria", "Autorización de uso de maquinaria", "personal", 36, False),
    # Recursos — vehículos y máquinas.
    ("itv", "ITV en vigor", "recurso", 12, True),
    ("seguro-vehiculo", "Seguro del vehículo", "recurso", 12, True),
    ("marcado-ce", "Declaración CE de conformidad", "recurso", 120, True),
    ("manual-instrucciones", "Manual de instrucciones", "recurso", 120, False),
    ("mantenimiento", "Último mantenimiento / revisión", "recurso", 12, True),
    ("inspeccion-periodica", "Inspección periódica reglamentaria", "recurso", 12, False),
    # Obra — RD 1627/1997 y Ley 32/2006.
    ("plan-seguridad", "Plan de seguridad y salud", "obra", 60, True),
    ("acta-aprobacion-pss", "Acta de aprobación del plan de seguridad", "obra", 60, True),
    ("apertura-centro", "Comunicación de apertura del centro de trabajo", "obra", 60, True),
    ("libro-subcontratacion", "Libro de subcontratación", "obra", 60, False),
    ("libro-incidencias", "Libro de incidencias", "obra", 60, False),
    ("nombramiento-recurso-preventivo", "Nombramiento de recurso preventivo", "obra", 12, False),
    ("acta-coordinacion", "Acta de coordinación de actividades (CAE)", "obra", 12, True),
    # Proveedor / subcontrata — RD 171/2004.
    ("cae-proveedor", "Documentación CAE de la subcontrata", "proveedor", 12, True),
    ("rea-proveedor", "Inscripción en el REA de la subcontrata", "proveedor", 36, False),
    ("ss-proveedor", "Corriente de pago con la SS de la subcontrata", "proveedor", 6, True),
]


def _enum(nombre: str, *valores: str) -> sa.Enum:
    """Mismo criterio que el resto del proyecto: `native_enum=False` (un
    CHECK sobre VARCHAR) en vez de un tipo ENUM de PostgreSQL, para poder
    añadir valores sin un ALTER TYPE que bloquee la tabla."""
    return sa.Enum(*valores, name=nombre, native_enum=False, length=32)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS prl")

    op.create_table(
        "recurso",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column(
            "tipo",
            _enum("tipo_recurso", "vehiculo", "maquinaria", "herramienta", "epi", "otro"),
            nullable=False,
            server_default="maquinaria",
        ),
        sa.Column("marca", sa.String(length=80), nullable=True),
        sa.Column("modelo", sa.String(length=80), nullable=True),
        sa.Column("matricula", sa.String(length=20), nullable=True),
        sa.Column("numero_serie", sa.String(length=60), nullable=True),
        sa.Column("anio_fabricacion", sa.Integer(), nullable=True),
        sa.Column("fecha_adquisicion", sa.Date(), nullable=True),
        sa.Column("obra_id", sa.UUID(), nullable=True),
        sa.Column("responsable_id", sa.UUID(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_recurso_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"], name=op.f("fk_recurso_obra_id_obra"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["responsable_id"], ["obras.personal.id"],
            name=op.f("fk_recurso_responsable_id_personal"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurso")),
        sa.UniqueConstraint("organization_id", "codigo", name="recurso_codigo_unique"),
        schema="prl",
    )
    op.create_index(
        op.f("ix_prl_recurso_organization_id"), "recurso", ["organization_id"], schema="prl"
    )
    op.create_index("ix_prl_recurso_obra", "recurso", ["obra_id"], schema="prl")
    op.create_index("ix_prl_recurso_responsable", "recurso", ["responsable_id"], schema="prl")

    op.create_table(
        "tipo_documento_prl",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("ambito", _enum("ambito_prl", *_AMBITOS), nullable=False),
        sa.Column("meses_validez", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("obligatorio", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_tipo_documento_prl_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tipo_documento_prl")),
        sa.UniqueConstraint(
            "organization_id", "codigo", name="tipo_documento_prl_codigo_unique"
        ),
        schema="prl",
    )
    op.create_index(
        op.f("ix_prl_tipo_documento_prl_organization_id"),
        "tipo_documento_prl", ["organization_id"], schema="prl",
    )

    op.create_table(
        "documento_prl",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("tipo_id", sa.UUID(), nullable=False),
        sa.Column("ambito", _enum("ambito_prl", *_AMBITOS), nullable=False),
        sa.Column("entidad_id", sa.UUID(), nullable=True),
        sa.Column("fecha_emision", sa.Date(), nullable=True),
        sa.Column("fecha_caducidad", sa.Date(), nullable=False),
        sa.Column("documento_id", sa.UUID(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_documento_prl_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_id"], ["prl.tipo_documento_prl.id"],
            name=op.f("fk_documento_prl_tipo_id_tipo_documento_prl"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["documento_id"], ["documentos.documento.id"],
            name=op.f("fk_documento_prl_documento_id_documento"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documento_prl")),
        schema="prl",
    )
    op.create_index(
        op.f("ix_prl_documento_prl_organization_id"),
        "documento_prl", ["organization_id"], schema="prl",
    )
    op.create_index(
        "ix_prl_documento_ambito", "documento_prl",
        ["organization_id", "ambito", "entidad_id"], schema="prl",
    )
    op.create_index(
        "ix_prl_documento_caducidad", "documento_prl",
        ["organization_id", "fecha_caducidad"], schema="prl",
    )

    op.create_table(
        "plantilla_documento",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column(
            "ambito", _enum("ambito_prl", *_AMBITOS), nullable=False, server_default="proveedor"
        ),
        sa.Column("tipo_documento_id", sa.UUID(), nullable=True),
        sa.Column("contenido", sa.Text(), nullable=False, server_default=""),
        sa.Column("requiere_firma", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_plantilla_documento_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_documento_id"], ["prl.tipo_documento_prl.id"],
            name=op.f("fk_plantilla_documento_tipo_documento_id"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plantilla_documento")),
        sa.UniqueConstraint(
            "organization_id", "codigo", name="plantilla_documento_codigo_unique"
        ),
        schema="prl",
    )
    op.create_index(
        op.f("ix_prl_plantilla_documento_organization_id"),
        "plantilla_documento", ["organization_id"], schema="prl",
    )

    op.create_table(
        "solicitud_firma",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("contenido_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("plantilla_id", sa.UUID(), nullable=True),
        sa.Column("obra_id", sa.UUID(), nullable=True),
        sa.Column("tercero_id", sa.UUID(), nullable=True),
        sa.Column("destinatario_nombre", sa.String(length=160), nullable=False),
        sa.Column("destinatario_email", sa.String(length=200), nullable=False),
        sa.Column(
            "estado",
            _enum(
                "estado_firma",
                "borrador", "enviada", "vista", "firmada", "rechazada", "cancelada",
            ),
            nullable=False,
            server_default="borrador",
        ),
        sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vista_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("firmada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("firmante_nombre", sa.String(length=160), nullable=True),
        sa.Column("firmante_dni", sa.String(length=20), nullable=True),
        sa.Column("firma_imagen", sa.Text(), nullable=True),
        sa.Column("ip_firma", sa.String(length=45), nullable=True),
        sa.Column("user_agent_firma", sa.String(length=400), nullable=True),
        sa.Column("motivo_rechazo", sa.Text(), nullable=True),
        sa.Column("documento_id", sa.UUID(), nullable=True),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_solicitud_firma_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plantilla_id"], ["prl.plantilla_documento.id"],
            name=op.f("fk_solicitud_firma_plantilla_id"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_solicitud_firma_obra_id_obra"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tercero_id"], ["terceros.tercero.id"],
            name=op.f("fk_solicitud_firma_tercero_id_tercero"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["documento_id"], ["documentos.documento.id"],
            name=op.f("fk_solicitud_firma_documento_id_documento"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solicitud_firma")),
        sa.UniqueConstraint("organization_id", "codigo", name="solicitud_firma_codigo_unique"),
        schema="prl",
    )
    op.create_index(
        op.f("ix_prl_solicitud_firma_organization_id"),
        "solicitud_firma", ["organization_id"], schema="prl",
    )
    op.create_index("ix_prl_solicitud_firma_obra", "solicitud_firma", ["obra_id"], schema="prl")
    op.create_index(
        "ix_prl_solicitud_firma_estado", "solicitud_firma",
        ["organization_id", "estado"], schema="prl",
    )

    op.create_table(
        "firma_token",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("solicitud_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_firma_token_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solicitud_id"], ["prl.solicitud_firma.id"],
            name=op.f("fk_firma_token_solicitud_id_solicitud_firma"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_firma_token")),
        sa.UniqueConstraint("token_hash", name="firma_token_hash_unique"),
        schema="prl",
    )

    # RLS en todo menos en `firma_token` — ver el docstring del módulo.
    for tabla in (
        "recurso",
        "tipo_documento_prl",
        "documento_prl",
        "plantilla_documento",
        "solicitud_firma",
    ):
        activar_rls("prl", tabla)
    conceder_privilegios_app("prl")

    # Catálogo inicial para las organizaciones que ya existen. Las nuevas lo
    # reciben al crearse (ver `core.service.crear_organizacion`); aquí se
    # siembra a las de ahora para que el módulo no arranque vacío.
    valores = ", ".join(
        f"('{codigo}', $${nombre}$$, '{ambito}', {meses}, {'true' if obligatorio else 'false'})"
        for codigo, nombre, ambito, meses, obligatorio in _TIPOS_INICIALES
    )
    op.execute(
        f"""
        INSERT INTO prl.tipo_documento_prl
            (id, organization_id, codigo, nombre, ambito, meses_validez, obligatorio, activo)
        SELECT gen_random_uuid(), o.id, t.codigo, t.nombre, t.ambito, t.meses, t.obligatorio, true
        FROM core.organization o
        CROSS JOIN (VALUES {valores})
            AS t(codigo, nombre, ambito, meses, obligatorio)
        ON CONFLICT (organization_id, codigo) DO NOTHING
        """
    )


def downgrade() -> None:
    revocar_privilegios_app("prl")
    for tabla in (
        "solicitud_firma",
        "plantilla_documento",
        "documento_prl",
        "tipo_documento_prl",
        "recurso",
    ):
        desactivar_rls("prl", tabla)
    op.drop_table("firma_token", schema="prl")
    op.drop_table("solicitud_firma", schema="prl")
    op.drop_table("plantilla_documento", schema="prl")
    op.drop_table("documento_prl", schema="prl")
    op.drop_table("tipo_documento_prl", schema="prl")
    op.drop_table("recurso", schema="prl")
    op.execute("DROP SCHEMA IF EXISTS prl CASCADE")
