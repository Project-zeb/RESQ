// ==========================================
// 1. DATA PROCESSING & UTILITIES
// ==========================================

function aggregateMapData(minY, maxY) {
    const filtered = dfData.filter(d => d.Year >= minY && d.Year <= maxY);
    const grouped = new Map();
    filtered.forEach(d => {
        const zoneName = d.City.split(' ').slice(0, -1).join(' ');
        if (!grouped.has(zoneName)) {
            grouped.set(zoneName, { ...d, ZoneName: zoneName, Events: [d] });
        } else {
            const existing = grouped.get(zoneName);
            existing.Events.push(d);
            if (d.Intensity_Metric > existing.Intensity_Metric) {
                existing.Intensity_Metric = d.Intensity_Metric;
                existing.Max_Vibration_PGA = d.Max_Vibration_PGA;
                existing.Depth_km = d.Depth_km;
                existing.City = d.City; 
            }
        }
    });
    return Array.from(grouped.values());
}

document.getElementById('btn-download').addEventListener('click', () => {
    const replacer = (key, value) => value === null ? '' : value; 
    const header = Object.keys(dfData[0]);
    const csv = [header.join(','), ...dfData.map(row => header.map(f => JSON.stringify(row[f], replacer)).join(','))].join('\r\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a'); a.setAttribute('href', url); a.setAttribute('download', 'resqfy_export.csv'); a.click();
});

function formatRow(label, val, unit='', colorClass='') {
    if (val === undefined || val === null || val === '') return '';
    const displayVal = typeof val === 'number' && val > 100 ? val.toLocaleString() : val;
    return `<div class="card-row"><span class="card-label">${label}</span><span class="card-val ${colorClass}">${displayVal} <span style="font-size:11px; color:#888;">${unit}</span></span></div>`;
}

// ==========================================
// 2. THE 3D ENGINE
// ==========================================

let scene, camera, renderer, controls, currentModel;
let pWaves = [], sWaves = [], rWaves = []; 
let annotationGroup = new THREE.Group(); 
let clippingPlanes = [];
let trackPoints = { surfTarget: null, epiTarget: null, altTop: null, altMid: null, altBot: null };
let activeEpicenterCore = null;

// SMART CACHING VARIABLES to prevent lag during live testing
let currentModelFile = null; 
let blockBoundingBox = null;

function init3DEngine() {
    const container = document.getElementById('geological-3d-canvas');
    scene = new THREE.Scene(); scene.add(annotationGroup);
    camera = new THREE.PerspectiveCamera(35, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.set(15, 8, 20); 
    
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.localClippingEnabled = true; 
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.appendChild(renderer.domElement);
    
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true; controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 + 0.1; 
    controls.enablePan = false; 
    
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4); scene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8); dirLight.position.set(15, 25, 15); scene.add(dirLight);
    const backLight = new THREE.DirectionalLight(0x00d4ff, 0.6); backLight.position.set(-15, -10, -15); scene.add(backLight);
    animate3D();
}

function render3DGeology(pointData) {
    // 1. Determine which model we need
    let modelFile = 'mountain.glb'; // Default
    switch (pointData.Terrain) {
        case 'Forest':     
        case 'Mountain':   modelFile = 'mountain.glb'; break;
        case 'Plain':      
        case 'Plateau':    modelFile = 'city.glb'; break;
        case 'Desert':     modelFile = 'desert.glb'; break;
        case 'Coastal':    modelFile = 'river.glb'; break;
    }

    // 2. Clear old data layers instantly
    const toRemove = scene.children.filter(c => c.name === 'data-layer');
    toRemove.forEach(c => scene.remove(c));
    while(annotationGroup.children.length > 0){ annotationGroup.remove(annotationGroup.children[0]); }
    
    pWaves = []; sWaves = []; rWaves = []; 
    clippingPlanes = []; activeEpicenterCore = null;
    trackPoints = { surfTarget: null, epiTarget: null, altTop: null, altMid: null, altBot: null };
    
    // 3. SMART CHECK: Do we need to load a new .glb?
    if (currentModelFile === modelFile && currentModel) {
        injectDataLayers(pointData);
        return; 
    }

    // 4. STANDALONE LOAD: Use Embedded Base64 Data
    if (currentModel) scene.remove(currentModel);
    currentModelFile = modelFile; 
    
    const glbDataUri = embeddedModels[modelFile]; //
    if (!glbDataUri) {
        console.error("Model data missing internally:", modelFile);
        return;
    }

    const loaderOverlay = document.getElementById('model-loader-overlay');
    const loaderText = document.getElementById('loader-text');
    if (loaderOverlay) {
        loaderOverlay.style.display = 'flex';
        loaderText.style.color = '#00d4ff';
        loaderText.innerHTML = `DECODING INTERNAL ASSET: ${modelFile.toUpperCase()}...`;
    }
    
    const loader = new THREE.GLTFLoader();
    loader.load(
        glbDataUri, 
        function(gltf) {
            if (loaderOverlay) loaderOverlay.style.display = 'none';
            currentModel = gltf.scene;
            
            const box = new THREE.Box3().setFromObject(currentModel);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const scale = 14 / Math.max(size.x, size.y, size.z);
            
            currentModel.scale.set(scale, scale, scale);
            currentModel.position.set(-center.x * scale, -center.y * scale, -center.z * scale);
            scene.add(currentModel);
            
            blockBoundingBox = new THREE.Box3().setFromObject(currentModel);
            injectDataLayers(pointData);
        },
        undefined,
        function(error) {
            currentModelFile = null;
            console.error("Internal Load Error:", error);
            if (loaderText) {
                loaderText.style.color = '#ff3333';
                loaderText.innerHTML = `❌ INTERNAL ERROR: ${modelFile.toUpperCase()}`;
            }
        }
    );
}

