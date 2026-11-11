// VitePress's default theme, with the figure components and their style module.
import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import CallGraph from './figures/CallGraph.vue'
import ChecksFigure from './figures/ChecksFigure.vue'
import ControlFigure from './figures/ControlFigure.vue'
import EdgesFigure from './figures/EdgesFigure.vue'
import FlowFigure from './figures/FlowFigure.vue'
import LayersFigure from './figures/LayersFigure.vue'
import MutantFigure from './figures/MutantFigure.vue'
import OverviewFigure from './figures/OverviewFigure.vue'
import PipelineFigure from './figures/PipelineFigure.vue'
import SandboxFigure from './figures/SandboxFigure.vue'
import WalkThrough from './figures/WalkThrough.vue'
import HomeEditLink from './HomeEditLink.vue'
import './figures.css'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('CallGraph', CallGraph)
    app.component('ChecksFigure', ChecksFigure)
    app.component('ControlFigure', ControlFigure)
    app.component('EdgesFigure', EdgesFigure)
    app.component('FlowFigure', FlowFigure)
    app.component('LayersFigure', LayersFigure)
    app.component('MutantFigure', MutantFigure)
    app.component('OverviewFigure', OverviewFigure)
    app.component('PipelineFigure', PipelineFigure)
    app.component('SandboxFigure', SandboxFigure)
    app.component('WalkThrough', WalkThrough)
    app.component('HomeEditLink', HomeEditLink)
    // A throw in a component's setup fails the build. Vue logs such a throw during the server
    // render and VitePress goes on to `build complete`, so the handler sets the exit status.
    if (import.meta.env.SSR) {
      app.config.errorHandler = (error) => {
        console.error(error)
        process.exitCode = 1
      }
    }
  }
} satisfies Theme
