// ═══════════════════════════════════════════════════════
// MUMBAI SAFE ROUTE NAVIGATOR - COMPLETE MAP.JS
// ═══════════════════════════════════════════════════════

let map;
let routeLayers = [];
let accidentMarkers = [];
let currentRoutes = [];
let accidentReportMode = false;
let tempAccidentMarker = null;
let selectedAccidentLocation = null;
let selectedRouteId = null;
let userMarker = null;
let geocoder = null;
let riskChart = null;
let riskHeatmapLayer = null;
let currentCity = 'mumbai';

// ═══════════════════════════════════════════════════════
// 🚗 VEHICLE CONFIG
// ═══════════════════════════════════════════════════════

const VEHICLE_INFO = {
    car: { text: 'Cars are baseline. Standard risk applies.' },
    bike: { text: '🏍️ Bikes are 1.8x more risky.' },
    auto: { text: '🛺 Auto rickshaws are 1.5x more risky.' },
    bus: { text: '🚌 Buses are 1.2x more risky.' },
    truck: { text: '🚚 Trucks are 1.3x more risky.' }
};

// ═══════════════════════════════════════════════════════
// MAP INITIALIZATION
// ═══════════════════════════════════════════════════════

function initMap() {
    const mapElement = document.getElementById('map');
    if (!mapElement) {
        console.error('Map element not found');
        return;
    }

    // 🎨 BASE TILES
    const darkTile = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap contributors © CARTO',
        maxZoom: 18
    });

    const streetTile = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    });

    const satelliteTile = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles © Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EBP, and the GIS User Community'
    });

    // Default to Mumbai center
    map = L.map('map', {
        center: [19.0760, 72.8777],
        zoom: 11,
        layers: [streetTile],
        zoomControl: false // We'll add it manually to position it better
    });

    // Add zoom control at top right
    L.control.zoom({ position: 'topright' }).addTo(map);

    // 🛠️ LAYER CONTROL
    const baseMaps = {
        "Dark Mode": darkTile,
        "Standard Streets": streetTile,
        "Satellite View": satelliteTile
    };

    L.control.layers(baseMaps, null, { position: 'bottomright' }).addTo(map);

    // Resize Observer to handle dynamic height changes
    const resizeObserver = new ResizeObserver(() => {
        if (map) map.invalidateSize();
    });
    resizeObserver.observe(mapElement);

    // Initialize Geocoder
    geocoder = L.Control.Geocoder.nominatim();

    // Map Click Listener for Accident Reporting
    map.on('click', function (e) {
        if (!accidentReportMode) return;

        selectedAccidentLocation = e.latlng;

        if (tempAccidentMarker) {
            map.removeLayer(tempAccidentMarker);
        }

        tempAccidentMarker = L.marker(e.latlng).addTo(map);

        document.getElementById('accidentReportForm').style.display = 'block';
        document.getElementById('accidentLocationPreview').textContent =
            `${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`;
    });

    // Initialize city selector
    initCitySelector();

    // Final check for size
    setTimeout(() => map.invalidateSize(), 500);
}

async function initCitySelector() {
    const selector = document.getElementById('citySelector');
    if (!selector) return;

    selector.addEventListener('change', async (e) => {
        const cityId = e.target.value;
        await switchCity(cityId);
    });

    // Load initial city locations
    await loadLocationsForCity(currentCity);
}

async function switchCity(cityId) {
    currentCity = cityId;

    // Clear existing map data
    routeLayers.forEach(l => map.removeLayer(l));
    routeLayers = [];
    accidentMarkers.forEach(m => map.removeLayer(m));
    accidentMarkers = [];
    if (riskHeatmapLayer) {
        map.removeLayer(riskHeatmapLayer);
        riskHeatmapLayer = null;
        const heatmapBtn = document.getElementById('heatmapToggle');
        if (heatmapBtn) {
            heatmapBtn.innerHTML = '<i class="fas fa-layer-group"></i> Show Risk Heatmap';
            heatmapBtn.classList.remove('heatmap-active');
        }
    }

    // Reset route results
    document.getElementById('routeResults').style.display = 'none';
    document.getElementById('routeDetails').style.display = 'none';
    const forecastSection = document.getElementById('riskForecastSection');
    if (forecastSection) forecastSection.style.display = 'none';

    try {
        const response = await fetch(`/api/locations?city=${cityId}`);
        const data = await response.json();

        if (data.success) {
            // Update map view
            map.setView(data.center, data.zoom || 11);

            // Update dropdowns
            updateLocationDropdowns(data.locations);

            // Update location count stat
            const count = Object.keys(data.locations).length;
            document.getElementById('cityLocationCount').textContent = `${count} locations available`;

            // Reload accidents for this city
            loadActiveAccidents();

            showToast('success', `Switched to ${data.city_name}`);
        }
    } catch (err) {
        console.error('Failed to switch city:', err);
        showToast('error', 'Failed to load city data');
    }
}

