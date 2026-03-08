import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@mzon7/zon-incubator-sdk/auth";
import { installFrontendErrorCapture } from "@mzon7/zon-incubator-sdk";
import { supabase, PROJECT_PREFIX } from "./lib/supabase";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient();

installFrontendErrorCapture(supabase, PROJECT_PREFIX);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider supabase={supabase}>
          <App />
        </AuthProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
);
