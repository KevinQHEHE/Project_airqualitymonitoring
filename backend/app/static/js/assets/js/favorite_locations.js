/**
 * Favorite Locations Manager
 * Handles geolocation, nearest stations API calls, and location saving
 */

class FavoriteLocationsManager {
    constructor() {
        this.apiBaseUrl = window.location.origin; // Use current origin instead of hardcoded localhost
        this.locationPermissionKey = 'location_permission_asked';
        this.savedLocationKey = 'saved_location';
        this.favoriteStationKey = 'favorite_station';
        this.currentLocation = null;
        this.nearestStations = [];
        this.isModalOpen = false;
        
        // Default location - Hanoi, Vietnam coordinates
        this.defaultLocation = {
            lat: 21.0491,
            lng: 105.8831
        };
        
        // Bind methods
        this.init = this.init.bind(this);
        this.showLocationPermissionModal = this.showLocationPermissionModal.bind(this);
        this.handleLocationPreference = this.handleLocationPreference.bind(this);
        this.getCurrentLocation = this.getCurrentLocation.bind(this);
        this.fetchNearestStations = this.fetchNearestStations.bind(this);
        this.displayNearestStations = this.displayNearestStations.bind(this);
        this.selectStation = this.selectStation.bind(this);
    }

    init() {
        console.log('[LocationManager] Initializing...');
        
        // Check location preference
        const locationPreference = localStorage.getItem('location_preference');
        const savedLocation = localStorage.getItem(this.savedLocationKey);
        
        if (locationPreference === 'never') {
            // User chose "never" - use default Hanoi location
            console.log('[LocationManager] Using default Hanoi location (user disabled location access)');
            this.currentLocation = this.defaultLocation;
            // Auto-load station for default Hanoi (explicit selection: Use Hanoi)
            this.autoLoadNearestStation({ explicit: true });
            return;
        } else if (locationPreference === 'always' && savedLocation) {
            // User chose "always" - auto-load nearest station
            console.log('[LocationManager] Auto-loading nearest station based on saved location');
            try {
                this.currentLocation = JSON.parse(savedLocation);
                // Auto-load station based on the user's saved location (explicit)
                this.autoLoadNearestStation({ explicit: true });
            } catch (error) {
                console.error('[LocationManager] Error parsing saved location:', error);
                // Show modal if saved location is corrupted
                setTimeout(() => {
                    this.showLocationPermissionModal();
                }, 2000);
            }
        } else if (locationPreference === 'once' || !locationPreference) {
            // User chose "once" or first time user - show permission modal
            setTimeout(() => {
                this.showLocationPermissionModal();
            }, 2000);
        }
    }

    showLocationPermissionModal() {
        if (this.isModalOpen) return;
        
        console.log('[LocationManager] Showing location permission modal');
        this.isModalOpen = true;
        
        const modalHtml = this.createLocationModalHTML();
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Show modal with animation
        setTimeout(() => {
            const modal = document.getElementById('locationPermissionModal');
            if (modal) {
                modal.classList.add('show');
            }
        }, 100);
        
        // Add event listeners
        this.attachModalEventListeners();
    }

    createLocationModalHTML() {
        return `
            <div class="location-permission-modal" id="locationPermissionModal">
                <div class="location-modal-content">
                    <div class="location-modal-header">
                        <div class="location-modal-icon">
                            <i class="fas fa-map-marker-alt"></i>
                        </div>
                        <h2 class="location-modal-title">Save Your Location?</h2>
                        <p class="location-modal-text">
                            We can show you the nearest air quality monitoring stations based on your location. 
                            Your location will be saved locally and never shared. If you choose "Use Hanoi", we'll show stations in Hanoi, Vietnam.
                        </p>
                    </div>
                    
                    <div class="location-modal-actions">
                        <button class="location-btn location-btn-primary" id="alwaysAllowBtn" data-preference="always">
                            <i class="fas fa-check-double mr-2"></i>Always Allow
                        </button>
                        <button class="location-btn location-btn-secondary" id="thisTimeOnlyBtn" data-preference="once">
                            <i class="fas fa-check mr-2"></i>Just This Time
                        </button>
                        <button class="location-btn location-btn-danger" id="neverAllowBtn" data-preference="never">
                            <i class="fas fa-map-marker-alt mr-2"></i>Use Hanoi
                        </button>
                    </div>
                    
                    <!-- Container for nearest stations (hidden initially) -->
                    <div class="nearest-stations-container" id="nearestStationsContainer" style="display: none;">
                        <h3 class="nearest-stations-title">
                            <i class="fas fa-broadcast-tower"></i>
                            Nearest Stations
                        </h3>
                        <div id="nearestStationsList"></div>
                    </div>
                </div>
            </div>
        `;
    }

