import React, { useEffect, useMemo, useRef, useState } from "react";
import baseStyles from "/styles.module.css";
import pageStyles from "/home.module.css";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { cx } from "../utils/cx.js";
import { apiRequest } from "../utils/api.js";
import {
  fetchSessionUser,
  getUserFirstName
} from "../utils/session.js";
import "leaflet/dist/leaflet.css";

const c = (classNames) => cx(classNames, baseStyles, pageStyles);
const INDIA_BOUNDS = {
  minLat: 7.2,
  maxLat: 36.9,
  minLon: 68.1,
  maxLon: 97.3
};
const INDIA_MAP_BOUNDS = [
  [INDIA_BOUNDS.minLat, INDIA_BOUNDS.minLon],
  [INDIA_BOUNDS.maxLat, INDIA_BOUNDS.maxLon]
];
let leafletLoaderPromise = null;
const LOCATION_STORAGE_KEY = "resqfy:home:selected-region";
const LOCATION_COORD_STORAGE_KEY = "resqfy:home:user-coordinates";
const REGIONAL_ALERTS_PAGE_SIZE = 2;
const MIN_MAP_ZOOM = 2;
const MAX_MAP_ZOOM = 12;
const INDIA_FULL_VIEW_ZOOM = 5;
const GLOBAL_VIEW_ZOOM = 2;
const INDIA_STATES_GEOJSON_URL =
  "https://raw.githubusercontent.com/geohacker/india/master/state/india_state.geojson";
const REGION_OPTIONS = [
  { value: "india", label: "India", mode: "coverage" },
  { value: "international", label: "International", mode: "coverage" },
  { value: "andhra pradesh", label: "Andhra Pradesh", mode: "state" },
  { value: "arunachal pradesh", label: "Arunachal Pradesh", mode: "state" },
  { value: "assam", label: "Assam", mode: "state" },
  { value: "bihar", label: "Bihar", mode: "state" },
  { value: "chhattisgarh", label: "Chhattisgarh", mode: "state" },
  { value: "goa", label: "Goa", mode: "state" },
  { value: "gujarat", label: "Gujarat", mode: "state" },
  { value: "delhi", label: "Delhi", mode: "state" },
  { value: "haryana", label: "Haryana", mode: "state" },
  { value: "himachal pradesh", label: "Himachal Pradesh", mode: "state" },
  { value: "jharkhand", label: "Jharkhand", mode: "state" },
  { value: "karnataka", label: "Karnataka", mode: "state" },
  { value: "kerala", label: "Kerala", mode: "state" },
  { value: "madhya pradesh", label: "Madhya Pradesh", mode: "state" },
  { value: "maharashtra", label: "Maharashtra", mode: "state" },
  { value: "manipur", label: "Manipur", mode: "state" },
  { value: "meghalaya", label: "Meghalaya", mode: "state" },
  { value: "mizoram", label: "Mizoram", mode: "state" },
  { value: "nagaland", label: "Nagaland", mode: "state" },
  { value: "odisha", label: "Odisha", mode: "state" },
  { value: "punjab", label: "Punjab", mode: "state" },
  { value: "rajasthan", label: "Rajasthan", mode: "state" },
  { value: "sikkim", label: "Sikkim", mode: "state" },
  { value: "tamil nadu", label: "Tamil Nadu", mode: "state" },
  { value: "telangana", label: "Telangana", mode: "state" },
  { value: "tripura", label: "Tripura", mode: "state" },
  { value: "uttar pradesh", label: "Uttar Pradesh", mode: "state" },
  { value: "uttarakhand", label: "Uttarakhand", mode: "state" },
  { value: "west bengal", label: "West Bengal", mode: "state" }
];
const REGION_FILTER_EXEMPT = new Set(["", "all", "india", "international"]);
const REGION_VIEWPORTS = {
  india: { center: [22.9734, 78.6569], zoom: 5 },
  international: { center: [22.9734, 78.6569], zoom: 3.25 },
  "andhra pradesh": { center: [15.9129, 79.74], zoom: 7 },
  "arunachal pradesh": { center: [28.218, 94.7278], zoom: 7 },
  assam: { center: [26.2006, 92.9376], zoom: 7 },
  bihar: { center: [25.0961, 85.3131], zoom: 7 },
  chhattisgarh: { center: [21.2787, 81.8661], zoom: 7 },
  goa: { center: [15.2993, 74.124], zoom: 9 },
  gujarat: { center: [22.2587, 71.1924], zoom: 7 },
  delhi: { center: [28.6139, 77.209], zoom: 9 },
  haryana: { center: [29.0588, 76.0856], zoom: 7 },
  "himachal pradesh": { center: [31.1048, 77.1734], zoom: 7 },
  jharkhand: { center: [23.6102, 85.2799], zoom: 7 },
  karnataka: { center: [15.3173, 75.7139], zoom: 7 },
  kerala: { center: [10.8505, 76.2711], zoom: 7 },
  "madhya pradesh": { center: [22.9734, 78.6569], zoom: 7 },
  maharashtra: { center: [19.7515, 75.7139], zoom: 7 },
  manipur: { center: [24.6637, 93.9063], zoom: 8 },
  meghalaya: { center: [25.467, 91.3662], zoom: 8 },
  mizoram: { center: [23.1645, 92.9376], zoom: 8 },
  nagaland: { center: [26.1584, 94.5624], zoom: 8 },
  odisha: { center: [20.9517, 85.0985], zoom: 7 },
  punjab: { center: [31.1471, 75.3412], zoom: 7 },
  rajasthan: { center: [27.0238, 74.2179], zoom: 7 },
  sikkim: { center: [27.533, 88.5122], zoom: 8 },
  "tamil nadu": { center: [11.1271, 78.6569], zoom: 7 },
  telangana: { center: [18.1124, 79.0193], zoom: 7 },
  tripura: { center: [23.9408, 91.9882], zoom: 8 },
  "uttar pradesh": { center: [26.8467, 80.9462], zoom: 7 },
  uttarakhand: { center: [30.0668, 79.0193], zoom: 7 },
  "west bengal": { center: [22.9868, 87.855], zoom: 7 }
};
const REGION_ALIASES = {
  delhi: ["new delhi", "nct", "nct delhi", "national capital territory of delhi"],
  odisha: ["orissa"],
  "west bengal": ["bengal"],
  international: ["global", "outside india"]
};
const ALERT_SOURCE_REGION_HINTS = {
  bhubaneswar: "odisha",
  guwahati: "assam",
  kolkata: "west bengal",
  lucknow: "uttar pradesh",
  ranchi: "jharkhand",
  mumbai: "maharashtra",
  gangtok: "sikkim",
  jaipur: "rajasthan",
  chennai: "tamil nadu",
  hyderabad: "telangana",
  bengaluru: "karnataka",
  bangalore: "karnataka",
  thiruvananthapuram: "kerala",
  trivandrum: "kerala",
  ahmedabad: "gujarat",
  delhi: "delhi",
  "new delhi": "delhi",
  chandigarh: "punjab",
  shimla: "himachal pradesh",
  dehradun: "uttarakhand",
  bhopal: "madhya pradesh",
  patna: "bihar",
  agartala: "tripura",
  imphal: "manipur",
  aizawl: "mizoram",
  kohima: "nagaland",
  shillong: "meghalaya",
  itanagar: "arunachal pradesh",
  panaji: "goa"
};
const DISTRICT_REGION_HINTS = {
  bajali: "assam",
  baksa: "assam",
  barpeta: "assam",
  bongaigaon: "assam",
  chirang: "assam",
  goalpara: "assam",
  kokrajhar: "assam",
  sonitpur: "assam",
  nalbari: "assam",
  udalguri: "assam",
  kamrup: "assam",
  dibrugarh: "assam",
  tinsukia: "assam",
  dhemaji: "assam"
};
const MAP_VIEW_MODES = {
  street: "m",
  terrain: "p"
};
const THREAT_MATRIX_ROW_ORDER = [
  "Flood",
  "Earthquake",
  "Wildfire",
  "Cyclone",
  "Landslide",
  "Heatwave",
  "Thunder\nStorm"
];

function getRegionOption(value) {
  return REGION_OPTIONS.find((option) => option.value === value) || REGION_OPTIONS[0];
}

