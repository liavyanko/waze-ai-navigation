// Live Autocomplete for Waze AI Navigation
// Handles real-time search suggestions and location selection

// Global variables
let startSuggestions = [];
let endSuggestions = [];
let currentStartQuery = '';
let currentEndQuery = '';

// Debounce function to limit API calls
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Handle start location input with debouncing
function handleStartInput(value) {
    if (value.length < 2) {
        hideStartSuggestions();
        return;
    }
    
    currentStartQuery = value;
    
    // Use debounced function for API calls
    debouncedStartSearch(value);
}

// Debounced search function for start location
const debouncedStartSearch = debounce(async (value) => {
    try {
        // For now, use enhanced mock suggestions since we don't have a backend API
        startSuggestions = generateMockSuggestions(value);
        showStartSuggestions();
    } catch (error) {
        console.error('Autocomplete error:', error);
        startSuggestions = generateMockSuggestions(value);
        showStartSuggestions();
    }
}, 300);

// Handle end location input with debouncing
function handleEndInput(value) {
    if (value.length < 2) {
        hideEndSuggestions();
        return;
    }
    
    currentEndQuery = value;
    
    // Use debounced function for API calls
    debouncedEndSearch(value);
}

// Debounced search function for end location
const debouncedEndSearch = debounce(async (value) => {
    try {
        // Call the backend API for real suggestions
        const response = await fetch('/api/autocomplete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: value,
                type: 'end',
                limit: 5
            })
        });
        
        // For now, use enhanced mock suggestions since we don't have a backend API
        endSuggestions = generateMockSuggestions(value);
        showEndSuggestions();
    } catch (error) {
        console.error('Autocomplete error:', error);
        // Fallback to mock suggestions
        endSuggestions = generateMockSuggestions(value);
        showEndSuggestions();
    }
}, 300);

// Show start location suggestions
function showStartSuggestions() {
    if (startSuggestions.length === 0) return;
    
    const dropdown = document.getElementById('start-suggestions');
    if (!dropdown) return;
    
    dropdown.innerHTML = startSuggestions.map((suggestion, index) => `
        <div class="suggestion-item" onclick="selectStartLocation('${suggestion.label}', ${suggestion.lat}, ${suggestion.lon})">
            <span class="location-icon material-icons-outlined">my_location</span>
            <div>
                <div class="location-text">${suggestion.label}</div>
                <div class="location-details">${suggestion.city || ''} ${suggestion.state || ''}</div>
            </div>
        </div>
    `).join('');
    
    dropdown.style.display = 'block';
}

// Show end location suggestions
function showEndSuggestions() {
    if (endSuggestions.length === 0) return;
    
    const dropdown = document.getElementById('end-suggestions');
    if (!dropdown) return;
    
    dropdown.innerHTML = endSuggestions.map((suggestion, index) => `
        <div class="suggestion-item" onclick="selectEndLocation('${suggestion.label}', ${suggestion.lat}, ${suggestion.lon})">
            <span class="location-icon material-icons-outlined">place</span>
            <div>
                <div class="location-text">${suggestion.label}</div>
                <div class="location-details">${suggestion.city || ''} ${suggestion.state || ''}</div>
            </div>
        </div>
    `).join('');
    
    dropdown.style.display = 'block';
}

// Hide start suggestions
function hideStartSuggestions() {
    const dropdown = document.getElementById('start-suggestions');
    if (dropdown) {
        // Delay hiding to allow for click events
        setTimeout(() => {
            dropdown.style.display = 'none';
        }, 150);
    }
}

// Hide end suggestions
function hideEndSuggestions() {
    const dropdown = document.getElementById('end-suggestions');
    if (dropdown) {
        // Delay hiding to allow for click events
        setTimeout(() => {
            dropdown.style.display = 'none';
        }, 150);
    }
}

// Select start location
function selectStartLocation(label, lat, lon) {
    console.log(`Selected start location: ${label} (${lat}, ${lon})`);
    
    const input = document.getElementById('start-input');
    if (input) {
        input.value = label;
        // Store coordinates in data attributes for later use
        input.setAttribute('data-lat', lat);
        input.setAttribute('data-lon', lon);
    }
    
    // Clear suggestions
    startSuggestions = [];
    hideStartSuggestions();
    
    // Store in localStorage for Streamlit to read
    localStorage.setItem('waze_start_location', JSON.stringify({label, lat, lon}));
    
    // Show success message
    showNotification(`📍 Start location set: ${label}`, 'success');
    
    // Trigger route calculation if both inputs are filled
    checkAndCalculateRoute();
}

// Select end location
function selectEndLocation(label, lat, lon) {
    console.log(`Selected end location: ${label} (${lat}, ${lon})`);
    
    const input = document.getElementById('end-input');
    if (input) {
        input.value = label;
        // Store coordinates in data attributes for later use
        input.setAttribute('data-lat', lat);
        input.setAttribute('data-lon', lon);
    }
    
    // Clear suggestions
    endSuggestions = [];
    hideEndSuggestions();
    
    // Store in localStorage for Streamlit to read
    localStorage.setItem('waze_end_location', JSON.stringify({label, lat, lon}));
    
    // Show success message
    showNotification(`🏁 End location set: ${label}`, 'success');
    
    // Trigger route calculation if both inputs are filled
    checkAndCalculateRoute();
}

// Check if both inputs are filled and calculate route
function checkAndCalculateRoute() {
    const startInput = document.getElementById('start-input');
    const endInput = document.getElementById('end-input');
    
    if (startInput && endInput && 
        startInput.value.trim() && endInput.value.trim() &&
        startInput.getAttribute('data-lat') && endInput.getAttribute('data-lon')) {
        
        // Auto-calculate route
        if (typeof calculateRoute === 'function') {
            calculateRoute();
        } else {
            console.log('Route calculation triggered - both locations selected');
        }
    }
}