async function loadLocationsForCity(cityId) {
    try {
        const response = await fetch(`/api/locations?city=${cityId}`);
        const data = await response.json();
        if (data.success) {
            updateLocationDropdowns(data.locations);
            const count = Object.keys(data.locations).length;
            document.getElementById('cityLocationCount').textContent = `${count} locations available`;
        }
    } catch (err) {
        console.error('Failed to load locations:', err);
    }
}

function updateLocationDropdowns(locations) {
    const startSelect = document.getElementById('startLocation');
    const endSelect = document.getElementById('endLocation');

    if (!startSelect || !endSelect) return;

    // Clear and add placeholder
    const placeholder = '<option value="" disabled selected>Select point...</option>';
    startSelect.innerHTML = placeholder;
    endSelect.innerHTML = placeholder;

    // Add new locations
    Object.keys(locations).sort().forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        startSelect.appendChild(opt.cloneNode(true));
        endSelect.appendChild(opt);
    });
}

// ═══════════════════════════════════════════════════════
// 🔍 SEARCH & GEOLOCATION
// ═══════════════════════════════════════════════════════




// ═══════════════════════════════════════════════════════
// ROUTE FORM SUBMISSION
// ═══════════════════════════════════════════════════════

document.getElementById('routeForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();

    const start = document.getElementById('startLocation').value;
    const end = document.getElementById('endLocation').value;
    const vehicleType = document.getElementById('vehicleType')?.value || 'car';

    if (!start || !end) {
        showToast('error', 'Select both locations');
        return;
    }

    if (start === end) {
        showToast('error', 'Starting point and destination cannot be the same');
        return;
    }

    const loader = document.getElementById('loadingIndicator');
    if (loader) loader.style.display = 'block';

    // Reveal the Save and Share buttons
    const saveBtn = document.getElementById('saveFavoriteBtn');
    const shareBtn = document.getElementById('shareWhatsAppBtn');
    if (saveBtn) saveBtn.style.display = 'block';
    if (shareBtn) shareBtn.style.display = 'block';

    try {
        const response = await fetch('/api/routes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start: document.getElementById('startLocation').dataset.latlng ?
                    JSON.parse(document.getElementById('startLocation').dataset.latlng) : start,
                end: document.getElementById('endLocation').dataset.latlng ?
                    JSON.parse(document.getElementById('endLocation').dataset.latlng) : end,
                vehicle_type: vehicleType,
                city: currentCity
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to load routes');
        }

        currentRoutes = data.routes || [];

        if (currentRoutes.length === 0) {
            showToast('info', 'No routes found for this journey.');
            return;
        }

        displayRoutes(data.routes);
        displayRouteCards(data.routes);

        const rec = data.routes.find(r => r.recommended);
        if (rec) {
            selectRoute(rec.id);
            showRouteDetails(rec);
        }

    } catch (err) {
        showToast('error', err.message || 'Failed to load routes');
    } finally {
        const loader = document.getElementById('loadingIndicator');
        if (loader) loader.style.display = 'none';
    }

    // New: Fetch Time-Based Risk Forecast
    fetchTimeRisk(start, end, vehicleType);
});

// ═══════════════════════════════════════════════════════
// TIME-BASED RISK FORECAST (CHART.JS)
// ═══════════════════════════════════════════════════════

async function fetchTimeRisk(start, end, vehicleType) {
    try {
        const response = await fetch('/api/time-risk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start, end, vehicle_type: vehicleType, city: currentCity })
        });
        const data = await response.json();
        if (data.predictions) {
            renderRiskChart(data.predictions, data.optimal_time);
            const section = document.getElementById('riskForecastSection') || document.getElementById('routeDetails');
            if (section) section.style.display = 'block';
        }
    } catch (err) {
        console.error('Failed to fetch time-based risk:', err);
    }
}