function buildGoogleTileLayer(L, mapMode) {
  const layerMode = MAP_VIEW_MODES[mapMode] || MAP_VIEW_MODES.street;
  return L.tileLayer(
    `https://{s}.google.com/vt/lyrs=${layerMode}&x={x}&y={y}&z={z}&hl=en&gl=IN`,
    {
      maxZoom: 20,
      minZoom: 1,
      subdomains: ["mt0", "mt1", "mt2", "mt3"]
    }
  );
}

function buildMapAlertsPath(regionValue) {
  const params = new URLSearchParams({
    state: getRegionOption(regionValue).label,
    limit: "220",
    scope: "expanded",
    source_policy: "auto_fallback",
    active_only: "true",
    lang: "en"
  });
  return `/mobile/live-alerts?${params.toString()}`;
}

function getRegionViewport(regionValue) {
  return REGION_VIEWPORTS[regionValue] || REGION_VIEWPORTS.india;
}

function normalizeRegionName(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function regionFeatureName(feature) {
  const props = feature?.properties || {};
  return (
    props?.st_nm ||
    props?.ST_NM ||
    props?.name ||
    props?.NAME ||
    props?.NAME_1 ||
    ""
  );
}

function approximateBoundsFromViewport(viewport) {
  const [lat, lon] = viewport.center || REGION_VIEWPORTS.india.center;
  const zoom = Number(viewport.zoom) || 6;
  const latSpan = Math.max(1.2, 9.6 - zoom * 0.95);
  const lonSpan = latSpan * 1.25;
  return [
    [lat - latSpan, lon - lonSpan],
    [lat + latSpan, lon + lonSpan]
  ];
}

function isInsideBounds(lat, lon, bounds) {
  if (!bounds) {
    return false;
  }
  const [[minLat, minLon], [maxLat, maxLon]] = bounds;
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lon) &&
    lat >= minLat &&
    lat <= maxLat &&
    lon >= minLon &&
    lon <= maxLon
  );
}

function clampValue(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function buildOverlayPinsFromBounds(alerts, bounds) {
  if (!Array.isArray(alerts) || alerts.length === 0 || !bounds) {
    return [];
  }

  const latSpan = Math.max(0.0001, bounds.maxLat - bounds.minLat);
  const lonSpan = Math.max(0.0001, bounds.maxLon - bounds.minLon);
  const latPadding = latSpan * 0.035;
  const lonPadding = lonSpan * 0.035;
  const occupied = new Set();

  return alerts
    .slice(0, 24)
    .map((alert, index) => {
      const lat = Number(alert?.lat);
      const lon = Number(alert?.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        return null;
      }

      if (
        lat < bounds.minLat - latPadding ||
        lat > bounds.maxLat + latPadding ||
        lon < bounds.minLon - lonPadding ||
        lon > bounds.maxLon + lonPadding
      ) {
        return null;
      }

      let left = ((lon - bounds.minLon) / lonSpan) * 100;
      let top = ((bounds.maxLat - lat) / latSpan) * 100;
      left = clampValue(left, 3.5, 96.5);
      top = clampValue(top, 4, 95);

      const occupiedKey = `${Math.round(left / 3)}:${Math.round(top / 3)}`;
      if (occupied.has(occupiedKey)) {
        left = clampValue(left + ((index % 3) - 1) * 1.8, 3.5, 96.5);
        top = clampValue(top + ((index % 5) - 2) * 1.35, 4, 95);
      }
      occupied.add(`${Math.round(left / 3)}:${Math.round(top / 3)}`);

      const tone = mapAlertTone(alert);
      const background =
        tone === "critical" ? "#ef4444" : tone === "warning" ? "#f59f00" : "#facc15";
      const iconFill = tone === "critical" ? "#ffffff" : "#111827";

      return {
        id: alert?.id || `overlay-${index}`,
        label: mapAlertLabel(alert),
        style: {
          left: `${left}%`,
          top: `${top}%`,
          background
        },
        iconMarkup: disasterIconSvg(inferDisasterIconKind(alert), iconFill)
      };
    })
    .filter(Boolean);
}

function hashSeed(input) {
  const text = String(input || "seed");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash << 5) - hash + text.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
}

function parseAlertCoordinates(alert) {
  const candidatePairs = [
    [alert?.lat, alert?.lon],
    [alert?.latitude, alert?.longitude],
    [alert?.location?.lat, alert?.location?.lon],
    [alert?.location?.latitude, alert?.location?.longitude],
    [alert?.coordinates?.lat, alert?.coordinates?.lon],
    [alert?.coordinates?.latitude, alert?.coordinates?.longitude]
  ];

  for (const [rawLat, rawLon] of candidatePairs) {
    const lat = Number(rawLat);
    const lon = Number(rawLon);
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      return { lat, lon, approximated: false };
    }
  }
  return null;
}

function inferAlertRegionValue(alert) {
  const blob = normalizeRegionName(
    `${alert?.area || ""} ${alert?.message || ""} ${alert?.type || ""} ${alert?.source || ""}`
  );
  if (!blob) {
    return null;
  }

  const matchedState = REGION_OPTIONS.find(
    (option) => option.mode === "state" && blob.includes(normalizeRegionName(option.label))
  );
  if (matchedState) {
    return matchedState.value;
  }

  for (const [keyword, stateValue] of Object.entries(ALERT_SOURCE_REGION_HINTS)) {
    if (blob.includes(keyword)) {
      return stateValue;
    }
  }

  for (const [keyword, stateValue] of Object.entries(DISTRICT_REGION_HINTS)) {
    if (blob.includes(keyword)) {
      return stateValue;
    }
  }

  return null;
}

function createApproximateAlertPoint(alert, selectedRegionValue, selectedRegionViewport) {
  const inferredRegionValue = inferAlertRegionValue(alert);
  const inferredViewport = inferredRegionValue
    ? getRegionViewport(inferredRegionValue)
    : null;
  const anchorViewport = inferredViewport || selectedRegionViewport || REGION_VIEWPORTS.india;
  const [anchorLat, anchorLon] = anchorViewport.center || REGION_VIEWPORTS.india.center;

  let latSpread = 0.55;
  let lonSpread = 0.8;

  if (selectedRegionValue === "international") {
    latSpread = inferredViewport ? 1.2 : 20;
    lonSpread = inferredViewport ? 1.8 : 30;
  } else if (selectedRegionValue === "india") {
    latSpread = inferredViewport ? 0.45 : 3.2;
    lonSpread = inferredViewport ? 0.65 : 4.4;
  } else if (selectedRegionValue === inferredRegionValue) {
    latSpread = 0.32;
    lonSpread = 0.46;
  }

  const seed = hashSeed(
    `${alert?.id || ""}|${alert?.type || ""}|${alert?.area || ""}|${alert?.source || ""}|${alert?.start_time || ""}`
  );
  const latNoise = ((seed % 2001) - 1000) / 1000;
  const lonNoise = (((Math.floor(seed / 2003) % 2001) - 1000) / 1000);

  let lat = anchorLat + latNoise * latSpread;
  let lon = anchorLon + lonNoise * lonSpread;

  if (selectedRegionValue !== "international" || inferredViewport) {
    lat = clampValue(lat, INDIA_BOUNDS.minLat + 0.35, INDIA_BOUNDS.maxLat - 0.35);
    lon = clampValue(lon, INDIA_BOUNDS.minLon + 0.35, INDIA_BOUNDS.maxLon - 0.35);
  }

  if (inferredViewport) {
    const [[minLat, minLon], [maxLat, maxLon]] =
      approximateBoundsFromViewport(inferredViewport);
    lat = clampValue(lat, minLat, maxLat);
    lon = clampValue(lon, minLon, maxLon);
  }

  return { lat, lon, approximated: true, inferredRegionValue };
}

