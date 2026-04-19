import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import styles from "/ngos.module.css";

const DEFAULT_LOCATION = {
  lat: 28.6139,
  lon: 77.209,
  label: "Delhi"
};

function formatDistance(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "N/A";
  }
  return `${number.toFixed(number >= 10 ? 1 : 2)} km`;
}

function normalizeWebsite(url) {
  const text = String(url || "").trim();
  if (!text || text.toLowerCase() === "not available") {
    return "";
  }
  if (text.startsWith("http://") || text.startsWith("https://")) {
    return text;
  }
  return `https://${text}`;
}

function toPhoneHref(phone) {
  const digits = String(phone || "").replace(/[^\d+]/g, "");
  if (!digits) {
    return "";
  }
  return `tel:${digits}`;
}

export default function NgosPage() {
  const [coords, setCoords] = useState(DEFAULT_LOCATION);
  const [ngos, setNgos] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [error, setError] = useState("");

  const locationText = useMemo(
    () => `Using ${coords.label}: ${coords.lat.toFixed(4)}, ${coords.lon.toFixed(4)}`,
    [coords]
  );

  const fetchNearbyNgos = async (lat, lon, label) => {
    setIsLoading(true);
    setError("");
    try {
      const url = `/api/live-ngos?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(
        lon
      )}&radius=120000`;
      const response = await fetch(url, {
        headers: { Accept: "application/json" }
      });
      if (!response.ok) {
        throw new Error(`Unable to load NGOs (${response.status})`);
      }
      const payload = await response.json();
      const items = Array.isArray(payload) ? payload : [];
      const sorted = [...items].sort(
        (a, b) => Number(a?.distance_km || 99999) - Number(b?.distance_km || 99999)
      );
      setCoords({ lat, lon, label });
      setNgos(sorted.slice(0, 20));
      if (sorted.length === 0) {
        setError("No nearby NGOs found for this location right now.");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load NGO list.";
      setError(message);
      setNgos([]);
    } finally {
      setIsLoading(false);
    }
  };

  const useDefaultLocation = () => {
    fetchNearbyNgos(DEFAULT_LOCATION.lat, DEFAULT_LOCATION.lon, DEFAULT_LOCATION.label);
  };

  const useCurrentLocation = () => {
    if (!navigator.geolocation) {
      setError("Geolocation is not supported in this browser.");
      return;
    }
    setIsDetecting(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = Number(position.coords?.latitude);
        const lon = Number(position.coords?.longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
          setError("Unable to detect location coordinates.");
          setIsDetecting(false);
          return;
        }
        fetchNearbyNgos(lat, lon, "Current Location");
        setIsDetecting(false);
      },
      () => {
        setError("Location permission denied. Using default Delhi location.");
        setIsDetecting(false);
        useDefaultLocation();
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 120000 }
    );
  };

  return (
    <div className={styles.page}>
      <div className={styles.phoneShell}>
        <div className={styles.topNotch} />

        <div className={styles.controls}>
          <button
            type="button"
            onClick={useCurrentLocation}
            disabled={isDetecting || isLoading}
            className={styles.primaryBtn}
          >
            {isDetecting ? "Detecting..." : "Use GPS"}
          </button>
          <button
            type="button"
            onClick={useDefaultLocation}
            disabled={isLoading}
            className={styles.ghostBtn}
          >
            Use Default (Delhi)
          </button>
        </div>

        <p className={styles.locationText}>{locationText}</p>

        <div className={styles.list}>
          {isLoading ? <div className={styles.infoCard}>Loading nearby NGOs...</div> : null}
          {error ? <div className={styles.errorCard}>{error}</div> : null}

          {!isLoading &&
            !error &&
            ngos.map((ngo) => {
              const website = normalizeWebsite(ngo?.website);
              const phoneHref = toPhoneHref(ngo?.phone);
              const routeHref = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(
                `${ngo?.lat},${ngo?.lon}`
              )}`;
              const typeText = String(ngo?.type || "NGO").toUpperCase();
              const isRegional = (ngo?.distance_km || 0) > 30;

              return (
                <article key={`${ngo?.name}-${ngo?.lat}-${ngo?.lon}`} className={styles.card}>
                  <div className={styles.cardHead}>
                    <div>
                      <h3>{ngo?.name || "Nearby NGO"}</h3>
                      <div className={styles.badges}>
                        <span className={styles.badgeBlue}>{typeText}</span>
                        {isRegional ? <span className={styles.badgeAmber}>REGIONAL</span> : null}
                      </div>
                    </div>
                    <a
                      href={phoneHref || "#"}
                      className={styles.callIcon}
                      aria-label={`Call ${ngo?.name || "NGO"}`}
                      onClick={(event) => {
                        if (!phoneHref) {
                          event.preventDefault();
                        }
                      }}
                    >
                      ☎
                    </a>
                  </div>

                  <div className={styles.metrics}>
                    <div>
                      <span>Distance</span>
                      <strong>{formatDistance(ngo?.distance_km)}</strong>
                    </div>
                    <div>
                      <span>Estimated Time</span>
                      <strong>{ngo?.estimated_duration || "N/A"}</strong>
                    </div>
                  </div>

                  <div className={styles.details}>
                    <p>📍 {ngo?.address || "Support address not available"}</p>
                    <p>
                      🗺 Coverage:{" "}
                      {Array.isArray(ngo?.areas) && ngo.areas.length
                        ? ngo.areas.slice(0, 2).join(", ")
                        : "Nearby districts"}
                    </p>
                    <p>📞 {ngo?.phone || "Not available"}</p>
                    <p>✉ {ngo?.email || "Not available"}</p>
                    {website ? (
                      <p>
                        🌐{" "}
                        <a href={website} target="_blank" rel="noreferrer">
                          Visit website
                        </a>
                      </p>
                    ) : null}
                  </div>

                  <div className={styles.actions}>
                    <a
                      href={phoneHref || "#"}
                      className={styles.callBtn}
                      onClick={(event) => {
                        if (!phoneHref) {
                          event.preventDefault();
                        }
                      }}
                    >
                      Call
                    </a>
                    <a href={routeHref} target="_blank" rel="noreferrer" className={styles.routeBtn}>
                      Route
                    </a>
                  </div>
                </article>
              );
            })}
        </div>

        <div className={styles.bottomBar}>
          <Link to="/" className={styles.bottomItem} aria-label="Home">
            ⌂
          </Link>
          <Link to="/sos" className={`${styles.bottomItem} ${styles.sos}`} aria-label="SOS">
            SOS
          </Link>
          <button type="button" className={styles.bottomItem} aria-label="Menu">
            ☰
          </button>
        </div>
      </div>
    </div>
  );
}

