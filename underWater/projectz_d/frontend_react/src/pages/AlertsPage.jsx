import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import baseStyles from "/styles.module.css";
import pageStyles from "/alerts.module.css";
import { cx } from "../utils/cx.js";
import { apiRequest } from "../utils/api.js";
import { fetchSessionUser, getUserFirstName } from "../utils/session.js";

const c = (classNames) => cx(classNames, baseStyles, pageStyles);
const PAGE_SIZE = 4;
const PIE_COLORS = ["#00d4ff", "#004dff", "#ffd400", "#7b2cff", "#2ecc40", "#ff2e2e", "#00c9a7", "#8b4513", "#b388ff", "#ff6d00", "#ff1493"];
const PIE_INDEX_CATEGORIES = [
  { label: "Rain", color: "#00d4ff" },
  { label: "Flood", color: "#004dff" },
  { label: "Lightning", color: "#ffd400" },
  { label: "Thunderstorm", color: "#7b2cff" },
  { label: "Earthquake", color: "#2ecc40" },
  { label: "Fire", color: "#ff2e2e" },
  { label: "Cyclone", color: "#00c9a7" },
  { label: "Landslide", color: "#8b4513" },
  { label: "Avalanche", color: "#b388ff" },
  { label: "Heat Wave", color: "#ff6d00" },
  { label: "Other", color: "#ff1493" },
];

const ALERT_KEY_ORDER = [
  "id",
  "type",
  "category",
  "severity",
  "severity_color",
  "area",
  "message",
  "source",
  "source_section",
  "start_time",
  "end_time",
  "lat",
  "lon",
  "location_available",
];

const DISASTER_TYPE_OPTIONS = [
  { value: "all", label: "All Types" },
  { value: "cyclone", label: "Cyclone" },
  { value: "landslide", label: "Landslide" },
  { value: "avalanche", label: "Avalanche" },
  { value: "flood", label: "Flood" },
  { value: "rain", label: "Rain" },
  { value: "lightning", label: "Lightning" },
  { value: "thunderstorm", label: "Thunderstorm" },
  { value: "fire", label: "Fire" },
  { value: "earthquake", label: "Earthquake" },
  { value: "heat wave", label: "Heat Wave" },
  { value: "other", label: "Other" },
];

const STATE_FILTER_OPTIONS = [
  { value: "india", label: "All India" },
  { value: "all", label: "All Regions" },
  { value: "andhra pradesh", label: "Andhra Pradesh" },
  { value: "arunachal pradesh", label: "Arunachal Pradesh" },
  { value: "assam", label: "Assam" },
  { value: "bihar", label: "Bihar" },
  { value: "chhattisgarh", label: "Chhattisgarh" },
  { value: "goa", label: "Goa" },
  { value: "gujarat", label: "Gujarat" },
  { value: "haryana", label: "Haryana" },
  { value: "himachal pradesh", label: "Himachal Pradesh" },
  { value: "jharkhand", label: "Jharkhand" },
  { value: "karnataka", label: "Karnataka" },
  { value: "kerala", label: "Kerala" },
  { value: "madhya pradesh", label: "Madhya Pradesh" },
  { value: "maharashtra", label: "Maharashtra" },
  { value: "manipur", label: "Manipur" },
  { value: "meghalaya", label: "Meghalaya" },
  { value: "mizoram", label: "Mizoram" },
  { value: "nagaland", label: "Nagaland" },
  { value: "odisha", label: "Odisha" },
  { value: "punjab", label: "Punjab" },
  { value: "rajasthan", label: "Rajasthan" },
  { value: "sikkim", label: "Sikkim" },
  { value: "tamil nadu", label: "Tamil Nadu" },
  { value: "telangana", label: "Telangana" },
  { value: "tripura", label: "Tripura" },
  { value: "uttar pradesh", label: "Uttar Pradesh" },
  { value: "uttarakhand", label: "Uttarakhand" },
  { value: "west bengal", label: "West Bengal" },
  { value: "andaman and nicobar islands", label: "Andaman and Nicobar Islands" },
  { value: "chandigarh", label: "Chandigarh" },
  { value: "dadra and nagar haveli and daman and diu", label: "Dadra and Nagar Haveli and Daman and Diu" },
  { value: "delhi", label: "Delhi" },
  { value: "jammu and kashmir", label: "Jammu and Kashmir" },
  { value: "ladakh", label: "Ladakh" },
  { value: "lakshadweep", label: "Lakshadweep" },
  { value: "puducherry", label: "Puducherry" },
];

const DEFAULT_FILTERS = Object.freeze({
  section: "live",
  search: "",
  state: "india",
  coverage: "india",
  dateFrom: "",
  dateTo: "",
  severity: "all",
  disasterType: "all",
  sortBy: "newest",
  scope: "official",
  limit: "200",
  onlyMappable: false,
});

