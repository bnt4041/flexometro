import asyncio, sys, re
from app.core.database import SessionFactory
from app.core.tenancy import set_organization_id
from app.modules.presupuestos import informes
from app.modules.presupuestos.presupuesto_service import obtener, listar
import uuid

async def main():
    set_organization_id(uuid.UUID("00000000-0000-0000-0000-000000000001"))
    async with SessionFactory() as s:
        items, _ = await listar(s, limit=1)
        p = items[0]
        for doc in ("presupuesto", "mediciones", "descompuestos"):
            # Mismo camino que el PDF, parando antes de rasterizar.
            plantilla, titulo = informes.DOCUMENTOS[doc]
            ctx = {"presupuesto": p, "cliente": await informes._cliente_de(s, p), "titulo": titulo}
            if doc == "descompuestos":
                cs = await informes._conceptos_del_presupuesto(s, p.id)
                ctx["conceptos"] = [{"codigo": c.codigo, "resumen": c.resumen, "texto": c.texto,
                                     "unidad": c.unidad, "precio": c.precio,
                                     "costes_indirectos": c.costes_indirectos,
                                     "coste_directo": c.coste_directo, "lineas": c.lineas_informe} for c in cs]
            else:
                nodos = await informes._arbol(s, p.id, con_mediciones=(doc == "mediciones"))
                ctx["capitulos"] = informes._serializar(nodos)
                if doc == "presupuesto":
                    _, t = await informes._totales(s, p)
                    ctx["totales"] = t
            html = informes._entorno().get_template(plantilla).render(**ctx)
            cuerpo = html[html.find("</style>"):]
            texto = re.sub(r"<[^>]+>", " ", cuerpo)
            texto = re.sub(r"\s+", " ", texto).strip()
            print(f"\n===== {doc.upper()} =====")
            print(texto[:1000])

asyncio.run(main())
