document.addEventListener('DOMContentLoaded', () => {
    // Initialize map
    const map = L.map('map', {
        zoomControl: false // We use our custom controls
    }).setView([22.5937, 78.9629], 5);

    // Add Tile Layer (OpenStreetMap)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap',
        maxZoom: 19
    }).addTo(map);

    // Custom Icons setup based on image references: storm, fire, flood
    const createMarkerIcon = (svgPath, bgColor, iconColor = "white") => {
        return L.divIcon({
            className: 'custom-leaflet-icon',
            html: `<div style="background-color: ${bgColor}; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 2px solid white; position: relative;">
                     <svg viewBox="0 0 24 24" width="16" height="16" fill="${iconColor}" stroke="${iconColor}" stroke-width="1.5">
                        ${svgPath}
                     </svg>
                     <div style="position: absolute; bottom: -6px; left: 50%; transform: translateX(-50%); width: 0; height: 0; border-left: 6px solid transparent; border-right: 6px solid transparent; border-top: 6px solid ${bgColor};"></div>
                   </div>`,
            iconSize: [28, 34],
            iconAnchor: [14, 34]
        });
    };

    const icons = {
        fireRed: createMarkerIcon('<path d="M12 2c-3.5 3.5-5 7.5-5 10a5 5 0 0 0 10 0c0-2.5-1.5-6.5-5-10zM12 22a7 7 0 0 0 7-7c0-2-1-3.5-2-4.5M5 15a7 7 0 0 0 7 7"/>', '#ef4444', 'white'),
        fireOrange: createMarkerIcon('<path d="M12 2c-3.5 3.5-5 7.5-5 10a5 5 0 0 0 10 0c0-2.5-1.5-6.5-5-10zM12 22a7 7 0 0 0 7-7c0-2-1-3.5-2-4.5M5 15a7 7 0 0 0 7 7"/>', '#f97316', 'black'),
        storm: createMarkerIcon('<path d="M11 9.49V2L1 15h10v7.51L21 9h-10z"/>', '#facc15', 'black'),
        cloud: createMarkerIcon('<path d="M17.5 19c.3 0 .5-.1.7-.3.2-.2.3-.5.3-.7s-.1-.5-.3-.7c-.2-.2-.5-.3-.7-.3h-.5c-.1-1.3-.7-2.6-1.7-3.6-1-1-2.3-1.6-3.6-1.7V11c0-.3-.1-.5-.3-.7-.2-.2-.5-.3-.7-.3s-.5.1-.7.3c-.2.2-.3.5-.3.7v.7c-1.3.1-2.6.7-3.6 1.7-1 1-1.6 2.3-1.7 3.6h-.5c-.3 0-.5.1-.7.3-.2.2-.3.5-.3.7s.1.5.3.7c.2.2.5.3.7.3h12z"/>', 'black', '#facc15')
    };

    // Scatter markers roughly matching the provided India map distribution
    const markers = [
        // North
        [34.0, 74.8, icons.cloud], [33.5, 75.2, icons.storm], // Kashmir
        [31.1, 77.1, icons.fireOrange], [30.3, 78.0, icons.storm], [29.9, 78.1, icons.fireRed], [29.0, 79.0, icons.fireRed], // HP/Uttarakhand
        // Central/East
        [27.5, 80.0, icons.fireRed], [26.0, 83.0, icons.storm], [25.5, 84.5, icons.fireOrange],
        [24.5, 86.0, icons.storm], [24.0, 88.0, icons.fireRed], [23.5, 89.0, icons.storm], [22.5, 88.3, icons.storm], // UP/Bihar/Bengal
        // North East
        [27.0, 93.0, icons.storm], [26.5, 94.0, icons.fireOrange], [25.5, 92.5, icons.fireOrange], [24.8, 93.9, icons.fireOrange], [23.8, 91.2, icons.fireOrange],
        // Central / West
        [23.0, 72.0, icons.fireOrange], [22.7, 75.8, icons.fireOrange], [21.5, 79.0, icons.fireOrange], [21.0, 80.0, icons.storm],
        // South
        [19.0, 73.0, icons.storm], [18.5, 73.8, icons.storm], [17.5, 78.0, icons.fireOrange], [17.3, 78.4, icons.storm],
        [15.5, 73.8, icons.storm], [15.0, 74.5, icons.storm], [14.0, 75.0, icons.storm],
        [16.0, 80.5, icons.fireOrange], [16.5, 82.0, icons.fireRed], [15.5, 80.0, icons.storm], [15.0, 79.9, icons.storm],
        [14.5, 78.0, icons.fireRed], [11.0, 77.0, icons.fireOrange]
    ];

    markers.forEach(data => {
        L.marker([data[0], data[1]], {icon: data[2]}).addTo(map);
    });

    // Wire zoom buttons
    const zoomInBtn = document.querySelector('.zoom-plus');
    const zoomOutBtn = document.querySelector('.zoom-minus');

    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', () => map.zoomIn());
    }
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', () => map.zoomOut());
    }
    
    // Wire location button to center map
    const locBtn = document.querySelector('.location-btn');
    if (locBtn) {
        locBtn.addEventListener('click', () => map.setView([22.5937, 78.9629], 5));
    }
});