function renderRiskChart(predictions, optimal) {
    const ctx = document.getElementById('riskChart').getContext('2d');

    if (riskChart) {
        riskChart.destroy();
    }

    const labels = predictions.map(p => p.hour);
    const scores = predictions.map(p => p.risk_score);

    // Determine chart colors based on risk levels
    const bgGradient = ctx.createLinearGradient(0, 0, 0, 300);
    bgGradient.addColorStop(0, 'rgba(56, 239, 125, 0.4)');
    bgGradient.addColorStop(1, 'rgba(56, 239, 125, 0.0)');

    riskChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Route Risk Score (%)',
                data: scores,
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                fill: true,
                tension: 0.4,
                borderWidth: 2,
                pointBackgroundColor: '#6366f1',
                pointBorderColor: '#fff',
                pointHoverRadius: 6,
                pointRadius: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0f172a',
                    titleFont: { family: 'Outfit', size: 13 },
                    bodyFont: { family: 'Inter', size: 12 },
                    padding: 10,
                    cornerRadius: 8,
                    displayColors: false,
                    callbacks: {
                        label: (context) => `Risk: ${context.parsed.y}%`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: 'rgba(0, 0, 0, 0.05)' },
                    ticks: { color: '#475569', font: { family: 'Inter', size: 10 } }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#475569', font: { family: 'Inter', size: 10 } }
                }
            }
        }
    });

    // Update optimal time badge
    const badge = document.getElementById('optimalTimeBadge');
    if (optimal.offset === 0) {
        badge.innerHTML = `<span class="security-badge">Optimal: Leave Now</span>`;
    } else {
        const riskDiff = (predictions[0].risk_score - optimal.risk_score).toFixed(0);
        badge.innerHTML = `<span class="security-badge" style="color:var(--accent-primary); background:var(--accent-primary-glow)">
            ${optimal.hour} (${riskDiff}% safer)</span>`;
    }
}

