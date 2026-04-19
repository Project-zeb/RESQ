import React, { useEffect, useMemo, useState } from "react";
import baseStyles from "/styles.module.css";
import pageStyles from "/pipeline.module.css";
import { Link, useNavigate } from "react-router-dom";
import { cx } from "../utils/cx.js";
import { fetchSessionUser, getUserFirstName } from "../utils/session.js";
import {
  readPipelineData,
  updatePipelineFromInputs
} from "../utils/predictionPipeline.js";

const c = (classNames) => cx(classNames, baseStyles, pageStyles);

export default function RiskPredictionPage() {
  const navigate = useNavigate();
  const initialData = useMemo(() => readPipelineData(), []);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sessionUser, setSessionUser] = useState(null);
  const [rain, setRain] = useState(initialData.rain);
  const [slope, setSlope] = useState(initialData.slope);
  const [soil, setSoil] = useState(initialData.soil);
  const [pipelineData, setPipelineData] = useState(initialData);

  useEffect(() => {
    let active = true;
    const loadSession = async () => {
      try {
        const user = await fetchSessionUser();
        if (active) {
          setSessionUser(user || null);
        }
      } catch (_error) {
        // Page remains accessible without session.
      }
    };
    loadSession();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const next = updatePipelineFromInputs({ rain, slope, soil });
    setPipelineData(next);
  }, [rain, slope, soil]);

  const riskRows = useMemo(
    () => [
      { label: "Flash Flood", value: pipelineData.flood },
      { label: "Landslide", value: pipelineData.land },
      { label: "Urban Flood", value: pipelineData.urb },
      { label: "Infrastructure", value: pipelineData.infra }
    ],
    [pipelineData]
  );

  const explainText = pipelineData.isCrit
    ? `Danger: rainfall at ${Math.round(
        rain
      )} mm can overwhelm drainage and trigger cascading failures in vulnerable sectors. Immediate response escalation is advised.`
    : "Sensors indicate normal weather. No immediate threat to infrastructure or human life detected.";

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
              id="risk-primary-nav"
              onClick={() => setMobileMenuOpen(false)}
            >
              <Link to="/">Home</Link>
              <Link to="/alerts">Alerts</Link>
              <Link to="/report">Report Incident</Link>
              <Link to="/risk-prediction" className={c("active")}>Risk Prediction</Link>
              <Link to="/outcome-prediction">Outcome Predictor</Link>
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
              aria-controls="risk-primary-nav"
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
          <p className={c("pipeline-eyebrow")}>Neural Disaster Intelligence Pipeline</p>
          <h1 className={c("pipeline-title")}>Risk Prediction Command</h1>
          <p className={c("pipeline-subtitle")}>
            Tune rainfall, slope, and saturation to simulate projected disaster pressure.
          </p>
        </section>

        <main className={c("pipeline-grid")}>
          <section className={c("panel control-panel")}>
            <h2>Tactical Parameters</h2>
            <div className={c("control-stack")}>
              <label>
                <span>Rainfall</span>
                <strong>{Math.round(rain)} mm</strong>
                <input
                  type="range"
                  min={0}
                  max={500}
                  value={rain}
                  onChange={(event) => setRain(Number(event.target.value))}
                />
              </label>
              <label>
                <span>Slope</span>
                <strong>{Math.round(slope)}&deg;</strong>
                <input
                  type="range"
                  min={0}
                  max={45}
                  value={slope}
                  onChange={(event) => setSlope(Number(event.target.value))}
                />
              </label>
              <label>
                <span>Saturation</span>
                <strong>{Math.round(soil)}%</strong>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={soil}
                  onChange={(event) => setSoil(Number(event.target.value))}
                />
              </label>
            </div>
            <button
              type="button"
              className={c(`launch-btn ${pipelineData.isCrit ? "launch-btn-live" : ""}`)}
              disabled={!pipelineData.isCrit}
              onClick={() => navigate("/outcome-prediction")}
            >
              {pipelineData.isCrit ? "Launch Impact Auditor" : "Awaiting Threshold"}
            </button>
          </section>

          <section className={c("panel signature-panel")}>
            <div className={c("signature-head")}>
              <h2>Neural Threat Signature</h2>
              <span className={c(`status-pill ${pipelineData.isCrit ? "critical" : "stable"}`)}>
                {pipelineData.isCrit ? "Critical Threat" : "System Stable"}
              </span>
            </div>
            <div className={c("risk-bars")}>
              {riskRows.map((row) => (
                <div key={row.label} className={c("risk-row")}>
                  <div className={c("risk-label-row")}>
                    <span>{row.label}</span>
                    <strong>{Math.round(row.value)}%</strong>
                  </div>
                  <div className={c("risk-track")}>
                    <span
                      className={c(`risk-fill ${row.value > 75 ? "risk-fill-danger" : ""}`)}
                      style={{ width: `${Math.max(4, row.value)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>
        </main>

        <section className={c("panel explain-panel")}>
          <p className={c("pipeline-eyebrow")}>Situation Report (Human Language)</p>
          <p className={c("explain-text")}>{explainText}</p>
        </section>
      </div>
    </div>
  );
}

