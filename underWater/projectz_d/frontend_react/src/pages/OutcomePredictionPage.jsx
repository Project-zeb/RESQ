import React, { useEffect, useMemo, useState } from "react";
import baseStyles from "/styles.module.css";
import pageStyles from "/pipeline.module.css";
import { Link } from "react-router-dom";
import { cx } from "../utils/cx.js";
import { fetchSessionUser, getUserFirstName } from "../utils/session.js";
import {
  buildOutcomeScenarios,
  readPipelineData
} from "../utils/predictionPipeline.js";

const c = (classNames) => cx(classNames, baseStyles, pageStyles);

export default function OutcomePredictionPage() {
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

  const scenarios = useMemo(() => buildOutcomeScenarios(pipelineData), [pipelineData]);

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
              id="outcome-primary-nav"
              onClick={() => setMobileMenuOpen(false)}
            >
              <Link to="/">Home</Link>
              <Link to="/alerts">Alerts</Link>
              <Link to="/report">Report Incident</Link>
              <Link to="/risk-prediction">Risk Prediction</Link>
              <Link to="/outcome-prediction" className={c("active")}>Outcome Predictor</Link>
              <Link to="/resource-management">Resource Management</Link>
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
              aria-controls="outcome-primary-nav"
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
          <p className={c("pipeline-eyebrow")}>Combinatorial Scenario Matrix</p>
          <h1 className={c("pipeline-title")}>Impact Auditor</h1>
          <p className={c("pipeline-subtitle")}>
            Projected casualty and loss envelopes generated from active risk signatures.
          </p>
        </section>

        {scenarios.length === 0 ? (
          <section className={c("panel empty-block")}>
            <h2>No high-risk combination detected yet.</h2>
            <p>Raise parameters in Risk Prediction to cross threshold and unlock scenario generation.</p>
            <Link to="/risk-prediction" className={c("nav-cta")}>Open Risk Prediction</Link>
          </section>
        ) : (
          <section className={c("scenario-grid")}>
            {scenarios.map((scenario, index) => (
              <article key={scenario.id} className={c("panel scenario-card")}>
                <p className={c("scenario-tag")}>Scenario {index + 1}</p>
                <h2>{scenario.name}</h2>
                <div className={c("scenario-metrics")}>
                  <div>
                    <span>Casualties</span>
                    <strong>{scenario.casualties.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>Loss Index</span>
                    <strong>${scenario.loss.toFixed(1)}M</strong>
                  </div>
                </div>
              </article>
            ))}
          </section>
        )}

        <div className={c("action-row")}>
          <Link to="/resource-management" className={c("nav-cta")}>
            Go To Dispatch
          </Link>
        </div>
      </div>
    </div>
  );
}