    attachModalEventListeners() {
        const alwaysBtn = document.getElementById('alwaysAllowBtn');
        const thisTimeBtn = document.getElementById('thisTimeOnlyBtn');
        const neverBtn = document.getElementById('neverAllowBtn');
        
        if (alwaysBtn) {
            alwaysBtn.addEventListener('click', () => this.handleLocationPreference('always'));
        }
        
        if (thisTimeBtn) {
            thisTimeBtn.addEventListener('click', () => this.handleLocationPreference('once'));
        }
        
        if (neverBtn) {
            neverBtn.addEventListener('click', () => this.handleLocationPreference('never'));
        }
    }

    async handleLocationPreference(preference) {
        // Save preference to localStorage
        localStorage.setItem('location_preference', preference);
        console.log('[LocationManager] Location preference set to:', preference);
        
        if (preference === 'never') {
            // Use default Hanoi location instead of asking for user location
            this.currentLocation = this.defaultLocation;
            this.showToast('Using default location: Hanoi, Vietnam', 'info');
            
            try {
                // Fetch and display nearest stations for Hanoi
                await this.fetchAndDisplayNearestStations();
            } catch (error) {
                console.error('[LocationManager] Error fetching stations for default location:', error);
                this.closeModal();
                this.showToast('Unable to load stations for default location', 'error');
            }
            return;
        }
        
        if (preference === 'always' || preference === 'once') {
            // Get the clicked button for loading state
            const clickedBtn = document.querySelector(`[data-preference="${preference}"]`);
            if (clickedBtn) {
                clickedBtn.classList.add('loading');
                clickedBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Getting Location...';
            }
            
            try {
                const location = await this.getCurrentLocation();
                if (location) {
                    this.currentLocation = location;
                    
                    // Save location if preference is 'always'
                    if (preference === 'always') {
                        localStorage.setItem(this.savedLocationKey, JSON.stringify(location));
                    }
                    
                    // Fetch and display nearest stations
                    await this.fetchAndDisplayNearestStations();
                }
            } catch (error) {
                console.error('[LocationManager] Location error:', error);
                this.showErrorMessage('Unable to get your location. Please try again or skip.');
                
                // Reset button state
                if (clickedBtn) {
                    clickedBtn.classList.remove('loading');
                    const icon = preference === 'always' ? 'fas fa-check-double' : 'fas fa-check';
                    const text = preference === 'always' ? 'Always Allow' : 'Just This Time';
                    clickedBtn.innerHTML = `<i class="${icon} mr-2"></i>${text}`;
                }
            }
        }
    }

