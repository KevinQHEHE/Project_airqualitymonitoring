// station_subscriptions.js - minimal functionality to render subscriptions
// Expected backend endpoints:
// GET  /api/subscriptions -> { subscriptions: [...] }
// POST /api/subscriptions/unsubscribe { station_id }
// POST /api/subscriptions/subscribe { station_id, ... }
// PUT  /api/subscriptions/{id} { alert_enabled, threshold, nickname }

let currentView = 'grid';
let subscriptionsInitialized = false;

// Initialize subscriptions only when explicitly called
function initializeSubscriptions() {
	if (subscriptionsInitialized) {
		refreshSubscriptions();
		return;
	}
	subscriptionsInitialized = true;
	setView(currentView);
	refreshSubscriptions();
}

// Only auto-initialize if we're on a standalone subscriptions page
document.addEventListener('DOMContentLoaded', () => {
	// Check if we're on the integrated dashboard or standalone subscriptions page
	const isDashboardIntegrated = document.getElementById('dashboard-content') !== null;
	const isStandaloneSubscriptions = document.querySelector('.subscriptions-container') !== null && !isDashboardIntegrated;
	
	if (isStandaloneSubscriptions) {
		initializeSubscriptions();
	}
});

function setView(view) {
	currentView = view;
	document.getElementById('gridViewBtn').classList.toggle('active', view === 'grid');
	document.getElementById('listViewBtn').classList.toggle('active', view === 'list');
	document.getElementById('subscriptionsGrid').style.display = view === 'grid' ? 'grid' : 'none';
	document.getElementById('subscriptionsList').style.display = view === 'list' ? 'block' : 'none';
}

async function refreshSubscriptions() {
	const token = localStorage.getItem('access_token');
	const containerGrid = document.getElementById('subscriptionsGrid');
	const containerList = document.getElementById('subscriptionsList');
	const emptyState = document.getElementById('emptyState');
	const countEl = document.getElementById('subscriptionCount');

	containerGrid.innerHTML = '';
	containerList.innerHTML = '';
	
	console.log('Token:', token ? 'Present' : 'Missing');

	try {
		const resp = await fetch('/api/subscriptions', { headers: { 'Authorization': `Bearer ${token}` } });
		console.log('API Response status:', resp.status);
		
		if (!resp.ok) {
			const errorText = await resp.text();
			console.error('API Error:', errorText);
			throw new Error('Failed to fetch subscriptions');
		}
		
		const data = await resp.json();
		console.log('API Data received:', data);
		
		const subs = data.subscriptions || [];
		console.log('Subscriptions count:', subs.length);
		console.log('First subscription:', subs[0]);
		
		// Debug AQI values
		subs.forEach((sub, i) => {
			console.log(`=== SUBSCRIPTION ${i} DEBUG ===`);
			console.log(`Station ID: ${sub.station_id}`);
			console.log(`Station Name: ${sub.station_name}`);
			console.log(`Current AQI: ${sub.current_aqi} (type: ${typeof sub.current_aqi})`);
			console.log(`Last Updated: ${sub.last_updated}`);
			console.log(`Full object:`, sub);
		});

		countEl.textContent = String(subs.length || 0);

		if (!subs.length) {
			console.log('No subscriptions - showing empty state');
			emptyState.style.display = 'block';
			return;
		} else {
			emptyState.style.display = 'none';
		}

		subs.forEach((s, index) => {
			console.log(`Creating card ${index}:`, s);
			const card = createStationCard(s);
			containerGrid.appendChild(card.grid);
			containerList.appendChild(card.list);
		});

	} catch (e) {
		console.error('Error loading subscriptions', e);
		emptyState.style.display = 'block';
	}
}

