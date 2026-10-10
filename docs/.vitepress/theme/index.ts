// VitePress's default theme, with the figure components and their style module.
import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import CallGraph from './figures/CallGraph.vue'
import FlowFigure from './figures/FlowFigure.vue'
import OverviewFigure from './figures/OverviewFigure.vue'
import './figures.css'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('CallGraph', CallGraph)
    app.component('FlowFigure', FlowFigure)
    app.component('OverviewFigure', OverviewFigure)
  }
} satisfies Theme