// ==========================================
// 3. THE LIVE DATA INJECTOR
// ==========================================

function injectDataLayers(pointData) {
    if (!blockBoundingBox) return;

    const totalHeight = blockBoundingBox.max.y - blockBoundingBox.min.y;
    
    clippingPlanes = [
        new THREE.Plane(new THREE.Vector3(-1, 0, 0), blockBoundingBox.max.x),
        new THREE.Plane(new THREE.Vector3(1, 0, 0), -blockBoundingBox.min.x),
        new THREE.Plane(new THREE.Vector3(0, -1, 0), blockBoundingBox.max.y),
        new THREE.Plane(new THREE.Vector3(0, 1, 0), -blockBoundingBox.min.y),
        new THREE.Plane(new THREE.Vector3(0, 0, -1), blockBoundingBox.max.z),
        new THREE.Plane(new THREE.Vector3(0, 0, 1), -blockBoundingBox.min.z)
    ];
    
    let surfaceHTML = formatRow('Terrain Class', pointData.Terrain);
    surfaceHTML += formatRow('Pop. Impacted', pointData.Affected_Population);
    surfaceHTML += formatRow('Est. Loss', pointData.Economic_Loss_Millions, 'M USD', 'money');
    surfaceHTML += formatRow('Block Matrix ID', pointData.Block_ID.substring(0, 15) + '...');
    document.getElementById('ui-surface-content').innerHTML = surfaceHTML;
    document.getElementById('card-surface').classList.add('active');
    
    let epiHTML = formatRow('Magnitude', pointData.Intensity_Metric, 'Mw', 'alert');
    epiHTML += formatRow('PGA Force', pointData.Max_Vibration_PGA, 'g');
    epiHTML += formatRow('Focal Depth', pointData.Depth_km, 'km', 'alert');
    epiHTML += formatRow('Soil Composition', pointData.Soil_Type);
    epiHTML += formatRow('Coordinates', `${pointData.Lat}, ${pointData.Lon}`);
    document.getElementById('ui-epi-content').innerHTML = epiHTML;
    document.getElementById('card-epicenter').classList.add('active');
    
    const leftEdgeX = blockBoundingBox.min.x - 0.5; 
    const frontEdgeZ = blockBoundingBox.max.z + 0.5;
    const rulerColor = 0x00d4ff;
    
    const pTop = new THREE.Vector3(leftEdgeX, blockBoundingBox.max.y, frontEdgeZ);
    const pMid = new THREE.Vector3(leftEdgeX, blockBoundingBox.max.y - (totalHeight/2), frontEdgeZ);
    const pBot = new THREE.Vector3(leftEdgeX, blockBoundingBox.min.y, frontEdgeZ);
    create3DLine(pBot, pTop, rulerColor, true);
    
    const tickLen = 0.5;
    create3DLine(pTop, new THREE.Vector3(leftEdgeX - tickLen, pTop.y, frontEdgeZ), rulerColor);
    create3DLine(pMid, new THREE.Vector3(leftEdgeX - tickLen, pMid.y, frontEdgeZ), rulerColor);
    create3DLine(pBot, new THREE.Vector3(leftEdgeX - tickLen, pBot.y, frontEdgeZ), rulerColor);
    
    trackPoints.altTop = new THREE.Vector3(leftEdgeX - tickLen, pTop.y, frontEdgeZ);
    trackPoints.altMid = new THREE.Vector3(leftEdgeX - tickLen, pMid.y, frontEdgeZ);
    trackPoints.altBot = new THREE.Vector3(leftEdgeX - tickLen, pBot.y, frontEdgeZ);
    
    if (pointData.Depth_km) {
        const MAX_DEPTH = 80.0; 
        let depthRatio = pointData.Depth_km / MAX_DEPTH;
        if(depthRatio > 1.0) depthRatio = 1.0;
        
        const epiY = blockBoundingBox.max.y - (depthRatio * totalHeight);
        const tEpi = new THREE.Vector3(0, epiY, 0); 
        
        trackPoints.epiTarget = tEpi;
        trackPoints.surfTarget = new THREE.Vector3(0, blockBoundingBox.max.y, 0);
        
        // CAMERA LOCK FIX: Target center of block, not the moving bubble
        controls.target.set(0, blockBoundingBox.max.y - (totalHeight/2), 0);
        controls.update();
        
        const radius = Math.max(0.12, pointData.Intensity_Metric / 45); 
        const sphereGeom = new THREE.SphereGeometry(radius, 32, 32);
        const sphereMat = new THREE.MeshStandardMaterial({ color: 0xff3333, emissive: 0xaa0000, depthTest: false, transparent: true, opacity: 1.0 });
        activeEpicenterCore = new THREE.Mesh(sphereGeom, sphereMat);
        activeEpicenterCore.position.copy(tEpi);
        activeEpicenterCore.name = 'data-layer';
        activeEpicenterCore.renderOrder = 999; 
        scene.add(activeEpicenterCore);
        
        const intensityScale = (pointData.Intensity_Metric / 2.0); 
        
        for(let i=0; i<2; i++) { 
            const waveMat = new THREE.MeshBasicMaterial({ color: 0x88ccff, transparent: true, opacity: 0.3, blending: THREE.AdditiveBlending, depthWrite: false, clippingPlanes: clippingPlanes, clipIntersection: false, side: THREE.DoubleSide });
            const shockwave = new THREE.Mesh(new THREE.SphereGeometry(intensityScale*1.5, 48, 48), waveMat);
            shockwave.position.copy(tEpi); shockwave.name = 'data-layer'; scene.add(shockwave);
            pWaves.push({ mesh: shockwave, progress: i * 0.5, speed: 0.0008 }); 
        }
        for(let i=0; i<3; i++) { 
            const waveMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false, clippingPlanes: clippingPlanes, clipIntersection: false, side: THREE.DoubleSide });
            const shockwave = new THREE.Mesh(new THREE.SphereGeometry(intensityScale, 48, 48), waveMat);
            shockwave.position.copy(tEpi); shockwave.name = 'data-layer'; scene.add(shockwave);
            sWaves.push({ mesh: shockwave, progress: i * 0.33, speed: 0.0003 }); 
        }
        let surfaceY = blockBoundingBox.max.y + 0.05;
        for(let i=0; i<4; i++) {
            const surfGeom = new THREE.RingGeometry(0.1, 0.5, 64);
            const surfMat = new THREE.MeshBasicMaterial({ color: 0xff3333, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
            const surfaceRipple = new THREE.Mesh(surfGeom, surfMat);
            surfaceRipple.rotation.x = -Math.PI / 2; 
            surfaceRipple.position.set(0, surfaceY, 0);
            surfaceRipple.name = 'data-layer'; scene.add(surfaceRipple);
            rWaves.push({ mesh: surfaceRipple, progress: i * 0.25, speed: 0.0005 });
        }
    }
}