function resolvePinnedAlertPoint(alert, selectedRegionValue, selectedRegionViewport) {
  const inferredRegionValue = inferAlertRegionValue(alert);
  const inferredViewport = inferredRegionValue
    ? getRegionViewport(inferredRegionValue)
    : null;
  const exactPoint = parseAlertCoordinates(alert);
  if (exactPoint) {
    if (selectedRegionValue === "international") {
      return exactPoint;
    }
    if (selectedRegionValue === "india") {
      const matchesInferredViewport = inferredViewport
        ? isInsideBounds(
            exactPoint.lat,
            exactPoint.lon,
            approximateBoundsFromViewport(inferredViewport)
          )
        : true;
      if (isInsideIndia(exactPoint.lat, exactPoint.lon) && matchesInferredViewport) {
        return exactPoint;
      }
    } else {
      const viewportBounds = approximateBoundsFromViewport(
        selectedRegionViewport || REGION_VIEWPORTS.india
      );
      if (isInsideBounds(exactPoint.lat, exactPoint.lon, viewportBounds)) {
        return exactPoint;
      }
    }
  }

  return createApproximateAlertPoint(
    alert,
    selectedRegionValue,
    selectedRegionViewport
  );
}

function alertMatchesSelectedRegion(alert, regionValue) {
  if (REGION_FILTER_EXEMPT.has(regionValue)) {
    return true;
  }
  const blob = `${alert?.type || ""} ${alert?.category || ""} ${alert?.area || ""} ${alert?.message || ""} ${alert?.source || ""}`
    .toLowerCase()
    .replace(/&/g, " and ");
  if (blob.includes(regionValue)) {
    return true;
  }
  const aliases = REGION_ALIASES[regionValue] || [];
  return aliases.some((term) => blob.includes(term));
}

function isInsideIndia(lat, lon) {
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lon) &&
    lat >= INDIA_BOUNDS.minLat &&
    lat <= INDIA_BOUNDS.maxLat &&
    lon >= INDIA_BOUNDS.minLon &&
    lon <= INDIA_BOUNDS.maxLon
  );
}

