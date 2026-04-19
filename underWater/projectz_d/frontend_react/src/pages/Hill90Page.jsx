import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import baseStyles from "/styles.module.css";
import pageStyles from "/hill90.module.css";
import { cx } from "../utils/cx.js";
import { apiRequest } from "../utils/api.js";
import { fetchSessionUser, getUserFirstName } from "../utils/session.js";

const c = (classNames) => cx(classNames, baseStyles, pageStyles);

function formatUtc(value) {
  if (!value) {
    return "N/A";
  }

  try {
    return new Date(value).toLocaleString();
  } catch (_error) {
    return String(value);
  }
}

function statusLabel(value, okLabel = "Healthy", badLabel = "Down") {
  return value ? okLabel : badLabel;
}

function shortError(value, maxLength = 200) {
  const text = String(value || "").trim();
  if (!text) {
    return "N/A";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 3)}...`;
}

export default function Hill90Page() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sessionUser, setSessionUser] = useState(null);
  const [diagnostics, setDiagnostics] = useState(null);
  const [liveData, setLiveData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [notice, setNotice] = useState({ type: "", text: "" });

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
        // Keep Hill90 page accessible without auth.
      }
    };

    loadSession();
    return () => {
      active = false;
    };
  }, []);

  const loadHill90Data = async ({ silent = false } = {}) => {
    if (!silent) {
      setIsLoading(true);
    }

    try {
      const [diagPayload, livePayload] = await Promise.all([
        apiRequest("/mobile/hill90/diagnostics"),
        apiRequest("/mobile/live-alerts?limit=8")
      ]);

      setDiagnostics(diagPayload || null);
      setLiveData(livePayload || null);
      if (notice.type === "error") {
        setNotice({ type: "", text: "" });
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to load Hill90 diagnostics right now.";
      setNotice({ type: "error", text: message });
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  };

  useEffect(() => {
    loadHill90Data();
  }, []);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await loadHill90Data({ silent: true });
    setIsRefreshing(false);
  };

  const handleForceSync = async () => {
    setIsSyncing(true);
    try {
      const payload = await apiRequest("/mobile/hill90/force-sync", {
        method: "POST",
      });
      if (payload && payload.success) {
        setNotice({
          type: "success",
          text: `Force sync completed at ${formatUtc(payload.attempted_at_utc)}.`,
        });
      } else {
        setNotice({
          type: "error",
          text: "Force sync returned an unexpected response.",
        });
      }
      await loadHill90Data({ silent: true });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Force sync failed.";
      setNotice({ type: "error", text: message });
    } finally {
      setIsSyncing(false);
    }
  };

  const pipeline = diagnostics?.pipeline || {};
  const updates = diagnostics?.updates || {};
  const sources = diagnostics?.sources || {};
  const storage = diagnostics?.storage || {};
  const internalApi = diagnostics?.internal_api || {};
  const database = diagnostics?.database || {};
  const mainSqlite = storage?.main_sqlite || {};
  const internalSqlite = storage?.internal_sqlite || {};
  const fallbackFile = storage?.fallback_file || {};
  const mainDbRows = storage?.main_db_rows || {};
  const internalMongoSnapshot = storage?.internal_mongo_snapshot || {};
  const internalJsonFallback = storage?.internal_json_fallback || {};
  const internalFailoverReady = storage?.internal_failover_ready || {};
  const mongo = database?.mongodb || {};
  const mongoStorage = mongo?.storage || {};
  const mongoCandidateUris = mongo?.candidate_uris_masked || {};
  const mongoBridge = database?.mongo_bridge_sync || {};
  const sqliteFallbackSync = database?.sqlite_fallback_sync || {};
  const sqliteMirrorFile = sqliteFallbackSync?.file || {};
  const activeMode = String(database?.active_mode || "").toLowerCase();
  const activeModeHealthy = ["mongodb", "sqlite", "mysql"].includes(activeMode);
  const startupFetchOk = Boolean(pipeline.last_sync_success_utc);
  const fallbackMirrorHealthy = Boolean(
    sqliteFallbackSync.enabled &&
      !sqliteFallbackSync.last_error &&
      (sqliteFallbackSync.last_success_utc || activeMode === "sqlite")
  );
  const fallbackMirrorLabel = fallbackMirrorHealthy
    ? "Healthy"
    : sqliteFallbackSync.enabled
      ? "Needs Check"
      : "Disabled";
  const fallbackReady = Boolean(sqliteFallbackSync.ready);
  const alerts = Array.isArray(liveData?.alerts) ? liveData.alerts : [];
  const mongoSelectedSource = String(mongo.selected_source || "").trim().toLowerCase();
  const mongoSourceLabel = mongoSelectedSource === "local"
    ? "Local MongoDB"
    : mongoSelectedSource === "shared"
      ? "MongoDB Atlas"
      : mongoSelectedSource === "env"
        ? "Custom Mongo URI"
        : "Auto";
  const mongoPriorityBase = Array.isArray(mongo.priority_order) && mongo.priority_order.length
    ? mongo.priority_order
      .filter((item) => String(item || "").toLowerCase() !== "env")
      .map((item) => {
        const key = String(item || "").toLowerCase();
        if (key === "local") {
          return "local";
        }
        if (key === "shared") {
          return "shared";
        }
        return key;
      })
      .join(" -> ")
    : "local -> shared";
  const mongoBridgeHealthy = Boolean(
    mongoBridge.enabled
      ? (mongoBridge.last_success_utc && !mongoBridge.last_error)
      : true
  );
  const mongoBridgeScope = String(mongoBridge.scope || "").toLowerCase() === "full"
    ? "Full Data"
    : "Users Only";
  const mongoBridgeLabel = mongoBridge.enabled
    ? (mongoBridgeHealthy ? "Healthy" : "Needs Check")
    : "Disabled";
  const userDataLiveStore = activeMode === "mongodb"
    ? (mongoSelectedSource === "local" ? "Local MongoDB" : mongoSelectedSource === "shared" ? "MongoDB Atlas" : "MongoDB")
    : "SQLite Fallback";
  const userDataPriority = `${mongoPriorityBase} -> sqlite_fallback`;
  const internalApiLiveMode = pipeline.internal_api_healthy ? "internal_api_live" : "fallback_mode";
  const internalApiPriorityChain = pipeline.priority_chain || internalApi.priority_chain || "local_mongodb -> internal_sqlite -> file_fallback -> degraded";
  const internalApiAlertsMode = String(liveData?.source_mode || "unknown");
  const internalMongoReady = Boolean(internalFailoverReady.mongo_primary ?? internalMongoSnapshot.ready);
  const internalSqliteReady = Boolean(internalFailoverReady.sqlite_fallback ?? (internalSqlite.rows?.alerts > 0));
  const internalJsonReady = Boolean(internalFailoverReady.file_fallback ?? internalJsonFallback.ready);
  const activeMongoUriMasked = mongo.uri_masked || mongoCandidateUris.env || "Not configured";
  const localMongoUriMasked = mongoCandidateUris.local || (mongoSelectedSource === "local" ? activeMongoUriMasked : "Not configured");
  const atlasMongoUriMasked = mongo.shared_uri_masked || mongoCandidateUris.shared || "Not configured";
  const cloneSharingReady = Boolean(mongo.clone_sharing_ready ?? mongo.shared_configured ?? mongo.shared_ready);
  const mongoScopeLabel = mongo.scope === "shared_remote"
    ? "Shared (Remote)"
    : mongo.scope === "local"
      ? "Local Device"
      : "Not configured";
  const mainDbSize = activeMode === "mongodb"
    ? (mongoStorage.storage_size_human || mongoStorage.data_size_human || "N/A")
    : (mainSqlite.size_human || "N/A");
  const mainDbUsers = mainDbRows.users ?? (activeMode === "mongodb" ? mongoStorage.rows?.users : mainSqlite.rows?.users) ?? "N/A";
  const mainDbProfiles = mainDbRows.profiles ?? (activeMode === "mongodb" ? mongoStorage.rows?.profiles : mainSqlite.rows?.profiles) ?? "N/A";
  const mainDbDisasters = mainDbRows.disasters ?? (activeMode === "mongodb" ? mongoStorage.rows?.disasters : mainSqlite.rows?.disasters) ?? "N/A";
  const pushUniqueError = (bucket, errorText) => {
    if (!errorText) {
      return;
    }
    const duplicate = bucket.some(
      (existing) =>
        existing === errorText ||
        existing.includes(errorText) ||
        errorText.includes(existing)
    );
    if (!duplicate) {
      bucket.push(errorText);
    }
  };
  const userLogErrors = [];
  [
    mongo.selection_error,
    mongo.fallback_reason,
    mongo.connect_error,
    sqliteFallbackSync.last_error,
    sqliteFallbackSync.ready_reason,
    mongoStorage.error,
    mongoBridge.last_error,
    mongoBridge.last_warning,
  ]
    .forEach((errorText) => pushUniqueError(userLogErrors, errorText));
  const internalApiErrors = [];
  [sources.status_error, sources.latest_alert_error]
    .forEach((errorText) => pushUniqueError(internalApiErrors, errorText));

  return (
    <div className={c("page-hill90")}>
      <div className={c("cloud-overlay")} />
      <header className={c("top-nav")}>
        <div
          className={c("nav-content")}
          data-mobile-menu={mobileMenuOpen ? "open" : "closed"}
        >
          <div className={c("nav-left")}>
            <div className={c("logo")}>
              <Link to="/" className={c("logo-container")} style={{ textDecoration: "none" }}>
                <img src="/logo.png" alt="Resqfy Logo" className={c("main-logo")} />
              </Link>
            </div>
            <nav
              className={c("nav-links")}
              id="hill90-primary-nav"
              onClick={() => setMobileMenuOpen(false)}
            >
              <Link to="/">Home</Link>
              <Link to="/alerts">Alerts</Link>
              <Link to="/satellite">Satellite / Geo</Link>
              <Link to="/profile">Profile</Link>
              <Link to="/hill90" className={c("active")}>Hill90</Link>
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
              aria-controls="hill90-primary-nav"
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
              <svg className={c("chevron")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
            </Link>
          </div>
        </div>
      </header>

      <div className={c("dashboard-container hill90-shell")}>
        <section className={c("panel hill90-hero")}>
          <div className={c("hero-head")}>
            <div>
              <h1 className={c("hero-title")}>Hill90 Diagnostics</h1>
              <p className={c("hero-subtitle")}>
                Live internal API, sync, source, and storage status in one place.
              </p>
            </div>
            <div className={c("hero-actions")}>
              <button
                type="button"
                className={c("action-btn action-ghost")}
                onClick={handleRefresh}
                disabled={isRefreshing || isSyncing}
              >
                {isRefreshing ? "Refreshing..." : "Refresh"}
              </button>
              <button
                type="button"
                className={c("action-btn action-primary")}
                onClick={handleForceSync}
                disabled={isSyncing || isRefreshing}
              >
                {isSyncing ? "Syncing..." : "Force Sync"}
              </button>
            </div>
          </div>

          {notice.text ? (
            <p className={c(notice.type === "error" ? "notice notice-error" : "notice notice-success")}>
              {notice.text}
            </p>
          ) : null}
        </section>

        {isLoading && !diagnostics ? (
          <section className={c("panel loading-box")}>Loading Hill90 data...</section>
        ) : (
          <div className={c("hill90-grid")}>
            <section className={c("panel info-card")}>
              <h2>Pipeline</h2>
              <div className={c("kv-list")}>
                <div className={c("kv-row")}>
                  <span>Internal API</span>
                  <strong className={c(pipeline.internal_api_healthy ? "pill green" : "pill red")}>
                    {statusLabel(pipeline.internal_api_healthy)}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Recommended Mode</span>
                  <strong>{pipeline.recommended_mode || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Last Sync Attempt</span>
                  <strong>{formatUtc(pipeline.last_sync_attempt_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Last Sync Success</span>
                  <strong>{formatUtc(pipeline.last_sync_success_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Startup Fetch</span>
                  <strong className={c(startupFetchOk ? "pill green" : "pill red")}>
                    {startupFetchOk ? "Completed" : "Pending"}
                  </strong>
                </div>
              </div>
            </section>

            <section className={c("panel info-card")}>
              <h2>Sources</h2>
              <div className={c("kv-list")}>
                <div className={c("kv-row")}>
                  <span>Total Sources</span>
                  <strong>{sources.count ?? 0}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Healthy Sources</span>
                  <strong>{sources.healthy_count ?? 0}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Failing Sources</span>
                  <strong>{sources.failing_count ?? 0}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Latest Alert Time</span>
                  <strong>{formatUtc(updates.latest_alert_updated_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Latest Alert Source</span>
                  <strong>{updates.latest_alert_source || "N/A"}</strong>
                </div>
              </div>
            </section>

            <section className={c("panel info-card")}>
              <h2>Storage</h2>
              <div className={c("kv-list")}>
                <div className={c("kv-row")}>
                  <span>Total SQLite Size</span>
                  <strong>{storage.total_sqlite_human || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Main DB Mode</span>
                  <strong>{(storage.main_db_mode || database.active_mode || "unknown").toUpperCase()}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Main DB Users</span>
                  <strong>{storage.main_db_rows?.users ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Main DB Disasters</span>
                  <strong>{storage.main_db_rows?.disasters ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Storage</span>
                  <strong>{mongoStorage.storage_size_human || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Collections</span>
                  <strong>{mongoStorage.collections_count ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Internal Alerts Rows</span>
                  <strong>{storage.internal_sqlite?.rows?.alerts ?? "N/A"}</strong>
                </div>
              </div>
            </section>

            <section className={c("panel info-card full-span")}>
              <h2>User Log Tracking</h2>
              <div className={c("kv-list")}>
                <div className={c("kv-row")}>
                  <span>Requested Primary</span>
                  <strong>{database.requested_primary || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Active Mode</span>
                  <strong className={c(activeModeHealthy ? "pill green" : "pill red")}>
                    {database.active_mode || "unknown"}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Django Engine</span>
                  <strong>{database.django_engine || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Live Store</span>
                  <strong>{userDataLiveStore}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Active Source</span>
                  <strong>{mongoSourceLabel}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Priority Chain</span>
                  <strong>{userDataPriority}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Scope</span>
                  <strong>{mongoScopeLabel}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Clone Sharing Ready</span>
                  <strong className={c(cloneSharingReady ? "pill green" : "pill red")}>
                    {cloneSharingReady ? "Yes" : "No"}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>MongoDB Atlas URI</span>
                  <strong className={c("mono-value")}>{atlasMongoUriMasked}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Local Mongo URI</span>
                  <strong className={c("mono-value")}>{localMongoUriMasked}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Active Mongo URI</span>
                  <strong className={c("mono-value")}>{activeMongoUriMasked}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Main DB Size</span>
                  <strong>{mainDbSize}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Main DB Users</span>
                  <strong>{mainDbUsers}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Main DB Profiles</span>
                  <strong>{mainDbProfiles}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Main DB Disasters</span>
                  <strong>{mainDbDisasters}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Collections</span>
                  <strong>{mongoStorage.collections_count ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Objects</span>
                  <strong>{mongoStorage.objects_count ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Bridge Sync</span>
                  <strong className={c(mongoBridgeHealthy ? "pill green" : "pill red")}>
                    {mongoBridgeLabel}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Bridge Scope</span>
                  <strong>{mongoBridgeScope}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Last User Bridge Sync</span>
                  <strong>{formatUtc(mongoBridge.last_success_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Last Bridge Attempt</span>
                  <strong>{formatUtc(mongoBridge.last_attempt_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Bridge Error</span>
                  <strong title={mongoBridge.last_error || ""}>{shortError(mongoBridge.last_error)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>SQLite Mirror Sync</span>
                  <strong className={c(fallbackMirrorHealthy ? "pill green" : "pill red")}>
                    {fallbackMirrorLabel}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>SQLite Fallback Ready</span>
                  <strong className={c(fallbackReady ? "pill green" : "pill red")}>
                    {fallbackReady ? "Ready" : "Not Ready"}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>SQLite Mirror File</span>
                  <strong className={c("mono-value")}>{sqliteMirrorFile.path || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>SQLite Mirror Size</span>
                  <strong>{sqliteMirrorFile.size_human || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>SQLite User Mirror</span>
                  <strong>{formatUtc(sqliteFallbackSync.last_success_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>SQLite Mirror Users</span>
                  <strong>{sqliteFallbackSync.rows?.users ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>SQLite Mirror Profiles</span>
                  <strong>{sqliteFallbackSync.rows?.profiles ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>SQLite Mirror Disasters</span>
                  <strong>{sqliteFallbackSync.rows?.disasters ?? "N/A"}</strong>
                </div>
              </div>
              {userLogErrors.map((errorText) => (
                <p key={errorText} className={c("notice notice-error")}>{errorText}</p>
              ))}
            </section>

            <section className={c("panel info-card full-span")}>
              <h2>Internal API Tracking</h2>
              <div className={c("kv-list")}>
                <div className={c("kv-row")}>
                  <span>Live Mode</span>
                  <strong className={c(pipeline.internal_api_healthy ? "pill green" : "pill red")}>
                    {internalApiLiveMode}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Priority Mode</span>
                  <strong>{pipeline.recommended_mode || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Priority Chain</span>
                  <strong>{internalApiPriorityChain}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Primary Ready</span>
                  <strong className={c(internalMongoReady ? "pill green" : "pill red")}>
                    {internalMongoReady ? "Ready" : "Not Ready"}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Snapshot Rows</span>
                  <strong>{internalMongoSnapshot.count ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Mongo Snapshot Last Sync</span>
                  <strong>{formatUtc(internalMongoSnapshot.saved_at_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Alerts Feed Mode</span>
                  <strong>{internalApiAlertsMode}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Last Fetch Attempt</span>
                  <strong>{formatUtc(pipeline.last_sync_attempt_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Last Fetch Success</span>
                  <strong>{formatUtc(pipeline.last_sync_success_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Latest Alert Source</span>
                  <strong>{updates.latest_alert_source || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Latest Alert ID</span>
                  <strong>{updates.latest_alert_id || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Source Status</span>
                  <strong>{sources.failing_count ? "Partial Failure" : "Healthy"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Base URL</span>
                  <strong className={c("mono-value")}>{internalApi.base_url || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Health URL</span>
                  <strong className={c("mono-value")}>{internalApi.health_url || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Alerts URL</span>
                  <strong className={c("mono-value")}>{internalApi.alerts_url || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Diagnostics URL</span>
                  <strong className={c("mono-value")}>/api/mobile/hill90/diagnostics</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Force Sync URL</span>
                  <strong className={c("mono-value")}>/api/mobile/hill90/force-sync</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Internal DB File</span>
                  <strong className={c("mono-value")}>{internalSqlite.path || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Internal DB Size</span>
                  <strong>{internalSqlite.size_human || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Internal DB Updated</span>
                  <strong>{formatUtc(internalSqlite.modified_at_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>SQLite Fallback Ready</span>
                  <strong className={c(internalSqliteReady ? "pill green" : "pill red")}>
                    {internalSqliteReady ? "Ready" : "Not Ready"}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Internal Alerts Rows</span>
                  <strong>{internalSqlite.rows?.alerts ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Internal Source Runs</span>
                  <strong>{internalSqlite.rows?.source_runs ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Fallback JSON File</span>
                  <strong className={c("mono-value")}>{fallbackFile.path || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>JSON Fallback Ready</span>
                  <strong className={c(internalJsonReady ? "pill green" : "pill red")}>
                    {internalJsonReady ? "Ready" : "Not Ready"}
                  </strong>
                </div>
                <div className={c("kv-row")}>
                  <span>JSON Alerts Count</span>
                  <strong>{internalJsonFallback.alerts_count ?? "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Fallback JSON Size</span>
                  <strong>{fallbackFile.size_human || "N/A"}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>Fallback JSON Updated</span>
                  <strong>{formatUtc(fallbackFile.modified_at_utc)}</strong>
                </div>
                <div className={c("kv-row")}>
                  <span>JSON Last Generated</span>
                  <strong>{formatUtc(internalJsonFallback.generated_at_utc)}</strong>
                </div>
              </div>
              {internalApiErrors.map((errorText) => (
                <p key={errorText} className={c("notice notice-error")}>{errorText}</p>
              ))}
            </section>

            <section className={c("panel info-card full-span")}>
              <h2>Live Alerts ({liveData?.count ?? alerts.length ?? 0})</h2>
              {alerts.length === 0 ? (
                <p className={c("empty-text")}>No live alerts available right now.</p>
              ) : (
                <div className={c("alert-list")}>
                  {alerts.slice(0, 8).map((alert, index) => (
                    <article className={c("alert-item")} key={`${alert.id || alert.title || "alert"}-${index}`}>
                      <div className={c("alert-top")}>
                        <strong>{alert.title || alert.type || "Alert"}</strong>
                        <span className={c("severity-pill")}>{alert.severity || "WATCH"}</span>
                      </div>
                      <p>{alert.message || "No description"}</p>
                      <div className={c("alert-meta")}>
                        <span>{alert.area || "Area not specified"}</span>
                        <span>{alert.source || "Unknown source"}</span>
                        <span>{formatUtc(alert.start_time || alert.end_time || liveData?.generated_at)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