// ==========================================
// 4. ANIMATION & OVERLAYS
// ==========================================

function create3DLine(p1, p2, colorHex, isDashed=false) {
    let mat = isDashed ? new THREE.LineDashedMaterial({ color: colorHex, dashSize: 0.2, gapSize: 0.1, linewidth: 2 }) : new THREE.LineBasicMaterial({ color: colorHex, linewidth: 2 });
    const geo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
    const line = new THREE.Line(geo, mat);
    if(isDashed) line.computeLineDistances();
    annotationGroup.add(line);
    return line;
}

function updateHTMLOverlays() {
    const container = document.getElementById('canvas-container');
    const w = container.clientWidth / 2; const h = container.clientHeight / 2;
    const svgLayer = document.getElementById('ui-svg-layer');
    const cardSurf = document.getElementById('card-surface');
    const cardEpi = document.getElementById('card-epicenter');
    
    function project(vec3) {
        let pos = vec3.clone(); pos.project(camera);
        return { x: (pos.x * w) + w, y: -(pos.y * h) + h, visible: pos.z < 1 };
    }

    if (trackPoints.epiTarget) {
        svgLayer.style.opacity = 1;
        if(trackPoints.surfTarget) {
            let pTop = project(trackPoints.surfTarget);
            if(pTop.visible) {
                const surfRect = cardSurf.getBoundingClientRect();
                const contRect = container.getBoundingClientRect();
                const startX = surfRect.right - contRect.left + 10;
                const startY = surfRect.bottom - contRect.top - 20;
                document.getElementById('line-surf').setAttribute('x1', startX);
                document.getElementById('line-surf').setAttribute('y1', startY);
                document.getElementById('line-surf').setAttribute('x2', pTop.x);
                document.getElementById('line-surf').setAttribute('y2', pTop.y);
            }
        }
        let pEpiCore = project(trackPoints.epiTarget);
        if (pEpiCore.visible) {
            const epiRect = cardEpi.getBoundingClientRect();
            const contRect = container.getBoundingClientRect();
            const startX = epiRect.left - contRect.left - 10;
            const startY = epiRect.top - contRect.top + 20;
            document.getElementById('line-epi').setAttribute('x1', startX);
            document.getElementById('line-epi').setAttribute('y1', startY);
            document.getElementById('line-epi').setAttribute('x2', pEpiCore.x);
            document.getElementById('line-epi').setAttribute('y2', pEpiCore.y);
        }
        ['altTop', 'altMid', 'altBot'].forEach(id => {
            if (trackPoints[id]) {
                const p = project(trackPoints[id]);
                let htmlId = id === 'altTop' ? 'alt-label-top' : (id === 'altMid' ? 'alt-label-mid' : 'alt-label-bot');
                const el = document.getElementById(htmlId);
                if (p.visible) { el.style.left = `${p.x}px`; el.style.top = `${p.y}px`; el.style.opacity = 1; } else { el.style.opacity = 0; }
            }
        });
    } else {
        svgLayer.style.opacity = 0;
        ['alt-label-top', 'alt-label-mid', 'alt-label-bot'].forEach(id => document.getElementById(id).style.opacity = 0);
    }
}