function humanizeKey(key) {
  return String(key || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatUtc(value) {
  if (!value) {
    return "N/A";
  }

  try {
    const asDate = new Date(value);
    if (Number.isNaN(asDate.getTime())) {
      return String(value);
    }
    return asDate.toLocaleString();
  } catch (_error) {
    return String(value);
  }
}

function parseMillis(value) {
  if (!value) {
    return 0;
  }
  const asDate = new Date(value);
  const millis = asDate.getTime();
  return Number.isNaN(millis) ? 0 : millis;
}

function formatCoordinate(value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }

  const asNumber = Number(value);
  if (!Number.isFinite(asNumber)) {
    return String(value);
  }
  return asNumber.toFixed(5);
}

function shorten(text, maxLength = 220) {
  const value = String(text || "");
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 3))}...`;
}

function formatValue(key, value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  const normalizedKey = String(key || "").toLowerCase();
  if (normalizedKey === "lat" || normalizedKey === "lon") {
    return formatCoordinate(value);
  }

  if (normalizedKey.includes("time") || normalizedKey.includes("date")) {
    return formatUtc(value);
  }

  if (typeof value === "number") {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value.length ? value.map((item) => String(item)).join(", ") : "N/A";
  }

  if (typeof value === "object") {
    return shorten(JSON.stringify(value), 300);
  }

  return shorten(String(value), 300);
}

function categoryBlob(alert) {
  const tags = Array.isArray(alert?.category_tags) ? alert.category_tags.join(" ") : "";
  return `${alert?.category || ""} ${tags} ${alert?.type || ""}`.toLowerCase();
}

function normalizeCategoryLabel(value) {
  const backendCategory = String(value || "").trim().toLowerCase();
  if (backendCategory === "rain") {
    return "Rain";
  }
  if (backendCategory === "flood") {
    return "Flood";
  }
  if (backendCategory === "lightning") {
    return "Lightning";
  }
  if (backendCategory === "thunderstorm") {
    return "Thunderstorm";
  }
  if (backendCategory === "earthquake") {
    return "Earthquake";
  }
  if (backendCategory === "fire") {
    return "Fire";
  }
  if (backendCategory === "cyclone" || backendCategory === "cyclonic") {
    return "Cyclone";
  }
  if (backendCategory === "landslide") {
    return "Landslide";
  }
  if (backendCategory === "avalanche") {
    return "Avalanche";
  }
  if (backendCategory === "heat wave" || backendCategory === "heatwave") {
    return "Heat Wave";
  }
  if (backendCategory === "other") {
    return "Other";
  }
  return "";
}

function inferAlertCategory(alert) {
  const normalizedBackend = normalizeCategoryLabel(alert?.category);
  if (normalizedBackend) {
    return normalizedBackend;
  }

  const blob = `${alert?.category || ""} ${alert?.type || ""} ${alert?.message || ""} ${alert?.source || ""}`.toLowerCase();

  if (
    blob.includes("lightning") ||
    blob.includes("lighting") ||
    blob.includes("thunderbolt") ||
    blob.includes("पिडुग") ||
    blob.includes("మెరుపు") ||
    blob.includes("ಮಿಂಚು") ||
    blob.includes("ಪಿಡುಗು") ||
    blob.includes("ବଜ୍ରପାତ")
  ) {
    return "Lightning";
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
    blob.includes("avalanche") ||
    blob.includes("snow avalanche") ||
    blob.includes("snow slide") ||
    blob.includes("ice slide")
  ) {
    return "Avalanche";
  }
  if (
    blob.includes("heat wave") ||
    blob.includes("heatwave") ||
    blob.includes("extreme heat")
  ) {
    return "Heat Wave";
  }
  if (
    blob.includes("earthquake") ||
    blob.includes("seismic") ||
    blob.includes("aftershock") ||
    blob.includes("tremor")
  ) {
    return "Earthquake";
  }
  if (
    blob.includes("fire") ||
    blob.includes("wildfire") ||
    blob.includes("forest fire") ||
    blob.includes("blaze")
  ) {
    return "Fire";
  }
  if (
    blob.includes("flood") ||
    blob.includes("inundation") ||
    blob.includes("waterlogging") ||
    blob.includes("dam release") ||
    blob.includes("ನೆರೆ") ||
    blob.includes("ବନ୍ୟା")
  ) {
    return "Flood";
  }
  if (
    blob.includes("thunderstorm") ||
    blob.includes("thunderstrom") ||
    blob.includes("thunder") ||
    blob.includes("lightning") ||
    blob.includes("ఉరుము") ||
    blob.includes("ಗುಡುಗು")
  ) {
    return "Thunderstorm";
  }
  if (
    blob.includes("rain") ||
    blob.includes("rainfall") ||
    blob.includes("downpour") ||
    blob.includes("cloudburst") ||
    blob.includes("వర్ష") ||
    blob.includes("ಮಳೆ") ||
    blob.includes("ବର୍ଷା")
  ) {
    return "Rain";
  }

  return "Other";
}

function inferAlertCategoryTags(alert) {
  const rawTags = Array.isArray(alert?.category_tags) ? alert.category_tags : [];
  const normalizedTags = [];
  rawTags.forEach((tag) => {
    const normalized = normalizeCategoryLabel(tag);
    if (normalized && !normalizedTags.includes(normalized)) {
      normalizedTags.push(normalized);
    }
  });
  if (!normalizedTags.length) {
    normalizedTags.push(inferAlertCategory(alert));
  }
  return normalizedTags;
}

function alertSeverityClass(alert) {
  const severityColor = String(alert?.severity_color || "").toLowerCase();
  const severity = String(alert?.severity || "").toLowerCase();

  if (severityColor === "red" || severity === "alert") {
    return "high";
  }
  if (severityColor === "orange" || severity === "warning") {
    return "medium";
  }
  return "low";
}

function alertIconClass(alert) {
  const severityClass = alertSeverityClass(alert);
  if (severityClass === "high") {
    return "severity-high";
  }
  if (severityClass === "medium") {
    return "severity-medium";
  }
  return "severity-low";
}

function renderAlertIcon(alert) {
  const blob = categoryBlob(alert);

  if (blob.includes("thunder") || blob.includes("cyclon")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 18a4 4 0 0 0 .7-7.94A6 6 0 0 0 6.03 9.5 3.5 3.5 0 0 0 7 18h10z" />
        <path d="M13 11l-3 5h3l-1 4 4-6h-3l1-3z" />
      </svg>
    );
  }

  if (blob.includes("flood") || blob.includes("rain")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3c3 4 5 7 5 10a5 5 0 1 1-10 0c0-3 2-6 5-10z" />
        <path d="M5 20h14" />
      </svg>
    );
  }

  if (blob.includes("earthquake")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="2 12 6 12 8 7 12 17 14 12 22 12" />
      </svg>
    );
  }

  if (blob.includes("fire")) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3s4 3 4 8a4 4 0 1 1-8 0c0-2 1-3 2-5 1 1 2 1 2-3z" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8h.01" />
      <path d="M11 12h1v4h1" />
    </svg>
  );
}

function buildAlertSearchBlob(alert) {
  const values = [];
  for (const value of Object.values(alert || {})) {
    if (value === null || value === undefined) {
      continue;
    }
    if (typeof value === "object") {
      values.push(JSON.stringify(value));
    } else {
      values.push(String(value));
    }
  }
  return values.join(" ").toLowerCase();
}

function buildAlertDuplicateSignature(alert) {
  return [
    String(alert?.type_original || alert?.type || "").trim().toLowerCase(),
    String(alert?.message_original || alert?.message || "").trim().toLowerCase(),
    String(alert?.area || "").trim().toLowerCase(),
    String(alert?.start_time || "").trim().toLowerCase(),
    String(alert?.end_time || "").trim().toLowerCase(),
    String(alert?.source || "").trim().toLowerCase(),
  ].join("|");
}

function normalizeAlertDedupeToken(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function alertDayBucket(value) {
  const millis = parseMillis(value);
  if (!millis) {
    return "";
  }
  const date = new Date(millis);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toISOString().slice(0, 10);
}

function buildAlertCanonicalSignature(alert) {
  return [
    normalizeAlertDedupeToken(alert?.category || inferAlertCategory(alert)),
    normalizeAlertDedupeToken(alert?.type_original || alert?.type),
    normalizeAlertDedupeToken(alert?.message_original || alert?.message),
    normalizeAlertDedupeToken(alert?.area),
    normalizeAlertDedupeToken(alert?.source),
    alertDayBucket(alert?.start_time),
  ].join("|");
}

function isLikelyEnglishText(value) {
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
  return asciiCount / Math.max(1, text.length) >= 0.98;
}

function orderedAlertEntries(alert) {
  if (!alert || typeof alert !== "object") {
    return [];
  }

  const entries = [];
  const used = new Set();

  ALERT_KEY_ORDER.forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(alert, key)) {
      entries.push([key, alert[key]]);
      used.add(key);
    }
  });

  Object.entries(alert).forEach(([key, value]) => {
    if (!used.has(key)) {
      entries.push([key, value]);
    }
  });

  return entries;
}

function buildPieSegments(categoryCounts, total) {
  if (!total || total <= 0) {
    return [];
  }

  const classified = categoryCounts.map((item, index) => ({
    ...item,
    color: item.color || PIE_COLORS[index % PIE_COLORS.length],
  }));

  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  let runningOffset = 0;

  return classified.map((item) => {
    const fraction = item.count / total;
    const length = fraction * circumference;
    const segment = {
      ...item,
      percentage: Math.round(fraction * 1000) / 10,
      circumference,
      radius,
      length,
      offset: runningOffset,
    };
    runningOffset += length;
    return segment;
  });
}

function getOtherBucketLabel(alert) {
  const type = String(alert?.type || "").trim();
  const category = String(alert?.category || "").trim();
  const source = String(alert?.source || "").trim();

  if (type && category && type.toLowerCase() !== category.toLowerCase()) {
    return `${type} (${category})`;
  }
  if (type) {
    return type;
  }
  if (category) {
    return category;
  }
  if (source) {
    return `Source: ${source}`;
  }
  return "Unlabeled alert";
}

export default function AlertsPage() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sessionUser, setSessionUser] = useState(null);
  const [alertsPayload, setAlertsPayload] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isApplying, setIsApplying] = useState(false);
  const [speakingAlertKey, setSpeakingAlertKey] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [expandedAlertKey, setExpandedAlertKey] = useState("");
  const [selectedSliceLabel, setSelectedSliceLabel] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [translatedAlertsById, setTranslatedAlertsById] = useState({});
  const [translatedRowKeys, setTranslatedRowKeys] = useState({});
  const [isTranslating, setIsTranslating] = useState(false);
  const [filters, setFilters] = useState(() => ({ ...DEFAULT_FILTERS }));

  const listenSupported =
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    "SpeechSynthesisUtterance" in window;

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
        // Keep page visible even without session.
      }
    };

    loadSession();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.body.setAttribute("data-page", "alerts");
    }
    return () => {
      if (typeof document !== "undefined" && document.body.getAttribute("data-page") === "alerts") {
        document.body.removeAttribute("data-page");
      }
    };
  }, []);

  useEffect(() => {
    return () => {
      if (listenSupported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [listenSupported]);

  const buildApiParams = (activeFilters, options = {}) => {
    const useEnglish = Boolean(options.english);
    const params = new URLSearchParams();
    params.set("limit", String(activeFilters.limit || "200"));
    const section = String(activeFilters.section || "live");
    const isHistory = section === "history";
    params.set("section", isHistory ? "history" : "live");
    params.set("active_only", isHistory ? "false" : "true");

    if (String(activeFilters.state || "").trim()) {
      params.set("state", String(activeFilters.state).trim());
    }

    params.set("coverage", String(activeFilters.coverage || "india"));
    params.set("scope", String(activeFilters.scope || "official"));
    if (useEnglish) {
      params.set("lang", "en");
    }

    if (activeFilters.dateFrom) {
      params.set("date_from", activeFilters.dateFrom);
    }
    if (activeFilters.dateTo) {
      params.set("date_to", activeFilters.dateTo);
    }

    if (activeFilters.severity && activeFilters.severity !== "all") {
      params.set("severity", activeFilters.severity);
    }

    if (activeFilters.disasterType && activeFilters.disasterType !== "all") {
      params.set("disaster_type", activeFilters.disasterType);
    }
    return params;
  };

  const fetchAlerts = async ({ silent = false, nextFilters = null } = {}) => {
    const activeFilters = nextFilters || filters;
    const params = buildApiParams(activeFilters);

    try {
      if (silent) {
        setIsApplying(true);
      } else {
        setIsLoading(true);
      }

      const payload = await apiRequest(`/mobile/live-alerts?${params.toString()}`);
      setAlertsPayload(payload || null);
      setExpandedAlertKey("");
      setCurrentPage(1);
      setSelectedSliceLabel("");
      setSpeakingAlertKey("");
      setTranslatedAlertsById({});
      setTranslatedRowKeys({});
      if (listenSupported) {
        window.speechSynthesis.cancel();
      }
      setErrorMessage("");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to load alerts right now.";
      setErrorMessage(message);
    } finally {
      if (silent) {
        setIsApplying(false);
      } else {
        setIsLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchAlerts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const allAlerts = useMemo(
    () => (Array.isArray(alertsPayload?.alerts) ? alertsPayload.alerts : []),
    [alertsPayload]
  );

  const filterMatchedAlerts = useMemo(() => {
    const query = String(filters.search || "").trim().toLowerCase();
    const records = allAlerts.filter((alert) => {
      if (filters.onlyMappable && !alert?.location_available) {
        return false;
      }

      if (!query) {
        return true;
      }

      return buildAlertSearchBlob(alert).includes(query);
    });

    records.sort((left, right) => {
      const leftMillis = parseMillis(left?.start_time);
      const rightMillis = parseMillis(right?.start_time);
      if (filters.sortBy === "oldest") {
        return leftMillis - rightMillis;
      }
      return rightMillis - leftMillis;
    });

    const uniqueRecords = [];
    const seenIds = new Set();
    const seenSignatures = new Set();
    const canonicalPositions = new Map();

    records.forEach((alert) => {
      const idKey = String(alert?.id || "").trim().toLowerCase();
      const signature = buildAlertDuplicateSignature(alert);
      const canonicalSignature = buildAlertCanonicalSignature(alert);

      if (idKey && seenIds.has(idKey)) {
        return;
      }
      if (seenSignatures.has(signature)) {
        return;
      }

      const existingCanonicalIndex = canonicalPositions.get(canonicalSignature);
      if (existingCanonicalIndex !== undefined) {
        const previousAlert = uniqueRecords[existingCanonicalIndex];
        const previousMillis = parseMillis(previousAlert?.start_time);
        const incomingMillis = parseMillis(alert?.start_time);
        if (incomingMillis > previousMillis) {
          uniqueRecords[existingCanonicalIndex] = alert;
          if (idKey) {
            seenIds.add(idKey);
          }
          seenSignatures.add(signature);
        }
        return;
      }

      if (idKey) {
        seenIds.add(idKey);
      }
      seenSignatures.add(signature);
      canonicalPositions.set(canonicalSignature, uniqueRecords.length);
      uniqueRecords.push(alert);
    });

    return uniqueRecords;
  }, [allAlerts, filters.onlyMappable, filters.search, filters.sortBy]);

  const visibleAlerts = useMemo(() => {
    if (!selectedSliceLabel) {
      return filterMatchedAlerts;
    }
    return filterMatchedAlerts.filter(
      (alert) => inferAlertCategoryTags(alert).includes(selectedSliceLabel)
    );
  }, [filterMatchedAlerts, selectedSliceLabel]);

  const alertsIn24h = useMemo(() => {
    const now = Date.now();
    const oneDay = 24 * 60 * 60 * 1000;
    return allAlerts.filter((alert) => {
      const millis = parseMillis(alert?.start_time);
      return millis > 0 && now - millis <= oneDay;
    }).length;
  }, [allAlerts]);

  const mappableCount = useMemo(() => {
    if (typeof alertsPayload?.mappable_count === "number") {
      return alertsPayload.mappable_count;
    }
    return allAlerts.filter((alert) => Boolean(alert?.location_available)).length;
  }, [alertsPayload, allAlerts]);

  const categoryCounts = useMemo(() => {
    const seeded = PIE_INDEX_CATEGORIES.map((category) => ({
      label: category.label,
      color: category.color,
      count: 0,
    }));
    const byLabel = new Map(seeded.map((item) => [item.label, item]));

    filterMatchedAlerts.forEach((alert) => {
      const label = inferAlertCategory(alert);
      const target = byLabel.get(label) || byLabel.get("Other");
      if (target) {
        target.count += 1;
      }
    });

    return seeded;
  }, [filterMatchedAlerts]);

  const pieSegments = useMemo(
    () => buildPieSegments(categoryCounts.filter((item) => item.count > 0), filterMatchedAlerts.length),
    [categoryCounts, filterMatchedAlerts.length]
  );

  const selectedPieSegment = useMemo(
    () => pieSegments.find((segment) => segment.label === selectedSliceLabel) || null,
    [pieSegments, selectedSliceLabel]
  );

  const pieLegendRows = useMemo(() => {
    const total = filterMatchedAlerts.length;
    return categoryCounts.map((item, index) => {
      const percentage = total > 0 ? Math.round((item.count / total) * 1000) / 10 : 0;
      return {
        ...item,
        index: index + 1,
        percentage,
      };
    });
  }, [categoryCounts, filterMatchedAlerts.length]);

  const totalPages = Math.max(1, Math.ceil(visibleAlerts.length / PAGE_SIZE));
  const currentPageSafe = Math.min(currentPage, totalPages);
  const pageStart = (currentPageSafe - 1) * PAGE_SIZE;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, visibleAlerts.length);
  const pagedAlerts = visibleAlerts.slice(pageStart, pageEnd);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  useEffect(() => {
    if (!pagedAlerts.length) {
      setExpandedAlertKey("");
      return;
    }

    const hasExpanded = pagedAlerts.some((alert, index) => {
      const rowKey = `${alert?.id || "alert"}-${pageStart + index}`;
      return rowKey === expandedAlertKey;
    });

    if (!hasExpanded) {
      setExpandedAlertKey("");
    }
  }, [expandedAlertKey, pageStart, pagedAlerts]);

  useEffect(() => {
    if (!selectedSliceLabel) {
      return;
    }
    const exists = pieSegments.some((segment) => segment.label === selectedSliceLabel);
    if (!exists) {
      setSelectedSliceLabel("");
    }
  }, [pieSegments, selectedSliceLabel]);

  const topCategory = useMemo(() => {
    if (!categoryCounts.length) {
      return { label: "N/A", count: 0 };
    }
    const highest = categoryCounts.reduce((best, current) =>
      current.count > best.count ? current : best
    );
    if (!highest || highest.count <= 0) {
      return { label: "N/A", count: 0 };
    }
    return highest;
  }, [categoryCounts]);

  const hasSpecificStateFilter = useMemo(() => {
    const selectedState = String(filters.state || "").trim().toLowerCase();
    return Boolean(selectedState && !["india", "all"].includes(selectedState));
  }, [filters.state]);

  const emptyStateMessage = useMemo(() => {
    if (filters.section === "live" && hasSpecificStateFilter) {
      return "No active live alerts for the selected state right now. Switch to History to view archived alerts.";
    }
    return "No alerts matched your current filter/search.";
  }, [filters.section, hasSpecificStateFilter]);

  const noticeTone = useMemo(() => {
    if (!errorMessage) {
      return "error";
    }
    if (/not available/i.test(errorMessage)) {
      return "warning";
    }
    return "error";
  }, [errorMessage]);

  useEffect(() => {
    if (!errorMessage) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setErrorMessage("");
    }, 4500);
    return () => window.clearTimeout(timer);
  }, [errorMessage]);

  const handleApplyFilters = async (event) => {
    event.preventDefault();
    await fetchAlerts({ silent: true });
  };

  const handleRefresh = async () => {
    await fetchAlerts({ silent: true });
  };

  const handleFilterField = (event) => {
    const { name, value, type, checked } = event.target;
    const nextValue = type === "checkbox" ? checked : value;
    setFilters((previous) => {
      const nextFilters = {
        ...previous,
        [name]: nextValue,
      };
      if (name === "dateFrom" && nextFilters.dateTo && nextValue && nextValue > nextFilters.dateTo) {
        nextFilters.dateTo = nextValue;
      }
      if (name === "dateTo" && nextFilters.dateFrom && nextValue && nextValue < nextFilters.dateFrom) {
        nextFilters.dateFrom = nextValue;
      }
      return nextFilters;
    });
    if (name === "onlyMappable") {
      setCurrentPage(1);
      setExpandedAlertKey("");
    }
  };

  const handleNextPage = () => {
    if (currentPageSafe >= totalPages) {
      return;
    }
    if (listenSupported) {
      window.speechSynthesis.cancel();
    }
    setSpeakingAlertKey("");
    setExpandedAlertKey("");
    setCurrentPage((previous) => previous + 1);
  };

  const handlePrevPage = () => {
    if (currentPageSafe <= 1) {
      return;
    }
    if (listenSupported) {
      window.speechSynthesis.cancel();
    }
    setSpeakingAlertKey("");
    setExpandedAlertKey("");
    setCurrentPage((previous) => previous - 1);
  };

  const handleNewAlertsMode = async () => {
    const nextFilters = {
      ...filters,
      section: "live",
      sortBy: "newest",
      onlyMappable: false,
    };
    if (listenSupported) {
      window.speechSynthesis.cancel();
    }
    setSpeakingAlertKey("");
    setFilters(nextFilters);
    await fetchAlerts({ silent: true, nextFilters });
  };

  const handleHistoryMode = async () => {
    const nextFilters = {
      ...filters,
      section: "history",
      sortBy: "newest",
      onlyMappable: false,
    };
    if (listenSupported) {
      window.speechSynthesis.cancel();
    }
    setSpeakingAlertKey("");
    setSelectedSliceLabel("");
    setFilters(nextFilters);
    await fetchAlerts({ silent: true, nextFilters });
  };

  const handleClearFilters = async () => {
    const nextFilters = { ...DEFAULT_FILTERS };
    if (listenSupported) {
      window.speechSynthesis.cancel();
    }
    setSpeakingAlertKey("");
    setExpandedAlertKey("");
    setCurrentPage(1);
    setSelectedSliceLabel("");
    setTranslatedAlertsById({});
    setTranslatedRowKeys({});
    setErrorMessage("");
    setFilters(nextFilters);
    await fetchAlerts({ silent: true, nextFilters });
  };

  const buildAlertMapPath = (alert) => {
    const lat = Number(alert?.lat);
    const lon = Number(alert?.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      return "";
    }

    const params = new URLSearchParams({
      mapLat: String(lat),
      mapLon: String(lon),
      alertType: String(alert?.type || "Alert"),
      alertArea: String(alert?.area || ""),
      alertId: String(alert?.id || ""),
    });
    return `/home?${params.toString()}`;
  };

  const handleSpeakAlert = (rowKey, alert) => {
    if (!listenSupported) {
      setErrorMessage("Listen is not supported in this browser.");
      return;
    }

    if (speakingAlertKey === rowKey) {
      window.speechSynthesis.cancel();
      setSpeakingAlertKey("");
      return;
    }

    const spokenMessage = String(alert?.type || "Alert").trim() || "Alert";

    const utterance = new window.SpeechSynthesisUtterance(spokenMessage);
    utterance.rate = 0.98;
    utterance.pitch = 1;
    utterance.onend = () => setSpeakingAlertKey("");
    utterance.onerror = () => setSpeakingAlertKey("");

    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    setSpeakingAlertKey(rowKey);
    setErrorMessage("");
  };

  const handleSliceSelect = (label) => {
    if (label === "Other") {
      return;
    }
    setCurrentPage(1);
    setExpandedAlertKey("");
    setSpeakingAlertKey("");
    if (listenSupported) {
      window.speechSynthesis.cancel();
    }
    setSelectedSliceLabel((previous) => (previous === label ? "" : label));
  };

  const handleTranslateAlert = async (rowKey, alert) => {
    const alertLookupKey = String(alert?.id || rowKey);
    const originalType = String(alert?.type || "").trim();
    const originalMessage = String(alert?.message || "").trim();

    if (translatedRowKeys[rowKey]) {
      if (speakingAlertKey === rowKey && listenSupported) {
        window.speechSynthesis.cancel();
        setSpeakingAlertKey("");
      }
      setTranslatedRowKeys((previous) => ({
        ...previous,
        [rowKey]: false,
      }));
      return;
    }

    const existingTranslation = translatedAlertsById[alertLookupKey];
    if (existingTranslation) {
      const sameAsOriginal =
        String(existingTranslation.type || "").trim() === originalType &&
        String(existingTranslation.message || "").trim() === originalMessage;
      if (sameAsOriginal) {
        setErrorMessage("Translation is not available for this alert yet.");
        return;
      }
      setTranslatedRowKeys((previous) => ({
        ...previous,
        [rowKey]: true,
      }));
      setErrorMessage("");
      return;
    }

    try {
      setIsTranslating(true);
      const payload = await apiRequest("/mobile/translate-alert", {
        method: "POST",
        body: {
          type: originalType,
          message: originalMessage,
        },
      });

      const selected = {
        type: String(payload?.translated_type || "").trim() || originalType,
        message: String(payload?.translated_message || "").trim() || originalMessage,
      };
      setTranslatedAlertsById((previous) => ({
        ...previous,
        [alertLookupKey]: selected,
      }));

      const sameAsOriginal =
        String(selected.type || "").trim() === originalType &&
        String(selected.message || "").trim() === originalMessage;
      if (sameAsOriginal) {
        setErrorMessage("Translation is not available for this alert yet.");
        return;
      }

      setTranslatedRowKeys((previous) => ({
        ...previous,
        [rowKey]: true,
      }));
      setErrorMessage("");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to translate this alert right now.";
      setErrorMessage(message);
    } finally {
      setIsTranslating(false);
    }
  };

  return (
    <div className={c("page-alerts")}>
      <div className={c("cloud-overlay")} />

      <header className={c("top-nav")}>
        <div className={c("nav-content")} data-mobile-menu={mobileMenuOpen ? "open" : "closed"}>
          <div className={c("nav-left")}>
            <div className={c("logo")}>
              <Link to="/" className={c("logo-container")} style={{ textDecoration: "none" }}>
                <img src="/logo.png" alt="Resqfy Logo" className={c("main-logo")} />
              </Link>
            </div>

            <nav className={c("nav-links")} id="alerts-primary-nav" onClick={() => setMobileMenuOpen(false)}>
              <Link to="/">Home</Link>
              <Link to="/alerts" className={c("active")}>Alerts</Link>
              <Link to="/satellite">Satellite / Geo</Link>
              <Link to="/profile">Profile</Link>
              <Link to="/hill90">Hill90</Link>
            </nav>
          </div>

          <div className={c("nav-right")}>
            <div className={c("theme-toggle")}>
              <button className={c("toggle-btn")} data-theme-toggle aria-label="Toggle theme">
                <svg className={c("sun")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <circle cx={12} cy={12} r={5} />
                  <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
                </svg>
                <div className={c("toggle-track")}><div className={c("toggle-thumb")} /></div>
                <svg className={c("moon")} viewBox="0 0 24 24" fill="currentColor">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              </button>
            </div>

            <button
              className={c("mobile-menu-btn")}
              type="button"
              aria-label="Toggle navigation menu"
              aria-controls="alerts-primary-nav"
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
              <svg className={c("chevron")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </Link>
          </div>
        </div>
      </header>

      <div className={c("dashboard-container alerts-wrapper")}>
        <main className={c("alerts-layout")}>
          <form className={c("panel filter-panel")} onSubmit={handleApplyFilters}>
            <div className={c("filter-header")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              <h2>Filter Alerts</h2>
            </div>

            <div className={c("search-box")}>
              <input
                type="text"
                name="search"
                value={filters.search}
                onChange={handleFilterField}
                placeholder="Search all alert fields..."
              />
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <circle cx={11} cy={11} r={8} />
                <path d="M21 21L16.65 16.65" />
              </svg>
            </div>

            <div className={c("filter-grid")}>
              <div className={c("filter-group")}>
                <label htmlFor="filter-state">State / Region</label>
                <select id="filter-state" name="state" value={filters.state} onChange={handleFilterField}>
                  {STATE_FILTER_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>

              <div className={c("filter-group full-width")}>
                <label htmlFor="filter-date-from">From Date</label>
                <input id="filter-date-from" type="date" name="dateFrom" value={filters.dateFrom} onChange={handleFilterField} />
              </div>

              <div className={c("filter-group full-width")}>
                <label htmlFor="filter-date-to">To Date</label>
                <input id="filter-date-to" type="date" name="dateTo" value={filters.dateTo} onChange={handleFilterField} />
              </div>

              <div className={c("filter-group")}>
                <label htmlFor="filter-severity">Severity</label>
                <select id="filter-severity" name="severity" value={filters.severity} onChange={handleFilterField}>
                  <option value="all">All Severities</option>
                  <option value="watch">Watch</option>
                  <option value="warning">Warning</option>
                  <option value="alert">Alert</option>
                </select>
              </div>

              <div className={c("filter-group")}>
                <label htmlFor="filter-disaster">Disaster Type</label>
                <select id="filter-disaster" name="disasterType" value={filters.disasterType} onChange={handleFilterField}>
                  {DISASTER_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>

              <div className={c("filter-group")}>
                <label htmlFor="filter-sort">Sort By</label>
                <select id="filter-sort" name="sortBy" value={filters.sortBy} onChange={handleFilterField}>
                  <option value="newest">Newest First</option>
                  <option value="oldest">Oldest First</option>
                </select>
              </div>

              <div className={c("filter-group")}>
                <label htmlFor="filter-coverage">Coverage</label>
                <select id="filter-coverage" name="coverage" value={filters.coverage} onChange={handleFilterField}>
                  <option value="india">India</option>
                  <option value="international">International</option>
                  <option value="all">All</option>
                </select>
              </div>

              <div className={c("filter-group")}>
                <label htmlFor="filter-scope">Scope</label>
                <select id="filter-scope" name="scope" value={filters.scope} onChange={handleFilterField}>
                  <option value="official">Official</option>
                  <option value="expanded">Expanded</option>
                </select>
              </div>

              <div className={c("filter-group")}>
                <label htmlFor="filter-limit">Max Records</label>
                <select id="filter-limit" name="limit" value={filters.limit} onChange={handleFilterField}>
                  <option value="50">50</option>
                  <option value="100">100</option>
                  <option value="200">200</option>
                  <option value="500">500</option>
                  <option value="1000">1000</option>
                </select>
              </div>
            </div>

            <label className={c("checkbox-container")}>
              <input type="checkbox" name="onlyMappable" checked={filters.onlyMappable} onChange={handleFilterField} />
              <span className={c("checkmark")} />
              Show only alerts with map location
            </label>

            <div className={c("filter-actions")}>
              <button className={c("apply-btn")} type="submit" disabled={isApplying || isLoading}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <line x1={4} y1={21} x2={4} y2={14} />
                  <line x1={4} y1={10} x2={4} y2={3} />
                  <line x1={12} y1={21} x2={12} y2={12} />
                  <line x1={12} y1={8} x2={12} y2={3} />
                  <line x1={20} y1={21} x2={20} y2={16} />
                  <line x1={20} y1={12} x2={20} y2={3} />
                  <line x1={1} y1={14} x2={7} y2={14} />
                  <line x1={9} y1={8} x2={15} y2={8} />
                  <line x1={17} y1={16} x2={23} y2={16} />
                </svg>
                {isApplying ? "Applying..." : "Apply Filters"}
              </button>
              <button
                type="button"
                className={c("clear-btn")}
                onClick={handleClearFilters}
                disabled={isApplying || isLoading}
              >
                Clear Filters
              </button>
            </div>

            <div className={c("filter-footer")}>
              <span className={c("dot green")} />
              Showing {visibleAlerts.length} filtered alerts
              {" • "}
              Mode: {filters.section === "history" ? "History" : "Live"}
              {" • "}
              Last sync: {formatUtc(alertsPayload?.generated_at)}
            </div>
          </form>

          <div className={c("alerts-content")}>
            <div className={c("alerts-header")}> 
              <h2>
                {filters.section === "history" ? "Alert History (Archive)" : "Live Disaster Alerts"}
                <span className={c("badge active-badge")}>{visibleAlerts.length} Visible</span>
              </h2>

              <button type="button" className={c("refresh-btn")} onClick={handleRefresh} disabled={isApplying || isLoading}>
                {isApplying ? "Refreshing..." : "Refresh"}
              </button>
            </div>

            <div className={c("mode-toolbar")}>
              <button type="button" className={c(`mode-btn new-alerts ${filters.section === "live" ? "active" : ""}`)} onClick={handleNewAlertsMode}>
                Live ({alertsIn24h})
              </button>
              <button type="button" className={c(`mode-btn history-alerts ${filters.section === "history" ? "active" : ""}`)} onClick={handleHistoryMode}>
                History
              </button>
            </div>

            {errorMessage ? <div className={c(`notice-banner ${noticeTone}`)}>{errorMessage}</div> : null}

            <div className={c("stats-grid")}> 
              <div className={c("panel stat-card")}> 
                <div className={c("stat-icon-wrapper red")}> 
                  <div className={c("stat-icon")}> 
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2v20" />
                      <path d="M2 12h20" />
                    </svg>
                  </div>
                </div>
                <div className={c("stat-info")}> 
                  <h3>{allAlerts.length}</h3>
                  <p>Total Alerts (API)</p>
                </div>
              </div>

              <div className={c("panel stat-card")}> 
                <div className={c("stat-icon-wrapper orange")}> 
                  <div className={c("stat-icon")}> 
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="9" />
                      <path d="M12 7v5l3 3" />
                    </svg>
                  </div>
                </div>
                <div className={c("stat-info")}> 
                  <h3>{alertsIn24h}</h3>
                  <p>Alerts in 24h</p>
                </div>
              </div>

              <div className={c("panel stat-card")}> 
                <div className={c("stat-icon-wrapper blue")}> 
                  <div className={c("stat-icon")}> 
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 22s-7-4-7-10a7 7 0 0 1 14 0c0 6-7 10-7 10z" />
                      <circle cx="12" cy="12" r="2.5" />
                    </svg>
                  </div>
                </div>
                <div className={c("stat-info")}> 
                  <h3>{mappableCount}</h3>
                  <p>Map-ready Alerts</p>
                </div>
              </div>

              <div className={c("panel stat-card")}> 
                <div className={c("stat-icon-wrapper purple")}> 
                  <div className={c("stat-icon")}> 
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M4 20h16" />
                      <path d="M6 16l3-4 3 2 3-6 3 5" />
                    </svg>
                  </div>
                </div>
                <div className={c("stat-info")}> 
                  <h3>{topCategory.label}</h3>
                  <p>Top Category ({topCategory.count})</p>
                </div>
              </div>
            </div>

            <div className={c("content-row")}> 
              <div className={c("alerts-feed")}> 
                {isLoading ? <div className={c("panel empty-state")}>Loading live alerts...</div> : null}

                {!isLoading && pagedAlerts.length === 0 ? (
                  <div className={c("panel empty-state")}>
                    <div>{emptyStateMessage}</div>
                    {filters.section === "live" && hasSpecificStateFilter ? (
                      <button type="button" className={c("view-details-btn")} onClick={handleHistoryMode}>
                        Switch to History
                      </button>
                    ) : null}
                  </div>
                ) : null}

                {!isLoading
                  ? pagedAlerts.map((alert, index) => {
                      const absoluteIndex = pageStart + index;
                      const detailEntries = orderedAlertEntries(alert);
                      const iconClass = alertIconClass(alert);
                      const rowKey = `${alert?.id || "alert"}-${absoluteIndex}`;
                      const isExpanded = expandedAlertKey === rowKey;
                      const mapPath = buildAlertMapPath(alert);
                      const isSpeakingThis = speakingAlertKey === rowKey;
                      const alertLookupKey = String(alert?.id || rowKey);
                      const isTranslated = Boolean(translatedRowKeys[rowKey]);
                      const translatedPayload = isTranslated ? translatedAlertsById[alertLookupKey] : null;
                      const titleText = translatedPayload?.type || alert?.type || "Alert";
                      const messageText = translatedPayload?.message || alert?.message || "No alert message provided.";
                      const hasStoredEnglish = Boolean(
                        String(alert?.type_en || "").trim() || String(alert?.message_en || "").trim()
                      );
                      const hasNonEnglishText = !isLikelyEnglishText(`${alert?.type || ""} ${alert?.message || ""}`);
                      const canTranslate = hasStoredEnglish || hasNonEnglishText;
                      const listenRequiresTranslation = hasNonEnglishText && !isTranslated;
                      const listenDisabled = !listenSupported || listenRequiresTranslation;
                      const isTranslatingThis =
                        isTranslating && !translatedAlertsById[alertLookupKey] && !isTranslated;

                      return (
                        <div key={rowKey} className={c("panel alert-feed-card row")}>
                          <div className={c(`icon-box ${iconClass}`)}>{renderAlertIcon(alert)}</div>

                          <div className={c("alert-feed-content")}>
                            <div className={c("feed-header")}>
                              <h4 className={c("card-title")}>
                                {titleText}
                              </h4>
                              <span className={c(`severity-badge ${alertSeverityClass(alert)}`)}>
                                {alert?.severity || "WATCH"}
                              </span>
                            </div>

                            <div className={c("feed-meta")}>
                              <span>{alert?.area || "Area not specified"}</span>
                              <span>{formatUtc(alert?.start_time)}</span>
                              <span className={c("source")}>{alert?.source || "Unknown source"}</span>
                            </div>

                            {isExpanded ? (
                              <div className={c("alert-detail-grid")}>
                                {detailEntries.map(([key, value]) => (
                                  <div key={key} className={c("detail-item")}>
                                    <span className={c("detail-key")}>{humanizeKey(key)}</span>
                                    <strong className={c("detail-value")}>{formatValue(key, value)}</strong>
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </div>

                          <div className={c("card-action")}>
                            <span className={c("region-count")}>
                              {alert?.location_available ? "Map Location: Yes" : "Map Location: No"}
                            </span>
                            <div className={c("card-actions-group")}>
                              <button
                                type="button"
                                className={c(`card-cta listen ${isSpeakingThis ? "active" : ""}`)}
                                disabled={listenDisabled}
                                title={
                                  !listenSupported
                                    ? "Listen is not supported in this browser."
                                    : listenRequiresTranslation
                                      ? "Translate this alert to English before using Listen."
                                      : "Listen to this alert"
                                }
                                onClick={() => handleSpeakAlert(rowKey, { ...alert, type: titleText, message: messageText })}
                              >
                                {isSpeakingThis ? "Stop" : "Listen"}
                              </button>
                              {canTranslate ? (
                                <button
                                  type="button"
                                  className={c(`card-cta translate ${translatedRowKeys[rowKey] ? "active" : ""}`)}
                                  onClick={() => handleTranslateAlert(rowKey, alert)}
                                  disabled={isTranslatingThis}
                                >
                                  {translatedRowKeys[rowKey]
                                    ? "Original"
                                    : isTranslatingThis
                                      ? "Translating..."
                                      : "Translate"}
                                </button>
                              ) : null}
                              {mapPath ? (
                                <Link to={mapPath} className={c("card-cta map")} style={{ textDecoration: "none" }}>
                                  Map
                                </Link>
                              ) : (
                                <button type="button" className={c("card-cta map")} disabled>
                                  Map
                                </button>
                              )}
                              <button
                                type="button"
                                className={c(`view-details-btn ${isExpanded ? "active" : ""}`)}
                                onClick={() =>
                                  setExpandedAlertKey((previous) => (previous === rowKey ? "" : rowKey))
                                }
                              >
                                {isExpanded ? "Hide Details" : "See Details"}
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  : null}

                {!isLoading && visibleAlerts.length > 0 ? (
                  <div className={c("panel pagination-bar")}>
                    <button type="button" className={c("page-btn")} onClick={handlePrevPage} disabled={currentPageSafe <= 1}>
                      Previous
                    </button>
                    <span className={c("page-info")}>Page {currentPageSafe} of {totalPages}</span>
                    <span className={c("page-range")}>
                      Showing {pageStart + 1}-{pageEnd} of {visibleAlerts.length}
                    </span>
                    <button type="button" className={c("page-btn")} onClick={handleNextPage} disabled={currentPageSafe >= totalPages}>
                      Next
                    </button>
                  </div>
                ) : null}
              </div>

              <aside className={c("panel alert-types-panel")}> 
                <div className={c("alert-types-title")}>Live Alert Mix</div>

                <div className={c("pie-chart-container")}> 
                  <svg viewBox="0 0 120 120" className={c("donut-chart live-donut")}> 
                    <circle cx="60" cy="60" r="42" fill="none" stroke="rgba(148,163,184,0.22)" strokeWidth="24" />
                    {pieSegments.map((segment) => (
                      <circle
                        key={segment.label}
                        className={c(
                          `slice-segment ${
                            selectedSliceLabel
                              ? selectedSliceLabel === segment.label
                                ? "slice-active"
                                : "slice-inactive"
                              : ""
                          } ${segment.label === "Other" ? "slice-disabled-other" : ""}`
                        )}
                        cx="60"
                        cy="60"
                        r={segment.radius}
                        fill="none"
                        stroke={segment.color}
                        strokeWidth="24"
                        strokeDasharray={`${segment.length} ${segment.circumference}`}
                        strokeDashoffset={-segment.offset}
                        strokeLinecap="butt"
                        role={segment.label === "Other" ? undefined : "button"}
                        tabIndex={segment.label === "Other" ? -1 : 0}
                        aria-disabled={segment.label === "Other"}
                        aria-label={`${segment.percentage}%`}
                        onClick={() => {
                          if (segment.label !== "Other") {
                            handleSliceSelect(segment.label);
                          }
                        }}
                        onKeyDown={(event) => {
                          if (segment.label !== "Other" && (event.key === "Enter" || event.key === " ")) {
                            event.preventDefault();
                            handleSliceSelect(segment.label);
                          }
                        }}
                      />
                    ))}
                  </svg>

                  <div className={c("donut-center")}> 
                    <strong>{selectedPieSegment ? `${selectedPieSegment.percentage}%` : filterMatchedAlerts.length}</strong>
                    <span>{selectedPieSegment ? "Selected %" : "Live"}</span>
                  </div>
                </div>

                <div className={c("slice-detail")} aria-live="polite">
                  {selectedPieSegment ? (
                    <>
                      <strong className={c("slice-detail-value")}>{selectedPieSegment.label}</strong>
                      <span className={c("slice-detail-text")}>
                        {selectedPieSegment.count} of {filterMatchedAlerts.length} alerts
                      </span>
                    </>
                  ) : (
                    <span className={c("slice-detail-hint")}>Click a pie slice to filter alerts.</span>
                  )}
                </div>

                <ul className={c("chart-legend-list")}> 
                  {pieLegendRows.map((row) => (
                    <li
                      key={row.label}
                      className={c("legend-row")}
                    >
                      <div className={c("legend-index-item")}>
                        <span className={c("legend-left")}>
                          <span className={c("legend-swatch")} style={{ backgroundColor: row.color }} />
                          <span className={c("legend-label")}>{row.label}</span>
                        </span>
                        <span className={c("legend-right")}>{row.count} ({row.percentage}%)</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </aside>
            </div>
          </div>
        </main>

        <footer className={c("app-footer-text")}>
          About Resqfy | Contact Support | Privacy Policy | Terms of Service | © 2026 Resqfy
        </footer>
      </div>
    </div>
  );
}
