"""Cliente del API de administración de Keycloak.

Se autentica contra el realm `master` con las credenciales de arranque del
propio contenedor de Keycloak (`KEYCLOAK_ADMIN`/`KEYCLOAK_ADMIN_PASSWORD`) —
no hace falta un client de servicio aparte solo para esto. Cubre el alta de
usuarios (Fase 11) y, desde la Fase 12, listarlos/editarlos/darlos de baja
por organización — filtrando por el atributo `organizacion` del User
Profile, que hubo que declarar explícitamente (ver README, Fase 11): un
atributo no declarado se descarta en silencio al crear, y no aparece en las
búsquedas por `q=`.
"""

import logging

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class KeycloakAdminError(Exception):
    pass


class KeycloakAdminClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _base(self) -> str:
        return (
            f"{self._settings.keycloak_server_url.rstrip('/')}"
            f"/admin/realms/{self._settings.keycloak_realm}"
        )

    async def _token_admin(self, cliente: httpx.AsyncClient) -> str:
        respuesta = await cliente.post(
            f"{self._settings.keycloak_server_url.rstrip('/')}"
            "/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "username": self._settings.keycloak_admin_username,
                "password": self._settings.keycloak_admin_password,
                "grant_type": "password",
            },
        )
        if respuesta.status_code != 200:
            raise KeycloakAdminError(
                f"No se pudo autenticar contra Keycloak como administrador: {respuesta.text}"
            )
        return respuesta.json()["access_token"]

    async def crear_usuario(
        self,
        *,
        username: str,
        email: str,
        nombre: str,
        apellidos: str,
        organizacion_slug: str | None,
        password_temporal: str,
        roles: list[str],
    ) -> str:
        """Crea el usuario en el realm de la aplicación con una contraseña
        temporal (a cambiar en el primer login) y le asigna los roles
        indicados. Devuelve el id de Keycloak del usuario creado.

        `organizacion_slug=None` es el caso del personal de la plataforma
        (superadmin): no lleva el atributo `organizacion` en absoluto, así
        que no pertenece a ninguna organización ni aparece en
        `listar_usuarios` de ninguna — solo en `listar_usuarios_por_rol`."""
        base = self._base()
        async with httpx.AsyncClient(timeout=15.0) as cliente:
            token = await self._token_admin(cliente)
            cabeceras = {"Authorization": f"Bearer {token}"}

            respuesta = await cliente.post(
                f"{base}/users",
                headers=cabeceras,
                json={
                    "username": username,
                    "email": email,
                    "firstName": nombre,
                    "lastName": apellidos,
                    "enabled": True,
                    "emailVerified": False,
                    "attributes": (
                        {"organizacion": [organizacion_slug]} if organizacion_slug else {}
                    ),
                    "credentials": [
                        {"type": "password", "value": password_temporal, "temporary": True}
                    ],
                    "requiredActions": ["UPDATE_PASSWORD"],
                },
            )
            if respuesta.status_code == 409:
                raise KeycloakAdminError(
                    f"Ya existe un usuario con el nombre '{username}' o el correo '{email}'"
                )
            if respuesta.status_code != 201:
                raise KeycloakAdminError(
                    f"No se pudo crear el usuario en Keycloak: {respuesta.text}"
                )

            ubicacion = respuesta.headers.get("location", "")
            user_id = ubicacion.rstrip("/").rsplit("/", 1)[-1]
            if not user_id:
                raise KeycloakAdminError("Keycloak no devolvió el id del usuario creado")

            if roles:
                await self._asignar_roles(cliente, base, cabeceras, user_id, roles)

            return user_id

    async def resetear_password(self, user_id: str, password_nueva: str) -> None:
        """Usado por «reenviar invitación»: en vez de recordar la contraseña
        temporal original en algún sitio, se genera una nueva y se sustituye
        en Keycloak — así nunca queda una contraseña en texto plano
        persistida más tiempo del necesario para mandarla por correo."""
        base = self._base()
        async with httpx.AsyncClient(timeout=15.0) as cliente:
            token = await self._token_admin(cliente)
            respuesta = await cliente.put(
                f"{base}/users/{user_id}/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"type": "password", "value": password_nueva, "temporary": True},
            )
            if respuesta.status_code not in (200, 204):
                raise KeycloakAdminError(
                    f"No se pudo restablecer la contraseña: {respuesta.text}"
                )

    async def _asignar_roles(
        self,
        cliente: httpx.AsyncClient,
        base: str,
        cabeceras: dict[str, str],
        user_id: str,
        roles: list[str],
    ) -> None:
        respuesta_roles = await cliente.get(f"{base}/roles", headers=cabeceras)
        if respuesta_roles.status_code != 200:
            raise KeycloakAdminError(
                f"Usuario creado pero no se pudo leer el catálogo de roles: {respuesta_roles.text}"
            )
        catalogo = {r["name"]: r for r in respuesta_roles.json()}
        asignables = [catalogo[nombre] for nombre in roles if nombre in catalogo]
        if not asignables:
            return

        respuesta = await cliente.post(
            f"{base}/users/{user_id}/role-mappings/realm",
            headers=cabeceras,
            json=asignables,
        )
        if respuesta.status_code not in (200, 204):
            raise KeycloakAdminError(
                f"Usuario creado pero no se pudieron asignar los roles: {respuesta.text}"
            )

    async def listar_usuarios(self, organizacion_slug: str) -> list[dict]:
        """Busca por el atributo `organizacion` del User Profile — hay que
        tenerlo declarado (ver módulo docstring) o esta búsqueda no encuentra
        nada aunque el atributo esté guardado."""
        base = self._base()
        async with httpx.AsyncClient(timeout=15.0) as cliente:
            token = await self._token_admin(cliente)
            respuesta = await cliente.get(
                f"{base}/users",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": f"organizacion:{organizacion_slug}", "max": 200},
            )
            if respuesta.status_code != 200:
                raise KeycloakAdminError(f"No se pudo listar usuarios: {respuesta.text}")
            usuarios = respuesta.json()

            for usuario in usuarios:
                respuesta_roles = await cliente.get(
                    f"{base}/users/{usuario['id']}/role-mappings/realm",
                    headers={"Authorization": f"Bearer {token}"},
                )
                usuario["roles"] = (
                    [r["name"] for r in respuesta_roles.json()]
                    if respuesta_roles.status_code == 200
                    else []
                )
            return usuarios

    async def listar_usuarios_por_rol(self, role: str) -> list[dict]:
        """Personal de la plataforma: no tiene el atributo `organizacion`, así
        que no se puede buscar como en `listar_usuarios` — se lista por el
        mapeo de rol de Keycloak directamente (`GET
        /roles/{role}/users`), que ya devuelve solo quien lo tiene."""
        base = self._base()
        async with httpx.AsyncClient(timeout=15.0) as cliente:
            token = await self._token_admin(cliente)
            cabeceras = {"Authorization": f"Bearer {token}"}
            respuesta = await cliente.get(
                f"{base}/roles/{role}/users", headers=cabeceras, params={"max": 200}
            )
            if respuesta.status_code != 200:
                raise KeycloakAdminError(f"No se pudo listar usuarios por rol: {respuesta.text}")
            usuarios = respuesta.json()

            for usuario in usuarios:
                respuesta_roles = await cliente.get(
                    f"{base}/users/{usuario['id']}/role-mappings/realm", headers=cabeceras
                )
                usuario["roles"] = (
                    [r["name"] for r in respuesta_roles.json()]
                    if respuesta_roles.status_code == 200
                    else []
                )
            return usuarios

    async def pertenece_a_organizacion(self, user_id: str, organizacion_slug: str) -> bool:
        """Usado por el autoservicio de tenant antes de editar/borrar un
        usuario: sin esto, el rol `admin` de una organización podría mutar
        cualquier usuario de Keycloak con solo adivinar su id, ya que el
        propio API de Keycloak no filtra por organización."""
        base = self._base()
        async with httpx.AsyncClient(timeout=15.0) as cliente:
            token = await self._token_admin(cliente)
            respuesta = await cliente.get(
                f"{base}/users/{user_id}", headers={"Authorization": f"Bearer {token}"}
            )
            if respuesta.status_code != 200:
                return False
            atributos = respuesta.json().get("attributes") or {}
            slugs = atributos.get("organizacion") or []
            return organizacion_slug in slugs

    async def actualizar_usuario(
        self,
        user_id: str,
        *,
        email: str | None = None,
        nombre: str | None = None,
        apellidos: str | None = None,
        habilitado: bool | None = None,
    ) -> dict:
        """Aplica los cambios y devuelve el usuario resultante (con roles),
        en el mismo formato que `listar_usuarios`, para que el router pueda
        responder sin una segunda llamada desde fuera."""
        base = self._base()
        cambios: dict = {}
        if email is not None:
            cambios["email"] = email
        if nombre is not None:
            cambios["firstName"] = nombre
        if apellidos is not None:
            cambios["lastName"] = apellidos
        if habilitado is not None:
            cambios["enabled"] = habilitado

        async with httpx.AsyncClient(timeout=15.0) as cliente:
            token = await self._token_admin(cliente)
            cabeceras = {"Authorization": f"Bearer {token}"}

            if cambios:
                respuesta = await cliente.put(
                    f"{base}/users/{user_id}", headers=cabeceras, json=cambios
                )
                if respuesta.status_code not in (200, 204):
                    raise KeycloakAdminError(
                        f"No se pudo actualizar el usuario: {respuesta.text}"
                    )

            respuesta_usuario = await cliente.get(f"{base}/users/{user_id}", headers=cabeceras)
            if respuesta_usuario.status_code != 200:
                raise KeycloakAdminError(
                    f"Usuario actualizado pero no se pudo releer: {respuesta_usuario.text}"
                )
            usuario = respuesta_usuario.json()

            respuesta_roles = await cliente.get(
                f"{base}/users/{user_id}/role-mappings/realm", headers=cabeceras
            )
            usuario["roles"] = (
                [r["name"] for r in respuesta_roles.json()]
                if respuesta_roles.status_code == 200
                else []
            )
            return usuario

    async def anadir_organizacion(self, user_id: str, organizacion_slug: str) -> None:
        """Añade un slug al atributo `organizacion` de un usuario que ya
        existe, sin tocar los que ya tuviera (Fase 41: el admin que crea una
        segunda empresa de su cuenta gana acceso a las dos).

        Se reenvía la representación COMPLETA del usuario (no solo
        `attributes`): con el User Profile declarativo de Keycloak 26, un PUT
        que solo manda `attributes` vacía `email` y el resto de campos no
        incluidos en vez de dejarlos como estaban — se comprobó en vivo
        (Fase 41, un usuario real se quedó sin `email` y no podía iniciar
        sesión). Mandar el objeto entero que se acaba de leer evita ese
        vaciado, sea cual sea el motivo exacto."""
        base = self._base()
        async with httpx.AsyncClient(timeout=15.0) as cliente:
            token = await self._token_admin(cliente)
            cabeceras = {"Authorization": f"Bearer {token}"}

            respuesta = await cliente.get(f"{base}/users/{user_id}", headers=cabeceras)
            if respuesta.status_code != 200:
                raise KeycloakAdminError(f"No se pudo leer el usuario: {respuesta.text}")
            usuario = respuesta.json()

            atributos = usuario.get("attributes") or {}
            slugs = list(atributos.get("organizacion") or [])
            if organizacion_slug not in slugs:
                slugs.append(organizacion_slug)
            atributos["organizacion"] = slugs
            usuario["attributes"] = atributos

            respuesta = await cliente.put(f"{base}/users/{user_id}", headers=cabeceras, json=usuario)
            if respuesta.status_code not in (200, 204):
                raise KeycloakAdminError(
                    f"No se pudo conceder acceso a la nueva empresa: {respuesta.text}"
                )

    async def eliminar_usuario(self, user_id: str) -> None:
        base = self._base()
        async with httpx.AsyncClient(timeout=15.0) as cliente:
            token = await self._token_admin(cliente)
            respuesta = await cliente.delete(
                f"{base}/users/{user_id}", headers={"Authorization": f"Bearer {token}"}
            )
            if respuesta.status_code not in (200, 204):
                raise KeycloakAdminError(f"No se pudo eliminar el usuario: {respuesta.text}")