function createStationCard(s) {
	console.log('Creating station card for:', s.station_name || s.nickname, 'AQI:', s.current_aqi);
	
	// Handle null/undefined AQI
	const displayAQI = s.current_aqi != null ? s.current_aqi : 'N/A';
	const aqiValue = s.current_aqi != null ? s.current_aqi : 0; // For color calculation
	
	// Grid card
	const gridCard = document.createElement('div');
	gridCard.className = 'station-card new';
	gridCard.style.setProperty('--station-color', getAQIColor(aqiValue));
	gridCard.innerHTML = `
		<div class="station-header">
			<div class="station-name-container">
				<h4 class="station-name">${escapeHtml(s.nickname || s.location || 'Station')}</h4>
				<div class="station-id">${escapeHtml(String(s.station_id))}</div>
				<div class="added-date">${formatTimestamp(s.created_at) || ''}</div>
			</div>
			<div class="aqi-display">
				<div class="aqi-circle ${getAQIClass(aqiValue)}">
					<div class="aqi-value">${displayAQI}</div>
					<div class="aqi-label">AQI</div>
				</div>
				<div class="aqi-details">
					<div class="aqi-description">Last: ${formatTimestamp(s.last_updated) || 'No data'}</div>
					<div class="added-date">Added: ${formatTimestamp(s.created_at) || ''}</div>
				</div>
			</div>
			<div class="alert-controls">
				<div class="alert-toggle">
					<div class="alert-label" data-subscription-id="${s.id}">Alerts
						<small data-subscription-id="${s.id}" style="font-weight:400;color:#7f8c8d;">${s.alert_enabled ? 'On' : 'Off'}</small>
					</div>
					<button data-subscription-id="${s.id}" class="toggle-switch ${s.alert_enabled ? 'active' : ''}" onclick="toggleAlert(this, '${s.station_id}', '${s.id}')"></button>
				</div>
				<div class="threshold-control">
					<div class="threshold-label">
						<div>Threshold</div>
							<div class="threshold-value" data-subscription-id="${s.id}">${s.threshold ?? s.current_aqi ?? 100}</div>
					</div>
						<input data-subscription-id="${s.id}" type="range" min="0" max="500" value="${s.threshold ?? s.current_aqi ?? 100}" class="threshold-slider" oninput="onThresholdChange(event, '${s.station_id}', '${s.id}')">
				</div>
			</div>
			<div class="station-controls">
				<button class="unsubscribe-btn" onclick="confirmUnsubscribe('${s.station_id}')">Unsubscribe</button>
			</div>
		</div>
	`;

	// List item (with AQI display)
	const listItem = document.createElement('div');
	listItem.className = 'station-card list-item';
	listItem.innerHTML = `
		<div class="station-header">
			<div class="station-name-container">
				<h4 class="station-name">${escapeHtml(s.nickname || s.station_name || s.location || 'Station')}</h4>
				<div class="station-id">${escapeHtml(String(s.station_id))}</div>
				<div class="added-date">${formatTimestamp(s.created_at) || ''}</div>
			</div>

			<div class="controls-column">
				<div class="aqi-compact-mobile">
					<div class="aqi-circle-small ${getAQIClass(aqiValue)}">
						<span class="aqi-value-small">${displayAQI}</span>
					</div>
				</div>
				<div class="control-stack">
					<div class="alert-toggle-small">
						<span class="alert-label-small" data-subscription-id="${s.id}">Alerts ${s.alert_enabled ? 'On' : 'Off'}</span>
						<button data-subscription-id="${s.id}" class="toggle-switch-small ${s.alert_enabled ? 'active' : ''}" onclick="toggleAlert(this, '${s.station_id}', '${s.id}')"></button>
					</div>
					<div class="threshold-inline">
						<span class="threshold-label-small">Threshold: <span class="threshold-value" data-subscription-id="${s.id}">${s.threshold ?? s.current_aqi ?? 100}</span></span>
					</div>
					<div class="unsubscribe-wrap">
						<button class="unsubscribe-btn" onclick="confirmUnsubscribe('${s.station_id}')">Unsubscribe</button>
					</div>
				</div>
			</div>
		</div>
	`;

	return { grid: gridCard, list: listItem };
}

