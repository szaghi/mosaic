import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid({
  title: 'MOSAIC',
  description: 'Multi-source Scientific Article Indexer and Collector',
  base: '/mosaic/',
  themeConfig: {
    logo: {
      light: '/mosaic-logo-alpha-black.png',
      dark:  '/mosaic-logo-alpha-white.png',
    },
    nav: [
      { text: 'Home', link: '/' },
      {
        text: 'Guide',
        items: [
          { text: 'About',         link: '/guide/' },
          { text: 'Installation',  link: '/guide/installation' },
          { text: 'Configuration', link: '/guide/configuration' },
          { text: 'Usage',         link: '/guide/usage' },
          { text: 'Sources',       link: '/guide/sources' },
        ],
      },
      {
        text: 'AI & Analysis',
        items: [
          { text: 'Agent Workflows & Claude Code Skill', link: '/guide/agent-workflows' },
          { text: 'Local RAG',           link: '/guide/rag' },
          { text: 'Citation Graph',      link: '/guide/citation-graph' },
          { text: 'Citation Network',    link: '/guide/network' },
          { text: 'Compare Papers',      link: '/guide/compare' },
          { text: 'Relevance Ranking',   link: '/guide/relevance-ranking' },
          { text: 'NotebookLM',          link: '/guide/notebooklm' },
        ],
      },
      {
        text: 'Integrations',
        items: [
          { text: 'Zotero',              link: '/guide/zotero' },
          { text: 'Obsidian',            link: '/guide/obsidian' },
          { text: 'Web UI',              link: '/guide/web-ui' },
          { text: 'Custom Sources',      link: '/guide/custom-sources' },
          { text: 'Authenticated Access', link: '/guide/authenticated-access' },
          { text: 'Find Similar Papers', link: '/guide/similar' },
          { text: 'Cache Management',    link: '/guide/cache' },
        ],
      },
      {
        text: 'Reference',
        items: [
          { text: 'CLI Reference', link: '/guide/cli-reference' },
          { text: 'Changelog',     link: '/guide/changelog' },
          { text: 'Contributing',  link: '/guide/contributing' },
          { text: 'Telegram',      link: '/guide/telegram' },
        ],
      },
    ],
    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'About',   link: '/guide/' },
            { text: 'Sources', link: '/guide/sources' },
          ],
        },
        {
          text: 'Getting Started',
          items: [
            { text: 'Installation',  link: '/guide/installation' },
            { text: 'Configuration', link: '/guide/configuration' },
            { text: 'Usage',         link: '/guide/usage' },
          ],
        },
        {
          text: 'AI & Analysis',
          items: [
            { text: 'Agent Workflows & Claude Code Skill', link: '/guide/agent-workflows' },
            { text: 'Local RAG',         link: '/guide/rag' },
            { text: 'Citation Graph',    link: '/guide/citation-graph' },
            { text: 'Citation Network',  link: '/guide/network' },
            { text: 'Compare Papers',    link: '/guide/compare' },
            { text: 'Relevance Ranking', link: '/guide/relevance-ranking' },
            { text: 'NotebookLM',        link: '/guide/notebooklm' },
          ],
        },
        {
          text: 'Integrations',
          items: [
            { text: 'Zotero',              link: '/guide/zotero' },
            { text: 'Obsidian',            link: '/guide/obsidian' },
            { text: 'Web UI',              link: '/guide/web-ui' },
            { text: 'Custom Sources',      link: '/guide/custom-sources' },
            { text: 'Authenticated Access', link: '/guide/authenticated-access' },
            { text: 'Find Similar Papers', link: '/guide/similar' },
            { text: 'Cache Management',    link: '/guide/cache' },
          ],
        },
        {
          text: 'Reference',
          items: [
            { text: 'CLI Reference', link: '/guide/cli-reference' },
            { text: 'Changelog',     link: '/guide/changelog' },
            { text: 'Contributing',  link: '/guide/contributing' },
          ],
        },
        {
          text: 'Community',
          items: [
            { text: 'Telegram', link: '/guide/telegram' },
          ],
        },
      ],
    },
    search: {
      provider: 'local',
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/szaghi/mosaic' },
    ],
  },
  mermaid: {},
})