function animate3D() {
    requestAnimationFrame(animate3D);
    controls.update();
    
    if (activeEpicenterCore) {
        const pulseScale = 1.0 + 0.1 * Math.sin(Date.now() * 0.003); 
        activeEpicenterCore.scale.set(pulseScale, pulseScale, pulseScale);
    }
    
    pWaves.forEach(ring => {
        ring.progress += ring.speed; 
        if (ring.progress > 1.0) ring.progress = 0;
        const currentScale = 0.05 + (ring.progress * 5.0);
        ring.mesh.scale.set(currentScale, currentScale, currentScale);
        ring.mesh.material.opacity = Math.pow(1.0 - ring.progress, 3.0) * 0.4;
    });

    sWaves.forEach(ring => {
        ring.progress += ring.speed; 
        if (ring.progress > 1.0) ring.progress = 0;
        const currentScale = 0.05 + (ring.progress * 3.5);
        ring.mesh.scale.set(currentScale, currentScale, currentScale);
        const coreColor = new THREE.Color(0xff3333);
        const fadeColor = new THREE.Color(0x330000);
        ring.mesh.material.color.lerpColors(coreColor, fadeColor, ring.progress);
        ring.mesh.material.opacity = Math.pow(1.0 - ring.progress, 2.0) * 0.8;
    });

    rWaves.forEach(wave => {
        wave.progress += wave.speed;
        if(wave.progress > 1.0) wave.progress = 0;
        const currentScale = 0.05 + (wave.progress * 6.0);
        wave.mesh.scale.set(currentScale, currentScale, 1);
        wave.mesh.material.opacity = Math.pow(1.0 - wave.progress, 2.0) * 0.9;
    });
    
    updateHTMLOverlays();
    renderer.render(scene, camera);
}


// ==========================================
// 5. PLOTLY MAPS & TIMELINE
// ==========================================

let currentSectorEvents = [];

