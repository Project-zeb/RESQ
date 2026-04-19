import React, { useEffect, useMemo, useState } from "react";
import baseStyles from "/styles.module.css";
import pageStyles from "/pipeline.module.css";
import { Link } from "react-router-dom";
import { cx } from "../utils/cx.js";
import { fetchSessionUser, getUserFirstName } from "../utils/session.js";
import {
  buildResourceManifest,
  readPipelineData
} from "../utils/predictionPipeline.js";

const c = (classNames) => cx(classNames, baseStyles, pageStyles);

function buildManifestText(resources, agencies) {
  const lines = [
    "RESQFY TACTICAL DISPATCH MANIFEST",
    `Generated: ${new Date().toISOString()}`,
    "",
    "RESOURCE ALLOCATION"
  ];

  resources.forEach((item) => {
    lines.push(`- ${item.name}: ${item.quantity.toLocaleString()} ${item.unit}`);
  });

  lines.push("", "PERSONNEL & AGENCY DISPATCH");
  agencies.forEach((agency) => {
    lines.push(
      `- ${agency.name} | Lead: ${agency.lead} | UID: ${agency.id} | Status: ${agency.status}`
    );
  });

  return `${lines.join("\n")}\n`;
}

export default function ResourceManagementPage() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sessionUser, setSessionUser] = useState(null);
  const [pipelineData, setPipelineData] = useState(() => readPipelineData());

  useEffect(() => {
    let active = true;
    const loadSession = async () => {
      try {
        const user = await fetchSessionUser();
        if (active) {
          setSessionUser(user || null);
        }
      } catch (_error) {
        // Continue without auth lock.
      }
    };
    loadSession();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const refreshFromStorage = () => {
      setPipelineData(readPipelineData());
    };
    window.addEventListener("storage", refreshFromStorage);
    return () => {
      window.removeEventListener("storage", refreshFromStorage);
    };
  }, []);

  const manifest = useMemo(() => buildResourceManifest(pipelineData), [pipelineData]);

  const downloadManifest = () => {
    const text = buildManifestText(manifest.resources, manifest.agencies);
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "Resqfy_Tactical_Dispatch.txt";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={c("page-pipeline")}>
      <header className={c("top-nav")}>
        <div
          className={c("nav-content")}
          data-mobile-menu={mobileMenuOpen ? "open" : "closed"}
        >
          <div className={c("nav-left")}>
            <Link to="/" className={c("logo-container")} style={{ textDecoration: "none" }}>
              <img src="/logo.png" alt="Resqfy Logo" className={c("main-logo")} />
            </Link>
            <nav
              className={c("nav-links")}
              id="resource-primary-nav"
              onClick={() => setMobileMenuOpen(false)}
            >
              <Link to="/">Home</Link>
              <Link to="/alerts">Alerts</Link>
              <Link to="/report">Report Incident</Link>
              <Link to="/risk-prediction">Risk Prediction</Link>
              <Link to="/outcome-prediction">Outcome Predictor</Link>
              <Link to="/resource-management" className={c("active")}>Resource Management</Link>
              <Link to="/satellite">Satellite / Geo</Link>
            </nav>
          </div>
          <div className={c("nav-right")}>
            <div className={c("theme-toggle")}>
              <button className={c("toggle-btn")} data-theme-toggle aria-label="Toggle theme">
                <svg className={c("sun")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={12} cy={12} r={5} /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></svg>
                <div className={c("toggle-track")}><div className={c("toggle-thumb")} /></div>
                <svg className={c("moon")} viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
              </button>
            </div>
            <button
              className={c("mobile-menu-btn")}
              type="button"
              aria-label="Toggle navigation menu"
              aria-controls="resource-primary-nav"
              aria-expanded={mobileMenuOpen}
              onClick={() => setMobileMenuOpen((open) => !open)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
                {mobileMenuOpen ? (
                  <>
                    <path d="M6 6l12 12" />
                    <path d="M18 6l-12 12" />
                  </>
                ) : (
                  <>
                    <path d="M3 6h18" />
                    <path d="M3 12h18" />
                    <path d="M3 18h18" />
                  </>
                )}
              </svg>
            </button>
            <Link to="/profile" className={c("user-profile")} style={{ textDecoration: "none" }}>
              <img src="/profile-icon.svg" alt="User profile" className={c("avatar")} />
              <div className={c("user-info")}>
                <span className={c("name")}>{getUserFirstName(sessionUser)}</span>
              </div>
            </Link>
          </div>
        </div>
      </header>

      <div className={c("dashboard-container pipeline-wrap")}>
        <section className={c("pipeline-head panel")}>
          <p className={c("pipeline-eyebrow")}>Neural Logistics & Personnel Hub</p>
          <h1 className={c("pipeline-title")}>Sentinel Dispatch</h1>
          <p className={c("pipeline-subtitle")}>
            Operational manifest assembled from current risk telemetry and projected impact.
          </p>
        </section>

        <div className={c("action-row")}>
          <button type="button" className={c("nav-cta")} onClick={downloadManifest}>
            Download Manifest
          </button>
        </div>

        <main className={c("resource-layout")}>
          <section className={c("panel resource-panel")}>
            <h2>Resource Allocation</h2>
            <div className={c("resource-grid")}>
              {manifest.resources.map((item) => (
                <article key={item.name} className={c("resource-card")}>
                  <p>{item.name}</p>
                  <strong>{item.quantity.toLocaleString()}</strong>
                  <span>{item.unit}</span>
                </article>
              ))}
            </div>
          </section>

          <section className={c("panel agency-panel")}>
            <h2>Personnel & Agency Dispatch</h2>
            <div className={c("agency-list")}>
              {manifest.agencies.map((agency) => (
                <article key={agency.id} className={c("agency-card")}>
                  <div>
                    <strong>{agency.name}</strong>
                    <p>Lead: {agency.lead}</p>
                    <p>UID: {agency.id}</p>
                  </div>
                  <span className={c(`agency-status ${manifest.isCrit ? "critical" : "stable"}`)}>
                    {agency.status}
                  </span>
                </article>
              ))}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

