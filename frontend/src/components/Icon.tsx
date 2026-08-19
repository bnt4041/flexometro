import {
  ArrowLeft,
  Ban,
  Calculator,
  Check,
  CircleAlert,
  ClipboardCheck,
  Columns3,
  Copy,
  Download,
  FunctionSquare,
  FileDown,
  FilePlus,
  FileText,
  HardHat,
  MessageSquareText,
  Layers,
  ListPlus,
  Minus,
  MoreVertical,
  Pencil,
  Plus,
  Receipt,
  RefreshCw,
  Repeat,
  Ruler,
  Save,
  Search,
  Send,
  Settings,
  Sparkles,
  Star,
  StickyNote,
  Trash2,
  Truck,
  Upload,
  User,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react'

/** Nombres de icono que publica el registro de módulos del backend
 *  (`NavItem.icon`/`Module.icon`), más los de acciones genéricas de
 *  formulario. Central para que un nombre no resuelto caiga en un icono
 *  neutro en vez de romper la pantalla. */
const ICONOS: Record<string, LucideIcon> = {
  // Navegación (vienen del backend, ver ModuleSpec/NavItem de cada módulo)
  settings: Settings,
  users: Users,
  user: User,
  calculator: Calculator,
  layers: Layers,
  upload: Upload,
  truck: Truck,
  receipt: Receipt,
  'clipboard-check': ClipboardCheck,
  sparkles: Sparkles,
  'hard-hat': HardHat,
  'list-plus': ListPlus,
  'sticky-note': StickyNote,
  'file-text': FileText,

  // Acciones genéricas de formulario/listado
  nuevo: Plus,
  añadir: Plus,
  guardar: Save,
  descartar: X,
  cancelar: X,
  cerrar: X,
  eliminar: Trash2,
  editar: Pencil,
  buscar: Search,
  volver: ArrowLeft,
  recalcular: RefreshCw,
  medir: Ruler,
  preferente: Star,
  quitar: Minus,
  emitir: Send,
  anular: Ban,
  duplicar: Copy,
  descargar: Download,
  exportar: FileDown,
  documento: FilePlus,
  columnas: Columns3,
  confirmar: Check,
  aviso: CircleAlert,
  'mas-vertical': MoreVertical,
  formula: FunctionSquare,
  estado: Repeat,

  // Pestañas de la ficha genérica (Fase 27)
  datos: FileText,
  contactos: Users,
  crm: MessageSquareText,
  documentos: FilePlus,
}

export type NombreIcono = keyof typeof ICONOS | (string & {})

/** Icono de línea (lucide) a partir de un nombre — el mismo string que ya
 *  manda el backend en `NavItem.icon`/`Module.icon` (Fase 0) y que hasta la
 *  Fase 26 no se pintaba en ningún sitio. Un nombre desconocido cae en un
 *  círculo neutro en vez de tirar la pantalla abajo: mejor un icono soso que
 *  una pantalla en blanco por un nombre mal escrito en el backend. */
export function Icon({
  name,
  size = 16,
  className,
}: {
  name: NombreIcono
  size?: number
  className?: string
}) {
  const Componente = ICONOS[name] ?? CircleAlert
  return <Componente size={size} className={className} aria-hidden="true" />
}