    getCurrentLocation() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error('Geolocation is not supported by this browser'));
                return;
            }

            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const location = {
                        lat: position.coords.latitude,
                        lng: position.coords.longitude,
                        accuracy: position.coords.accuracy,
                        timestamp: Date.now()
                    };
                    console.log('[LocationManager] Got location:', location);
                    resolve(location);
                },
                (error) => {
                    console.error('[LocationManager] Geolocation error:', error);
                    let message = 'Unable to get location';
                    
                    switch(error.code) {
                        case error.PERMISSION_DENIED:
                            message = 'Location access denied by user';
                            break;
                        case error.POSITION_UNAVAILABLE:
                            message = 'Location information is unavailable';
                            break;
                        case error.TIMEOUT:
                            message = 'Location request timed out';
                            break;
                    }
                    
                    reject(new Error(message));
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 300000 // 5 minutes
                }
            );
        });
    }

    async autoLoadNearestStation(options = {}) {
        try {
            console.log('[LocationManager] Auto-loading nearest station...');
            const stations = await this.fetchNearestStations(this.currentLocation);
            if (stations && stations.length > 0) {
                const nearestStation = stations[0]; // Get the closest station
                console.log('[LocationManager] Auto-loaded station:', nearestStation);
                
                // Save as favorite and trigger dashboard update
                localStorage.setItem(this.favoriteStationKey, JSON.stringify(nearestStation));
                this.loadFavoriteStation(nearestStation);
                
                // Show success toast. If this auto-load was triggered from a saved/default location
                // (i.e. the user explicitly chose a saved/default), show a slightly different message.
                const explicit = options && options.explicit === true;
                const toastPrefix = explicit ? 'Auto-loaded station' : 'Auto-loaded nearest station';
                this.showToast(`${toastPrefix}: ${nearestStation.name || nearestStation.station_id}`, 'success');
            } else {
                console.warn('[LocationManager] No stations found for auto-load');
                this.showToast('No monitoring stations found nearby', 'warning');
            }
        } catch (error) {
            console.error('[LocationManager] Error auto-loading station:', error);
            this.showToast('Unable to load nearest station automatically', 'error');
        }
    }

    async fetchAndDisplayNearestStations() {
        try {
            console.log('[LocationManager] Starting fetchAndDisplayNearestStations with location:', this.currentLocation);
            const stations = await this.fetchNearestStations(this.currentLocation);
            console.log('[LocationManager] Received stations:', stations);
            
            if (stations && stations.length > 0) {
                this.nearestStations = stations;
                this.displayNearestStations(stations);
            } else {
                console.warn('[LocationManager] No stations returned');
                this.showErrorMessage('No monitoring stations found nearby');
            }
        } catch (error) {
            console.error('[LocationManager] Error fetching stations:', error);
            console.error('[LocationManager] Error stack:', error.stack);
            this.showErrorMessage(`Unable to fetch nearby stations: ${error.message}`);
        }
    }

    async fetchNearestStations(location, radius = 50) {
        try {
            // First, get the nearest single station
            const nearestUrl = `${this.apiBaseUrl}/api/stations/nearest?lat=${location.lat}&lng=${location.lng}&radius=${radius}`;
            console.log('[LocationManager] Fetching nearest station:', nearestUrl);
            console.log('[LocationManager] Location data:', location);
            
            const nearestResponse = await fetch(nearestUrl, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json'
                    // Remove Authorization header as it might not be needed for public endpoints
                }
            });

            console.log('[LocationManager] Response status:', nearestResponse.status);
            console.log('[LocationManager] Response headers:', nearestResponse.headers);

            if (!nearestResponse.ok) {
                const errorText = await nearestResponse.text();
                console.error('[LocationManager] API Error Response:', errorText);
                throw new Error(`HTTP error! status: ${nearestResponse.status} - ${errorText}`);
            }

            const nearestData = await nearestResponse.json();
            console.log('[LocationManager] Nearest station response:', nearestData);
            
            let stations = [];
            
            if (nearestData.station) {
                // Only use the nearest station
                let nearestStation = nearestData.station;

                // Detect placeholder/test station by name or city
                const cityName = nearestStation.city && typeof nearestStation.city === 'object' ? nearestStation.city.name : nearestStation.city;
                const stationName = nearestStation.name || cityName || '';
                const nameLower = (stationName || '').toString().toLowerCase();

                // If looks like a placeholder, attempt to enrich using meta.station_idx
                if (nameLower.includes('test') || cityName === 'Test City') {
                    const metaIdx = nearestStation.latest_reading && nearestStation.latest_reading.meta ? nearestStation.latest_reading.meta.station_idx : null;
                    if (metaIdx) {
                        try {
                            const enrichUrl = `${this.apiBaseUrl}/api/stations/by_meta_idx/${metaIdx}?lat=${location.lat}&lng=${location.lng}`;
                            console.log('[LocationManager] Enriching placeholder station via:', enrichUrl);
                            const enrichResp = await fetch(enrichUrl, { method: 'GET', headers: { 'Accept': 'application/json' } });
                            if (enrichResp.ok) {
                                const enrichData = await enrichResp.json();
                                if (enrichData.station) {
                                    nearestStation = enrichData.station;
                                    console.log('[LocationManager] Enriched station from meta index:', nearestStation);
                                }
                            }
                        } catch (e) {
                            console.warn('[LocationManager] Failed to enrich placeholder station:', e);
                        }
                    }
                }

                nearestStation.distance = this.calculateDistance(
                    location.lat, location.lng,
                    nearestStation.location?.coordinates?.[1] || 0,
                    nearestStation.location?.coordinates?.[0] || 0
                );
                stations.push(nearestStation);
                console.log('[LocationManager] Processed nearest station:', nearestStation);
            }
            
            return stations;
            
        } catch (error) {
            console.error('[LocationManager] Fetch error:', error);
            throw error;
        }
    }

    displayNearestStations(stations) {
        const container = document.getElementById('nearestStationsContainer');
        const stationsList = document.getElementById('nearestStationsList');
        
        if (!container || !stationsList) return;

        // Show container
        container.style.display = 'block';
        container.classList.add('fade-in');

        // Generate stations HTML
        const stationsHtml = stations.map((station, index) => {
            const distance = station.distance ? `${station.distance.toFixed(1)} km` : 'N/A';
            const stationName = station.name || station.station_name || `Station ${station.station_id}` || 'Unknown Station';
            const cityName = typeof station.city === 'object' ? (station.city?.name || 'Unknown City') : (station.city || 'Unknown City');
            
            return `
                <div class="nearest-station-item" data-station-id="${station.station_id}" data-index="${index}">
                    <div class="station-info">
                        <div class="station-details">
                            <h4>${this.escapeHtml(stationName)}</h4>
                            <p>${this.escapeHtml(cityName)}</p>
                        </div>
                        <div class="station-distance">${distance}</div>
                    </div>
                </div>
            `;
        }).join('');

        stationsList.innerHTML = stationsHtml;

        // Add click listeners to station items
        stationsList.querySelectorAll('.nearest-station-item').forEach((item) => {
            item.addEventListener('click', (e) => {
                const stationId = e.currentTarget.dataset.stationId;
                const index = parseInt(e.currentTarget.dataset.index);
                this.selectStation(stations[index]);
            });
        });
    }

    selectStation(station) {
        console.log('[LocationManager] Station selected:', station);
        
        // Extract station info properly
        const stationName = station.name || station.station_name || `Station ${station.station_id}`;
        const cityName = typeof station.city === 'object' ? station.city?.name : station.city;
        
        console.log(`[LocationManager] Station details - ID: ${station.station_id}, Name: "${stationName}", City: "${cityName}"`);
        
        // Save as favorite station with cleaned data
        const cleanedStation = {
            ...station,
            displayName: stationName,
            displayCity: cityName
        };
        localStorage.setItem(this.favoriteStationKey, JSON.stringify(cleanedStation));
        
        // Show success message
        const message = cityName ? 
            `Saved "${stationName}" in ${cityName} as your favorite station` : 
            `Saved "${stationName}" as your favorite station`;
        this.showToast(message, 'success');
        
        // Close modal first
        this.closeModal();
        
        // Small delay to let modal close, then load station data
        setTimeout(() => {
            console.log('[LocationManager] Loading station data in dashboard after modal close...');
            this.loadStationInDashboard(cleanedStation);
        }, 300);
        
        // Show favorite button
        this.showFavoriteLocationButton();
    }

    loadStationInDashboard(station) {
        console.log('[LocationManager] Loading station in dashboard:', station);
        
        // Extract station info with fallbacks
        const stationId = station.station_id;
        // Use the station name from API response
        const stationName = station.name || station.station_name || station.displayName || `Station ${stationId}`;
        const cityName = station.displayCity || (typeof station.city === 'object' ? station.city?.name : station.city);
        
        console.log(`[LocationManager] Loading station: ID=${stationId}, Name="${stationName}", City="${cityName}"`);
        
        // Wait a bit for dashboard to be ready, then call showLatestForStation
        setTimeout(async () => {
            try {
                if (typeof showLatestForStation === 'function') {
                    console.log('[LocationManager] Calling showLatestForStation with stationId:', stationId, 'stationName:', stationName);
                    await showLatestForStation(stationId, stationName);
                    console.log('[LocationManager] Successfully called showLatestForStation');
                    
                    // Also manually update the location name element to ensure it shows correctly
                    const locEl = document.getElementById('locationName');
                    if (locEl && stationName) {
                        locEl.textContent = stationName;
                        console.log('[LocationManager] Manually updated locationName to:', stationName);
                    }
                } else if (typeof window.showLatestForStation === 'function') {
                    console.log('[LocationManager] Calling window.showLatestForStation with stationId:', stationId, 'stationName:', stationName);
                    await window.showLatestForStation(stationId, stationName);
                    console.log('[LocationManager] Successfully called window.showLatestForStation');
                    
                    // Also manually update the location name element to ensure it shows correctly
                    const locEl = document.getElementById('locationName');
                    if (locEl && stationName) {
                        locEl.textContent = stationName;
                        console.log('[LocationManager] Manually updated locationName to:', stationName);
                    }
                } else {
                    console.error('[LocationManager] showLatestForStation function not found');
                    this.showToast('Dashboard function not available. Please refresh the page.', 'error');
                }
            } catch (error) {
                console.error('[LocationManager] Error calling showLatestForStation:', error);
                this.showToast(`Error loading station data: ${error.message}`, 'error');
            }
        }, 500);
    }

    async loadStationDataDirectly(stationId, stationName, cityName) {
        try {
            console.log(`[LocationManager] Direct API call for station ${stationId}`);
            
            // Update station name in UI if possible
            const stationNameEl = document.querySelector('#selected-station-name, .selected-station-name, .station-title');
            if (stationNameEl) {
                stationNameEl.textContent = stationName;
            }
            
            // Show toast with station info
            this.showToast(`Loading data for ${stationName}${cityName ? ` in ${cityName}` : ''}`, 'info');
            
            // You can add more direct API calls here to load station data
            // For now, just show the station selection success
            
        } catch (error) {
            console.error('[LocationManager] Error loading station data directly:', error);
        }
    }

    loadFavoriteStation(station) {
        console.log('[LocationManager] Auto-loading favorite station:', station);
        
        // Wait for dashboard to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                setTimeout(() => this.loadStationInDashboard(station), 1000);
            });
        } else {
            setTimeout(() => this.loadStationInDashboard(station), 1000);
        }
    }

    showFavoriteLocationButton() {
        // Check if button already exists
        if (document.getElementById('favoriteLocationBtn')) return;
        
        const buttonHtml = `
            <button class="favorite-location-btn saved" id="favoriteLocationBtn" title="Favorite Location Saved">
                <i class="fas fa-heart"></i>
            </button>
        `;
        
        document.body.insertAdjacentHTML('beforeend', buttonHtml);
        
        // Add click listener
        const btn = document.getElementById('favoriteLocationBtn');
        if (btn) {
            btn.addEventListener('click', () => this.showFavoriteLocationInfo());
        }
    }

    showFavoriteLocationInfo() {
        const station = localStorage.getItem(this.favoriteStationKey);
        if (station) {
            const stationData = JSON.parse(station);
            this.showInfoToast(`Your favorite station: ${stationData.name || stationData.station_name}`);
            
            // Reload the station
            this.loadStationInDashboard(stationData);
        }
    }

    closeModal() {
        const modal = document.getElementById('locationPermissionModal');
        if (modal) {
            modal.classList.remove('show');
            setTimeout(() => {
                modal.remove();
                this.isModalOpen = false;
            }, 400);
        }
    }

    showErrorMessage(message) {
        const container = document.querySelector('.location-modal-content');
        if (container) {
            const existingError = container.querySelector('.error-message');
            if (existingError) existingError.remove();
            
            const errorHtml = `
                <div class="error-message" style="background: rgba(244, 67, 54, 0.1); border: 1px solid rgba(244, 67, 54, 0.3); border-radius: 8px; padding: 1rem; margin-top: 1rem; color: #f44336;">
                    <i class="fas fa-exclamation-triangle mr-2"></i>${message}
                </div>
            `;
            container.insertAdjacentHTML('beforeend', errorHtml);
        }
    }

    showSuccessToast(message) {
        this.showToast(message, 'success');
    }

    showInfoToast(message) {
        this.showToast(message, 'info');
    }

    showToast(message, type = 'info') {
        // Create toast container if it doesn't exist
        let toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toastContainer';
            toastContainer.style.cssText = `
                position: fixed;
                top: 2rem;
                right: 2rem;
                z-index: 10001;
                max-width: 400px;
            `;
            document.body.appendChild(toastContainer);
        }

        const toastId = `toast-${Date.now()}`;
        const bgColor = type === 'success' ? '#00e676' : 
                       type === 'error' ? '#f44336' : '#667eea';
        
        const toastHtml = `
            <div class="toast-notification" id="${toastId}" style="
                background: ${bgColor};
                color: white;
                padding: 1rem 1.5rem;
                border-radius: 12px;
                margin-bottom: 0.5rem;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                transform: translateX(400px);
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                display: flex;
                align-items: center;
                gap: 0.5rem;
            ">
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
                <span>${this.escapeHtml(message)}</span>
            </div>
        `;

        toastContainer.insertAdjacentHTML('afterbegin', toastHtml);
        
        const toast = document.getElementById(toastId);
        
        // Show animation
        setTimeout(() => {
            if (toast) toast.style.transform = 'translateX(0)';
        }, 100);

        // Hide and remove after delay
        setTimeout(() => {
            if (toast) {
                toast.style.transform = 'translateX(400px)';
                setTimeout(() => toast.remove(), 400);
            }
        }, 4000);
    }

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    /**
     * Calculate distance between two coordinates using Haversine formula
     * @param {number} lat1 - Latitude of first point
     * @param {number} lng1 - Longitude of first point  
     * @param {number} lat2 - Latitude of second point
     * @param {number} lng2 - Longitude of second point
     * @returns {number} Distance in kilometers
     */
    calculateDistance(lat1, lng1, lat2, lng2) {
        const R = 6371; // Radius of the Earth in kilometers
        const dLat = this.deg2rad(lat2 - lat1);
        const dLng = this.deg2rad(lng2 - lng1);
        const a = 
            Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(this.deg2rad(lat1)) * Math.cos(this.deg2rad(lat2)) * 
            Math.sin(dLng/2) * Math.sin(dLng/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        const distance = R * c; // Distance in kilometers
        return Math.round(distance * 10) / 10; // Round to 1 decimal place
    }

    /**
     * Convert degrees to radians
     * @param {number} deg - Degrees
     * @returns {number} Radians
     */
    deg2rad(deg) {
        return deg * (Math.PI/180);
    }

    // Public methods for external use
    clearSavedLocation() {
        localStorage.removeItem(this.savedLocationKey);
        localStorage.removeItem(this.favoriteStationKey);
        localStorage.removeItem(this.locationPermissionKey);
        
        const btn = document.getElementById('favoriteLocationBtn');
        if (btn) btn.remove();
        
        this.showInfoToast('Location data cleared');
    }

    refreshNearestStations() {
        const savedLocation = localStorage.getItem(this.savedLocationKey);
        if (savedLocation) {
            this.currentLocation = JSON.parse(savedLocation);
            this.showLocationPermissionModal();
        } else {
            this.showInfoToast('No saved location found');
        }
    }
}

// Global instance
window.FavoriteLocationsManager = FavoriteLocationsManager;

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    if (!window.favoriteLocationsManager) {
        window.favoriteLocationsManager = new FavoriteLocationsManager();
        
        // Initialize after auth check is complete
        setTimeout(() => {
            const authOverlay = document.getElementById('authLoadingOverlay');
            if (!authOverlay || authOverlay.style.display === 'none') {
                window.favoriteLocationsManager.init();
            } else {
                // Wait for auth overlay to disappear
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        if (mutation.target === authOverlay && authOverlay.style.display === 'none') {
                            window.favoriteLocationsManager.init();
                            observer.disconnect();
                        }
                    });
                });
                observer.observe(authOverlay, { attributes: true, attributeFilter: ['style'] });
            }
        }, 1000);
    }
});

// Export for module use if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FavoriteLocationsManager;
}