import { useCallback, useEffect, useRef, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import {
  Bold,
  Heading1,
  Heading2,
  Image as ImageIcon,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  Loader2,
  Quote,
  Redo2,
  Strikethrough,
  Undo2,
} from 'lucide-react'

import { api, urlBlob } from '../lib/api'

const RETARDO_GUARDADO = 1200

/** Variante de `@tiptap/extension-image` que además recuerda de qué
 *  documento (módulo `documentos`, Fase 30) viene la imagen — el `src` que
 *  de verdad se guarda no sirve para mostrarla, porque el endpoint de
 *  descarga exige la cabecera Authorization y un `<img src>` no puede
 *  llevarla. `documentoId` es la referencia estable; `src` es solo una
 *  caché de pantalla que se resuelve aparte (ver `resolverImagenes`). */
const ImagenConDocumento = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      documentoId: {
        default: null,
        parseHTML: (elemento) => elemento.getAttribute('data-documento-id'),
        renderHTML: (atributos) =>
          atributos.documentoId ? { 'data-documento-id': atributos.documentoId } : {},
      },
    }
  },
  // La regla del `Image` de base es `img[src]`: como el HTML guardado no
  // trae `src` (ver arriba), esa regla no la reconoce y la imagen desaparece
  // al recargar. Hace falta aceptar también un `<img>` que solo traiga
  // `data-documento-id`.
  parseHTML() {
    return [{ tag: 'img[data-documento-id], img[src]' }]
  },
})

/** Descripción con formato de un capítulo o una partida (Fase 38): editor
 *  WYSIWYG con imágenes incrustadas, que se cuelgan del propio presupuesto en
 *  el gestor documental (misma entidad que la pestaña "Documentos") para no
 *  duplicar el guardado en MinIO. */
