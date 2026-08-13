import { LineChart } from 'echarts/charts'
import {
  DataZoomInsideComponent,
  DataZoomSliderComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

// Register only the modules used by the starter chart. Add other chart types here
// when a concrete page needs scatter, heatmap, gauge, or other ECharts features.
use([
  CanvasRenderer,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomInsideComponent,
  DataZoomSliderComponent,
])