// Handle departure range slider
document.getElementById('departureSlider')?.addEventListener('input', (e) => {
    const val = parseInt(e.target.value);
    const label = document.getElementById('departureTimeLabel');
    if (val === 0) {
        label.textContent = 'Now';
    } else {
        const now = new Date();
        now.setHours(now.getHours() + val);
        label.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
});

// ═══════════════════════════════════════════════════════
// 🌡️ ROUTE RISK HEATMAP
// ═══════════════════════════════════════════════════════

async function toggleRiskHeatmap() {
    const btn = document.getElementById('heatmapToggle');

    if (riskHeatmapLayer && map.hasLayer(riskHeatmapLayer)) {
        map.removeLayer(riskHeatmapLayer);
        btn.innerHTML = '<i class="fas fa-layer-group"></i> Show Risk Heatmap';
        btn.classList.remove('heatmap-active');
        return;
    }

    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading Heatmap...';

    if (!riskHeatmapLayer) {
        try {
            const resp = await fetch(`/api/heatmap-data?city=${currentCity}`);
            const data = await resp.json();

            if (data.success) {
                riskHeatmapLayer = L.featureGroup();

                data.segments.forEach(seg => {
                    const score = seg.risk_score;
                    // Color gradient: Green (0) -> Yellow (50) -> Red (100)
                    const color = score < 30 ? '#28a745' : (score < 60 ? '#ffc107' : '#dc3545');

                    const poly = L.polyline(seg.coords, {
                        color: color,
                        weight: 5,
                        opacity: 0.7,
                        lineCap: 'round'
                    });

                    poly.bindPopup(`<strong>${seg.name}</strong><br>Risk Score: ${score}%`);
                    poly.on('mouseover', function () { this.setStyle({ opacity: 1, weight: 8 }); });
                    poly.on('mouseout', function () { this.setStyle({ opacity: 0.7, weight: 5 }); });

                    riskHeatmapLayer.addLayer(poly);
                });
            }
        } catch (e) {
            console.error('Heatmap load failed:', e);
            showToast('error', 'Failed to load heatmap data');
            btn.innerHTML = '<i class="fas fa-layer-group"></i> Show Risk Heatmap';
            return;
        }
    }

    riskHeatmapLayer.addTo(map);
    btn.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Risk Heatmap';
    btn.classList.add('heatmap-active');
}

document.getElementById('heatmapToggle')?.addEventListener('click', toggleRiskHeatmap);

// ═══════════════════════════════════════════════════════
// DISPLAY ROUTES ON MAP & UI
// ═══════════════════════════════════════════════════════

function getRiskColor(score) {
    if (score <= 35) return '#28a745'; // Green
    if (score <= 65) return '#ffc107'; // Yellow
    return '#dc3545'; // Red
}

function displayRoutes(routes) {
    routeLayers.forEach(l => map.removeLayer(l));
    routeLayers = [];

    routes.forEach(route => {
        const routeGroup = L.featureGroup().addTo(map);

        // Draw individual segments with different colors
        for (let i = 0; i < route.waypoints.length - 1; i++) {
            const segmentCoords = [route.waypoints[i], route.waypoints[i + 1]];
            const segmentRisk = route.risk_details[i] ? route.risk_details[i].risk : route.risk_score;
            const roadName = route.risk_details[i] ? route.risk_details[i].road : "Unknown Segment";

            const poly = L.polyline(segmentCoords, {
                color: getRiskColor(segmentRisk),
                weight: route.selected ? 8 : 5,
                opacity: route.selected ? 1.0 : 0.7,
                smoothFactor: 1
            }).addTo(routeGroup);

            // Add tooltip with risk info
            poly.bindTooltip(`
                <div class="risk-tooltip">
                    <strong>${roadName}</strong><br>
                    <span>Risk Level: ${segmentRisk}%</span>
                </div>
            `, { sticky: true });

            poly.on('click', (e) => {
                L.DomEvent.stopPropagation(e);
                selectRoute(route.id);
                showRouteDetails(route);
            });
        }

        routeGroup.on('click', () => {
            selectRoute(route.id);
            showRouteDetails(route);
        });

        routeLayers.push(routeGroup);
    });

    if (routes.length > 0) {
        map.fitBounds(routes[0].waypoints, { padding: [50, 50] });
    }
}

function selectRoute(routeId) {
    selectedRouteId = routeId;

    // Update route cards UI
    const allCards = document.querySelectorAll('.route-card');
    allCards.forEach(card => {
        const cardRouteId = parseInt(card.dataset.routeId);
        if (cardRouteId === routeId) {
            card.classList.add('route-card-selected');
        } else {
            card.classList.remove('route-card-selected');
        }
    });

    // Update map polylines
    routeLayers.forEach(layer => {
        if (layer.options && layer.options.routeId === routeId) {
            layer.setStyle({ weight: 8, opacity: 1.0 });
            layer.bringToFront();
        } else {
            layer.setStyle({ weight: 4, opacity: 0.5 });
        }
    });
}

function displayRouteCards(routes) {
    const container = document.getElementById('routeCards');
    container.innerHTML = '';

    routes.forEach(route => {
        const card = document.createElement('div');
        card.className = `route-card ${selectedRouteId === route.id ? 'route-card-selected' : ''}`;
        card.dataset.routeId = route.id;

        const riskColorClass = route.risk_level === 'low' ? 'text-success' : (route.risk_level === 'medium' ? 'text-warning' : 'text-danger');

        card.innerHTML = `
            <h6>${route.name} ${route.recommended ? '<small class="text-success ms-2"><i class="fas fa-check-circle"></i></small>' : ''}</h6>
            <div class="route-meta">
                <span><i class="fas fa-clock me-1"></i> ${route.time_minutes} min</span>
                <span><i class="fas fa-road me-1"></i> ${route.distance_km} km</span>
                <span class="route-risk-val ${riskColorClass}">${route.road_risk || route.risk_score}% Road Risk</span>
            </div>
        `;

        card.onclick = () => {
            selectRoute(route.id);
            showRouteDetails(route);
        };

        container.appendChild(card);
    });

    document.getElementById('routeResults').style.display = 'block';
}

function showRouteDetails(route) {
    const container = document.getElementById('detailsContent');
    const riskColorClass = route.risk_level === 'low' ? 'text-success' : (route.risk_level === 'medium' ? 'text-warning' : 'text-danger');

    container.innerHTML = `
        <div class="mb-3">
            <h4 class="outfit-font fw-bold ${riskColorClass}">${route.road_risk || route.risk_score}% Inherent Road Risk</h4>
            <p class="text-secondary small mb-0">${route.name} segments analysis</p>
        </div>
        
        <div class="row g-2">
            <div class="col-6">
                <div class="city-card p-2">
                    <span class="stat-label" style="font-size: 0.6rem;">Est. Time</span>
                    <div class="stat-value" style="font-size: 0.9rem;"><i class="fas fa-clock text-primary me-1"></i>${route.time_minutes}m</div>
                </div>
            </div>
            <div class="col-6">
                <div class="city-card p-2">
                    <span class="stat-label" style="font-size: 0.6rem;">Distance</span>
                    <div class="stat-value" style="font-size: 0.9rem;"><i class="fas fa-road text-info me-1"></i>${route.distance_km}km</div>
                </div>
            </div>
            <div class="col-12">
                <div class="city-card p-2" style="border-color: var(--accent-primary); background: rgba(59, 130, 246, 0.05);">
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="stat-label" style="font-size: 0.6rem;">Vehicle Vulnerability</span>
                        <span class="badge bg-primary" style="font-size: 0.6rem;">+${route.vehicle_vulnerability || 0}% Info</span>
                    </div>
                    <div class="stat-value text-primary" style="font-size: 0.9rem;">
                        <i class="fas fa-shield-halved me-1"></i>
                        ${route.vehicle_info?.vehicle_name || 'Vehicle'} specific factor
                    </div>
                </div>
            </div>
            ${route.weather_data ? `
            <div class="col-12">
                <div class="city-card p-2">
                    <span class="stat-label" style="font-size: 0.6rem;">Atmospheric Impact</span>
                    <div class="stat-value d-flex align-items-center gap-2" style="font-size: 0.9rem;">
                        <span><i class="fas fa-cloud-sun text-warning me-1"></i>${route.weather_data.weather_category}</span>
                    </div>
                </div>
            </div>` : ''}
        </div>
    `;

    document.getElementById('routeDetails').style.display = 'block';
}

// ═══════════════════════════════════════════════════════
// ACCIDENT REPORTING & DISPLAY
// ═══════════════════════════════════════════════════════

document.getElementById('enableReportMode')?.addEventListener('click', () => {
    accidentReportMode = true;
    showToast('success', 'Click on map to report accident');
});

document.getElementById('submitAccidentReport')?.addEventListener('click', async () => {
    if (!selectedAccidentLocation) {
        showToast('error', 'Select location first');
        return;
    }

    const severity = document.getElementById('accidentSeverity').value;
    const desc = document.getElementById('accidentDescription')?.value || '';

    try {
        await fetch('/api/accidents/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                latitude: selectedAccidentLocation.lat,
                longitude: selectedAccidentLocation.lng,
                severity: severity,
                description: desc,
                city: currentCity
            })
        });

        showToast('success', 'Accident reported successfully');
        cancelAccidentReport();
        loadActiveAccidents();
    } catch (err) {
        showToast('error', 'Failed to report accident');
    }
});

