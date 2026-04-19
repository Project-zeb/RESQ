// ==========================================
// NDMA STRATEGIC COMMAND: MICRO-LOGISTICS ENGINE
// ==========================================

let scene, camera, renderer, controls;
let balanceGroup; 
let currentBalance = null;
let currentBalanceState = ''; 

// Kinematic Physics State
let swapState = { active: false, phase: 0, pendingModel: null };
let physics = { angle: 0, angleVelocity: 0, angleTarget: 0, yOffset: 0, yVelocity: 0, yTarget: 0 };

let isLiveIntelMode = false;
let currentMissionLevel = 0;

// 1. 3D ENGINE INITIALIZATION (KINEMATIC PIVOT)
function init3DEngine() {
    const container = document.getElementById('geological-3d-canvas');
    scene = new THREE.Scene();
    
    balanceGroup = new THREE.Group();
    scene.add(balanceGroup);
    
    camera = new THREE.PerspectiveCamera(40, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.set(0, 5, 15); 
    
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    container.appendChild(renderer.domElement);
    
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2; 
    controls.enablePan = false;
    
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);
    
    const dirLight = new THREE.DirectionalLight(0x00d4ff, 0.9);
    dirLight.position.set(10, 20, 10);
    scene.add(dirLight);

    const redLight = new THREE.DirectionalLight(0xff3333, 0.5);
    redLight.position.set(-10, 10, -10);
    scene.add(redLight);

    loadBalanceModel('empty', true); 
    animate3D();
}

function loadBalanceModel(state, isInitialLoad = false) {
    if (currentBalanceState === state) return; 
    currentBalanceState = state;

    let modelFile = '';
    switch(state) {
        case 'empty': modelFile = 'balance_empty.glb'; break;
        case 'left':  modelFile = 'balance_left.glb'; break;   
        case 'right': modelFile = 'balance_right.glb'; break;  
        case 'equal': modelFile = 'balance_equal.glb'; break;  
    }

    let modelUrl = `static/models/${modelFile}`;
    if (typeof embeddedModels !== 'undefined' && embeddedModels[state] !== null) {
        modelUrl = embeddedModels[state];
    }

    const loader = new THREE.GLTFLoader();
    loader.load(
        modelUrl,
        function(gltf) {
            let newBalance = gltf.scene;
            
            const box = new THREE.Box3().setFromObject(newBalance);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const scale = 10 / Math.max(size.x, size.y, size.z);
            
            newBalance.scale.set(scale, scale, scale);
            newBalance.position.set(-center.x * scale, -center.y * scale, -center.z * scale);
            
            newBalance.traverse((child) => {
                if (child.isMesh && child.material) {
                    child.material.transparent = false;
                    child.material.depthWrite = true;
                    child.material.needsUpdate = true;
                }
            });

            if (isInitialLoad || !currentBalance) {
                currentBalance = newBalance;
                balanceGroup.add(currentBalance);
            } else {
                swapState.pendingModel = newBalance;
                swapState.active = true;
                swapState.phase = 1; 
                physics.angleTarget = Math.PI / 2; 
                physics.yTarget = -2.0; 
            }
        },
        undefined,
        function(error) { console.error(`Failed to load ${modelFile}.`, error); }
    );
}

