import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid({
  title: 'MOSAIC',
  description: 'Multi-source Scientific Article Index and Collector',
  base: '/mosaic/',
  themeConfig: {
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
          { text: 'CLI Reference', link: '/guide/cli-reference' },
          { text: 'Changelog',     link: '/guide/changelog' },
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
          text: 'Reference',
          items: [
            { text: 'CLI Reference', link: '/guide/cli-reference' },
            { text: 'Changelog',     link: '/guide/changelog' },
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
