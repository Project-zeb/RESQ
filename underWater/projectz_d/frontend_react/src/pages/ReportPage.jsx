import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import baseStyles from "/styles.module.css";
import styles from "/report.module.css";
import { apiRequest } from "../utils/api.js";
import { fetchSessionUser, getUserFirstName } from "../utils/session.js";

const INCIDENT_TYPES = [
  "Flash Flood",
  "River Flood",
  "Urban Flood",
  "Cyclone",
  "Thunderstorm",
  "Lightning Strike",
  "Urban Fire",
  "Wildfire",
  "Landslide",
  "Avalanche",
  "Cloudburst",
  "Earthquake",
  "Tsunami",
  "Heat Wave",
  "Cold Wave",
  "Building Collapse",
  "Industrial Accident",
  "Chemical Spill",
  "Gas Leak",
  "Drought",
  "Epidemic / Health Emergency",
  "Other"
];

const MEDIA_TYPES = [
  { label: "Image", value: "image" },
  { label: "Video", value: "video" },
  { label: "Audio", value: "audio" },
  { label: "Document", value: "document" }
];

const SEVERITY_LEVELS = ["Watch", "Elevated", "Alert", "Critical", "Emergency"];
const SEVERITY_COLORS = ["#facc15", "#f59e0b", "#fb923c", "#ef4444", "#dc2626"];

function toLocalDatetimeValue(date) {
  const copy = new Date(date);
  copy.setMinutes(copy.getMinutes() - copy.getTimezoneOffset());
  return copy.toISOString().slice(0, 16);
}