function animate3D() {
    requestAnimationFrame(animate3D);
    controls.update();
    
    const springTension = 0.15; 
    const dampening = 0.75;     

    physics.angleVelocity += (physics.angleTarget - physics.angle) * springTension;
    physics.angleVelocity *= dampening;
    physics.angle += physics.angleVelocity;

    physics.yVelocity += (physics.yTarget - physics.yOffset) * (springTension * 0.8);
    physics.yVelocity *= dampening;
    physics.yOffset += physics.yVelocity;

    if (swapState.active) {
        if (swapState.phase === 1) {
            if (physics.angle >= (Math.PI / 2) - 0.1) {
                balanceGroup.remove(currentBalance);
                currentBalance = swapState.pendingModel;
                balanceGroup.add(currentBalance);
                
                physics.angle = -Math.PI / 2;
                physics.angleTarget = 0;
                physics.yTarget = 0;
                swapState.phase = 2;
            }
        } else if (swapState.phase === 2) {
            if (Math.abs(physics.angle) < 0.01 && Math.abs(physics.angleVelocity) < 0.01) {
                physics.angle = 0;
                physics.angleVelocity = 0;
                swapState.active = false;
                swapState.phase = 0;
            }
        }
    }

    balanceGroup.rotation.y = physics.angle;
    balanceGroup.position.y = physics.yOffset;
    if (!swapState.active) balanceGroup.position.y += Math.sin(Date.now() * 0.002) * 0.03;
    
    renderer.render(scene, camera);
}

// 2. HUD & TELEMETRY UPDATES
function updateMeter(id, deployed, required) {
    const lbl = document.getElementById(`lbl-${id}`);
    const bar = document.getElementById(`bar-${id}`);

    if (required === 0) {
        lbl.innerText = "0 / 0 (0%)";
        bar.style.width = "0%";
        bar.style.background = "#222";
        return 100; 
    }

    const pct = (deployed / required) * 100;
    lbl.innerText = `${Math.floor(deployed).toLocaleString()} / ${required.toLocaleString()} (${Math.floor(pct)}%)`;
    bar.style.width = `${Math.min(pct, 100)}%`; 

    if (pct < 90) bar.style.background = "#ff4444"; 
    else if (pct > 120) bar.style.background = "#ffbb00"; 
    else bar.style.background = "#00ff88"; 

    return pct;
}

function updateStrategicBalance() {
    currentMissionLevel = parseInt(document.getElementById('disaster-magnitude').value);
    document.getElementById('target-val').innerText = currentMissionLevel;

    // Base Requirements based on Level
    const reqVols = currentMissionLevel * 5000;
    const reqShelter = currentMissionLevel * 2000;
    const reqMeals = currentMissionLevel * 15000;
    const reqKits = currentMissionLevel * 1000;

    let depVols = 0, depShelter = 0, depMeals = 0, depKits = 0;

    // BUG FIX: Null Safety checks for missing DOM elements
    ngoPool.forEach((ngo, i) => {
        const volEl = document.getElementById(`in-vols-${i}`);
        const shelterEl = document.getElementById(`in-shelter-${i}`);
        const mealsEl = document.getElementById(`in-meals-${i}`);
        const kitsEl = document.getElementById(`in-kits-${i}`);

        depVols += volEl ? (parseInt(volEl.value) || 0) : 0;
        depShelter += shelterEl ? (parseInt(shelterEl.value) || 0) : 0;
        depMeals += mealsEl ? (parseInt(mealsEl.value) || 0) : 0;
        depKits += kitsEl ? (parseInt(kitsEl.value) || 0) : 0;
    });

    const statusText = document.getElementById('balance-status-text');

    if (currentMissionLevel === 0) {
        updateMeter('vols', 0, 0); updateMeter('shelter', 0, 0);
        updateMeter('meals', 0, 0); updateMeter('kits', 0, 0);
        loadBalanceModel('empty');
        statusText.innerText = "SYSTEM STANDBY";
        statusText.style.color = "#888";
        return;
    }

    const pVols = updateMeter('vols', depVols, reqVols);
    const pShelter = updateMeter('shelter', depShelter, reqShelter);
    const pMeals = updateMeter('meals', depMeals, reqMeals);
    const pKits = updateMeter('kits', depKits, reqKits);

    // ADVANCED SURPLUS/DEFICIT ALGORITHM FIX
    const minPct = Math.min(pVols, pShelter, pMeals, pKits);
    const maxPct = Math.max(pVols, pShelter, pMeals, pKits);
    const avgPct = (pVols + pShelter + pMeals + pKits) / 4;

    if (minPct < 90) {
        // Failing condition: At least one critical resource is under-allocated
        loadBalanceModel('left');
        statusText.innerText = "CRITICAL DEFICIT: MISSION COMPROMISED";
        statusText.style.color = "#ff4444";
    } else if (minPct >= 90 && maxPct <= 115) {
        // Optimal condition: All resources are between 90% and 115% fulfilled
        loadBalanceModel('equal');
        statusText.innerText = "OPTIMAL DEPLOYMENT ACHIEVED";
        statusText.style.color = "#00ff88";
    } else if (minPct >= 90 && maxPct > 115 && avgPct <= 150) {
        // Inefficient condition: Nothing is failing, but some resources are heavily over-allocated
        loadBalanceModel('right');
        statusText.innerText = "INEFFICIENT ALLOCATION (PARTIAL SURPLUS)";
        statusText.style.color = "#ffbb00";
    } else {
        // Full Surplus: Massive over-allocation pulling resources from elsewhere unnecessarily
        loadBalanceModel('right');
        statusText.innerText = "FULL SURPLUS: MASSIVE OVER-ALLOCATION";
        statusText.style.color = "#ff8800";
    }
}