function cancelAccidentReport() {
    accidentReportMode = false;
    selectedAccidentLocation = null;

    if (tempAccidentMarker) {
        map.removeLayer(tempAccidentMarker);
        tempAccidentMarker = null;
    }

    const form = document.getElementById('accidentReportForm');
    const desc = document.getElementById('accidentDescription');

    if (form) form.style.display = 'none';
    if (desc) desc.value = '';
}

document.getElementById('cancelAccidentReport')?.addEventListener('click', cancelAccidentReport);

async function loadActiveAccidents() {
    try {
        const resp = await fetch(`/api/accidents/active?city=${currentCity}`);
        const data = await resp.json();

        if (data.success) {
            // Remove old markers
            accidentMarkers.forEach(m => map.removeLayer(m));
            accidentMarkers = [];

            data.accidents.forEach(acc => {
                const color = acc.severity === 'minor' ? '#28a745' : acc.severity === 'moderate' ? '#ffc107' : '#dc3545';

                // Create pulsing marker
                const icon = L.divIcon({
                    className: 'accident-marker-container',
                    html: `
                        <div class="accident-marker-pulse" style="background:${color};"></div>
                        <div class="accident-marker-icon" style="background:${color};">
                            <i class="fas fa-exclamation" style="color:#fff;"></i>
                        </div>
                    `,
                    iconSize: [32, 32],
                    iconAnchor: [16, 16]
                });

                const marker = L.marker([acc.latitude, acc.longitude], { icon: icon }).addTo(map);
                marker.bindPopup(`<b>${acc.severity.toUpperCase()} Accident</b><br>${acc.description || 'Watch out for delays.'}`);
                accidentMarkers.push(marker);
            });

            // Update UI count
            const countEl = document.getElementById('activeAccidentsCount');
            if (countEl) countEl.textContent = data.count || data.accidents.length;
        }
    } catch (e) {
        console.error('Failed to load accidents:', e);
    }
}