function loadSector(aggZoneData) {
    document.getElementById('ui-city').textContent = aggZoneData.ZoneName.toUpperCase();
    document.getElementById('ui-subtext').textContent = "Sector Render Active // Analytical Scan Mode";
    currentSectorEvents = aggZoneData.Events.sort((a, b) => a.Year - b.Year);
    
    const timelineDiv = document.getElementById('sector-timeline');
    let timelineHTML = `<div class="timeline-label" style="font-size:12px; color:#556677; margin-right:10px; font-weight:700;">EVENT HISTORY</div>`;
    currentSectorEvents.forEach((evt, idx) => {
        const isMax = evt.City === aggZoneData.City ? 'active' : '';
        timelineHTML += `<div class="timeline-node ${isMax}" onclick="switchTimelineEvent(${idx})" id="node-${idx}">${evt.Year}</div>`;
    });
    timelineDiv.innerHTML = timelineHTML;
    timelineDiv.classList.add('active');
    
    const maxEventData = currentSectorEvents.find(e => e.City === aggZoneData.City);
    render3DGeology(maxEventData);
}

window.switchTimelineEvent = function(idx) {
    document.querySelectorAll('.timeline-node').forEach(node => node.classList.remove('active'));
    document.getElementById(`node-${idx}`).classList.add('active');
    render3DGeology(currentSectorEvents[idx]);
}

function generateMap(minYear, maxYear) {
    const mapData = aggregateMapData(minYear, maxYear);
    if (mapData.length === 0) return;
    const impactSizes = mapData.map(d => Math.pow(d.Intensity_Metric, 1.2) / 2);
    const maxSize = Math.max(...impactSizes); const minSize = Math.min(...impactSizes);
    const normalizedSizes = impactSizes.map(s => 15 + ((s - minSize) / (maxSize - minSize || 1)) * 30);
    const trace = {
        lat: mapData.map(d => d.Lat), lon: mapData.map(d => d.Lon),
        mode: 'markers', type: 'scattermapbox',
        marker: { size: normalizedSizes, color: mapData.map(d => d.Intensity_Metric), colorscale: configParams.colorScale, showscale: true, opacity: 0.95, line: { color: '#111', width: 1 } },
        text: mapData.map(d => d.ZoneName + ` (Max M${d.Intensity_Metric})`), 
        customdata: mapData.map(d => d.ZoneName), hoverinfo: 'text'
    };
    return { data: [trace], layout: { title: { text: ``, margin: 0 }, mapbox: { style: 'carto-darkmatter', center: { lat: 22.5, lon: 82.0 }, zoom: 4.5 }, paper_bgcolor: '#050505', margin: { r: 0, t: 0, l: 0, b: 0 } } };
}

function generateTrendGraph(zoneName) {
    const zoneData = dfData.filter(d => d.City.startsWith(zoneName));
    const stats = {};
    for (let year = 2007; year <= 2017; year++) {
        const yearData = zoneData.filter(d => d.Year === year);
        stats[year] = yearData.length > 0 ? yearData.reduce((sum, d) => sum + d.Intensity_Metric, 0) / yearData.length : null;
    }
    const years = Object.keys(stats).map(Number); const vals = years.map(y => stats[y]);
    const trace = { x: years, y: vals, name: 'Magnitude', type: 'scatter', mode: 'lines+markers', line: { color: '#00d4ff', width: 2, shape: 'spline' }, connectgaps: true };
    return { data: [trace], layout: { title: { text: `SEISMIC HISTORY: ${zoneName.toUpperCase()}`, font: { color: '#00d4ff', size: 12, family: 'monospace' } }, paper_bgcolor: '#080808', plot_bgcolor: '#080808', font: { color: '#888', size: 10 }, margin: { l: 35, r: 20, t: 35, b: 20 }, yaxis: { gridcolor: '#1a1a1a' }, xaxis: { gridcolor: '#1a1a1a' } } };
}

function updateDashboard() {
    const minYear = parseInt(document.getElementById('year-min').value);
    const maxYear = parseInt(document.getElementById('year-max').value);
    if (minYear <= maxYear) {
        document.getElementById('year-display').textContent = minYear + ' - ' + maxYear;
        Plotly.newPlot('seismic-map', generateMap(minYear, maxYear).data, generateMap(minYear, maxYear).layout, { responsive: true }).then(() => attachMapHoverListener());
    }
}