function parseCoordinate(rawValue, label) {
  const trimmed = String(rawValue || "").trim();
  if (!trimmed) {
    return null;
  }

  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a valid number.`);
  }

  return parsed;
}

export default function ReportPage() {
  const navigate = useNavigate();
  const mediaInputRef = useRef(null);

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sessionUser, setSessionUser] = useState(null);
  const [severityIndex, setSeverityIndex] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitMessage, setSubmitMessage] = useState({
    kind: "idle",
    text: ""
  });
  const [mediaFile, setMediaFile] = useState(null);
  const [mediaType, setMediaType] = useState("");
  const [isDetectingLocation, setIsDetectingLocation] = useState(false);
  const [locationHint, setLocationHint] = useState("");
  const [formState, setFormState] = useState({
    incidentType: "",
    reportTime: toLocalDatetimeValue(new Date()),
    location: "Gaffar Manzil, Sarita Vihar Tehsil, South East Delhi",
    latitude: "28.55478081",
    longitude: "77.28381017",
    summary: ""
  });
  const severityTone = SEVERITY_COLORS[severityIndex] || SEVERITY_COLORS[0];
  const handleSeverityInput = (event) =>
    setSeverityIndex(Number(event.target.value));

  useEffect(() => {
    let cancelled = false;

    async function loadSessionUser() {
      try {
        const user = await fetchSessionUser();
        if (!cancelled) {
          setSessionUser(user);
        }
      } catch (_error) {
        if (!cancelled) {
          setSessionUser(null);
        }
      }
    }

    loadSessionUser();
    return () => {
      cancelled = true;
    };
  }, []);

  const updateField = (event) => {
    const { name, value } = event.target;
    setFormState((previous) => ({
      ...previous,
      [name]: value
    }));
  };

  const handleMediaPick = (event) => {
    const file = event.target.files?.[0] || null;
    if (!file) {
      setMediaFile(null);
      return;
    }

    if (!mediaType) {
      setSubmitMessage({
        kind: "info",
        text: "Choose media type before file upload."
      });
      event.target.value = "";
      return;
    }

    setMediaFile(file);
    setSubmitMessage({
      kind: "info",
      text: `${mediaType} attached: ${file.name}`
    });
  };

  const clearMediaSelection = () => {
    setMediaFile(null);
    if (mediaInputRef.current) {
      mediaInputRef.current.value = "";
    }
  };

  const resetDraft = () => {
    setFormState({
      incidentType: "",
      reportTime: toLocalDatetimeValue(new Date()),
      location: "",
      latitude: "",
      longitude: "",
      summary: ""
    });
    setMediaType("");
    setSeverityIndex(0);
    setLocationHint("");
    setSubmitMessage({ kind: "info", text: "Draft cleared." });
    clearMediaSelection();
  };

  const handleAutoDetectLocation = () => {
    setFormState((previous) => ({
      ...previous,
      reportTime: toLocalDatetimeValue(new Date())
    }));

    if (!navigator.geolocation) {
      setLocationHint("Time updated. Auto-detect is not supported on this browser.");
      return;
    }

    setIsDetectingLocation(true);
    setLocationHint("Detecting address and coordinates...");

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const latitude = position.coords.latitude.toFixed(6);
        const longitude = position.coords.longitude.toFixed(6);
        let locationLabel = `Auto-detected (${latitude}, ${longitude})`;

        try {
          const controller = new AbortController();
          const timeoutId = window.setTimeout(() => controller.abort(), 3000);
          const response = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${latitude}&lon=${longitude}`,
            {
              signal: controller.signal,
              headers: { Accept: "application/json" }
            }
          );
          window.clearTimeout(timeoutId);

          if (response.ok) {
            const payload = await response.json();
            if (payload && payload.display_name) {
              locationLabel = String(payload.display_name);
            }
          }
        } catch (_error) {
          // Keep coordinate-based label when reverse lookup is unavailable.
        }

        setFormState((previous) => ({
          ...previous,
          latitude,
          longitude,
          location: locationLabel
        }));
        setLocationHint("Address, coordinates, and time auto-filled.");
        setIsDetectingLocation(false);
      },
      (error) => {
        const fallbackMessage =
          error && typeof error === "object" && "code" in error
            ? Number(error.code) === 1
              ? "Location access denied. Please allow location permission."
              : Number(error.code) === 2
                ? "Location unavailable. Try again in a moment."
                : "Location request timed out. Please retry."
            : "Unable to auto-detect location right now.";
        setLocationHint(`${fallbackMessage} Time has been updated.`);
        setIsDetectingLocation(false);
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000
      }
    );
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitMessage({ kind: "idle", text: "" });

    if (!formState.incidentType) {
      setSubmitMessage({
        kind: "error",
        text: "Please select a disaster type."
      });
      return;
    }

    const location = formState.location.trim();
    const summary = formState.summary.trim();
    if (!location || !summary) {
      setSubmitMessage({
        kind: "error",
        text: "Address and description are required."
      });
      return;
    }

    let latitude = null;
    let longitude = null;

    try {
      latitude = parseCoordinate(formState.latitude, "Latitude");
      longitude = parseCoordinate(formState.longitude, "Longitude");
    } catch (error) {
      setSubmitMessage({
        kind: "error",
        text: error.message || "Invalid coordinates."
      });
      return;
    }

    const description = [
      `Disaster Type: ${formState.incidentType}`,
      `Severity: ${SEVERITY_LEVELS[severityIndex]}`,
      `Report Time: ${formState.reportTime || "N/A"}`,
      `Coordinates: ${latitude ?? "N/A"}, ${longitude ?? "N/A"}`,
      "",
      summary
    ].join("\n");

    const payload = new FormData();
    payload.append("disaster_type", formState.incidentType);
    payload.append("description", description);
    payload.append("address_text", location);

    if (latitude !== null) {
      payload.append("latitude", String(latitude));
    }
    if (longitude !== null) {
      payload.append("longitude", String(longitude));
    }

    if (mediaFile) {
      payload.append("media", mediaFile);
      if (mediaType) {
        payload.append("media_type", mediaType);
      }
    }

    setIsSubmitting(true);

    try {
      const response = await apiRequest("/report-disaster", {
        method: "POST",
        body: payload
      });

      const successText =
        response && typeof response === "object" && "message" in response
          ? String(response.message)
          : "Disaster report submitted successfully.";

      setSubmitMessage({ kind: "success", text: successText });
      setFormState({
        incidentType: "",
        reportTime: toLocalDatetimeValue(new Date()),
        location: "",
        latitude: "",
        longitude: "",
        summary: ""
      });
      setMediaType("");
      setSeverityIndex(0);
      clearMediaSelection();
    } catch (error) {
      if (
        error &&
        typeof error === "object" &&
        "status" in error &&
        error.status === 401
      ) {
        setSubmitMessage({
          kind: "error",
          text: "Please sign in to submit a report."
        });
        window.setTimeout(() => {
          navigate("/login");
        }, 700);
      } else {
        setSubmitMessage({
          kind: "error",
          text:
            error instanceof Error
              ? error.message
              : "Unable to submit report right now."
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={styles.reportPage}>
      <header className={baseStyles["top-nav"]}>
        <div
          className={baseStyles["nav-content"]}
          data-mobile-menu={mobileMenuOpen ? "open" : "closed"}
        >
          <div className={baseStyles["nav-left"]}>
            <Link
              to="/"
              className={baseStyles["logo-container"]}
              style={{ textDecoration: "none" }}
            >
              <img
                src="/logo.png"
                alt="Resqfy Logo"
                className={baseStyles["main-logo"]}
              />
            </Link>
            <nav
              className={baseStyles["nav-links"]}
              id="report-primary-nav"
              onClick={() => setMobileMenuOpen(false)}
            >
              <Link to="/">Home</Link>
              <Link to="/alerts">Alerts</Link>
              <Link to="/report" className={baseStyles.active}>
                Report Incident
              </Link>
              <Link to="/risk-prediction">Risk Prediction</Link>
              <Link to="/outcome-prediction">Outcome Predictor</Link>
              <Link to="/resource-management">Resource Management</Link>
              <Link to="/satellite">Satellite / Geo</Link>
            </nav>
          </div>
          <div className={baseStyles["nav-right"]}>
            <div className={baseStyles["theme-toggle"]}>
              <button
                className={baseStyles["toggle-btn"]}
                data-theme-toggle
                aria-label="Toggle theme"
                type="button"
              >
                <svg
                  className={baseStyles.sun}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <circle cx={12} cy={12} r={5} />
                  <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
                </svg>
                <div className={baseStyles["toggle-track"]}>
                  <div className={baseStyles["toggle-thumb"]} />
                </div>
                <svg
                  className={baseStyles.moon}
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              </button>
            </div>
            <button
              className={baseStyles["mobile-menu-btn"]}
              type="button"
              aria-label="Toggle navigation menu"
              aria-controls="report-primary-nav"
              aria-expanded={mobileMenuOpen}
              onClick={() => setMobileMenuOpen((open) => !open)}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
              >
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
            <Link
              to="/profile"
              className={baseStyles["user-profile"]}
              style={{ textDecoration: "none" }}
            >
              <img
                src="/profile-icon.svg"
                alt="User profile"
                className={baseStyles.avatar}
              />
              <div className={baseStyles["user-info"]}>
                <span className={baseStyles.name}>
                  {getUserFirstName(sessionUser)}
                </span>
              </div>
              <svg
                className={baseStyles.chevron}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </Link>
          </div>
        </div>
      </header>

      <div className={`${baseStyles["dashboard-container"]} ${styles.pageWrap}`}>
        <main className={styles.formShell}>
          <div className={styles.formOuterBox}>
            <form className={styles.reportForm} onSubmit={handleSubmit}>
              <input
                name="reportTime"
                type="hidden"
                value={formState.reportTime}
                readOnly
              />

              <section className={styles.sectionCard}>
                <h2 className={styles.sectionTitle}>Incident Report</h2>
                <label className={styles.field}>
                  <span>Disaster Type *</span>
                  <select
                    name="incidentType"
                    value={formState.incidentType}
                    onChange={updateField}
                  >
                    <option value="">Select a disaster type</option>
                    {INCIDENT_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                </label>

                <div className={styles.severityStrip}>
                  <div className={styles.severityStripHead}>
                    <span>
                      Severity: <strong>{SEVERITY_LEVELS[severityIndex]}</strong>
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max={SEVERITY_LEVELS.length - 1}
                    step="1"
                    value={severityIndex}
                    onInput={handleSeverityInput}
                    onChange={handleSeverityInput}
                    className={styles.severitySlider}
                    style={{
                      "--severity-progress": `${
                        (severityIndex / (SEVERITY_LEVELS.length - 1)) * 100
                      }%`,
                      "--severity-thumb": severityTone
                    }}
                    aria-label="Severity from watch to emergency"
                    aria-valuetext={SEVERITY_LEVELS[severityIndex]}
                  />
                  <div className={styles.severityEnds}>
                    <span>Watch</span>
                    <span>Emergency</span>
                  </div>
                  <p className={styles.severityHintLine}>
                    Drag the slider to set severity priority.
                  </p>
                </div>

                <label className={styles.field}>
                  <span>Description *</span>
                  <textarea
                    name="summary"
                    rows={5}
                    value={formState.summary}
                    onChange={updateField}
                    placeholder="Describe impact, intensity, and affected area..."
                  />
                </label>
                <p className={styles.helperText}>Add useful details for responders.</p>
              </section>

              <section className={styles.sectionCard}>
                <h2 className={styles.sectionTitle}>Location</h2>
                <label className={styles.field}>
                  <span>Location/Address *</span>
                  <div className={styles.inputWithAction}>
                    <input
                      className={styles.addressInput}
                      name="location"
                      type="text"
                      value={formState.location}
                      onChange={updateField}
                      placeholder="Street, district, or nearest landmark"
                    />
                    <button
                      type="button"
                      className={styles.mapActionBtn}
                      onClick={handleAutoDetectLocation}
                      aria-label="Auto-fill address from current location"
                      title="Auto-fill address"
                      disabled={isDetectingLocation}
                    >
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M12 21s-6-4.35-6-10a6 6 0 1 1 12 0c0 5.65-6 10-6 10z" />
                        <circle cx={12} cy={11} r={2.5} />
                      </svg>
                    </button>
                  </div>
                </label>

                <div className={styles.locationMetaRow}>
                  <button
                    type="button"
                    className={styles.locationDetectBtn}
                    onClick={handleAutoDetectLocation}
                    disabled={isDetectingLocation}
                  >
                    {isDetectingLocation ? "Detecting Location..." : "Use Current Location"}
                  </button>
                  <span className={styles.captureMeta}>
                    {isDetectingLocation ? "Capturing..." : "Captured • ±35m"}
                  </span>
                </div>

                <div className={styles.coordGrid}>
                  <label className={styles.field}>
                    <span>Latitude *</span>
                    <input
                      name="latitude"
                      type="text"
                      value={formState.latitude}
                      onChange={updateField}
                      inputMode="decimal"
                    />
                  </label>
                  <label className={styles.field}>
                    <span>Longitude *</span>
                    <input
                      name="longitude"
                      type="text"
                      value={formState.longitude}
                      onChange={updateField}
                      inputMode="decimal"
                    />
                  </label>
                </div>

                {locationHint ? (
                  <small className={styles.locationHint}>{locationHint}</small>
                ) : null}
              </section>

              <section className={styles.sectionCard}>
                <h2 className={styles.sectionTitle}>Media (Optional)</h2>
                <div className={styles.mediaGrid}>
                  <label className={styles.field}>
                    <span>Media Type</span>
                    <select
                      value={mediaType}
                      onChange={(event) => {
                        setMediaType(event.target.value);
                        clearMediaSelection();
                      }}
                    >
                      <option value="">Select media type</option>
                      {MEDIA_TYPES.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className={styles.field}>
                    <span>Upload</span>
                    <input
                      ref={mediaInputRef}
                      type="file"
                      className={styles.fileInput}
                      accept={
                        mediaType === "image"
                          ? "image/*"
                          : mediaType === "video"
                            ? "video/*"
                            : mediaType === "audio"
                              ? "audio/*"
                              : mediaType === "document"
                                ? ".pdf,.doc,.docx,.txt,.csv,.xlsx,.xls"
                                : "*/*"
                      }
                      onChange={handleMediaPick}
                    />
                  </label>
                </div>
                <p className={styles.helperText}>Choose media type before file upload.</p>
                {mediaFile ? (
                  <p className={styles.fileMeta}>
                    Selected file: <strong>{mediaFile.name}</strong>
                  </p>
                ) : null}
              </section>

              {submitMessage.text ? (
                <p
                  className={`${styles.submitMessage} ${
                    submitMessage.kind === "success"
                      ? styles.successMessage
                      : submitMessage.kind === "error"
                        ? styles.errorMessage
                        : styles.infoMessage
                  }`}
                >
                  {submitMessage.text}
                </p>
              ) : null}

              <div className={styles.actionsSingle}>
                <button
                  className={styles.submitReportBtn}
                  type="submit"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "Submitting..." : "Submit Disaster Report"}
                </button>
              </div>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}