// 3. MICRO-LOGISTICS DOM GENERATOR & TWO-WAY BINDING
function bindInputPairs(sliderId, inputId) {
    const s = document.getElementById(sliderId);
    const i = document.getElementById(inputId);
    const maxVal = parseInt(s.max);

    // Slider moves -> Updates Input
    s.addEventListener('input', (e) => {
        i.value = e.target.value;
        updateStrategicBalance();
    });

    // Input types -> Updates Slider
    i.addEventListener('input', (e) => {
        let val = parseInt(e.target.value) || 0;
        if (val > maxVal) val = maxVal; // Prevent exceeding NGO max capacity
        if (val < 0) val = 0;
        i.value = val;
        s.value = val;
        updateStrategicBalance();
    });
}

function initNGOList() {
    const container = document.getElementById('dynamic-ngo-container');
    container.innerHTML = ''; 

    if (typeof ngoPool === 'undefined' || ngoPool.length === 0) return;

    ngoPool.forEach((ngo, i) => {
        // Skip NGOs that have zero resources across the board to save UI space
        if(ngo.resources.vols === 0 && ngo.resources.shelter === 0 && ngo.resources.meals === 0 && ngo.resources.kits === 0) return;

        let cardHTML = `
            <div class="ngo-card">
                <div class="ngo-header">
                    <div class="ngo-name">${ngo.name}</div>
                    <div class="ngo-state">${ngo.state}</div>
                </div>
                <div style="font-size: 10px; color: #00d4ff; margin-bottom: 12px; border-bottom: 1px solid #222; padding-bottom: 5px;">
                    FOCUS: ${ngo.focus}
                </div>`;
        
        // Helper to generate a row only if the NGO has that resource
        const makeRow = (id, label, max) => {
            if (max <= 0) return '';
            return `
                <div class="resource-row">
                    <span class="res-label">${label}</span>
                    <input type="range" class="res-slider" id="sl-${id}-${i}" min="0" max="${max}" value="0">
                    <input type="number" class="res-input" id="in-${id}-${i}" min="0" max="${max}" value="0">
                </div>`;
        };

        cardHTML += makeRow('vols', 'VOLUNTEERS', ngo.resources.vols);
        cardHTML += makeRow('shelter', 'SHELTERS', ngo.resources.shelter);
        cardHTML += makeRow('meals', 'MEALS/DAY', ngo.resources.meals);
        cardHTML += makeRow('kits', 'MED KITS', ngo.resources.kits);
        
        cardHTML += `</div>`;
        container.innerHTML += cardHTML;
    });

    // Bind all the newly created DOM elements
    ngoPool.forEach((ngo, i) => {
        if(ngo.resources.vols > 0) bindInputPairs(`sl-vols-${i}`, `in-vols-${i}`);
        if(ngo.resources.shelter > 0) bindInputPairs(`sl-shelter-${i}`, `in-shelter-${i}`);
        if(ngo.resources.meals > 0) bindInputPairs(`sl-meals-${i}`, `in-meals-${i}`);
        if(ngo.resources.kits > 0) bindInputPairs(`sl-kits-${i}`, `in-kits-${i}`);
    });
}