export function DescripcionEditor({
  id,
  html,
  presupuestoId,
  onGuardar,
}: {
  id: string
  html: string | null
  presupuestoId: string
  onGuardar: (html: string) => Promise<void>
}) {
  const [guardando, setGuardando] = useState(false)
  const [subiendoImagen, setSubiendoImagen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputFicheroRef = useRef<HTMLInputElement>(null)
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null)
  const urlsBlob = useRef<Set<string>>(new Set())
  const contenidoPendiente = useRef<string | null>(null)

  const guardar = useCallback(async () => {
    if (contenidoPendiente.current === null) return
    const contenido = contenidoPendiente.current
    contenidoPendiente.current = null
    setGuardando(true)
    try {
      await onGuardar(contenido)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }, [onGuardar])

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2] } }),
      Link.configure({ openOnClick: false, autolink: true }),
      Placeholder.configure({ placeholder: 'Sin descripción — escribe aquí…' }),
      ImagenConDocumento,
    ],
    content: html ?? '',
    onUpdate: ({ editor }) => {
      contenidoPendiente.current = editor.getHTML()
      if (temporizador.current) clearTimeout(temporizador.current)
      temporizador.current = setTimeout(() => void guardar(), RETARDO_GUARDADO)
    },
  })

  // El contenido llega por props (viene del árbol del presupuesto); cuando
  // cambia la fila seleccionada hay que recargar el editor entero, no seguir
  // editando el de la fila anterior.
  useEffect(() => {
    if (!editor) return
    editor.commands.setContent(html ?? '')
  }, [editor, id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Las imágenes se guardan como `data-documento-id`, sin `src` útil; se
  // resuelven contra el gestor documental cada vez que cambia el contenido
  // cargado, y se revocan los blobs anteriores para no acumular memoria.
  useEffect(() => {
    if (!editor) return
    let cancelado = false

    async function resolver() {
      const nodosImagen: { pos: number; documentoId: string }[] = []
      editor!.state.doc.descendants((nodo, pos) => {
        if (nodo.type.name === 'image' && nodo.attrs.documentoId && !nodo.attrs.src?.startsWith('blob:')) {
          nodosImagen.push({ pos, documentoId: nodo.attrs.documentoId })
        }
      })
      for (const { pos, documentoId } of nodosImagen) {
        try {
          const url = await urlBlob(api.documentos.descargarUrl(documentoId))
          if (cancelado) {
            URL.revokeObjectURL(url)
            return
          }
          urlsBlob.current.add(url)
          editor!.chain().setNodeSelection(pos).updateAttributes('image', { src: url }).run()
        } catch {
          // Documento borrado o inaccesible: se deja sin resolver, no rompe el resto.
        }
      }
    }
    void resolver()

    return () => {
      cancelado = true
    }
  }, [editor, id, html])

  useEffect(() => {
    const urls = urlsBlob.current
    return () => {
      for (const url of urls) URL.revokeObjectURL(url)
      urls.clear()
    }
  }, [id])

  // Guardar lo que quede al desmontar: cambiar de fila con la descripción a
  // medio teclear no debe perder esos cambios.
  useEffect(() => {
    return () => {
      if (temporizador.current) clearTimeout(temporizador.current)
      void guardar()
    }
  }, [guardar])

  async function subirImagen(archivo: File) {
    if (!editor) return
    setSubiendoImagen(true)
    setError(null)
    try {
      const documento = await api.documentos.upload('presupuesto', presupuestoId, archivo)
      const url = URL.createObjectURL(archivo)
      urlsBlob.current.add(url)
      editor
        .chain()
        .focus()
        .setImage({ src: url, alt: archivo.name, documentoId: documento.id } as never)
        .run()
      contenidoPendiente.current = editor.getHTML()
      if (temporizador.current) clearTimeout(temporizador.current)
      temporizador.current = setTimeout(() => void guardar(), RETARDO_GUARDADO)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setSubiendoImagen(false)
    }
  }

  if (!editor) return null

  const boton = (activo: boolean, onClick: () => void, icono: React.ReactNode, titulo: string) => (
    <button
      type="button"
      className={`descripcion-editor__boton${activo ? ' descripcion-editor__boton--activo' : ''}`}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      title={titulo}
      aria-label={titulo}
    >
      {icono}
    </button>
  )

  return (
    <div className="descripcion-editor">
      <div className="descripcion-editor__barra">
        {boton(
          editor.isActive('bold'),
          () => editor.chain().focus().toggleBold().run(),
          <Bold size={15} aria-hidden="true" />,
          'Negrita',
        )}
        {boton(
          editor.isActive('italic'),
          () => editor.chain().focus().toggleItalic().run(),
          <Italic size={15} aria-hidden="true" />,
          'Cursiva',
        )}
        {boton(
          editor.isActive('strike'),
          () => editor.chain().focus().toggleStrike().run(),
          <Strikethrough size={15} aria-hidden="true" />,
          'Tachado',
        )}
        <span className="descripcion-editor__separador" />
        {boton(
          editor.isActive('heading', { level: 1 }),
          () => editor.chain().focus().toggleHeading({ level: 1 }).run(),
          <Heading1 size={15} aria-hidden="true" />,
          'Título',
        )}
        {boton(
          editor.isActive('heading', { level: 2 }),
          () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
          <Heading2 size={15} aria-hidden="true" />,
          'Subtítulo',
        )}
        <span className="descripcion-editor__separador" />
        {boton(
          editor.isActive('bulletList'),
          () => editor.chain().focus().toggleBulletList().run(),
          <List size={15} aria-hidden="true" />,
          'Lista',
        )}
        {boton(
          editor.isActive('orderedList'),
          () => editor.chain().focus().toggleOrderedList().run(),
          <ListOrdered size={15} aria-hidden="true" />,
          'Lista numerada',
        )}
        {boton(
          editor.isActive('blockquote'),
          () => editor.chain().focus().toggleBlockquote().run(),
          <Quote size={15} aria-hidden="true" />,
          'Cita',
        )}
        <span className="descripcion-editor__separador" />
        {boton(
          editor.isActive('link'),
          () => {
            const previo = editor.getAttributes('link').href as string | undefined
            const url = window.prompt('Enlace', previo ?? 'https://')
            if (url === null) return
            if (url === '') {
              editor.chain().focus().unsetLink().run()
            } else {
              editor.chain().focus().setLink({ href: url }).run()
            }
          },
          <LinkIcon size={15} aria-hidden="true" />,
          'Enlace',
        )}
        {boton(
          false,
          () => inputFicheroRef.current?.click(),
          subiendoImagen ? (
            <Loader2 size={15} className="girando" aria-hidden="true" />
          ) : (
            <ImageIcon size={15} aria-hidden="true" />
          ),
          'Insertar imagen',
        )}
        <span className="descripcion-editor__separador" />
        {boton(
          false,
          () => editor.chain().focus().undo().run(),
          <Undo2 size={15} aria-hidden="true" />,
          'Deshacer',
        )}
        {boton(
          false,
          () => editor.chain().focus().redo().run(),
          <Redo2 size={15} aria-hidden="true" />,
          'Rehacer',
        )}
        <span className="descripcion-editor__estado">
          {guardando ? 'Guardando…' : error ? error : ''}
        </span>
      </div>
      <EditorContent editor={editor} className="descripcion-editor__contenido" />
      <input
        ref={inputFicheroRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        style={{ display: 'none' }}
        onChange={(e) => {
          const archivo = e.target.files?.[0]
          e.target.value = ''
          if (archivo) void subirImagen(archivo)
        }}
      />
    </div>
  )
}
