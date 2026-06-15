import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from "./context/AuthContext";
import { Toaster } from "./toast";

// No <StrictMode>: in dev it intentionally double-invokes effects (each data fetch fires
// twice). Effects here all clean up properly, so we drop it for a clean dev network tab.
// (StrictMode only affects development — production builds never double-rendered anyway.)
createRoot(document.getElementById('root')!).render(
  <AuthProvider>
    <App />
    <Toaster />
  </AuthProvider>,
)