// 4. NDMA OFFICIAL PDF REPORT EXPORT
document.getElementById('btn-export-pdf').addEventListener('click', () => {
    if (!window.jspdf) {
        alert("PDF Library is still loading. Please try again in a moment.");
        return;
    }

    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();
    
    // Header
    doc.setFontSize(18);
    doc.setTextColor(200, 0, 0);
    doc.text("NDMA OFFICIAL DEPLOYMENT REPORT", 14, 20);
    
    doc.setFontSize(11);
    doc.setTextColor(50, 50, 50);
    doc.text(`Generated: ${new Date().toLocaleString()}`, 14, 28);
    doc.text(`Mission Threat Level: ${currentMissionLevel} / 10`, 14, 34);
    doc.text(`System Status: ${document.getElementById('balance-status-text').innerText}`, 14, 40);

    // Build Data Table of Active NGOs
    const tableBody = [];
    
    // BUG FIX: Null Safety checks for the PDF generator
    ngoPool.forEach((ngo, i) => {
        const vEl = document.getElementById(`in-vols-${i}`);
        const sEl = document.getElementById(`in-shelter-${i}`);
        const mEl = document.getElementById(`in-meals-${i}`);
        const kEl = document.getElementById(`in-kits-${i}`);

        const v = vEl ? (parseInt(vEl.value) || 0) : 0;
        const s = sEl ? (parseInt(sEl.value) || 0) : 0;
        const m = mEl ? (parseInt(mEl.value) || 0) : 0;
        const k = kEl ? (parseInt(kEl.value) || 0) : 0;

        // Only add NGO to report if they are actually deploying something
        if (v > 0 || s > 0 || m > 0 || k > 0) {
            tableBody.push([
                ngo.name,
                v.toLocaleString(),
                s.toLocaleString(),
                m.toLocaleString(),
                k.toLocaleString()
            ]);
        }
    });

    if (tableBody.length === 0) {
        alert("No resources allocated! Please assign resources before exporting a report.");
        return;
    }

    doc.autoTable({
        startY: 50,
        head: [['Organization Name', 'Deployed Vols', 'Shelters', 'Meals', 'Med Kits']],
        body: tableBody,
        theme: 'grid',
        headStyles: { fillColor: [20, 25, 30] },
        styles: { fontSize: 9 }
    });

    doc.save(`NDMA_Deployment_Report_Lvl${currentMissionLevel}.pdf`);
});

// 5. TOGGLES & STARTUP
document.getElementById('mode-toggle').addEventListener('change', function(e) {
    isLiveIntelMode = e.target.checked; 
    const disasterSlider = document.getElementById('disaster-magnitude');
    
    if (isLiveIntelMode) {
        const synthMagnitude = Math.floor(Math.random() * 5) + 5; // Level 5 to 10
        disasterSlider.value = synthMagnitude;
        disasterSlider.disabled = true; 
        document.getElementById('mode-label-live').style.color = "#ff4444";
        document.getElementById('mode-label-war').style.color = "#555";
    } else {
        disasterSlider.value = 0;
        disasterSlider.disabled = false; 
        document.getElementById('mode-label-war').style.color = "#00d4ff";
        document.getElementById('mode-label-live').style.color = "#555";
        
        // Reset all inputs
        document.querySelectorAll('.res-input, .res-slider').forEach(el => el.value = 0);
    }
    updateStrategicBalance();
});

window.addEventListener('resize', () => {
    if (!camera || !renderer) return;
    const container = document.getElementById('geological-3d-canvas');
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
});

document.addEventListener('DOMContentLoaded', () => {
    init3DEngine();
    initNGOList();
    document.getElementById('disaster-magnitude').addEventListener('input', updateStrategicBalance);
});