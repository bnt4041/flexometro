import { useEffect } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import { Bold, Heading1, Heading2, Italic, Link as LinkIcon, List, ListOrdered, Quote, Redo2, Strikethrough, Undo2 } from 'lucide-react'

/** Editor de texto enriquecido genérico y controlado (sin autoguardado ni
 *  imágenes, a diferencia de `DescripcionEditor`): quien lo usa guarda el
 *  HTML cuando quiera, con su propio botón — pensado para textos largos de
 *  una sola pieza (p. ej. una política de privacidad), no para ir tecleando
 *  celda a celda. Reutiliza las clases `descripcion-editor__*` para no
 *  duplicar estilos de barra/botones. */
export function EditorHtml({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (html: string) => void
  placeholder?: string
}) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2] } }),
      Link.configure({ openOnClick: false, autolink: true }),
      Placeholder.configure({ placeholder: placeholder ?? 'Escribe aquí…' }),
    ],
    content: value,
    onUpdate: ({ editor }) => onChange(editor.getHTML()),
  })

  useEffect(() => {
    if (!editor) return
    if (editor.getHTML() === value) return
    editor.commands.setContent(value)
    // Solo cuando `value` cambia por fuera (p. ej. al cambiar de pestaña de
    // empresa): comparar contra el HTML actual evita reescribir el cursor
    // en cada pulsación, que es cuando `value` cambia por el propio editor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, editor])

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

  if (!editor) return null

  return (
    <div className="descripcion-editor">
      <div className="descripcion-editor__barra">
        {boton(editor.isActive('bold'), () => editor.chain().focus().toggleBold().run(), <Bold size={15} aria-hidden="true" />, 'Negrita')}
        {boton(editor.isActive('italic'), () => editor.chain().focus().toggleItalic().run(), <Italic size={15} aria-hidden="true" />, 'Cursiva')}
        {boton(editor.isActive('strike'), () => editor.chain().focus().toggleStrike().run(), <Strikethrough size={15} aria-hidden="true" />, 'Tachado')}
        <span className="descripcion-editor__separador" />
        {boton(editor.isActive('heading', { level: 1 }), () => editor.chain().focus().toggleHeading({ level: 1 }).run(), <Heading1 size={15} aria-hidden="true" />, 'Título')}
        {boton(editor.isActive('heading', { level: 2 }), () => editor.chain().focus().toggleHeading({ level: 2 }).run(), <Heading2 size={15} aria-hidden="true" />, 'Subtítulo')}
        <span className="descripcion-editor__separador" />
        {boton(editor.isActive('bulletList'), () => editor.chain().focus().toggleBulletList().run(), <List size={15} aria-hidden="true" />, 'Lista')}
        {boton(editor.isActive('orderedList'), () => editor.chain().focus().toggleOrderedList().run(), <ListOrdered size={15} aria-hidden="true" />, 'Lista numerada')}
        {boton(editor.isActive('blockquote'), () => editor.chain().focus().toggleBlockquote().run(), <Quote size={15} aria-hidden="true" />, 'Cita')}
        <span className="descripcion-editor__separador" />
        {boton(editor.isActive('link'), () => {
          const previo = editor.getAttributes('link').href as string | undefined
          const url = window.prompt('Enlace', previo ?? 'https://')
          if (url === null) return
          if (url === '') editor.chain().focus().unsetLink().run()
          else editor.chain().focus().setLink({ href: url }).run()
        }, <LinkIcon size={15} aria-hidden="true" />, 'Enlace')}
        <span className="descripcion-editor__separador" />
        {boton(false, () => editor.chain().focus().undo().run(), <Undo2 size={15} aria-hidden="true" />, 'Deshacer')}
        {boton(false, () => editor.chain().focus().redo().run(), <Redo2 size={15} aria-hidden="true" />, 'Rehacer')}
      </div>
      <EditorContent editor={editor} className="descripcion-editor__contenido" />
    </div>
  )
}
