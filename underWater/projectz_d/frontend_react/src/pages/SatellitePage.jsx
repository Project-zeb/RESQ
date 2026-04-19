import React, { useEffect, useState } from "react";
import baseStyles from "/styles.module.css";
import pageStyles from "/satellite.module.css";
import { Link } from "react-router-dom";
import { cx } from "../utils/cx.js";
import {
  fetchSessionUser,
  getUserFirstName
} from "../utils/session.js";

const c = (classNames) => cx(classNames, baseStyles, pageStyles);

export default function SatellitePage() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sessionUser, setSessionUser] = useState(null);

  useEffect(() => {
    let active = true;

    const loadSession = async () => {
      try {
        const user = await fetchSessionUser();
        if (!active) {
          return;
        }
        setSessionUser(user || null);
      } catch (_error) {
        // Keep Satellite accessible even when not logged in.
      }
    };

    loadSession();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className={c("page-satellite")}>
      <div className={c("cloud-overlay")} />
      {/* Top Navigation */}
      <header className={c("top-nav")}>
        <div
          className={c("nav-content")}
          data-mobile-menu={mobileMenuOpen ? "open" : "closed"}
        >
          <div className={c("nav-left")}>
            <div className={c("logo")}>
              <Link to="/" className={c("logo-container")} style={{textDecoration: 'none'}}>
                <img src="/logo.png" alt="Resqfy Logo" className={c("main-logo")} />
              </Link>
            </div>
            <nav
              className={c("nav-links")}
              id="satellite-primary-nav"
              onClick={() => setMobileMenuOpen(false)}
            >
              <Link to="/">Home</Link>
              <Link to="/alerts">Alerts</Link>
              <Link to="/risk-prediction">Risk Prediction</Link>
              <Link to="/outcome-prediction">Outcome Predictor</Link>
              <Link to="/resource-management">Resource Management</Link>
              <Link to="/satellite" className={c("active")}>Satellite / Geo</Link>
            </nav>
          </div>
          <div className={c("nav-right")}>
            <div className={c("theme-toggle")}>
              <button
                className={c("toggle-btn")}
                data-theme-toggle
                aria-label="Toggle theme"
              >
                <svg className={c("sun")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={12} cy={12} r={5} /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></svg>
                <div className={c("toggle-track")}><div className={c("toggle-thumb")} /></div>
                <svg className={c("moon")} viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
              </button>
            </div>
            <button
              className={c("mobile-menu-btn")}
              type="button"
              aria-label="Toggle navigation menu"
              aria-controls="satellite-primary-nav"
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
            <Link to="/profile" className={c("user-profile")} style={{textDecoration: "none"}}>
              <img src="/profile-icon.svg" alt="User profile" className={c("avatar")} />
              <div className={c("user-info")}>
                <span className={c("name")}>{getUserFirstName(sessionUser)}</span>
              </div>
              <svg className={c("chevron")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
            </Link>
          </div>
        </div>
      </header>
      <div className={c("dashboard-container")}>
        {/* Main Dashboard View */}
        <main className={c("satellite-layout")}>
          {/* LEFT COLUMN: MAP LAYERS */}
          <aside className={c("panel layers-sidebar")}>
            <div className={c("sidebar-header")}>
              <h2>MAP LAYERS</h2>
              <p>Select layer to display</p>
            </div>
            <div className={c("layer-group")}>
              {/* Temperature Layer */}
              <div className={c("layer-item active")}>
                <div className={c("layer-header")}>
                  <span>TEMPERATURE</span>
                  <div className={c("active-tag")}>ACTIVE</div>
                </div>
                <div className={c("layer-info")}>
                  <div className={c("layer-icon")} style={{background: '#ef4444'}}>
                    {/* Windy 'W' Logo Approximation */}
                    <svg width={20} height={20} viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12.12 1.5c-5.8 0-10.5 4.7-10.5 10.5s4.7 10.5 10.5 10.5 10.5-4.7 10.5-10.5-4.7-10.5-10.5-10.5zm3.8 15.8c-1.1 0-2.1-.6-2.6-1.5l-1.2-2.1-1.2 2.1c-.5.9-1.5 1.5-2.6 1.5-1.7 0-3.1-1.4-3.1-3.1s1.4-3.1 3.1-3.1c1.1 0 2.1.6 2.6 1.5l1.2 2.1 1.2-2.1c.5-.9 1.5-1.5 2.6-1.5 1.7 0 3.1 1.4 3.1 3.1s-1.4 3.1-3.1 3.1z" />
                    </svg>
                  </div>
                  <div className={c("layer-title")}>Temperature</div>
                </div>
                <div className={c("temp-scale")} />
                <div className={c("scale-labels")}>
                  <span>10°</span><span>20°</span><span>30°</span><span>40°</span>
                </div>
                <div className={c("heatwave-status-title")}>Heatwave Alert Status</div>
                <div className={c("heatwave-status-card")}>
                  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1={12} y1={9} x2={12} y2={13} /><line x1={12} y1={17} x2="12.01" y2={17} /></svg>
                  <span>Active - Moderate</span>
                </div>
              </div>
              {/* Wind Gusts Layer */}
              <div className={c("layer-item")}>
                <div className={c("layer-header")}>
                  <span>WIND GUSTS</span>
                </div>
                <div className={c("layer-info no-box wind-detailed")}>
                  <svg className={c("layer-svg")} width={32} height={32} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2" /></svg>
                  <div className={c("compass-icon")}>
                    <svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <circle cx={12} cy={12} r={9} strokeDasharray="2 2" />
                      <path d="M12 2v2m0 16v2m8-10h2M2 12h2" strokeWidth={1} />
                      <path d="M12 7l3 10-3-2-3 2 3-10z" fill="currentColor" />
                    </svg>
                  </div>
                </div>
              </div>
              {/* Fire Hotspots Layer */}
              <div className={c("layer-item")}>
                <div className={c("layer-header")}>
                  <div className={c("header-with-icon")}>
                    <svg width={18} height={18} viewBox="0 0 24 24" fill="#f97316"><path d="M12 2c-3.5 3.5-5 7.5-5 10a5 5 0 0 0 10 0c0-2.5-1.5-6.5-5-10zM12 22a7 7 0 0 0 7-7c0-2-1-3.5-2-4.5M5 15a7 7 0 0 0 7 7" /></svg>
                    <span>FIRE HOTSPOTS</span>
                  </div>
                </div>
                <div className={c("layer-content-detailed")}>
                  <div className={c("detail-label")}>Heat intensity</div>
                  <div className={c("fire-intensity-scale")} />
                </div>
              </div>
              {/* Storm Track Layer */}
              <div className={c("layer-item")}>
                <div className={c("layer-header")}>
                  <div className={c("header-with-icon")}>
                    <svg width={18} height={18} viewBox="0 0 24 24" fill="#94a3b8"><path d="M17.5 19c.3 0 .5-.1.7-.3.2-.2.3-.5.3-.7s-.1-.5-.3-.7c-.2-.2-.5-.3-.7-.3h-.5c-.1-1.3-.7-2.6-1.7-3.6-1-1-2.3-1.6-3.6-1.7V11c0-.3-.1-.5-.3-.7-.2-.2-.5-.3-.7-.3s-.5.1-.7.3c-.2.2-.3.5-.3.7v.7c-1.3.1-2.6.7-3.6 1.7-1 1-1.6 2.3-1.7 3.6h-.5c-.3 0-.5.1-.7.3-.2.2-.3.5-.3.7s.1.5.3.7c.2.2.5.3.7.3h12z" /><path d="M12 18l-1 3h2l-1-3z" fill="#ffb000" /></svg>
                    <span>STORM TRACK</span>
                  </div>
                </div>
                <div className={c("storm-legend-box")}>
                  <div className={c("legend-item")}>
                    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx={12} cy={12} r={6} /><circle cx={12} cy={12} r="1.5" fill="currentColor" /></svg>
                    <span>Current Position</span>
                  </div>
                  <div className={c("legend-item")}>
                    <svg width={32} height={16} viewBox="0 0 48 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1={0} y1={12} x2={16} y2={12} strokeDasharray="4 4" />
                      <circle cx={32} cy={12} r={6} />
                      <circle cx={32} cy={12} r="1.5" fill="currentColor" />
                    </svg>
                    <span>Forecast Path</span>
                  </div>
                </div>
              </div>
            </div>
          </aside>
          {/* CENTER COLUMN: SATELLITE VIEW */}
          <section className={c("satellite-main")}>
            <div className={c("main-header")}>
              <h1>SATELLITE VIEW</h1>
              <p>Track wind, fire, storm and weather layers over india</p>
            </div>
            <div className={c("map-container panel")}>
              <div className={c("satellite-controls")}>
                Satellite Controls
              </div>
              {/* Windy.com Interactive Iframe */}
              <iframe width="100%" height="100%" src="https://embed.windy.com/embed2.html?lat=21.000&lon=78.000&detailLat=21.000&detailLon=78.000&width=650&height=450&zoom=5&level=surface&overlay=temp&product=ecmwf&menu=&message=true&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1" frameBorder={0} style={{border: 'none'}}>
              </iframe>
              <div className={c("map-overlay-controls")}>
                <button className={c("control-btn")}><svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><line x1={12} y1={5} x2={12} y2={19} /><line x1={5} y1={12} x2={19} y2={12} /></svg></button>
                <button className={c("control-btn")}><svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><line x1={5} y1={12} x2={19} y2={12} /></svg></button>
                <button className={c("control-btn")}><svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z" /><circle cx={12} cy={10} r={3} /></svg></button>
                <button className={c("control-btn")}><svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" /><circle cx={12} cy={13} r={4} /></svg></button>
              </div>
            </div>
          </section>
        </main>
        {/* Global Footer */}
        <footer className={c("app-footer-text")}>
          About Resqfy &nbsp;|&nbsp; Contact Support &nbsp;|&nbsp; Privacy Policy &nbsp;|&nbsp; Terms of Service &nbsp;|&nbsp; © 2026 Resqfy. All rights reserved.
        </footer>
      </div>
    </div>
  );
}
