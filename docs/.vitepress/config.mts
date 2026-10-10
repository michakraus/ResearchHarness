// The VitePress configuration of the documentation site. Build it from docs/:
//
//   npm ci
//   npm run docs:build
//
// The pages are in docs/src/, and the site goes to docs/build/. The home page includes the
// README. The docs workflow deploys the site to gh-pages on a push to main.
import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'
import { callsMarkdown } from './calls.mjs'

/** A markdown-it plugin: the home page includes README.md, whose links into docs/src/ become links
 * between pages of the site. */
function readmeLinks(md) {
  md.core.ruler.push('readme-links', (state) => {
    if (state.env.relativePath !== 'index.md') return
    for (const block of state.tokens) {
      for (const token of block.children ?? []) {
        const href = token.type === 'link_open' && token.attrGet('href')
        if (href && href.startsWith('docs/src/')) token.attrSet('href', href.slice('docs/src/'.length))
      }
    }
  })
}

export default withMermaid(defineConfig({
  base: '/ResearchHarness/',
  title: 'ResearchHarness',
  description: 'A harness for coding agents in a research tree',
  srcDir: 'src',
  outDir: 'build',
  cleanUrls: true,
  markdown: {
    config(md) {
      md.use(callsMarkdown)
      md.use(readmeLinks)
    }
  },
  vite: {
    // Mermaid puts each kind of diagram into a chunk of its own, and the largest is about 700 kB.
    // A page loads only the chunks of the diagrams it draws.
    build: { chunkSizeWarningLimit: 1000 }
  },
  themeConfig: {
    outline: 'deep',
    search: { provider: 'local' },
    // The home page includes the README, so its edit link opens the README.
    editLink: {
      pattern: ({ filePath }) => 'https://github.com/michakraus/ResearchHarness/edit/main/' +
        (filePath === 'index.md' ? 'README.md' : `docs/src/${filePath}`)
    },
    socialLinks: [{ icon: 'github', link: 'https://github.com/michakraus/ResearchHarness' }],
    sidebar: [
      { text: 'Home', link: '/' },
      { text: 'Tutorial', link: '/tutorial' },
      {
        text: 'Setup',
        items: [
          { text: 'Setup on macOS', link: '/setup-macos' },
          { text: 'Setup on Linux', link: '/setup-linux' }
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
          { text: 'Architecture', link: '/architecture' },
          { text: 'The tools', link: '/tools' }
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
}))