// ═══════════════════════════════════════════════════════
// FOOLPROOF MODAL TRIGGERS (FAVORITES & WHATSAPP)
// ═══════════════════════════════════════════════════════

// 1. Load Favorites on Boot
async function loadFavorites() {
    try {
        const response = await fetch('/api/favorites');
        const data = await response.json();

        if (data.success && data.favorites) {
            const container = document.getElementById('favoritesContainer');
            if (!container) return;

            container.innerHTML = '';

            data.favorites.forEach(fav => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-sm btn-outline-secondary m-1';
                btn.innerHTML = fav.name;
                btn.onclick = (e) => {
                    e.preventDefault();
                    const startInput = document.getElementById('startLocation');
                    const endInput = document.getElementById('endLocation');

                    if (!startInput.value) {
                        startInput.value = fav.locationName;
                    } else {
                        endInput.value = fav.locationName;
                    }
                };
                container.appendChild(btn);
            });
        }
    } catch (err) {
        console.error('Failed to load favorites');
    }
}

// 2. Open Save Favorite Modal
window.triggerSaveFavorite = function () {
    const start = document.getElementById('startLocation').value;
    const end = document.getElementById('endLocation').value;

    if (!start || !end) return showToast('error', 'Please calculate a route first.');

    document.getElementById('modalStartLocation').textContent = start;
    document.getElementById('modalEndLocation').textContent = end;

    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('saveFavoriteModal'));
    modal.show();
};

// 3. Save Favorite Action
window.confirmSaveFavoriteAction = async function () {
    const name = document.getElementById('favoriteName').value;
    const end = document.getElementById('endLocation').value;

    if (!name) return showToast('error', 'Enter a name for this favorite');

    try {
        const getResp = await fetch('/api/favorites');
        let favs = (await getResp.json()).favorites || [];
        favs.push({ id: 'fav_' + Date.now(), name: '⭐ ' + name, locationName: end });

        await fetch('/api/favorites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ favorites: favs })
        });

        showToast('success', 'Favorite saved successfully!');
        document.getElementById('favoriteName').value = '';

        bootstrap.Modal.getInstance(document.getElementById('saveFavoriteModal')).hide();
        loadFavorites();
    } catch (err) {
        showToast('error', 'Failed to save favorite');
    }
};

// 4. Open WhatsApp Share Modal
window.triggerShareWhatsApp = function () {
    if (!selectedRouteId) return showToast('error', 'Select a route to share first.');

    document.getElementById('shareStartLocation').textContent = document.getElementById('startLocation').value;
    document.getElementById('shareEndLocation').textContent = document.getElementById('endLocation').value;

    const route = currentRoutes.find(r => r.id === selectedRouteId);
    document.getElementById('shareRouteOptions').innerHTML = `
        <div class="alert alert-info">Sharing: <strong>${route.name}</strong></div>
        <button class="btn btn-success w-100" onclick="executeShare()">
            <i class="fab fa-whatsapp"></i> Send Now
        </button>
    `;

    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('shareWhatsAppModal'));
    modal.show();
};

