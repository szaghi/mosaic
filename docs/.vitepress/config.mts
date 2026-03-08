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
          { text: 'Sources',        link: '/guide/sources' },
          { text: 'Custom Sources',       link: '/guide/custom-sources' },
          { text: 'Authenticated Access', link: '/guide/authenticated-access' },
          { text: 'NotebookLM',          link: '/guide/notebooklm' },
          { text: 'CLI Reference', link: '/guide/cli-reference' },
          { text: 'Changelog',     link: '/guide/changelog' },
          { text: 'Contributing',  link: '/guide/contributing' },
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
            { text: 'Installation',   link: '/guide/installation' },
            { text: 'Configuration',  link: '/guide/configuration' },
            { text: 'Usage',          link: '/guide/usage' },
            { text: 'Custom Sources',       link: '/guide/custom-sources' },
            { text: 'Authenticated Access', link: '/guide/authenticated-access' },
            { text: 'NotebookLM',          link: '/guide/notebooklm' },
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