function getAQIColor(aqi) {
	if (aqi <= 50) return '#00e676';
	if (aqi <= 100) return '#ffd54f';
	if (aqi <= 150) return '#ff9800';
	if (aqi <= 200) return '#f44336';
	if (aqi <= 300) return '#9c27b0';
	return '#8d6e63';
}

function getAQIClass(aqi) {
	if (aqi <= 50) return 'aqi-good';
	if (aqi <= 100) return 'aqi-moderate';
	if (aqi <= 150) return 'aqi-unhealthy-sensitive';
	if (aqi <= 200) return 'aqi-unhealthy';
	if (aqi <= 300) return 'aqi-very-unhealthy';
	return 'aqi-hazardous';
}

function formatTimestamp(timestamp) {
	if (!timestamp) return '';
	try {
		const date = new Date(timestamp);
		return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
	} catch (e) {
		return timestamp;
	}
}

function escapeHtml(unsafe) {
	return String(unsafe)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#039;');
}

function confirmUnsubscribe(stationId) {
	if (!confirm('Are you sure you want to unsubscribe from this station?')) return;
	unsubscribeStation(stationId);
}

async function unsubscribeStation(stationId) {
	const token = localStorage.getItem('access_token');
	try {
		const resp = await fetch('/api/subscriptions/unsubscribe', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
			body: JSON.stringify({ station_id: stationId })
		});
		if (!resp.ok) throw new Error('Unsubscribe failed');
		refreshSubscriptions();
		alert('Unsubscribed');
	} catch (e) {
		console.error(e);
		alert('Failed to unsubscribe');
	}
}