// Generate realistic mock suggestions for demo purposes
function generateMockSuggestions(query) {
    const mockData = [
        { label: `${query} City Center`, city: 'Downtown', state: 'NY', lat: 40.7128, lon: -74.0060 },
        { label: `${query} Station`, city: 'Transit Hub', state: 'NY', lat: 40.7589, lon: -73.9851 },
        { label: `${query} Mall`, city: 'Shopping District', state: 'NY', lat: 40.7505, lon: -73.9934 },
        { label: `${query} Park`, city: 'Green Space', state: 'NY', lat: 40.7829, lon: -73.9654 },
        { label: `${query} Airport`, city: 'Airport Area', state: 'NY', lat: 40.6413, lon: -73.7781 },
        { label: `${query} University`, city: 'Academic District', state: 'NY', lat: 40.7484, lon: -73.9857 },
        { label: `${query} Hospital`, city: 'Medical Center', state: 'NY', lat: 40.7614, lon: -73.9776 },
        { label: `${query} Library`, city: 'Cultural District', state: 'NY', lat: 40.7527, lon: -73.9812 }
    ];
    
    // Filter and sort by relevance
    const filtered = mockData.filter(item => 
        item.label.toLowerCase().includes(query.toLowerCase())
    );
    
    // Sort by relevance (exact matches first)
    return filtered.sort((a, b) => {
        const aExact = a.label.toLowerCase() === query.toLowerCase();
        const bExact = b.label.toLowerCase() === query.toLowerCase();
        if (aExact && !bExact) return -1;
        if (!aExact && bExact) return 1;
        return a.label.length - b.label.length;
    });
}

// Handle Enter key press for location confirmation
function handleEnterKey(type, value) {
    if (!value || value.trim().length < 2) {
        showNotification(`⚠️ Please enter a valid location (at least 2 characters)`, 'warning');
        return;
    }
    
    // Create a mock location object based on the input
    const mockLocation = {
        label: value.trim(),
        lat: 32.0853 + (Math.random() - 0.5) * 0.1, // Tel Aviv area with some variation
        lon: 34.7818 + (Math.random() - 0.5) * 0.1,
        city: 'Tel Aviv',
        state: 'Israel'
    };
    
    if (type === 'start') {
        selectStartLocation(mockLocation.label, mockLocation.lat, mockLocation.lon);
    } else {
        selectEndLocation(mockLocation.label, mockLocation.lat, mockLocation.lon);
    }
    
    // Store in localStorage for Streamlit to read
    localStorage.setItem(`waze_${type}_location`, JSON.stringify(mockLocation));
    
    // Show success message
    showNotification(`📍 ${type === 'start' ? 'Start' : 'End'} location set: ${mockLocation.label}`, 'success');
}

// Initialize autocomplete when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('Autocomplete system initialized');
    
    // Add click outside listener to hide suggestions
    document.addEventListener('click', function(event) {
        const startDropdown = document.getElementById('start-suggestions');
        const endDropdown = document.getElementById('end-suggestions');
        const startInput = document.getElementById('start-input');
        const endInput = document.getElementById('end-input');
        
        if (startDropdown && !startInput.contains(event.target) && !startDropdown.contains(event.target)) {
            hideStartSuggestions();
        }
        
        if (endDropdown && !endInput.contains(event.target) && !endDropdown.contains(event.target)) {
            hideEndSuggestions();
        }
    });
    
    // Add keyboard navigation
    const startInput = document.getElementById('start-input');
    const endInput = document.getElementById('end-input');
    
    if (startInput) {
        startInput.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                hideStartSuggestions();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                handleEnterKey('start', this.value);
            }
        });
    }
    
    if (endInput) {
        endInput.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                hideEndSuggestions();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                handleEnterKey('end', this.value);
            }
        });
    }
    
    // Log successful initialization
    console.log('Autocomplete event listeners attached successfully');
});

// Make functions globally accessible
window.handleStartInput = handleStartInput;
window.handleEndInput = handleEndInput;
window.showStartSuggestions = showStartSuggestions;
window.showEndSuggestions = showEndSuggestions;
window.hideStartSuggestions = hideStartSuggestions;
window.hideEndSuggestions = hideEndSuggestions;
window.selectStartLocation = selectStartLocation;
window.selectEndLocation = selectEndLocation;

// Add fallback calculateRoute function if it doesn't exist
if (typeof calculateRoute === 'undefined') {
    window.calculateRoute = function() {
        console.log('calculateRoute called (fallback function)');
        
        // Get locations from localStorage
        const startLoc = localStorage.getItem('waze_start_location');
        const endLoc = localStorage.getItem('waze_end_location');
        
        if (startLoc && endLoc) {
            const start = JSON.parse(startLoc);
            const end = JSON.parse(endLoc);
            showNotification(`🚗 Route calculation: ${start.label} → ${end.label}`, 'info');
            
            // Store in session state for Streamlit to use
            localStorage.setItem('waze_route_ready', 'true');
        } else {
            showNotification('⚠️ Please select both start and end locations', 'warning');
        }
    };
    console.log('Fallback calculateRoute function registered');
}

// Notification function
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `waze-notification waze-notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <span class="notification-message">${message}</span>
            <button class="notification-close" onclick="this.parentElement.parentElement.remove()">×</button>
        </div>
    `;
    
    // Add to page
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

// Log that functions are now globally available
console.log('Global functions registered');