function distanceKm(lat1, lon1, lat2, lon2) {
  const toRad = (value) => (value * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) *
      Math.cos(toRad(lat2)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return earthRadiusKm * c;
}

function resolveRegionFromCoordinatesFallback(lat, lon) {
  if (!isInsideIndia(lat, lon)) {
    return "international";
  }

  const stateOptions = REGION_OPTIONS.filter((option) => option.mode === "state");
  let closestState = "india";
  let closestDistance = Number.POSITIVE_INFINITY;

  stateOptions.forEach((state) => {
    const viewport = REGION_VIEWPORTS[state.value];
    if (!viewport || !Array.isArray(viewport.center)) {
      return;
    }
    const [stateLat, stateLon] = viewport.center;
    const distance = distanceKm(lat, lon, stateLat, stateLon);
    if (distance < closestDistance) {
      closestDistance = distance;
      closestState = state.value;
    }
  });

  return closestState;
}

function matchStateRegionFromText(value) {
  const normalized = normalizeRegionName(value);
  if (!normalized) {
    return "";
  }

  const directMatch = REGION_OPTIONS.find(
    (option) =>
      option.mode === "state" &&
      normalizeRegionName(option.label) === normalized
  );
  if (directMatch) {
    return directMatch.value;
  }

  const containedMatch = REGION_OPTIONS.find(
    (option) =>
      option.mode === "state" &&
      normalized.includes(normalizeRegionName(option.label))
  );
  if (containedMatch) {
    return containedMatch.value;
  }

  return "";
}

async function resolveRegionFromCoordinates(lat, lon) {
  if (!isInsideIndia(lat, lon)) {
    return "international";
  }

  try {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 3500);
    const response = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}`,
      {
        signal: controller.signal,
        headers: { Accept: "application/json" }
      }
    );
    window.clearTimeout(timeoutId);

    if (response.ok) {
      const payload = await response.json();
      const address = payload?.address || {};
      const candidates = [
        address.state,
        address.state_district,
        address.region,
        address.county,
        payload?.display_name
      ];
      for (const candidate of candidates) {
        const matchedRegion = matchStateRegionFromText(candidate);
        if (matchedRegion) {
          return matchedRegion;
        }
      }
    }
  } catch (_error) {
    // Fall through to deterministic center-distance fallback.
  }

  return resolveRegionFromCoordinatesFallback(lat, lon);
}

function ensureLeafletLoaded() {
  if (leafletLoaderPromise) {
    return leafletLoaderPromise;
  }
  leafletLoaderPromise = import("leaflet").then(
    (leafletModule) => leafletModule.default || leafletModule
  );
  return leafletLoaderPromise;
}

function inferDisasterIconKind(alert) {
  const blob = `${alert?.type || ""} ${alert?.category || ""} ${alert?.message || ""}`.toLowerCase();
  if (blob.includes("fire") || blob.includes("heat")) {
    return "fire";
  }
  if (
    blob.includes("thunder") ||
    blob.includes("lightning") ||
    blob.includes("storm") ||
    blob.includes("rain")
  ) {
    return "storm";
  }
  if (blob.includes("earthquake") || blob.includes("seismic")) {
    return "quake";
  }
  if (blob.includes("landslide")) {
    return "landslide";
  }
  if (blob.includes("flood") || blob.includes("cyclone")) {
    return "water";
  }
  return "hazard";
}

function disasterIconSvg(kind, fillColor) {
  if (kind === "storm") {
    return `<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><path fill="${fillColor}" d="M13.2 2 4.1 13.5h6.1L9 22l10.9-13h-6.1L15 2z"/></svg>`;
  }
  if (kind === "water") {
    return `<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><path fill="${fillColor}" d="M12 2c2.8 3.4 6 7.1 6 11a6 6 0 1 1-12 0c0-3.9 3.2-7.6 6-11zm0 13.3a2.9 2.9 0 0 0 2.9-2.8c0-1.1-.7-2.4-2.9-4.9-2.2 2.5-2.9 3.8-2.9 4.9a2.9 2.9 0 0 0 2.9 2.8z"/></svg>`;
  }
  if (kind === "fire") {
    return `<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><path fill="${fillColor}" d="M13.6 2.3c1.2 3.2-.4 4.9-1.9 6.4-1.1 1.1-2 2.1-1.8 3.6 1.1-.6 1.8-1.5 2.1-2.7 2.7 2.1 4.2 4 4.2 6.5A6.2 6.2 0 0 1 10 22c-3.2 0-5.8-2.6-5.8-5.8 0-2.4 1.2-4.5 3.9-6.8-.1 1.7.5 2.9 1.6 3.9.2-2.2 1.2-3.6 2.3-4.8 1.5-1.7 2.9-3.3 1.6-6.2z"/></svg>`;
  }
  if (kind === "quake") {
    return `<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><path fill="${fillColor}" d="M4 13.5h3.1l1.4-3.4 2.1 6.7 1.9-4.5H20v2h-6.3l-2.6 6.1-2-6.3-0.6 1.4H4zM6.6 3.8l1.4 1.4-2 2L4.6 5.8zm11.9 0 2 2-1.4 1.4-2-2z"/></svg>`;
  }
  if (kind === "landslide") {
    return `<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><path fill="${fillColor}" d="M3 18h18v2H3zm5.2-8 2.8 3.6 2-2.2L16.8 16H6.2zM14 5l2 2-1.4 1.4-2-2z"/></svg>`;
  }
  return `<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><path fill="${fillColor}" d="M11 2h2v6l4 2-1 2-4-2-4 2-1-2 4-2V2zm1 8a6.8 6.8 0 1 1 0 13.6A6.8 6.8 0 0 1 12 10zm0 3a3.8 3.8 0 1 0 0 7.6A3.8 3.8 0 0 0 12 13z"/></svg>`;
}

function buildLeafletAlertIcon(L, alert) {
  const tone = mapAlertTone(alert);
  const severityColor = String(alert?.severity_color || "").toLowerCase().trim();
  const background =
    severityColor === "green"
      ? "#22c55e"
      : tone === "critical"
        ? "#ef4444"
        : tone === "warning"
          ? "#f59f00"
          : "#facc15";
  const glyphColor = tone === "critical" ? "#ffffff" : "#101827";
  const kind = inferDisasterIconKind(alert);
  const iconMarkup = disasterIconSvg(kind, glyphColor);
  const html = `<div style="width:34px;height:34px;border-radius:50%;background:${background};display:flex;align-items:center;justify-content:center;border:2px solid #ffffff;box-shadow:0 3px 8px rgba(0,0,0,.24);">${iconMarkup}</div>`;

  return L.divIcon({
    className: "",
    html,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -14]
  });
}

function buildLeafletFocusIcon(L) {
  return L.divIcon({
    className: "",
    html: '<div style="width:18px;height:18px;border-radius:50%;background:#38bdf8;border:3px solid #0f172a;box-shadow:0 0 0 6px rgba(56,189,248,0.28);"></div>',
    iconSize: [18, 18],
    iconAnchor: [9, 9]
  });
}

function buildLeafletUserIcon(L) {
  return L.divIcon({
    className: "",
    html: '<div style="width:18px;height:18px;border-radius:50%;background:#2563eb;border:3px solid #0f172a;box-shadow:0 0 0 6px rgba(37,99,235,0.25);"></div>',
    iconSize: [18, 18],
    iconAnchor: [9, 9]
  });
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function buildAlertPopup(alert) {
  const title = escapeHtml(mapAlertLabel(alert));
  const severity = escapeHtml(String(alert?.severity || "WATCH"));
  const source = escapeHtml(String(alert?.source || "Unknown source"));
  const started = escapeHtml(formatMapTime(alert?.start_time));
  const mappedTag = alert?.approximated
    ? '<div style="font-size:11px;color:#64748b;margin-top:4px;">Approximate position</div>'
    : "";
  return `<div style="min-width:180px;font-family:Inter,system-ui,sans-serif;color:#0f172a;"><div style="font-weight:800;margin-bottom:4px;">${title}</div><div style="font-size:12px;"><strong>Severity:</strong> ${severity}</div><div style="font-size:12px;"><strong>Source:</strong> ${source}</div><div style="font-size:12px;"><strong>Start:</strong> ${started}</div>${mappedTag}</div>`;
}

function parseIsoMillis(value) {
  if (!value) {
    return 0;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

function mapAlertTone(alert) {
  const severityColor = String(alert?.severity_color || "").toLowerCase().trim();
  if (severityColor === "red") {
    return "critical";
  }
  if (severityColor === "orange" || severityColor === "amber") {
    return "warning";
  }
  if (severityColor === "yellow" || severityColor === "green") {
    return "watch";
  }
  const severity = String(alert?.severity || "").toLowerCase();
  if (severity === "alert" || severity === "high" || severity === "severe") {
    return "critical";
  }
  if (severity === "warning" || severity === "moderate") {
    return "warning";
  }
  return "watch";
}

function mapAlertLabel(alert) {
  const typeText = String(alert?.type || "Alert").trim() || "Alert";
  const areaText = String(alert?.area || "").trim();
  if (!areaText) {
    return typeText;
  }
  return `${typeText} • ${areaText.split(",")[0].trim()}`;
}

function formatMapTime(value) {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

function formatCardTime(value) {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
}

function mapAlertIntensity(alert) {
  const tone = mapAlertTone(alert);
  if (tone === "critical") {
    return "High Intensity";
  }
  if (tone === "warning") {
    return "Medium Intensity";
  }
  return "Low Intensity";
}

function normalizeThreatMatrixCategoryLabel(value) {
  const category = String(value || "").trim().toLowerCase();
  if (!category) {
    return "";
  }
  if (category === "flood") {
    return "Flood";
  }
  if (category === "earthquake") {
    return "Earthquake";
  }
  if (category === "fire") {
    return "Wildfire";
  }
  if (category === "cyclone" || category === "cyclonic") {
    return "Cyclone";
  }
  if (category === "landslide") {
    return "Landslide";
  }
  if (category === "heat wave" || category === "heatwave") {
    return "Heatwave";
  }
  if (
    category === "thunderstorm" ||
    category === "lightning" ||
    category === "rain"
  ) {
    return "Thunder\nStorm";
  }
  return "";
}

function inferThreatMatrixCategory(alert) {
  const rawTags = Array.isArray(alert?.category_tags) ? alert.category_tags : [];
  const sources = [alert?.category, ...rawTags];
  for (const source of sources) {
    const normalized = normalizeThreatMatrixCategoryLabel(source);
    if (normalized) {
      return normalized;
    }
  }

  const blob = `${alert?.category || ""} ${rawTags.join(" ")} ${alert?.type || ""} ${alert?.message || ""} ${alert?.source || ""}`
    .toLowerCase()
    .trim();

  if (
    blob.includes("earthquake") ||
    blob.includes("seismic") ||
    blob.includes("aftershock") ||
    blob.includes("tremor")
  ) {
    return "Earthquake";
  }
  if (
    blob.includes("cyclone") ||
    blob.includes("cyclonic") ||
    blob.includes("hurricane") ||
    blob.includes("typhoon")
  ) {
    return "Cyclone";
  }
  if (
    blob.includes("landslide") ||
    blob.includes("mudslide") ||
    blob.includes("rockfall")
  ) {
    return "Landslide";
  }
  if (
    blob.includes("heat wave") ||
    blob.includes("heatwave") ||
    blob.includes("extreme heat")
  ) {
    return "Heatwave";
  }
  if (
    blob.includes("fire") ||
    blob.includes("wildfire") ||
    blob.includes("forest fire") ||
    blob.includes("blaze")
  ) {
    return "Wildfire";
  }
  if (
    blob.includes("flood") ||
    blob.includes("inundation") ||
    blob.includes("waterlogging") ||
    blob.includes("dam release") ||
    blob.includes("flash flood")
  ) {
    return "Flood";
  }
  if (
    blob.includes("thunderstorm") ||
    blob.includes("thunderstrom") ||
    blob.includes("thunder") ||
    blob.includes("lightning") ||
    blob.includes("rain") ||
    blob.includes("cloudburst")
  ) {
    return "Thunder\nStorm";
  }
  return "";
}

function shortText(value, maxLength = 56) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

function looksMostlyEnglish(value) {
  const text = String(value || "").trim();
  if (!text) {
    return true;
  }
  let asciiCount = 0;
  for (const character of text) {
    if (character.charCodeAt(0) < 128) {
      asciiCount += 1;
    }
  }
  return asciiCount / Math.max(1, text.length) >= 0.92;
}

function buildRegionalTitle(alert) {
  const candidates = [
    alert?.type_en,
    alert?.type,
    alert?.category,
    alert?.message_en,
    alert?.message
  ];
  for (const candidate of candidates) {
    const cleaned = String(candidate || "")
      .replace(/\b(alert|warning|watch)\b/gi, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!cleaned) {
      continue;
    }
    if (looksMostlyEnglish(cleaned)) {
      return shortText(cleaned, 42);
    }
  }
  return "Weather Alert";
}

function buildRegionalBrief(alert) {
  const area = shortText(alert?.area, 84);
  if (area && looksMostlyEnglish(area)) {
    return area;
  }
  const message = shortText(alert?.message_en || alert?.message, 84);
  if (message && looksMostlyEnglish(message)) {
    return message;
  }
  return "Regional weather advisory";
}

export default function HomePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const mapCanvasRef = useRef(null);
  const mapStyleMenuRef = useRef(null);
  const leafletApiRef = useRef(null);
  const leafletMapRef = useRef(null);
  const leafletMarkerLayerRef = useRef(null);
  const leafletBaseLayerRef = useRef(null);
  const leafletStateOutlineRef = useRef(null);
  const stateGeoJsonDataRef = useRef(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sessionUser, setSessionUser] = useState(null);
  const [alertsPayload, setAlertsPayload] = useState(null);
  const [indiaAlertsPayload, setIndiaAlertsPayload] = useState(null);
  const [isMapLoading, setIsMapLoading] = useState(true);
  const [isMapRefreshing, setIsMapRefreshing] = useState(false);
  const [isLeafletReady, setIsLeafletReady] = useState(false);
  const [isLeafletFailed, setIsLeafletFailed] = useState(false);
  const [mapErrorMessage, setMapErrorMessage] = useState("");
  const [mapViewMode, setMapViewMode] = useState("street");
  const [isMapStyleMenuOpen, setIsMapStyleMenuOpen] = useState(false);
  const [fallbackMapCenter, setFallbackMapCenter] = useState(
    REGION_VIEWPORTS.india.center
  );
  const [fallbackMapZoom, setFallbackMapZoom] = useState(REGION_VIEWPORTS.india.zoom);
  const [isLocationModalOpen, setIsLocationModalOpen] = useState(false);
  const [locationSearch, setLocationSearch] = useState("");
  const [isDetectingLocation, setIsDetectingLocation] = useState(false);
  const [locationStatusMessage, setLocationStatusMessage] = useState("");
  const [regionalAlertsPage, setRegionalAlertsPage] = useState(1);
  const [selectedRegionValue, setSelectedRegionValue] = useState("india");
  const [userCoordinates, setUserCoordinates] = useState(() => {
    if (typeof window === "undefined") {
      return null;
    }
    const stored = window.localStorage.getItem(LOCATION_COORD_STORAGE_KEY);
    if (!stored) {
      return null;
    }
    try {
      const parsed = JSON.parse(stored);
      const lat = Number(parsed?.lat);
      const lon = Number(parsed?.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        return null;
      }
      return { lat, lon };
    } catch (_error) {
      return null;
    }
  });

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
        // Keep Home accessible even when not logged in.
      }
    };

    loadSession();
    return () => {
      active = false;
    };
  }, []);

  const fetchMapAlerts = async ({ silent = false } = {}) => {
    try {
      if (silent) {
        setIsMapRefreshing(true);
      } else {
        setIsMapLoading(true);
      }

      const requests = [apiRequest(buildMapAlertsPath(selectedRegionValue))];
      if (selectedRegionValue !== "india") {
        requests.push(apiRequest(buildMapAlertsPath("india")));
      }

      const [regionalResult, indiaResult] = await Promise.allSettled(requests);
      if (regionalResult.status !== "fulfilled") {
        throw regionalResult.reason;
      }

      const regionalPayload = regionalResult.value || null;
      setAlertsPayload(regionalPayload);

      if (selectedRegionValue === "india") {
        setIndiaAlertsPayload(regionalPayload);
      } else if (indiaResult && indiaResult.status === "fulfilled") {
        setIndiaAlertsPayload(indiaResult.value || null);
      }
      setMapErrorMessage("");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to load map alerts.";
      setMapErrorMessage(message);
    } finally {
      if (silent) {
        setIsMapRefreshing(false);
      } else {
        setIsMapLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchMapAlerts();
    const intervalId = window.setInterval(() => {
      fetchMapAlerts({ silent: true });
    }, 60_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [selectedRegionValue]);

  useEffect(() => {
    if (!isLocationModalOpen) {
      return undefined;
    }
    const closeOnEscape = (event) => {
      if (event.key === "Escape") {
        setIsLocationModalOpen(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [isLocationModalOpen]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsLocationModalOpen(true);
    }, 5000);
    return () => {
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(LOCATION_STORAGE_KEY, selectedRegionValue);
  }, [selectedRegionValue]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (!userCoordinates) {
      window.localStorage.removeItem(LOCATION_COORD_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      LOCATION_COORD_STORAGE_KEY,
      JSON.stringify({ lat: userCoordinates.lat, lon: userCoordinates.lon })
    );
  }, [userCoordinates]);

  useEffect(() => {
    let disposed = false;
    ensureLeafletLoaded()
      .then((L) => {
        if (disposed || !mapCanvasRef.current || leafletMapRef.current) {
          return;
        }

        leafletApiRef.current = L;

        const map = L.map(mapCanvasRef.current, {
          zoomControl: false,
          attributionControl: false,
          minZoom: 1,
          maxZoom: 20,
          zoomSnap: 0.25,
          zoomDelta: 0.25,
          worldCopyJump: false
        }).setView(REGION_VIEWPORTS.india.center, REGION_VIEWPORTS.india.zoom);

        const baseLayer = buildGoogleTileLayer(L, "street");
        baseLayer.addTo(map);
        leafletBaseLayerRef.current = baseLayer;
        map.fitBounds(INDIA_MAP_BOUNDS, { padding: [20, 20], maxZoom: 6 });
        map.on("moveend", () => {
          const center = map.getCenter();
          setFallbackMapCenter([Number(center.lat), Number(center.lng)]);
          setFallbackMapZoom(map.getZoom());
        });

        leafletMapRef.current = map;
        leafletMarkerLayerRef.current = L.layerGroup().addTo(map);
        setIsLeafletFailed(false);
        setIsLeafletReady(true);
      })
      .catch((error) => {
        setIsLeafletFailed(true);
        const reason =
          error instanceof Error ? error.message : "Unable to initialize live map.";
        setMapErrorMessage(`Live map unavailable: ${reason}`);
      });

    return () => {
      disposed = true;
      if (leafletMapRef.current) {
        leafletMapRef.current.remove();
      }
      leafletMapRef.current = null;
      leafletMarkerLayerRef.current = null;
      leafletBaseLayerRef.current = null;
      leafletApiRef.current = null;
    };
  }, []);

  useEffect(() => {
    const L = leafletApiRef.current;
    const map = leafletMapRef.current;
    if (!L || !map || !isLeafletReady || isLeafletFailed) {
      return;
    }

    if (leafletBaseLayerRef.current) {
      map.removeLayer(leafletBaseLayerRef.current);
      leafletBaseLayerRef.current = null;
    }

    const nextLayer = buildGoogleTileLayer(L, mapViewMode);
    nextLayer.addTo(map);
    leafletBaseLayerRef.current = nextLayer;
  }, [isLeafletFailed, isLeafletReady, mapViewMode]);

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (!mapStyleMenuRef.current) {
        return;
      }
      if (mapStyleMenuRef.current.contains(event.target)) {
        return;
      }
      setIsMapStyleMenuOpen(false);
    };

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("touchstart", handleOutsideClick, { passive: true });
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("touchstart", handleOutsideClick);
    };
  }, []);

  const liveAlerts = useMemo(
    () => (Array.isArray(alertsPayload?.alerts) ? alertsPayload.alerts : []),
    [alertsPayload]
  );
  const indiaWideAlerts = useMemo(() => {
    if (Array.isArray(indiaAlertsPayload?.alerts)) {
      return indiaAlertsPayload.alerts;
    }
    return liveAlerts;
  }, [indiaAlertsPayload, liveAlerts]);

  const regionScopedAlerts = useMemo(() => {
    return liveAlerts.filter((alert) =>
      alertMatchesSelectedRegion(alert, selectedRegionValue)
    );
  }, [liveAlerts, selectedRegionValue]);

  const focusFromQuery = useMemo(() => {
    const params = new URLSearchParams(location.search || "");
    const lat = Number(params.get("mapLat"));
    const lon = Number(params.get("mapLon"));
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      return null;
    }
    if (selectedRegionValue !== "international") {
      if (!isInsideIndia(lat, lon)) {
        return null;
      }
      if (selectedRegionValue !== "india") {
        const selectedBounds = approximateBoundsFromViewport(
          getRegionViewport(selectedRegionValue)
        );
        if (!isInsideBounds(lat, lon, selectedBounds)) {
          return null;
        }
      }
    }
    return {
      lat,
      lon,
      alertType: params.get("alertType") || "Focused Alert",
      alertArea: params.get("alertArea") || "",
      alertId: params.get("alertId") || ""
    };
  }, [location.search, selectedRegionValue]);

  const summaryAlerts = useMemo(() => {
    return regionScopedAlerts.slice(0, 10);
  }, [regionScopedAlerts]);

  const regionalAlertsTotalPages = useMemo(() => {
    return Math.max(
      1,
      Math.ceil(summaryAlerts.length / REGIONAL_ALERTS_PAGE_SIZE)
    );
  }, [summaryAlerts.length]);

  const regionalAlertsPageSafe = Math.min(
    regionalAlertsPage,
    regionalAlertsTotalPages
  );

  const regionalPagedAlerts = useMemo(() => {
    const start = (regionalAlertsPageSafe - 1) * REGIONAL_ALERTS_PAGE_SIZE;
    return summaryAlerts.slice(start, start + REGIONAL_ALERTS_PAGE_SIZE);
  }, [summaryAlerts, regionalAlertsPageSafe]);

  useEffect(() => {
    setRegionalAlertsPage(1);
  }, [selectedRegionValue]);

  useEffect(() => {
    if (regionalAlertsPage > regionalAlertsTotalPages) {
      setRegionalAlertsPage(regionalAlertsTotalPages);
    }
  }, [regionalAlertsPage, regionalAlertsTotalPages]);

  const selectedRegion = useMemo(
    () => getRegionOption(selectedRegionValue),
    [selectedRegionValue]
  );
  const selectedRegionViewport = useMemo(
    () => getRegionViewport(selectedRegionValue),
    [selectedRegionValue]
  );
  const pinnedRegionalAlerts = useMemo(() => {
    return summaryAlerts
      .map((alert) => {
        const point = resolvePinnedAlertPoint(
          alert,
          selectedRegionValue,
          selectedRegionViewport
        );
        if (!point) {
          return null;
        }

        return {
          ...alert,
          lat: point.lat,
          lon: point.lon,
          approximated: Boolean(point.approximated)
        };
      })
      .filter(Boolean)
      .sort(
        (left, right) =>
          parseIsoMillis(right?.start_time) - parseIsoMillis(left?.start_time)
      );
  }, [summaryAlerts, selectedRegionValue, selectedRegionViewport]);
  const fallbackOverlayBounds = useMemo(() => {
    if (selectedRegionValue === "international") {
      return {
        minLat: -55,
        maxLat: 82,
        minLon: -180,
        maxLon: 180
      };
    }
    if (selectedRegion.mode === "state") {
      const [[minLat, minLon], [maxLat, maxLon]] =
        approximateBoundsFromViewport(selectedRegionViewport);
      return {
        minLat,
        maxLat,
        minLon,
        maxLon
      };
    }
    return INDIA_BOUNDS;
  }, [selectedRegion.mode, selectedRegionValue, selectedRegionViewport]);

  const threatMatrixRows = useMemo(() => {
    const seeded = THREAT_MATRIX_ROW_ORDER.map((label) => ({
      label,
      severe: 0,
      moderate: 0,
      watch: 0,
      tone: "watch"
    }));
    const byLabel = new Map(seeded.map((row) => [row.label, row]));

    indiaWideAlerts.forEach((alert) => {
      const label = inferThreatMatrixCategory(alert);
      const target = byLabel.get(label);
      if (!target) {
        return;
      }

      const tone = mapAlertTone(alert);
      if (tone === "critical") {
        target.severe += 1;
      } else if (tone === "warning") {
        target.moderate += 1;
      } else {
        target.watch += 1;
      }
    });

    return seeded.map((row) => ({
      ...row,
      tone:
        row.severe > 0
          ? "severe"
          : row.moderate > 0
            ? "moderate"
            : "watch"
    }));
  }, [indiaWideAlerts]);

  const visibleMapPins = useMemo(() => {
    return buildOverlayPinsFromBounds(
      pinnedRegionalAlerts,
      fallbackOverlayBounds
    );
  }, [
    fallbackOverlayBounds,
    pinnedRegionalAlerts
  ]);

  useEffect(() => {
    if (focusFromQuery) {
      setFallbackMapCenter([focusFromQuery.lat, focusFromQuery.lon]);
      setFallbackMapZoom(8);
      return;
    }
    setFallbackMapCenter(selectedRegionViewport.center);
    setFallbackMapZoom(selectedRegionViewport.zoom);
  }, [focusFromQuery, selectedRegionViewport]);

  const fallbackMapEmbedSrc = useMemo(() => {
    if (selectedRegionValue === "india") {
      return `https://www.google.com/maps?output=embed&hl=en&gl=IN&ll=22.9734,78.6569&z=${INDIA_FULL_VIEW_ZOOM}&t=m`;
    }

    if (selectedRegionValue === "international") {
      return `https://www.google.com/maps?output=embed&hl=en&gl=IN&q=${encodeURIComponent(
        "World"
      )}&z=${GLOBAL_VIEW_ZOOM}`;
    }

    const [lat, lon] = selectedRegionViewport.center;
    const stateZoom = Math.min(
      MAX_MAP_ZOOM,
      Math.max(5, Math.round(selectedRegionViewport.zoom))
    );
    return `https://www.google.com/maps?output=embed&hl=en&gl=IN&ll=${lat},${lon}&z=${stateZoom}&t=m`;
  }, [selectedRegionValue, selectedRegionViewport]);

  const filteredRegionOptions = useMemo(() => {
    const query = locationSearch.trim().toLowerCase();
    if (!query) {
      return REGION_OPTIONS;
    }
    return REGION_OPTIONS.filter((option) =>
      option.label.toLowerCase().includes(query)
    );
  }, [locationSearch]);

  const handlePickRegion = (nextRegionValue) => {
    if (!nextRegionValue) {
      setIsLocationModalOpen(false);
      return;
    }
    const nextRegion = getRegionOption(nextRegionValue);
    const nextViewport = getRegionViewport(nextRegion.value);
    const nextZoom =
      nextRegion.value === "india"
        ? INDIA_FULL_VIEW_ZOOM
        : nextRegion.value === "international"
          ? GLOBAL_VIEW_ZOOM
          : Math.min(MAX_MAP_ZOOM, Math.max(5, Math.round(nextViewport.zoom)));
    setSelectedRegionValue(nextRegion.value);
    setFallbackMapCenter(nextViewport.center);
    setFallbackMapZoom(nextZoom);
    setLocationStatusMessage(`Showing live alerts for ${nextRegion.label}.`);
    if (leafletMapRef.current) {
      leafletMapRef.current.setView(nextViewport.center, Math.max(3, nextZoom));
    }
    setLocationSearch("");
    setIsLocationModalOpen(false);
  };

  const handleEnableCurrentLocation = () => {
    if (!navigator.geolocation) {
      setLocationStatusMessage("Location services are not available in this browser.");
      return;
    }

    setIsDetectingLocation(true);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const lat = Number(position.coords?.latitude);
        const lon = Number(position.coords?.longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
          setLocationStatusMessage("Unable to detect your current location.");
          setIsDetectingLocation(false);
          return;
        }

        const nextRegionValue = await resolveRegionFromCoordinates(lat, lon);
        const nextRegion = getRegionOption(nextRegionValue);
        const nextViewport = getRegionViewport(nextRegionValue);
        setSelectedRegionValue(nextRegionValue);
        setUserCoordinates({ lat, lon });
        setFallbackMapCenter([lat, lon]);
        setFallbackMapZoom(
          nextRegionValue === "international"
            ? GLOBAL_VIEW_ZOOM
            : Math.max(7, Math.round(nextViewport.zoom || 7))
        );
        if (leafletMapRef.current) {
          leafletMapRef.current.setView(
            [lat, lon],
            nextRegionValue === "international"
              ? GLOBAL_VIEW_ZOOM
              : Math.max(7, Math.round(nextViewport.zoom || 7))
          );
        }
        setLocationStatusMessage(
          `Location enabled in ${nextRegion.label} (${lat.toFixed(3)}, ${lon.toFixed(3)}).`
        );
        setLocationSearch("");
        setIsLocationModalOpen(false);
        setIsDetectingLocation(false);
      },
      (error) => {
        const fallbackMessage =
          error?.code === 1
            ? "Location permission denied. Please allow location access."
            : "Unable to access your current location.";
        setLocationStatusMessage(fallbackMessage);
        setIsDetectingLocation(false);
      },
      {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 60000
      }
    );
  };

  const handleMapZoomIn = () => {
    if (leafletMapRef.current && isLeafletReady && !isLeafletFailed) {
      leafletMapRef.current.zoomIn();
      return;
    }
    setFallbackMapZoom((previous) => Math.min(MAX_MAP_ZOOM, previous + 1));
  };

  const handleMapZoomOut = () => {
    if (leafletMapRef.current && isLeafletReady && !isLeafletFailed) {
      leafletMapRef.current.zoomOut();
      return;
    }
    setFallbackMapZoom((previous) => Math.max(MIN_MAP_ZOOM, previous - 1));
  };

  useEffect(() => {
    const L = leafletApiRef.current;
    const map = leafletMapRef.current;
    const markerLayer = leafletMarkerLayerRef.current;
    if (!isLeafletReady || isLeafletFailed || !L || !map || !markerLayer) {
      return;
    }

    markerLayer.clearLayers();
    const latLngs = [];
    const usedPoints = new Set();

    pinnedRegionalAlerts.slice(0, 12).forEach((alert) => {
      const lat = Number(alert?.lat);
      const lon = Number(alert?.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        return;
      }

      const dedupeKey = `${lat.toFixed(3)}:${lon.toFixed(3)}:${String(alert?.type || "").toLowerCase()}`;
      if (usedPoints.has(dedupeKey)) {
        return;
      }
      usedPoints.add(dedupeKey);
      latLngs.push([lat, lon]);

      const marker = L.marker([lat, lon], {
        icon: buildLeafletAlertIcon(L, alert),
        keyboard: false
      });
      marker.bindPopup(buildAlertPopup(alert), { maxWidth: 280 });
      marker.addTo(markerLayer);
    });

    if (
      latLngs.length === 0 &&
      regionScopedAlerts.length > 0 &&
      !REGION_FILTER_EXEMPT.has(selectedRegionValue)
    ) {
      const fallbackMarker = L.circleMarker(selectedRegionViewport.center, {
        radius: 9,
        color: "#1d4ed8",
        fillColor: "#3b82f6",
        fillOpacity: 0.78,
        weight: 2
      });
      fallbackMarker.bindPopup(
        `<div style="font-family:Inter,sans-serif;min-width:180px;"><strong>${regionScopedAlerts.length} alerts in ${escapeHtml(
          selectedRegion.label
        )}</strong><br/><span style="font-size:12px;color:#475569;">Exact coordinates unavailable from source</span></div>`,
        { maxWidth: 260 }
      );
      fallbackMarker.addTo(markerLayer);
      latLngs.push(selectedRegionViewport.center);
    }

    if (focusFromQuery) {
      latLngs.push([focusFromQuery.lat, focusFromQuery.lon]);
      const focusMarker = L.marker([focusFromQuery.lat, focusFromQuery.lon], {
        icon: buildLeafletFocusIcon(L),
        keyboard: false
      });
      focusMarker
        .bindPopup(
          `<div style="font-family:Inter,system-ui,sans-serif;color:#0f172a;"><strong>Focused Alert</strong><div style="font-size:12px;margin-top:4px;">${escapeHtml(
            focusFromQuery.alertType
          )}</div></div>`,
          { maxWidth: 220 }
        )
        .addTo(markerLayer);
    }

    if (userCoordinates) {
      const userMarker = L.marker([userCoordinates.lat, userCoordinates.lon], {
        icon: buildLeafletUserIcon(L),
        keyboard: false
      });
      userMarker.bindPopup("<strong>Your current location</strong>", { maxWidth: 180 });
      userMarker.addTo(markerLayer);
    }

    if (selectedRegionValue === "india") {
      map.setMaxBounds(INDIA_MAP_BOUNDS);
      map.options.maxBoundsViscosity = 0.85;
    } else {
      map.setMaxBounds(null);
      map.options.maxBoundsViscosity = 0;
    }

    if (focusFromQuery) {
      map.setView(
        [focusFromQuery.lat, focusFromQuery.lon],
        selectedRegionValue === "india" ? 6 : Math.max(7, selectedRegionViewport.zoom)
      );
    } else if (latLngs.length) {
      map.fitBounds(L.latLngBounds(latLngs), {
        padding: [18, 18],
        maxZoom: selectedRegionValue === "india" ? 6 : 8
      });
    } else {
      map.setView(selectedRegionViewport.center, selectedRegionViewport.zoom);
    }
  }, [
    isLeafletReady,
    isLeafletFailed,
    focusFromQuery,
    pinnedRegionalAlerts,
    regionScopedAlerts,
    userCoordinates,
    selectedRegionValue,
    selectedRegion,
    selectedRegionViewport
  ]);

  useEffect(() => {
    if (!isLeafletReady || !leafletMapRef.current) {
      return;
    }
    const timer = window.setTimeout(() => {
      leafletMapRef.current?.invalidateSize();
    }, 120);
    return () => {
      window.clearTimeout(timer);
    };
  }, [isLeafletReady, mobileMenuOpen]);

  return (
    <div className={c("page-home")}>
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
              id="home-primary-nav"
              onClick={() => setMobileMenuOpen(false)}
            >
              <Link to="/" className={c("active")}>Home</Link>
              <Link to="/alerts">Alerts</Link>
              <Link to="/report">Report Incident</Link>
              <Link to="/risk-prediction">Risk Prediction</Link>
              <Link to="/outcome-prediction">Outcome Predictor</Link>
              <Link to="/resource-management">Resource Management</Link>
              <Link to="/satellite">Satellite / Geo</Link>
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
              aria-controls="home-primary-nav"
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
        {/* Header for Dashboard */}
        <div className={c("dash-header")}>
          <div className={c("dash-title-group")}>
            <div
              className={c("region-trigger")}
              onClick={() => setIsLocationModalOpen(true)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setIsLocationModalOpen(true);
                }
              }}
              role="button"
              tabIndex={0}
              aria-label="Open region selector"
            >
              <span className={c("region-trigger-label")}>Region</span>
              <span className={c("region-trigger-value")}>
                {selectedRegion.label}
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </span>
            </div>
            <div className={c("dash-title-stack")}>
              <h1 className={c("dash-title")}>RESQFY DISASTER INTELLIGENCE</h1>
              <span className={c("dash-subtitle")}>- Home</span>
            </div>
          </div>
          <div className={c("dash-meta")}>
            <button className={c("perf-btn")}>
              <svg viewBox="0 0 24 24" fill="none" className={c("chart-i")} stroke="currentColor" strokeWidth={2}><line x1={18} y1={20} x2={18} y2={10} /><line x1={12} y1={20} x2={12} y2={4} /><line x1={6} y1={20} x2={6} y2={14} /></svg>
              Performance Dashboard
            </button>
            <div className={c("dash-time")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={12} cy={12} r={10} /><polyline points="12 6 12 12 16 14" /></svg>
              <span id="header-time">07:12 AM - 24 Oct 2024</span>
            </div>
          </div>
        </div>
        {/* Main Dashboard View */}
        <main className={c("dash-main")}>
          {/* LEFT COLUMN */}
          <div className={c("dash-left")}>
            {/* Map Panel */}
            <div className={c("map-panel")}>
              {mapErrorMessage ? (
                <div className={c("map-error-banner")}>{mapErrorMessage}</div>
              ) : null}

              <div className={c(`map-view ${selectedRegion.mode === "state" ? "map-view-state-focus" : ""}`)}>
                <div
                  ref={mapCanvasRef}
                  className={c(`leaflet-map-canvas ${!isLeafletReady || isLeafletFailed ? "map-canvas-hidden" : ""}`)}
                />
                {!isLeafletReady || isLeafletFailed ? (
                  <iframe
                    className={c(`map-embed-frame ${selectedRegion.mode === "state" ? "map-embed-state-focus" : ""}`)}
                    src={fallbackMapEmbedSrc}
                    title="India map"
                    loading="lazy"
                    referrerPolicy="no-referrer-when-downgrade"
                    allowFullScreen
                  />
                ) : null}
                {!isLeafletReady || isLeafletFailed ? (
                  visibleMapPins.length ? (
                    <div className={c("map-fallback-marker-layer")} aria-hidden="true">
                      {visibleMapPins.map((pin) => (
                        <span
                          key={pin.id}
                          className={c("map-fallback-marker")}
                          style={pin.style}
                          title={pin.label}
                          dangerouslySetInnerHTML={{ __html: pin.iconMarkup }}
                        />
                      ))}
                    </div>
                  ) : null
                ) : null}
                {isMapLoading ? (
                  <div className={c("map-loading-overlay")}>Loading map points...</div>
                ) : null}
              </div>
            </div>
          </div>
          {/* RIGHT COLUMN */}
          <div className={c("dash-right")}>
            <div className={c("dash-col-middle")}>
              <div className={c("panel card upcoming-card")}>
                <div className={c("card-header")}>
                  <h3 style={{textTransform: 'none', letterSpacing: 'normal', fontSize: 16, fontWeight: 600}}>Regional Upcoming Alert Summary</h3>
                  <svg className={c("more-icon")} viewBox="0 0 24 24" fill="currentColor"><circle cx={5} cy={12} r={2} /><circle cx={12} cy={12} r={2} /><circle cx={19} cy={12} r={2} /></svg>
                </div>
                <div className={c("alert-list")}>
                  {summaryAlerts.length === 0 ? (
                    <div className={c("regional-alert-empty")}>
                      No live alerts available right now.
                    </div>
                  ) : (
                    regionalPagedAlerts.map((alert, index) => {
                      const tone = mapAlertTone(alert);
                      const cardToneClass =
                        tone === "critical"
                          ? "regional-alert-high"
                          : tone === "warning"
                            ? "regional-alert-medium"
                            : "regional-alert-low";
                      const intensityText = mapAlertIntensity(alert);
                      const shortTitle = buildRegionalTitle(alert);
                      const shortBrief = buildRegionalBrief(alert);
                      return (
                        <article
                          className={c(`regional-alert-card ${cardToneClass}`)}
                          key={`${alert?.id || "summary"}-${regionalAlertsPageSafe}-${index}`}
                        >
                          <div className={c("regional-alert-head")}>
                            <h4>{shortTitle}</h4>
                            <span className={c("regional-alert-warning")}>
                              <svg viewBox="0 0 24 24" aria-hidden="true">
                                <path d="M12 2L2 22h20L12 2z" fill="currentColor" />
                                <rect x="11" y="8" width="2" height="7" fill="#ffffff" />
                                <rect x="11" y="17" width="2" height="2" fill="#ffffff" />
                              </svg>
                            </span>
                          </div>
                          <p className={c("regional-alert-issued")}>
                            Issued By {String(alert?.source || "Unknown source")}
                            <span>{formatCardTime(alert?.start_time)}</span>
                          </p>
                          <div className={c("regional-alert-body")}>
                            <div className={c("regional-alert-intensity")}>
                              <span className={c("regional-alert-meter")}>
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                  <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
                                  <path d="M12 12l4-3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                                  <circle cx="12" cy="12" r="1.3" fill="currentColor" />
                                </svg>
                              </span>
                              <strong>{intensityText.split(" ")[0]}</strong>
                              <span>{intensityText.split(" ").slice(1).join(" ")}</span>
                            </div>
                            <div className={c("regional-alert-divider")} />
                            <div className={c("regional-alert-location")}>
                              <p>{shortBrief}</p>
                              <span>
                                Valid till {formatCardTime(alert?.end_time)}
                              </span>
                            </div>
                          </div>
                        </article>
                      );
                    })
                  )}
                </div>
                {summaryAlerts.length > 0 ? (
                  <div className={c("regional-pagination")}>
                    <button
                      type="button"
                      className={c("regional-page-btn")}
                      onClick={() =>
                        setRegionalAlertsPage((previous) => Math.max(1, previous - 1))
                      }
                      disabled={regionalAlertsPageSafe <= 1}
                    >
                      Previous
                    </button>
                    <span className={c("regional-page-info")}>
                      {regionalAlertsPageSafe}/{regionalAlertsTotalPages}
                    </span>
                    <button
                      type="button"
                      className={c("regional-page-btn")}
                      onClick={() =>
                        setRegionalAlertsPage((previous) =>
                          Math.min(regionalAlertsTotalPages, previous + 1)
                        )
                      }
                      disabled={regionalAlertsPageSafe >= regionalAlertsTotalPages}
                    >
                      Next
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
            <div className={c("dash-col-right")}>
              {/* Active Threat Matrix */}
              <div className={c("panel card threat-matrix-card")}>
                <div className={c("card-header")}>
                  <h3>ACTIVE THREAT MATRIX</h3>
                  <svg className={c("more-icon")} viewBox="0 0 24 24" fill="currentColor"><circle cx={5} cy={12} r={2} /><circle cx={12} cy={12} r={2} /><circle cx={19} cy={12} r={2} /></svg>
                </div>
                <div className={c("matrix-grid")}>
                  <div className={c("matrix-row matrix-header")}>
                    <div className={c("matrix-disaster-head")}>Disaster</div>
                    <div className={c("matrix-head-severe")}>Severe</div>
                    <div className={c("matrix-head-moderate")}>Moderate</div>
                    <div className={c("matrix-head-watch")}>Watch</div>
                  </div>
                  {threatMatrixRows.map((row) => (
                    <div className={c("matrix-row matrix-data-row")} key={row.label}>
                      <div
                        className={c(
                          `m-label ${
                            row.tone === "moderate"
                              ? "m-label-max-moderate"
                              : row.tone === "watch"
                                ? "m-label-max-watch"
                                : "m-label-max-severe"
                          }`
                        )}
                      >
                        {row.label}
                      </div>
                      <div className={c("matrix-cell matrix-cell-severe")}>
                        <strong>{row.severe}</strong>
                      </div>
                      <div className={c("matrix-cell matrix-cell-moderate")}>
                        <strong>{row.moderate}</strong>
                      </div>
                      <div className={c("matrix-cell matrix-cell-watch")}>
                        <strong>{row.watch}</strong>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className={c("panel card quick-dm dm-only")}>
                <div className={c("card-header")} style={{justifyContent: 'center', marginBottom: 12, borderBottom: 'none'}}>
                  <h3 style={{letterSpacing: 1, color: '#ffffff', textAlign: 'center'}}>QUICK ACTIONS</h3>
                </div>
                <div className={c("dm-action-btns")}>
                  <button
                    className={c("qa-btn big-qa qa-report")}
                    type="button"
                    onClick={() => navigate("/report")}
                  >
                    <div className={c("qa-i-wrapper")}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                        <line x1={12} y1={9} x2={12} y2={13} />
                        <line x1={12} y1={17} x2="12.01" y2={17} />
                      </svg>
                    </div>
                    REPORT<br />INCIDENT
                  </button>
                  <button
                    className={c("qa-btn big-qa qa-sos")}
                    type="button"
                    onClick={() => navigate("/sos")}
                  >
                    <div className={c("qa-i-wrapper")}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
                      </svg>
                    </div>
                    EMERGENCY<br />SOS
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>
        {/* Global Footer */}
        <footer className={c("app-footer-text")}>
          About Resqfy &nbsp;|&nbsp; Contact Support &nbsp;|&nbsp; Privacy Policy &nbsp;|&nbsp; Terms of Service &nbsp;|&nbsp; © 2026 Resqfy. All rights reserved.
        </footer>
      </div>

      {isLocationModalOpen ? (
        <div
          className={c("location-modal-overlay")}
          role="presentation"
          onClick={() => setIsLocationModalOpen(false)}
        >
          <div
            className={c("location-modal")}
            role="dialog"
            aria-modal="true"
            aria-label="Choose your location"
            onClick={(event) => event.stopPropagation()}
          >
            <div className={c("location-modal-header")}>
              <h3>Your Location</h3>
              <button
                type="button"
                className={c("location-modal-close")}
                onClick={() => setIsLocationModalOpen(false)}
                aria-label="Close location selector"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path d="M6 6l12 12" />
                  <path d="M18 6l-12 12" />
                </svg>
              </button>
            </div>

            <label htmlFor="location-search-input" className={c("location-search-label")}>
              Search a new address
            </label>
            <div className={c("location-search-box")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <circle cx={11} cy={11} r={8} />
                <path d="M21 21L16.65 16.65" />
              </svg>
              <input
                id="location-search-input"
                type="text"
                value={locationSearch}
                onChange={(event) => setLocationSearch(event.target.value)}
                placeholder="Search a new address"
              />
            </div>

            <div className={c("location-option-list")}>
              {filteredRegionOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={c(`location-option ${selectedRegionValue === option.value ? "selected" : ""}`)}
                  onClick={() => handlePickRegion(option.value)}
                >
                  {option.label}
                </button>
              ))}
              {filteredRegionOptions.length === 0 ? (
                <div className={c("location-empty")}>No matching location found.</div>
              ) : null}
            </div>

            <div className={c("location-current-card")}>
              <div className={c("location-current-copy")}>
                <h4>Use My Current Location</h4>
                <p>Enable location service for better accuracy</p>
              </div>
              <button
                type="button"
                className={c("location-enable-btn")}
                onClick={handleEnableCurrentLocation}
                disabled={isDetectingLocation}
              >
                {isDetectingLocation ? "Detecting..." : "Enable"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
