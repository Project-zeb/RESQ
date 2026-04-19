const STORAGE_KEY = "resqfy_data";

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function toFinite(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function getDefaultInputs() {
  return {
    rain: 180,
    slope: 12,
    soil: 45
  };
}

export function computeRiskFromInputs(inputs) {
  const rain = clampNumber(toFinite(inputs?.rain, 0), 0, 500);
  const slope = clampNumber(toFinite(inputs?.slope, 0), 0, 45);
  const soil = clampNumber(toFinite(inputs?.soil, 0), 0, 100);

  const flood = clampNumber((rain / 500) * 60 + (soil / 100) * 40, 0, 100);
  const land = clampNumber(
    (rain / 500) * 30 + (slope / 45) * 55 + (soil / 100) * 15,
    0,
    100
  );
  const urb = clampNumber((rain / 500) * 100, 0, 100);
  const infra = clampNumber((rain / 500) * 80 + (soil / 100) * 20, 0, 100);
  const maxThreat = Math.max(flood, land, urb, infra);

  return {
    rain,
    slope,
    soil,
    flood,
    land,
    urb,
    infra,
    maxThreat,
    isCrit: maxThreat > 75
  };
}

function normalizePayload(raw) {
  const defaults = getDefaultInputs();
  const derived = computeRiskFromInputs({
    rain: raw?.rain ?? raw?.inputs?.rain ?? defaults.rain,
    slope: raw?.slope ?? raw?.inputs?.slope ?? defaults.slope,
    soil: raw?.soil ?? raw?.inputs?.soil ?? defaults.soil
  });

  return {
    ...derived,
    updatedAt: Number(raw?.updatedAt) || Date.now()
  };
}

export function readPipelineData() {
  if (typeof window === "undefined" || !window.localStorage) {
    return normalizePayload(null);
  }

  try {
    const text = window.localStorage.getItem(STORAGE_KEY);
    if (!text) {
      return normalizePayload(null);
    }
    return normalizePayload(JSON.parse(text));
  } catch (_error) {
    return normalizePayload(null);
  }
}

export function persistPipelineData(payload) {
  const normalized = normalizePayload(payload);
  if (typeof window !== "undefined" && window.localStorage) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
  }
  return normalized;
}

export function updatePipelineFromInputs(inputs) {
  return persistPipelineData({
    ...computeRiskFromInputs(inputs),
    updatedAt: Date.now()
  });
}

function getActiveThreats(data, threshold = 75) {
  return [
    { name: "Flood", value: toFinite(data?.flood) },
    { name: "Landslide", value: toFinite(data?.land) },
    { name: "Urban Flood", value: toFinite(data?.urb) },
    { name: "Infrastructure", value: toFinite(data?.infra) }
  ].filter((entry) => entry.value > threshold);
}

function buildCombinations(items) {
  const combinations = [];
  const total = 1 << items.length;
  for (let mask = 1; mask < total; mask += 1) {
    const current = [];
    for (let bit = 0; bit < items.length; bit += 1) {
      if (mask & (1 << bit)) {
        current.push(items[bit]);
      }
    }
    combinations.push(current);
  }
  return combinations;
}

export function buildOutcomeScenarios(data) {
  const active = getActiveThreats(data);
  const combinations = buildCombinations(active);

  return combinations.map((scenario, index) => {
    const average = scenario.reduce((sum, item) => sum + item.value, 0) / scenario.length;
    const casualties = Math.round((average / 100) * 160 * scenario.length);
    const loss = Number(((average / 100) * 3.5 * scenario.length).toFixed(1));

    return {
      id: `scenario-${index + 1}`,
      name: scenario.map((item) => item.name).join(" + "),
      average,
      casualties,
      loss
    };
  });
}

export function buildResourceManifest(data) {
  const normalized = normalizePayload(data);
  const isCrit = Boolean(normalized.isCrit);

  return {
    resources: [
      {
        name: "Relief Tents",
        quantity: Math.max(12, Math.round(normalized.urb * 15)),
        unit: "Units"
      },
      {
        name: "Potable Water",
        quantity: Math.max(4500, Math.round(normalized.urb * 400)),
        unit: "Liters"
      },
      {
        name: "Paramedic Teams",
        quantity: Math.max(6, Math.round(normalized.infra / 3)),
        unit: "Teams"
      }
    ],
    agencies: [
      {
        name: "NDRF Alpha Unit",
        lead: "Cmdr. Sharma",
        id: "SI-NDRF-09",
        status: isCrit ? "DEPLOYED" : "STANDBY"
      },
      {
        name: "Health Wing Delta",
        lead: "Dr. Verma",
        id: "SI-HW-14",
        status: isCrit ? "MOBILIZING" : "READY"
      },
      {
        name: "Infra Recovery Corps",
        lead: "Engr. Khan",
        id: "SI-IRC-22",
        status: isCrit ? "ALERTED" : "MONITORING"
      }
    ],
    isCrit
  };
}