function attachMapHoverListener() {
    const mapElement = document.getElementById('seismic-map');
    if (mapElement.removeAllListeners) mapElement.removeAllListeners('plotly_hover');
    mapElement.on('plotly_hover', function(data) {
        if (data.points && data.points.length > 0) {
            const hoveredZone = data.points[0].customdata;
            Plotly.newPlot('seismic-trend-graph', generateTrendGraph(hoveredZone).data, generateTrendGraph(hoveredZone).layout, { responsive: true });
            const aggDataMap = aggregateMapData(parseInt(document.getElementById('year-min').value), parseInt(document.getElementById('year-max').value));
            const sectorData = aggDataMap.find(d => d.ZoneName === hoveredZone);
            if (sectorData) loadSector(sectorData);
        }
    });
}

// ==========================================
// 6. LIVE TESTING SANDBOX
// ==========================================

function executeLiveSimulation() {
    const simTerrain = document.getElementById('test-model-select').value;
    const simMag = parseFloat(document.getElementById('test-mag').value);
    const simDepth = parseFloat(document.getElementById('test-depth').value);
    const simPGA = parseFloat(document.getElementById('test-pga').value);
    const simLoss = parseFloat(document.getElementById('test-loss').value);
    const simPop = parseInt(document.getElementById('test-pop').value);

    // Update text displays instantly
    document.getElementById('val-mag').textContent = simMag;
    document.getElementById('val-depth').textContent = simDepth;
    document.getElementById('val-pga').textContent = simPGA;
    document.getElementById('val-loss').textContent = simLoss;
    document.getElementById('val-pop').textContent = simPop.toLocaleString();

    const mockData = {
        Terrain: simTerrain,
        Intensity_Metric: simMag,
        Depth_km: simDepth,
        Max_Vibration_PGA: simPGA,
        Affected_Population: simPop,
        Economic_Loss_Millions: simLoss,
        Block_ID: "SYS_OVERRIDE_MANUAL",
        Soil_Type: "Synthetic Test Base",
        Lat: "0.00",
        Lon: "0.00"
    };

    document.getElementById('ui-city').textContent = "MANUAL OVERRIDE ACTIVE";
    document.getElementById('ui-subtext').textContent = "SIMULATING USER PARAMETERS...";
    document.getElementById('sector-timeline').innerHTML = `<div class="timeline-label" style="font-size:13px; color:#ff3333; font-weight:700; letter-spacing: 2px;">LIVE SIMULATION ENGAGED</div>`;

    render3DGeology(mockData);
}

// ==========================================
// 7. INITIALIZATION
// ==========================================

window.addEventListener('resize', () => {
    if (!camera || !renderer) return;
    const container = document.getElementById('geological-3d-canvas');
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
}, false);

document.addEventListener('DOMContentLoaded', function() {
    init3DEngine();
    Plotly.newPlot('seismic-map', generateMap(2007, 2017).data, generateMap(2007, 2017).layout, { responsive: true }).then(() => attachMapHoverListener());
    
    const firstZone = dfData[0].City.split(' ').slice(0, -1).join(' ');
    Plotly.newPlot('seismic-trend-graph', generateTrendGraph(firstZone).data, generateTrendGraph(firstZone).layout, { responsive: true });
    
    const aggDataMap = aggregateMapData(2007, 2017);
    if(aggDataMap.length > 0) loadSector(aggDataMap[0]);
    
    document.getElementById('year-min').addEventListener('input', updateDashboard);
    document.getElementById('year-max').addEventListener('input', updateDashboard);

    // BIND THE LIVE TESTING EVENTS
    ['test-mag', 'test-depth', 'test-pga', 'test-loss', 'test-pop'].forEach(id => {
        document.getElementById(id).addEventListener('input', executeLiveSimulation);
    });
    document.getElementById('test-model-select').addEventListener('change', executeLiveSimulation);

    // The Mode Toggle Buttons
    document.getElementById('mode-fetched').addEventListener('click', () => {
        document.getElementById('mode-fetched').classList.add('active');
        document.getElementById('mode-testing').classList.remove('active');
        document.getElementById('seismic-map').style.display = 'block';
        document.getElementById('testing-menu').style.display = 'none';
        window.dispatchEvent(new Event('resize')); 
        if(aggDataMap.length > 0) loadSector(aggDataMap[0]);
    });

    document.getElementById('mode-testing').addEventListener('click', () => {
        document.getElementById('mode-testing').classList.add('active');
        document.getElementById('mode-fetched').classList.remove('active');
        document.getElementById('seismic-map').style.display = 'none';
        document.getElementById('testing-menu').style.display = 'flex';
        executeLiveSimulation();
    });
});