async function toggleAlert(el, stationId, subscriptionId) {
	// Optimistic UI: toggle visual state immediately
	try {
		const token = localStorage.getItem('access_token');
		if (!token) {
			alert('You must be logged in to change alert settings');
			return;
		}

		// Determine current state from button class
		const button = el;
		const isActive = button.classList.contains('active');
		const newState = !isActive;

		// Update UI immediately
		button.classList.toggle('active', newState);
		// Update any matching labels; keep previous texts to allow revert on failure
		const labelEls = Array.from(document.querySelectorAll(`[data-subscription-id="${subscriptionId}"]`));
		const prevLabelStates = labelEls.map(l => ({ el: l, text: l.textContent }));
		labelEls.forEach(l => {
			// Some labels are small elements; change their text content
			if (l.tagName === 'SMALL' || l.classList.contains('alert-label-small')) {
				l.textContent = newState ? 'On' : 'Off';
			} else if (l.classList.contains('alert-label')) {
				// inner structure: 'Alerts <small>On/Off'
				const small = l.querySelector('small');
				if (small) small.textContent = newState ? 'On' : 'Off';
			} else if (l.classList.contains('alert-label-small')) {
				l.textContent = newState ? 'On' : 'Off';
			}
		});

		// Send update to server
		const resp = await fetch(`/api/subscriptions/${subscriptionId}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
			body: JSON.stringify({ alert_enabled: newState })
		});

		if (!resp.ok) {
			const txt = await resp.text().catch(() => 'no body');
			throw new Error(`Server responded ${resp.status}: ${txt}`);
		}

		console.log(`Alert ${newState ? 'enabled' : 'disabled'} for subscription ${subscriptionId}`);

	} catch (err) {
		console.error('Failed to toggle alert:', err);
		// Revert optimistic UI
		if (el && el.classList) el.classList.toggle('active');
		// Revert label texts if we captured previous states
		try {
			if (typeof prevLabelStates !== 'undefined' && Array.isArray(prevLabelStates)) {
				prevLabelStates.forEach(item => {
					try { item.el.textContent = item.text; } catch (e) { /* ignore */ }
				});
			}
		} catch (e) {
			// ignore revert errors
		}
		alert('Failed to toggle alert: ' + (err.message || err));
	}
}

async function onThresholdChange(e, stationId, subscriptionId) {
	const val = e.target.value;
	// Try multiple strategies to find the nearest .threshold-value element
	// Find all elements (displays and sliders) that belong to this subscription id and update them
	const subId = subscriptionId || e.target.getAttribute('data-subscription-id');
	if (subId) {
		// Update all display elements
		const displays = document.querySelectorAll(`.threshold-value[data-subscription-id="${subId}"]`);
		displays.forEach(d => d.textContent = val);

		// Update other sliders for the same subscription (e.g., grid vs list)
		const sliders = document.querySelectorAll(`input[type=range][data-subscription-id="${subId}"]`);
		sliders.forEach(s => {
			if (s !== e.target) s.value = val;
		});
	} else {
		// Fallback: try to update nearby display
		let display = null;
		display = e.target.parentElement?.querySelector('.threshold-value') || null;
		if (!display) {
			const header = e.target.closest('.station-header');
			display = header?.querySelector('.threshold-value') || null;
		}
		if (display) display.textContent = val;
	}

	console.log(`Threshold slider changed to ${val} for station ${stationId} (subscriptionId=${subscriptionId})`);

	// Debounced update to backend (per-subscription)
	window.thresholdUpdateTimeouts = window.thresholdUpdateTimeouts || {};
	const key = subscriptionId || e.target.getAttribute('data-subscription-id') || stationId;
	clearTimeout(window.thresholdUpdateTimeouts[key]);
	window.thresholdUpdateTimeouts[key] = setTimeout(async () => {
		console.log(`Sending threshold update: ${val} for station ${stationId} (subscriptionId=${key})`);
		await updateThreshold(stationId, parseInt(val), key);
	}, 1000);
}

async function updateThreshold(stationId, threshold, subscriptionId) {
	const token = localStorage.getItem('access_token');
	console.log(`updateThreshold called: station=${stationId}, threshold=${threshold}, subscriptionId=${subscriptionId}`);

	if (!token) {
		console.error('No access token found; user may be logged out');
		alert('You must be logged in to update thresholds');
		return;
	}

	try {
		let subId = subscriptionId;

		// If subscriptionId not provided, try to find it from the DOM element data attribute
		if (!subId) {
			console.log('subscriptionId not provided; attempting to find from DOM or API');
			// Try to find slider with stationId
			const slider = document.querySelector(`input[type=range][data-subscription-id]`);
			if (slider) subId = slider.getAttribute('data-subscription-id');
		}

		// As a last resort, fetch subscriptions
		if (!subId) {
			const resp = await fetch('/api/subscriptions', { 
				headers: { 'Authorization': `Bearer ${token}` } 
			});
			if (!resp.ok) {
				const txt = await resp.text().catch(() => 'no body');
				throw new Error(`Failed to fetch subscriptions: ${resp.status} ${txt}`);
			}
			const data = await resp.json();
			const subscription = data.subscriptions?.find(s => String(s.station_id) === String(stationId));
			if (!subscription) throw new Error('Subscription not found for station');
			subId = subscription.id;
		}

		console.log(`Using subscriptionId=${subId} to update threshold`);

		const updateResp = await fetch(`/api/subscriptions/${subId}`, {
			method: 'PUT',
			headers: { 
				'Content-Type': 'application/json', 
				'Authorization': `Bearer ${token}` 
			},
			body: JSON.stringify({ threshold: threshold })
		});

		console.log(`PUT response status: ${updateResp.status}`);

		if (!updateResp.ok) {
			const errorData = await updateResp.text().catch(() => 'no body');
			console.error('Threshold update failed:', updateResp.status, errorData);
			throw new Error(`Failed to update threshold: ${updateResp.status}`);
		}

		const responseData = await updateResp.json().catch(() => ({}));
		console.log('Threshold update response:', responseData);
		console.log(`✅ Threshold updated to ${threshold} for station ${stationId} (subscription ${subId})`);

	} catch (e) {
		console.error('Update threshold error:', e);
		// Provide a slightly more helpful alert message
		alert('Failed to update threshold: ' + (e.message || e));
	}
}

