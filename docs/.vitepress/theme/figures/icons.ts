// The icons of the figures and of the home page's feature cards, from Lucide (`lucide` in
// docs/package.json). The build inlines each icon as SVG shapes, so the site loads no icon from
// another host. A figure names an icon by its key here.
import {
  AppWindow, Ban, Blocks, Bot, BrainCircuit, Code, Container, Download, FileCode, FileCog, FileText,
  Files, FlaskConical, FolderTree, GitBranch, HardDrive, IdCard, Layers, Library, LockKeyhole,
  NotebookPen, Package, Pi, Plug, ScrollText, Settings, Settings2, ShieldCheck, Sparkles,
  SquareSlash, SquareTerminal, User, Workflow
} from 'lucide'

/** An icon: a list of SVG elements, each a tag and its attributes, on a 24 × 24 grid. */
export type IconNode = [string, Record<string, string | number>][]

const ICONS: Record<string, IconNode> = {
  agent: Bot,
  skill: Sparkles,
  command: SquareSlash,
  rule: ScrollText,
  guard: ShieldCheck,
  git: GitBranch,
  script: FileCode,
  settings: Settings,
  library: Library,
  knowledge: BrainCircuit,
  package: Package,
  experiment: FlaskConical,
  project: NotebookPen,
  paper: FileText,
  tree: FolderTree,
  components: Blocks,
  frontends: AppWindow,
  harness: Layers,
  terminal: SquareTerminal,
  code: Code,
  pi: Pi,
  sources: Files,
  template: FileCog,
  adapter: Plug,
  profile: IdCard,
  install: Download,
  'settings-install': Settings2,
  private: LockKeyhole,
  workflow: Workflow,
  ban: Ban,
  user: User,
  sandbox: Container,
  drive: HardDrive
}

/** The icon `name`, or an error that names it. */
export function icon(name: string): IconNode {
  const node = ICONS[name]
  if (node === undefined) throw new Error(`no icon named ${name}`)
  return node
}

const attrs = (a: Record<string, string | number>) =>
  Object.entries(a).map(([k, v]) => ` ${k}="${String(v).replaceAll('"', '&quot;')}"`).join('')

/** The icon `name` as SVG text, `size` pixels wide, drawn in the current text colour. */
export function iconSvg(name: string, size = 24): string {
  const inner = icon(name).map(([tag, a]) => `<${tag}${attrs(a)}/>`).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" ` +
    `fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`
}
