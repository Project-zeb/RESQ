# exporter.py
import json
import numpy as np
import pandas as pd
import os

def export_dashboard_html(df, config, filename, output_dir=None):
    data_records = df.to_dict('records')
    for record in data_records:
        for key, value in list(record.items()):
            if pd.isna(value): record[key] = None
            elif type(value).__module__ == 'numpy': record[key] = value.item()
    
    data_json = json.dumps(data_records, indent=2)
    
    safe_config = {
        "title": "RESQFY // CYCLONE & STORM SURGE ANALYSIS",
        "color_scale": "Purp",
        "metric_label": "Wind Speed (Kts)"
    }
    config_json = json.dumps(safe_config)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>RESQFY // CYCLONE RECONSTRUCTION</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html, body {{ width: 100%; height: 100%; background-color: #030008; color: #ff00ff; font-family: monospace; display: flex; flex-direction: column; overflow: hidden; }}
        
        .top-bar {{ height: 45px; background: #0a001a; border-bottom: 1px solid #440066; display: flex; justify-content: space-between; align-items: center; padding: 0 25px; z-index: 100; box-shadow: 0 0 15px rgba(255,0,255,0.2); }}
        .header-title {{ color: #ffb3ff; font-size: 18px; letter-spacing: 3px; font-weight: bold; text-shadow: 0 0 10px rgba(255,0,255,0.8); }}
        .btn-download {{ background: #6600cc; color: #fff; border: 1px solid #cc88ff; padding: 8px 18px; font-size: 13px; font-weight: bold; font-family: monospace; cursor: pointer; border-radius: 4px; transition: 0.2s; }}
        .btn-download:hover {{ background: #cc88ff; color: #000; box-shadow: 0 0 20px rgba(204,136,255,0.8); }}
        
        .main-container {{ display: flex; flex: 1; min-height: 0; gap: 10px; padding: 10px; }}
        
        .map-section {{ flex: 0 0 45%; background-color: #05000d; border: 1px solid #330066; border-radius: 6px; overflow: hidden; position: relative; box-shadow: inset 0 0 20px rgba(0,0,0,1); }}
        #seismic-map {{ width: 100% !important; height: 100% !important; }}
        
        .analysis-section {{ flex: 0 0 55%; display: flex; flex-direction: column; gap: 10px; background-color: transparent; }}
        .trend-panel {{ flex: 0 0 25%; background-color: #05000d; border: 1px solid #330066; border-radius: 6px; min-height: 0; box-shadow: inset 0 0 20px rgba(0,0,0,1); }}
        #seismic-trend-graph {{ width: 100% !important; height: 100% !important; }}
        
        .image-panel {{ flex: 0 0 75%; background: radial-gradient(circle at center, #1a0033 0%, #030008 100%); border: 1px solid #440066; border-radius: 6px; position: relative; min-height: 0; overflow: hidden; box-shadow: inset 0 0 80px rgba(0,0,0,0.9); }}
        #geological-3d-canvas {{ width: 100%; height: 100%; outline: none; cursor: move; }}
        
        #ui-svg-layer {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 5; opacity: 0; transition: opacity 0.5s; }}
        
        .data-card {{ position: absolute; background: rgba(5, 0, 10, 0.85); border: 1px solid #440088; padding: 15px 20px; border-radius: 4px; color: #eeccff; font-size: 12px; pointer-events: none; opacity: 0; transition: opacity 0.4s ease; box-shadow: 0 10px 40px rgba(100, 0, 200, 0.2); backdrop-filter: blur(10px); min-width: 260px; z-index: 10; }}
        .data-card.active {{ opacity: 1; }}
        
        #card-surface {{ top: 25px; left: 25px; border-left: 4px solid #cc88ff; }}
        #card-epicenter {{ bottom: 25px; right: 25px; border-right: 4px solid #ff3399; }}
        
        .card-title {{ font-weight: bold; font-size: 15px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 2px; padding-bottom: 8px; border-bottom: 1px solid #440088; }}
        #card-surface .card-title {{ color: #cc88ff; }}
        #card-epicenter .card-title {{ color: #ff3399; text-align: right; }}
        
        .card-row {{ display: flex; justify-content: space-between; gap: 20px; margin-bottom: 8px; }}
        .card-label {{ color: #9966cc; text-transform: uppercase; letter-spacing: 1px; font-size: 10px; }}
        .card-val {{ color: #fff; font-weight: bold; text-align: right; font-size: 13px; font-family: monospace; }}
        .card-val.alert {{ color: #ff3399; text-shadow: 0 0 10px rgba(255,51,153,0.5); font-size: 15px; }}
        .card-val.money {{ color: #ffeb3b; }}
        
        #master-timeline-ui {{ position: absolute; bottom: 25px; left: 25px; background: rgba(5,0,10,0.8); border: 1px solid #440088; padding: 18px 25px; border-radius: 6px; z-index: 10; box-shadow: 0 5px 20px rgba(0,0,0,0.8); border-left: 4px solid #cc88ff; pointer-events: auto; display: flex; align-items: center; gap: 20px; }}
        .sector-info {{ display: flex; flex-direction: column; }}
        #ui-city {{ font-size: 20px; color: #fff; letter-spacing: 2px; margin-bottom: 4px; font-weight: bold; text-shadow: 0 0 20px rgba(204,136,255,0.4);}}
        #ui-subtext {{ color: #cc88ff; font-size: 11px; text-transform: uppercase; letter-spacing: 2px; font-weight: bold; }}
        
        .timeline-container {{ display: flex; gap: 8px; align-items: center; opacity: 0; transition: opacity 0.3s; border-left: 1px solid #440088; padding-left: 20px; }}
        .timeline-container.active {{ opacity: 1; }}
        .timeline-node {{ width: 36px; height: 36px; border-radius: 50%; background: #0a001a; border: 2px solid #440088; color: #9966cc; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; cursor: pointer; transition: 0.2s; box-shadow: inset 0 0 5px rgba(0,0,0,0.8); }}
        .timeline-node:hover {{ border-color: #cc88ff; color: #fff; transform: scale(1.1); }}
        .timeline-node.active {{ background: #cc88ff; border-color: #fff; color: #000; box-shadow: 0 0 15px rgba(204,136,255,0.6); transform: scale(1.1); }}
        
        .control-panel {{ height: 70px; background-color: #05000a; border-top: 1px solid #330066; padding: 15px 50px; display: flex; align-items: center; gap: 25px; flex-shrink: 0; z-index: 20; }}
        .slider-input {{ flex: 1; max-width: 800px; height: 6px; background: #1a0033; border: none; outline: none; -webkit-appearance: none; border-radius: 3px; box-shadow: inset 0 1px 3px rgba(0,0,0,0.8); }}
        .slider-input::-webkit-slider-thumb {{ -webkit-appearance: none; appearance: none; width: 22px; height: 22px; border-radius: 50%; background: #cc88ff; cursor: pointer; transition: 0.2s; box-shadow: 0 0 15px rgba(204,136,255,0.6); border: 2px solid #fff; }}
        
        #model-error-overlay {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; color: #ff3399; display: none; z-index: 50; background: rgba(20,0,10,0.8); padding: 20px; border: 1px solid #ff3399; border-radius: 8px; backdrop-filter: blur(5px); }}
    </style>
</head>
<body>
    <div class="top-bar">
        <div class="header-title">RESQFY // CYCLONE & STORM SURGE ARCHIVE</div>
        <button class="btn-download" id="btn-download">EXPORT REGIONAL DATASET</button>
    </div>

    <div class="main-container">
        <div class="map-section"><div id="seismic-map"></div></div>
        
        <div class="analysis-section">
            <div class="trend-panel"><div id="seismic-trend-graph"></div></div>
            <div class="image-panel" id="canvas-container">
                <div id="geological-3d-canvas"></div>
                
                <div id="model-error-overlay">
                    <h2>3D ASSET PENDING</h2>
                    <p id="error-msg">Awaiting topology model from Asset Team.</p>
                </div>
                
                <svg id="ui-svg-layer">
                    <defs>
                        <marker id="arrow-purp" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto"><polygon points="0 0, 6 3, 0 6" fill="#cc88ff" /></marker>
                        <marker id="arrow-pink" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto"><polygon points="0 0, 6 3, 0 6" fill="#ff3399" /></marker>
                    </defs>
                    <line id="line-surf" x1="0" y1="0" x2="0" y2="0" stroke="#cc88ff" stroke-width="1.5" stroke-dasharray="4" marker-end="url(#arrow-purp)" opacity="1" />
                    <line id="line-epi" x1="0" y1="0" x2="0" y2="0" stroke="#ff3399" stroke-width="1.5" stroke-dasharray="4" marker-end="url(#arrow-pink)" opacity="1" />
                </svg>
                
                <div id="card-surface" class="data-card">
                    <div class="card-title">Coastal Surface Impact</div>
                    <div id="ui-surface-content"></div>
                </div>
                
                <div id="card-epicenter" class="data-card">
                    <div class="card-title">Vortex & Surge Metrics</div>
                    <div id="ui-epi-content"></div>
                </div>
                
                <div id="master-timeline-ui">
                    <div class="sector-info">
                        <div id="ui-city">SYSTEM STANDBY</div>
                        <div id="ui-subtext">Awaiting Coordinate Lock</div>
                    </div>
                    <div id="sector-timeline" class="timeline-container"></div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="control-panel">
        <input type="range" id="year-min" class="slider-input" min="2007" max="2017" value="2007">
        <span id="year-display" style="margin: 0 20px; font-weight: bold; color: #cc88ff; font-size: 18px; letter-spacing: 2px;">2007 - 2017</span>
        <input type="range" id="year-max" class="slider-input" min="2007" max="2017" value="2017">
    </div>

    <script>
        const dfData = {data_json};
        
        const terrainFileMap = {{
            "Coastal Delta": "coastal_delta.glb",
            "Coastal Urban": "coastal_urban.glb",
            "Floodplain": "floodplain.glb",
            "River Valley": "river_valley.glb"
        }};
        
        function aggregateMapData(minY, maxY) {{
            const filtered = dfData.filter(d => d.Year >= minY && d.Year <= maxY);
            const grouped = new Map();
            filtered.forEach(d => {{
                const zoneName = d.City.split(' ').slice(0, -1).join(' ');
                if (!grouped.has(zoneName)) {{
                    grouped.set(zoneName, {{ ...d, ZoneName: zoneName, Events: [d] }});
                }} else {{
                    const existing = grouped.get(zoneName);
                    existing.Events.push(d);
                    if (d.Wind_Speed_Knots > existing.Wind_Speed_Knots) {{
                        existing.Wind_Speed_Knots = d.Wind_Speed_Knots;
                        existing.Pressure_hPa = d.Pressure_hPa;
                        existing.City = d.City; 
                    }}
                }}
            }});
            return Array.from(grouped.values());
        }}

        // --- REALISTIC CLOUD GENERATOR ---
        // Creates a soft, blurry circle to use as a texture so particles look like real clouds
        function createCloudSprite() {{
            const canvas = document.createElement('canvas');
            canvas.width = 64; canvas.height = 64;
            const context = canvas.getContext('2d');
            const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32);
            gradient.addColorStop(0, 'rgba(255, 255, 255, 1)');
            gradient.addColorStop(0.4, 'rgba(255, 255, 255, 0.6)');
            gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
            context.fillStyle = gradient;
            context.fillRect(0, 0, 64, 64);
            return new THREE.CanvasTexture(canvas);
        }}

        let scene, camera, renderer, controls, currentModel;
        
        let cycloneCore = null;
        let lightningLight = null; // Flash simulator
        let surgePlane = null;
        let surgeVertices = [];
        
        let clippingPlanes = [];
        let trackPoints = {{ surfTarget: null, stormTarget: null }};
        let currentSectorEvents = [];
        let currentWindSpeed = 0;
        let cloudTexture;
        
        function init3DEngine() {{
            const container = document.getElementById('geological-3d-canvas');
            scene = new THREE.Scene(); 
            scene.fog = new THREE.FogExp2(0x030008, 0.015);
            
            camera = new THREE.PerspectiveCamera(40, container.clientWidth / container.clientHeight, 0.1, 1000);
            camera.position.set(15, 12, 22); 
            
            renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
            renderer.setSize(container.clientWidth, container.clientHeight);
            renderer.setPixelRatio(window.devicePixelRatio);
            renderer.localClippingEnabled = true;
            container.appendChild(renderer.domElement);
            
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true; controls.dampingFactor = 0.05;
            controls.maxPolarAngle = Math.PI / 2 - 0.1; 
            controls.enablePan = false; 
            
            const ambientLight = new THREE.AmbientLight(0xffffff, 0.2); scene.add(ambientLight);
            const dirLight = new THREE.DirectionalLight(0xffb3ff, 0.6); dirLight.position.set(15, 25, 15); scene.add(dirLight);
            
            cloudTexture = createCloudSprite();
            animate3D();
        }}
        
        function updateHTMLOverlays() {{
            const container = document.getElementById('canvas-container');
            const w = container.clientWidth / 2; const h = container.clientHeight / 2;
            const svgLayer = document.getElementById('ui-svg-layer');
            const cardSurf = document.getElementById('card-surface');
            const cardEpi = document.getElementById('card-epicenter');
            
            function project(vec3) {{
                let pos = vec3.clone(); pos.project(camera);
                return {{ x: (pos.x * w) + w, y: -(pos.y * h) + h, visible: pos.z < 1 }};
            }}

            if (trackPoints.stormTarget) {{
                svgLayer.style.opacity = 1;
                
                if(trackPoints.surfTarget) {{
                    let pTop = project(trackPoints.surfTarget);
                    if(pTop.visible) {{
                        const surfRect = cardSurf.getBoundingClientRect();
                        const contRect = container.getBoundingClientRect();
                        document.getElementById('line-surf').setAttribute('x1', surfRect.right - contRect.left + 10);
                        document.getElementById('line-surf').setAttribute('y1', surfRect.bottom - contRect.top - 20);
                        document.getElementById('line-surf').setAttribute('x2', pTop.x);
                        document.getElementById('line-surf').setAttribute('y2', pTop.y);
                    }}
                }}

                let pStorm = project(trackPoints.stormTarget);
                if (pStorm.visible) {{
                    const epiRect = cardEpi.getBoundingClientRect();
                    const contRect = container.getBoundingClientRect();
                    document.getElementById('line-epi').setAttribute('x1', epiRect.left - contRect.left - 10);
                    document.getElementById('line-epi').setAttribute('y1', epiRect.top - contRect.top + 20);
                    document.getElementById('line-epi').setAttribute('x2', pStorm.x);
                    document.getElementById('line-epi').setAttribute('y2', pStorm.y);
                }}
            }} else {{
                svgLayer.style.opacity = 0;
            }}
        }}
        
        function animate3D() {{
            requestAnimationFrame(animate3D);
            controls.update();
            const time = Date.now() * 0.002;
            
            if (cycloneCore) {{
                // Hurricane Rotation
                const spinSpeed = 0.01 + (currentWindSpeed / 10000); 
                cycloneCore.rotation.y -= spinSpeed;
                
                // Lightning Simulator (Random intense flashes)
                if (lightningLight) {{
                    if (Math.random() > 0.97) {{
                        lightningLight.intensity = 2.0 + Math.random() * 3.0; // Flash!
                        lightningLight.position.x = (Math.random() - 0.5) * 5;
                        lightningLight.position.z = (Math.random() - 0.5) * 5;
                    }} else {{
                        lightningLight.intensity *= 0.8; // Fade out quickly
                    }}
                }}
            }}
            
            if (surgePlane) {{
                const positionAttribute = surgePlane.geometry.getAttribute('position');
                const vertex = new THREE.Vector3();
                for (let i = 0; i < positionAttribute.count; i++) {{
                    vertex.fromBufferAttribute(positionAttribute, i);
                    const wave1 = Math.sin(vertex.x * 3.0 + time * 3) * 0.2;
                    const wave2 = Math.cos(vertex.y * 4.0 - time * 2.5) * 0.15;
                    positionAttribute.setZ(i, surgeVertices[i] + wave1 + wave2);
                }}
                positionAttribute.needsUpdate = true;
            }}
            
            updateHTMLOverlays();
            renderer.render(scene, camera);
        }}
        
        function formatRow(label, val, unit='', colorClass='') {{
            if (val === undefined || val === null || val === '') return '';
            const displayVal = typeof val === 'number' && val > 100 ? val.toLocaleString() : val;
            return `<div class="card-row"><span class="card-label">${{label}}</span><span class="card-val ${{colorClass}}">${{displayVal}} <span style="font-size:11px; color:#9966cc;">${{unit}}</span></span></div>`;
        }}
        
        function loadSector(aggZoneData) {{
            document.getElementById('ui-city').textContent = aggZoneData.ZoneName.toUpperCase();
            document.getElementById('ui-subtext').textContent = "Storm System rendering on Coastal Topology";
            currentSectorEvents = aggZoneData.Events.sort((a, b) => a.Year - b.Year);
            
            const timelineDiv = document.getElementById('sector-timeline');
            let timelineHTML = "";
            
            currentSectorEvents.forEach((evt, idx) => {{
                const isMax = evt.City === aggZoneData.City ? 'active' : '';
                timelineHTML += `<div class="timeline-node ${{isMax}}" onclick="switchTimelineEvent(${{idx}})" id="node-${{idx}}">${{evt.Year}}</div>`;
            }});
            
            timelineDiv.innerHTML = timelineHTML;
            timelineDiv.classList.add('active');
            
            const maxEventData = currentSectorEvents.find(e => e.City === aggZoneData.City);
            render3DGeology(maxEventData);
        }}
        
        window.switchTimelineEvent = function(idx) {{
            document.querySelectorAll('.timeline-node').forEach(node => node.classList.remove('active'));
            document.getElementById(`node-${{idx}}`).classList.add('active');
            render3DGeology(currentSectorEvents[idx]);
        }}

        function render3DGeology(pointData) {{
            if (currentModel) scene.remove(currentModel);
            if (cycloneCore) scene.remove(cycloneCore);
            if (surgePlane) scene.remove(surgePlane);
            
            clippingPlanes = [];
            trackPoints = {{ surfTarget: null, stormTarget: null }};
            currentWindSpeed = pointData.Wind_Speed_Knots;
            
            document.getElementById('card-surface').classList.remove('active');
            document.getElementById('card-epicenter').classList.remove('active');
            document.getElementById('model-error-overlay').style.display = 'none';
            
            let requestedFile = terrainFileMap[pointData.Terrain] || "river.glb";
            
            const loader = new THREE.GLTFLoader();
            loader.load(requestedFile, function(gltf) {{
                currentModel = gltf.scene;
                
                const box = new THREE.Box3().setFromObject(currentModel);
                const center = box.getCenter(new THREE.Vector3());
                const size = box.getSize(new THREE.Vector3());
                const scale = 14 / Math.max(size.x, size.y, size.z);
                
                currentModel.scale.set(scale, scale, scale);
                currentModel.position.set(-center.x * scale, -center.y * scale, -center.z * scale);
                scene.add(currentModel);
                
                let blockBoundingBox = new THREE.Box3().setFromObject(currentModel);
                const totalHeight = blockBoundingBox.max.y - blockBoundingBox.min.y;
                const surfaceY = blockBoundingBox.max.y;
                
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
                surfaceHTML += formatRow('Evacuation Zone', pointData.Block_ID.substring(0, 15));
                document.getElementById('ui-surface-content').innerHTML = surfaceHTML;
                document.getElementById('card-surface').classList.add('active');
                
                let surgeVal = pointData.Storm_Surge_Meters || (pointData.Storm_Category * 1.5);
                
                let epiHTML = formatRow('Storm Category', pointData.Storm_Category, '', 'alert');
                epiHTML += formatRow('Max Sustained', pointData.Wind_Speed_Knots, 'Knots', 'alert');
                epiHTML += formatRow('Storm Surge', surgeVal, 'm', 'alert');
                epiHTML += formatRow('Central Pressure', pointData.Pressure_hPa, 'hPa');
                document.getElementById('ui-epi-content').innerHTML = epiHTML;
                document.getElementById('card-epicenter').classList.add('active');
                
                trackPoints.surfTarget = new THREE.Vector3(0, surfaceY, 0);
                
                // --- STORM SURGE WATER PLANE ---
                const MAX_SURGE_M = 15.0; 
                let surgeRatio = surgeVal / MAX_SURGE_M;
                if(surgeRatio > 1.0) surgeRatio = 1.0;
                
                const waterY = blockBoundingBox.min.y + (surgeRatio * totalHeight);
                const surgeGeo = new THREE.PlaneGeometry(30, 30, 64, 64); 
                surgeVertices = [];
                const pos = surgeGeo.attributes.position.array;
                for(let i=2; i<pos.length; i+=3) {{ surgeVertices.push(pos[i]); }}
                
                const surgeMat = new THREE.MeshPhysicalMaterial({{
                    color: 0x112233, // Moody storm water
                    emissive: 0x050a11,
                    roughness: 0.1, metalness: 0.2, transmission: 0.8,
                    transparent: true, opacity: 0.9,
                    side: THREE.DoubleSide,
                    clippingPlanes: clippingPlanes, clipIntersection: false
                }});
                
                surgePlane = new THREE.Mesh(surgeGeo, surgeMat);
                surgePlane.rotation.x = -Math.PI / 2; 
                surgePlane.position.y = waterY;       
                scene.add(surgePlane);
                
                // --- 🚨 HYPER-REALISTIC VOLUMETRIC CYCLONE 🚨 ---
                cycloneCore = new THREE.Group();
                const stormAltitude = surfaceY + 3.0; 
                cycloneCore.position.set(0, stormAltitude, 0);
                trackPoints.stormTarget = new THREE.Vector3(0, stormAltitude, 0);
                
                let coreColor = new THREE.Color(0xccddff); // Grey/White storm clouds
                if (pointData.Storm_Category >= 5) coreColor = new THREE.Color(0xff4466); // Cat 5 gets a dangerous red tint
                else if (pointData.Storm_Category >= 3) coreColor = new THREE.Color(0xaa66ff); // Purple tint
                
                const particleCount = 20000; // Because we use soft sprites, it looks incredibly dense
                const pGeo = new THREE.BufferGeometry();
                const pPos = new Float32Array(particleCount * 3);
                const pColor = new Float32Array(particleCount * 3);
                
                const numArms = 5; // Spiral Arms
                const eyeRadius = 1.0;
                const stormRadius = 9.0;
                
                for(let i=0; i<particleCount; i++) {{
                    const i3 = i * 3;
                    const armIndex = i % numArms;
                    
                    // Distribute particles outward
                    const r = eyeRadius + Math.pow(Math.random(), 1.5) * (stormRadius - eyeRadius);
                    
                    // Logarithmic spiral angle calculation
                    const spiralAngle = r * 0.8; 
                    let theta = spiralAngle + (armIndex * (Math.PI * 2 / numArms));
                    theta += (Math.random() - 0.5) * 1.5; // Dispersion/thickness of the arm
                    
                    // Height is tallest at the eye wall, tapering off at the edges
                    const distFromEyeWall = Math.abs(r - eyeRadius);
                    const maxHeight = Math.max(0.5, 6.0 - (distFromEyeWall * 0.6));
                    const y = (Math.random() * maxHeight) - (maxHeight / 2);
                    
                    pPos[i3] = r * Math.cos(theta); 
                    pPos[i3+1] = y; 
                    pPos[i3+2] = r * Math.sin(theta); 
                    
                    // Color mapping: Inner wall is bright/tinted, outer bands fade to dark grey
                    const colorIntensity = 1.0 - (distFromEyeWall / stormRadius);
                    const finalColor = coreColor.clone().lerp(new THREE.Color(0x222233), 1.0 - colorIntensity);
                    
                    pColor[i3] = finalColor.r;
                    pColor[i3+1] = finalColor.g;
                    pColor[i3+2] = finalColor.b;
                }}
                
                pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
                pGeo.setAttribute('color', new THREE.BufferAttribute(pColor, 3));
                
                // The magic: mapping our procedural cloud sprite to the particles
                const pMat = new THREE.PointsMaterial({{ 
                    size: 1.5, // Large overlapping sprites
                    map: cloudTexture,
                    vertexColors: true,
                    transparent: true, 
                    opacity: 0.6, 
                    depthWrite: false, // Essential for volumetric look
                    blending: THREE.NormalBlending 
                }});
                
                const cloudMesh = new THREE.Points(pGeo, pMat);
                cycloneCore.add(cloudMesh);
                
                // Add the internal lightning simulator
                lightningLight = new THREE.PointLight(0xffffff, 0, 15);
                cycloneCore.add(lightningLight);
                
                scene.add(cycloneCore);
                
                controls.target.copy(new THREE.Vector3(0, surfaceY, 0));
                controls.update();
                
            }}, undefined, function(e) {{ 
                document.getElementById('model-error-overlay').style.display = 'block';
                document.getElementById('error-msg').textContent = `Missing Coastal File: ${{requestedFile}}`;
            }});
        }}
        
        function generateMap(minYear, maxYear) {{
            const mapData = aggregateMapData(minYear, maxYear);
            if (mapData.length === 0) return;
            
            const impactSizes = mapData.map(d => Math.pow(d.Wind_Speed_Knots, 1.2) / 8);
            const trace = {{
                lat: mapData.map(d => d.Lat), lon: mapData.map(d => d.Lon),
                mode: 'markers', type: 'scattermapbox',
                marker: {{ size: impactSizes, color: mapData.map(d => d.Wind_Speed_Knots), colorscale: 'PuRd', showscale: true, opacity: 0.8, line: {{ color: '#cc88ff', width: 1.5 }} }},
                text: mapData.map(d => d.ZoneName + ` (Max: ${{d.Wind_Speed_Knots}} Kts)`), 
                customdata: mapData.map(d => d.ZoneName), hoverinfo: 'text'
            }};
            return {{ data: [trace], layout: {{
                title: {{ text: ``, margin: 0 }}, mapbox: {{ style: 'carto-darkmatter', center: {{ lat: 18.0, lon: 82.0 }}, zoom: 3.8 }}, paper_bgcolor: '#05000d', margin: {{ r: 0, t: 0, l: 0, b: 0 }}
            }} }};
        }}
        
        function generateTrendGraph(zoneName) {{
            const zoneData = dfData.filter(d => d.City.startsWith(zoneName));
            const stats = {{}};
            for (let year = 2007; year <= 2017; year++) {{
                const yearData = zoneData.filter(d => d.Year === year);
                stats[year] = yearData.length > 0 ? yearData.reduce((sum, d) => sum + d.Wind_Speed_Knots, 0) / yearData.length : null;
            }}
            const years = Object.keys(stats).map(Number); const vals = years.map(y => stats[y]);
            
            const traceWind = {{
                x: years, y: vals, name: 'Wind (Kts)', type: 'scatter', mode: 'lines+markers', fill: 'tozeroy', line: {{ color: '#ff3399', width: 2, shape: 'spline' }}, connectgaps: true 
            }};
            
            return {{ data: [traceWind], layout: {{
                title: {{ text: `WIND VELOCITY HISTORY: ${{zoneName.toUpperCase()}}`, font: {{ color: '#ffb3ff', size: 10, family: 'monospace' }} }},
                paper_bgcolor: '#05000d', plot_bgcolor: '#05000d', font: {{ color: '#aa66cc', size: 9 }},
                margin: {{ l: 35, r: 20, t: 35, b: 20 }}, yaxis: {{ gridcolor: '#330066' }}, xaxis: {{ gridcolor: '#330066' }}
            }} }};
        }}
        
        function updateDashboard() {{
            const minYear = parseInt(document.getElementById('year-min').value);
            const maxYear = parseInt(document.getElementById('year-max').value);
            if (minYear <= maxYear) {{
                document.getElementById('year-display').textContent = minYear + ' - ' + maxYear;
                Plotly.newPlot('seismic-map', generateMap(minYear, maxYear).data, generateMap(minYear, maxYear).layout, {{ responsive: true }}).then(() => attachMapHoverListener());
            }}
        }}
        
        function attachMapHoverListener() {{
            const mapElement = document.getElementById('seismic-map');
            if (mapElement.removeAllListeners) mapElement.removeAllListeners('plotly_hover');
            mapElement.on('plotly_hover', function(data) {{
                if (data.points && data.points.length > 0) {{
                    const hoveredZone = data.points[0].customdata;
                    Plotly.newPlot('seismic-trend-graph', generateTrendGraph(hoveredZone).data, generateTrendGraph(hoveredZone).layout, {{ responsive: true }});
                    
                    const minYear = parseInt(document.getElementById('year-min').value);
                    const maxYear = parseInt(document.getElementById('year-max').value);
                    const aggDataMap = aggregateMapData(minYear, maxYear);
                    const sectorData = aggDataMap.find(d => d.ZoneName === hoveredZone);
                    
                    if (sectorData) loadSector(sectorData);
                }}
            }});
        }}
        
        window.addEventListener('resize', () => {{
            if (!camera || !renderer) return;
            const container = document.getElementById('geological-3d-canvas');
            camera.aspect = container.clientWidth / container.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(container.clientWidth, container.clientHeight);
        }}, false);
        
        document.addEventListener('DOMContentLoaded', function() {{
            init3DEngine();
            Plotly.newPlot('seismic-map', generateMap(2007, 2017).data, generateMap(2007, 2017).layout, {{ responsive: true }}).then(() => attachMapHoverListener());
            
            const firstZone = dfData[0].City.split(' ').slice(0, -1).join(' ');
            Plotly.newPlot('seismic-trend-graph', generateTrendGraph(firstZone).data, generateTrendGraph(firstZone).layout, {{ responsive: true }});
            
            const aggDataMap = aggregateMapData(2007, 2017);
            if(aggDataMap.length > 0) loadSector(aggDataMap[0]);
            
            document.getElementById('year-min').addEventListener('input', updateDashboard);
            document.getElementById('year-max').addEventListener('input', updateDashboard);
        }});
    </script>
</body>
</html>"""
    
    if output_dir is None: output_dir = '.'
    if not os.path.exists(output_dir) and output_dir != '.': os.makedirs(output_dir)
    output_path = os.path.join(output_dir, filename)
    with open(output_path, 'w', encoding='utf-8') as f: f.write(html_content)
    
    print(f"✅ EXPORT SUCCESS: {filename}")
    return output_path