import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Landing from './App'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import PatientViewer from './pages/PatientViewer'
import Writeup from './pages/Writeup'
import RequireAuth from './components/RequireAuth'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <Dashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/patient/:id"
          element={
            <RequireAuth>
              <PatientViewer />
            </RequireAuth>
          }
        />
        <Route path="/writeup" element={<Writeup />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
