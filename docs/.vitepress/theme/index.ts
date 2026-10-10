// VitePress's default theme, with the figure components and their style module.
import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import CallGraph from './figures/CallGraph.vue'
import ControlFigure from './figures/ControlFigure.vue'
import FlowFigure from './figures/FlowFigure.vue'
import LayersFigure from './figures/LayersFigure.vue'
import OverviewFigure from './figures/OverviewFigure.vue'
import WalkThrough from './figures/WalkThrough.vue'
import HomeEditLink from './HomeEditLink.vue'
import './figures.css'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('CallGraph', CallGraph)
    app.component('ControlFigure', ControlFigure)
    app.component('FlowFigure', FlowFigure)
    app.component('LayersFigure', LayersFigure)
    app.component('OverviewFigure', OverviewFigure)
    app.component('WalkThrough', WalkThrough)
    app.component('HomeEditLink', HomeEditLink)
  }
} satisfies Theme
