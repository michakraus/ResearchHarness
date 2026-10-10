// The VitePress configuration of the documentation site. Build it from docs/:
//
//   npm ci
//   npm run docs:build
//
// The pages are in docs/src/, and the site goes to docs/build/. The figures are Vue components
// in theme/figures/, which the build renders to SVG. The docs workflow deploys the site to
// gh-pages on a push to main.
import { defineConfig } from 'vitepress'
import { iconSvg } from './theme/figures/icons'

const attribute = (s: string) => s.replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')

/** A markdown-it plugin that turns each `calls <root>` block, or `calls` for every edge, into a
 * call graph of theme/figures/calls.data.ts. The block holds the figure's `title:` and `desc:`
 * lines. */
function callsMarkdown(md) {
  md.core.ruler.push('calls', (state) => {
    for (const token of state.tokens) {
      const m = token.type === 'fence' && /^calls(?:\s+(\S+))?\s*$/.exec(token.info)
      if (!m) continue
      const field = (name: string) => {
        const line = new RegExp(`^${name}:\\s*(.+)$`, 'm').exec(token.content)
        if (!line) throw new Error(`a calls block with no ${name}: line`)
        return attribute(line[1].trim())
      }
      token.type = 'html_block'
      token.content = `<CallGraph${m[1] ? ` root="${attribute(m[1])}"` : ''} title="${field('title')}" desc="${field('desc')}" />\n`
    }
  })
}

export default defineConfig({
  base: '/ResearchHarness/',
  title: 'Research Harness',
  description: 'A harness for coding agents in a research tree',
  srcDir: 'src',
  outDir: 'build',
  cleanUrls: true,
  markdown: {
    config(md) {
      md.use(callsMarkdown)
    }
  },
  // A feature card of the home page names its icon by a key of theme/figures/icons.ts; the build
  // inlines the icon's SVG.
  transformPageData(pageData) {
    for (const feature of pageData.frontmatter.features ?? []) {
      if (typeof feature.icon === 'string') feature.icon = iconSvg(feature.icon, 28)
    }
  },
  themeConfig: {
    outline: 'deep',
    search: { provider: 'local' },
    editLink: {
      pattern: 'https://github.com/michakraus/ResearchHarness/edit/main/docs/src/:path'
    },
    socialLinks: [{ icon: 'github', link: 'https://github.com/michakraus/ResearchHarness' }],
    sidebar: [
      {
        text: 'Getting started',
        items: [
          { text: 'Home', link: '/' },
          { text: 'Concepts', link: '/concepts' },
          { text: 'Dependencies', link: '/dependencies' },
          { text: 'Setup', link: '/setup-macos' },
          { text: 'Setup on Linux', link: '/setup-linux' },
          { text: 'Tutorial', link: '/tutorial' }
        ]
      },
      {
        text: 'Use',
        items: [
          { text: 'Daily use', link: '/daily-use' },
          { text: 'Adapting the profile', link: '/profile' },
          { text: 'The <code>harness</code> command', link: '/harness-command' }
        ]
      },
      {
        text: 'Background',
        items: [
          { text: 'Agents at work', link: '/agents-at-work' },
          { text: 'The security model', link: '/security' },
          { text: 'Architecture', link: '/architecture' }
        ]
      },
      {
        text: 'Components',
        items: [
          { text: 'Agents', link: '/components/agents' },
          { text: 'Skills', link: '/components/skills' },
          { text: 'Commands', link: '/components/commands' },
          { text: 'Rules and instructions', link: '/components/rules' },
          { text: 'Guard hooks', link: '/components/hooks' },
          { text: 'Git hooks and workflows', link: '/components/githooks' },
          { text: 'Scripts', link: '/components/scripts' },
          { text: 'Adapters', link: '/components/adapters' },
          { text: 'The harness command', link: '/components/harness' },
          { text: 'Jobs and configuration', link: '/components/other' }
        ]
      },
      { text: 'Development', link: '/development' }
    ]
  }
})
