import React, { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AlertsPage from "./pages/AlertsPage.jsx";
import HomePage from "./pages/HomePage.jsx";
import Hill90Page from "./pages/Hill90Page.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import NgosPage from "./pages/NgosPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";
import ReportPage from "./pages/ReportPage.jsx";
import SatellitePage from "./pages/SatellitePage.jsx";
import SignupPage from "./pages/SignupPage.jsx";

function AdminRedirect({ target = "/django-admin/" }) {
  useEffect(() => {
    window.location.replace(target);
  }, [target]);

  return null;
}

function formatHeaderTime(date) {
  const time = date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true
  });

  const day = date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric"
  });

  return `${time} - ${day}`;
}

export default function App() {
  const location = useLocation();

  useEffect(() => {
    const storedTheme = localStorage.getItem("theme") || "dark";
    document.documentElement.setAttribute("data-theme", storedTheme);
  }, []);

  useEffect(() => {
    const handleDocumentClick = (event) => {
      if (!(event.target instanceof Element)) {
        return;
      }

      const toggleButton = event.target.closest("[data-theme-toggle]");
      if (!toggleButton) {
        return;
      }

      const currentTheme =
        document.documentElement.getAttribute("data-theme") || "dark";
      const nextTheme = currentTheme === "light" ? "dark" : "light";

      document.documentElement.setAttribute("data-theme", nextTheme);
      localStorage.setItem("theme", nextTheme);
    };

    document.addEventListener("click", handleDocumentClick);
    return () => {
      document.removeEventListener("click", handleDocumentClick);
    };
  }, []);

  useEffect(() => {
    const updateTime = () => {
      const timeElement = document.getElementById("header-time");
      if (!timeElement) {
        return;
      }

      timeElement.textContent = formatHeaderTime(new Date());
    };

    updateTime();
    const intervalId = window.setInterval(updateTime, 60_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [location.pathname]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/" element={<HomePage />} />
      <Route path="/home" element={<HomePage />} />
      <Route path="/admin" element={<AdminRedirect target="/django-admin/" />} />
      <Route path="/admin/user-view" element={<AdminRedirect target="/django-admin/auth/user/" />} />
      <Route path="/alerts" element={<AlertsPage />} />
      <Route path="/report" element={<ReportPage />} />
      <Route path="/ngos" element={<NgosPage />} />
      <Route path="/mobile/organization" element={<NgosPage />} />
      <Route
        path="/risk-prediction"
        element={<AdminRedirect target="/model_1_only/model_1_command.html" />}
      />
      <Route
        path="/outcome-prediction"
        element={<AdminRedirect target="/model_2_only/model_2_impact_portal.html" />}
      />
      <Route
        path="/resource-management"
        element={<AdminRedirect target="/model_3_only/model_3_4_sentinel.html" />}
      />
      <Route path="/satellite" element={<SatellitePage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/hill90" element={<Hill90Page />} />
      <Route path="/mobile/hill90" element={<Hill90Page />} />
      <Route path="/mobile/live-alerts-check" element={<Hill90Page />} />
      <Route path="/signin" element={<Navigate to="/login" replace />} />
      <Route path="/sign-up" element={<Navigate to="/signup" replace />} />
      <Route path="/index.html" element={<Navigate to="/" replace />} />
      <Route path="/alerts.html" element={<Navigate to="/alerts" replace />} />
      <Route path="/report.html" element={<Navigate to="/report" replace />} />
      <Route
        path="/risk-prediction.html"
        element={<Navigate to="/risk-prediction" replace />}
      />
      <Route
        path="/outcome-prediction.html"
        element={<Navigate to="/outcome-prediction" replace />}
      />
      <Route
        path="/resource-management.html"
        element={<Navigate to="/resource-management" replace />}
      />
      <Route
        path="/satellite.html"
        element={<Navigate to="/satellite" replace />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
