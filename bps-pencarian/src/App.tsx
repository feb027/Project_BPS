import { SplitPaneLayout } from "./components/layout/SplitPaneLayout"
import { ErrorBoundary } from "./components/layout/ErrorBoundary"
import './App.css'

function App() {
  return (
    <ErrorBoundary>
      <SplitPaneLayout />
    </ErrorBoundary>
  )
}

export default App
