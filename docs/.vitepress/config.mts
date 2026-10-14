import { withMermaid } from 'vitepress-plugin-mermaid'

// One sidebar, in reading order, for every page: prev/next links walk the whole documentation.
const docs = [
  {
    text: 'Start here',
    items: [
      { text: 'About',        link: '/guide/' },
      { text: 'Installation', link: '/guide/installation' },
    ],
  },
  {
    text: 'Tutorial',
    items: [
      { text: 'Overview',                   link: '/tutorial/' },
      { text: '1. A first search',          link: '/tutorial/01-first-search' },
      { text: '2. Narrowing the results',   link: '/tutorial/02-narrowing' },
      { text: '3. The local cache',         link: '/tutorial/03-cache' },
      { text: '4. Getting the PDFs',        link: '/tutorial/04-pdfs' },
      { text: '5. Paywalled papers',        link: '/tutorial/05-paywalls' },
      { text: '6. Exporting',               link: '/tutorial/06-exporting' },
      { text: '7. Following a field',       link: '/tutorial/07-following' },
      { text: '8. A local model',           link: '/tutorial/08-local-model' },
      { text: '9. Asking your library',     link: '/tutorial/09-library' },
      { text: '10. The citation network',   link: '/tutorial/10-citations' },
    ],
  },
  {
    text: 'Cookbook',
    items: [
      { text: 'All recipes',          link: '/cookbook/' },
      { text: 'Searching',            link: '/cookbook/searching' },
      { text: 'Downloading',          link: '/cookbook/downloading' },
      { text: 'Paywalled papers',     link: '/cookbook/paywalls' },
      { text: 'Exporting',            link: '/cookbook/exporting' },
      { text: 'Keeping up',           link: '/cookbook/monitoring' },
      { text: 'Models and analysis',  link: '/cookbook/ai' },
      { text: 'Scripts and agents',   link: '/cookbook/scripting' },
      { text: 'Maintenance',          link: '/cookbook/maintenance' },
    ],
  },
  {
    text: 'Guides',
    items: [
      {
        text: 'Finding papers',
        collapsed: false,
        items: [
          { text: 'Sources',           link: '/guide/sources' },
          { text: 'Custom sources',    link: '/guide/custom-sources' },
          { text: 'Similar papers',    link: '/guide/similar' },
          { text: 'Watches',           link: '/guide/watch' },
          { text: 'Relevance ranking', link: '/guide/relevance-ranking' },
        ],
      },
      {
        text: 'Getting PDFs',
        collapsed: false,
        items: [
          { text: 'Downloads',            link: '/guide/downloads' },
          { text: 'Authenticated access', link: '/guide/authenticated-access' },
          { text: 'The cache',            link: '/guide/cache' },
        ],
      },
      {
        text: 'Your library',
        collapsed: false,
        items: [
          { text: 'Local RAG',         link: '/guide/rag' },
          { text: 'Citation graph',    link: '/guide/citation-graph' },
          { text: 'Citation network',  link: '/guide/network' },
          { text: 'Comparing papers',  link: '/guide/compare' },
        ],
      },
      {
        text: 'Elsewhere',
        collapsed: false,
        items: [
          { text: 'Zotero',                 link: '/guide/zotero' },
          { text: 'Obsidian',               link: '/guide/obsidian' },
          { text: 'NotebookLM',             link: '/guide/notebooklm' },
          { text: 'Web UI',                 link: '/guide/web-ui' },
          { text: 'Agents and Claude Code', link: '/guide/agent-workflows' },
        ],
      },
      { text: 'Configuration', link: '/guide/configuration' },
    ],
  },
  {
    text: 'Reference',
    items: [
      { text: 'All commands', link: '/reference/' },
      {
        text: 'Commands',
        collapsed: true,
        items: [
          { text: 'search',   link: '/reference/search' },
          { text: 'similar',  link: '/reference/similar' },
          { text: 'watch',    link: '/reference/watch' },
          { text: 'cite',     link: '/reference/cite' },
          { text: 'get',      link: '/reference/get' },
          { text: 'import',   link: '/reference/import' },
          { text: 'auth',     link: '/reference/auth' },
          { text: 'cache',    link: '/reference/cache' },
          { text: 'index',    link: '/reference/index-command' },
          { text: 'ask',      link: '/reference/ask' },
          { text: 'chat',     link: '/reference/chat' },
          { text: 'compare',  link: '/reference/compare' },
          { text: 'network',  link: '/reference/network' },
          { text: 'ui',       link: '/reference/ui' },
          { text: 'notebook', link: '/reference/notebook' },
          { text: 'skill',    link: '/reference/skill' },
          { text: 'config',   link: '/reference/config' },
        ],
      },
    ],
  },
  {
    text: 'Project',
    items: [
      { text: 'Architecture', link: '/guide/architecture' },
      { text: 'Contributing', link: '/guide/contributing' },
      { text: 'Changelog',    link: '/guide/changelog' },
      { text: 'Community',    link: '/guide/telegram' },
    ],
  },
]

export default withMermaid({
  title: 'MOSAIC',
  description: 'Search two dozen scientific databases at once, and build a local library of the papers',
  base: '/mosaic/',
  // examples/ holds the captured output the tutorial includes; social/ holds post drafts
  srcExclude: ['examples/**', 'social/**', 'maxwell_compare.md'],
  lastUpdated: true,

  themeConfig: {
    logo: {
      light: '/mosaic-logo-alpha-black.png',
      dark:  '/mosaic-logo-alpha-white.png',
    },
    nav: [
      { text: 'Tutorial',  link: '/tutorial/', activeMatch: '^/tutorial/' },
      { text: 'Cookbook',  link: '/cookbook/', activeMatch: '^/cookbook/' },
      {
        text: 'Guides',
        link: '/guide/sources',
        activeMatch: '^/guide/(?!(index|installation|architecture|contributing|changelog|telegram)?$)',
      },
      { text: 'Reference', link: '/reference/', activeMatch: '^/reference/' },
      {
        text: 'Project',
        items: [
          { text: 'Installation', link: '/guide/installation' },
          { text: 'Architecture', link: '/guide/architecture' },
          { text: 'Contributing', link: '/guide/contributing' },
          { text: 'Changelog',    link: '/guide/changelog' },
          { text: 'Community',    link: '/guide/telegram' },
        ],
      },
    ],

    sidebar: {
      '/guide/':     docs,
      '/tutorial/':  docs,
      '/cookbook/':  docs,
      '/reference/': docs,
    },

    outline: [2, 3],

    search: {
      provider: 'local',
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/szaghi/mosaic' },
    ],

    editLink: {
      pattern: 'https://github.com/szaghi/mosaic/edit/main/docs/:path',
      text: 'Edit this page on GitHub',
    },

    footer: {
      message: 'Released under GPL-3.0-or-later, BSD-2-Clause, BSD-3-Clause or MIT, at your choice.',
      copyright: 'Copyright © Stefano Zaghi',
    },
  },

  mermaid: {},
})
