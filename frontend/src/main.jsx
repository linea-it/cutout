import React from "react";
import { createRoot } from "react-dom/client";
import { CssBaseline, ThemeProvider } from "@mui/material";
import theme from "./theme";
import CutoutForm from "./components/CutoutForm";

const rootEl = document.getElementById("cutout-root");

if (rootEl) {
  const authenticated = rootEl.dataset.authenticated === "true";
  const loginUrl = rootEl.dataset.loginUrl || "/admin/login/?next=/";
  const csrfToken = rootEl.dataset.csrfToken || "";

  createRoot(rootEl).render(
    <React.StrictMode>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <CutoutForm
          authenticated={authenticated}
          loginUrl={loginUrl}
          csrfToken={csrfToken}
        />
      </ThemeProvider>
    </React.StrictMode>,
  );
}