// 5. Execute WhatsApp Share (with Popup Bypass)
window.executeShare = async function () {
    const route = currentRoutes.find(r => r.id === selectedRouteId);
    if (!route) return;

    const routeData = {
        start: document.getElementById('startLocation').value,
        end: document.getElementById('endLocation').value,
        vehicle_type: document.getElementById('vehicleType')?.value || 'car',
        selected_route_id: route.id
    };

    let fallbackPopup = null;
    if (!navigator.share || !window.isSecureContext) {
        fallbackPopup = window.open('about:blank', '_blank');
    }

    try {
        const response = await fetch('/api/share-route', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(routeData)
        });

        const data = await response.json();

        if (data.success) {
            const shareUrl = `${window.location.origin}/route/${data.route_id}`;
            const text = `🚗 I'm taking the "${route.name}" from ${routeData.start} to ${routeData.end}.\nRisk level: ${route.risk_level.toUpperCase()}.\nTrack my safe route here: ${shareUrl}`;

            if (navigator.share && window.isSecureContext) {
                try {
                    await navigator.share({ title: 'Safe Route', text: text, url: shareUrl });
                } catch (shareErr) {
                    console.warn("Share cancelled or failed");
                }
            } else if (fallbackPopup) {
                fallbackPopup.location.href = `https://api.whatsapp.com/send?text=${encodeURIComponent(text)}`;
            }

            const modalEl = document.getElementById('shareWhatsAppModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        }
    } catch (err) {
        console.error('Error sharing route:', err);
        showToast('error', 'Could not generate share link.');
        if (fallbackPopup) fallbackPopup.close();
    }
};

// ═══════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════

function showToast(type, message) {
    const toastBody = document.getElementById(type + 'ToastBody');
    if (toastBody) toastBody.textContent = message;

    const toastEl = document.getElementById(type + 'Toast');
    if (toastEl) {
        toastEl.style.display = 'block';
        setTimeout(() => {
            toastEl.style.display = 'none';
        }, 5000);
    }
}

// Swap locations button
document.getElementById('swapLocations')?.addEventListener('click', () => {
    const start = document.getElementById('startLocation');
    const end = document.getElementById('endLocation');
    const temp = start.value;
    start.value = end.value;
    end.value = temp;
});

// CSS for Pulsing Accident Markers
const accidentStyles = document.createElement('style');
accidentStyles.textContent = `
    .accident-marker-container { position: relative; background: none !important; border: none !important; }
    .accident-marker-pulse { position: absolute; width: 32px; height: 32px; border-radius: 50%; opacity: 0.6; animation: pulse-accident 2s infinite; }
    .accident-marker-icon { position: absolute; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3); z-index: 1; }
    @keyframes pulse-accident { 0%, 100% { transform: scale(1); opacity: 0.6; } 50% { transform: scale(1.3); opacity: 0.3; } }
`;
document.head.appendChild(accidentStyles);

// ═══════════════════════════════════════════════════════
// UNIFIED INIT ON LOAD
// ═══════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════
// FORCE-BIND EVENT LISTENERS (Failsafe)
// ═══════════════════════════════════════════════════════
setTimeout(() => {
    // 1. Bind the main "Save as Favorite" button under the route form
    const saveBtn = document.getElementById('saveFavoriteBtn');
    if (saveBtn) saveBtn.onclick = window.triggerSaveFavorite;

    // 2. Bind the "Save Favorite" confirm button inside the modal
    const confirmSaveBtn = document.getElementById('confirmSaveFavorite');
    if (confirmSaveBtn) confirmSaveBtn.onclick = window.confirmSaveFavoriteAction;

    // 3. Bind the "Share via WhatsApp" button
    const shareBtn = document.getElementById('shareWhatsAppBtn');
    if (shareBtn) shareBtn.onclick = window.triggerShareWhatsApp;
}, 500); // Slight delay to ensure HTML is fully rendered
window.addEventListener('load', () => {
    initMap();
    loadActiveAccidents();
    loadFavorites();

    // Ensure map renders correctly after layout settles
    setTimeout(() => {
        if (map) map.invalidateSize();
    }, 100);

    // Auto-refresh accidents every 60 seconds
    setInterval(loadActiveAccidents, 60000);

    // Handle shared routes (hydration)
    if (typeof preloadedRouteData !== 'undefined' && preloadedRouteData) {
        document.getElementById('startLocation').value = preloadedRouteData.start;
        document.getElementById('endLocation').value = preloadedRouteData.end;
        if (document.getElementById('vehicleType')) {
            document.getElementById('vehicleType').value = preloadedRouteData.vehicle_type;
        }

        // Programmatically submit the form
        const routeForm = document.getElementById('routeForm');
        if (routeForm) {
            routeForm.dispatchEvent(new Event('submit'));
        }
    }
});