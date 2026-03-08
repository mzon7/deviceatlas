import { Routes, Route, Navigate } from "react-router-dom";
import { ProtectedRoute, AuthCallback } from "@mzon7/zon-incubator-sdk/auth";
import { supabase } from "./lib/supabase";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import HomePage from "./pages/HomePage";
import AdminSignInPage from "./features/admin-sign-in/components/AdminSignInPage";
import AdminLandingPage from "./features/admin-sign-in/components/AdminLandingPage";
import AdminRoute from "./features/admin-sign-in/components/AdminRoute";

export default function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route
        path="/auth/callback"
        element={<AuthCallback supabase={supabase} redirectTo="/home" />}
      />

      {/* Admin sign-in entry point */}
      <Route path="/admin/sign-in" element={<AdminSignInPage />} />

      {/* Protected admin routes */}
      <Route
        path="/admin/devices"
        element={
          <AdminRoute>
            <AdminLandingPage />
          </AdminRoute>
        }
      />
      <Route path="/admin" element={<Navigate to="/admin/sign-in" replace />} />

      {/* Protected routes */}
      <Route
        path="/home"
        element={
          <ProtectedRoute>
            <HomePage />
          </ProtectedRoute>
        }
      />

      {/* Default redirect */}
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}
