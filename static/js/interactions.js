// Modern Waze-like interactions
function calculateRoute() {
    console.log('Calculating route...');
    // Add loading animation
    const button = document.querySelector('.modern-button');
    if (button) {
        button.innerHTML = '<div class="loading-spinner"></div>';
        setTimeout(() => {
            button.innerHTML = '<span class="material-icons-outlined">navigation</span>';
        }, 2000);
    }
}

function selectRoute(index) {
    console.log('Selected route:', index);
    // Update route selection in session state
    // This would need to be integrated with Streamlit's state management
}

function startNavigation() {
    console.log('Starting navigation...');
    // Show navigation mode
    showNotification('Navigation started!', 'success');
}

function toggleMute() {
    console.log('Toggling voice...');
    const icon = document.querySelector('.fab .material-icons-outlined');
    if (icon) {
        icon.textContent = icon.textContent === 'volume_up' ? 'volume_off' : 'volume_up';
    }
    showNotification('Voice guidance toggled', 'info');
}

function showSettings() {
    console.log('Showing settings...');
    showNotification('Settings panel opened', 'info');
}

function reportTraffic() {
    console.log('Reporting traffic...');
    showNotification('Traffic report submitted', 'success');
}

function simulateDrive() {
    console.log('Starting drive simulation...');
    showNotification('Drive simulation started', 'info');
    
    // Add a simple drive simulation
    const mapContainer = document.querySelector('iframe[title="st.iframe"]');
    if (mapContainer) {
        // Create a moving marker simulation
        const simulationMarker = document.createElement('div');
        simulationMarker.style.cssText = `
            position: absolute; width: 20px; height: 20px; background: #1daeff;
            border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(29, 174, 255, 0.5);
            z-index: 1000; transition: all 0.5s ease-out; pointer-events: none;
        `;
        simulationMarker.innerHTML = '<div style="width: 100%; height: 100%; background: #1daeff; border-radius: 50%; animation: pulse 1s infinite;"></div>';
        document.body.appendChild(simulationMarker);
        
        // Animate the marker
        let position = 0;
        const animate = () => {
            position += 2;
            simulationMarker.style.left = position + 'px';
            simulationMarker.style.top = (200 + Math.sin(position * 0.01) * 50) + 'px';
            
            if (position < window.innerWidth - 50) {
                requestAnimationFrame(animate);
            } else {
                simulationMarker.remove();
                showNotification('Drive simulation completed!', 'success');
            }
        };
        animate();
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert ${type}`;
    notification.style.cssText = `
        position: fixed; top: 20px; right: 20px; z-index: 10000;
        padding: 12px 16px; border-radius: 8px; color: white;
        background: ${type === 'success' ? '#00d4aa' : type === 'warning' ? '#ffb800' : '#1daeff'};
        box-shadow: 0 4px 16px rgba(0,0,0,0.3); animation: slideIn 0.3s ease-out;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
    }
`;
document.head.appendChild(style);

// Initialize interactions
document.addEventListener('DOMContentLoaded', function() {
    // Add button animations
    const buttons = document.querySelectorAll('.modern-button, .fab');
    buttons.forEach(button => {
        button.addEventListener('click', function() {
            this.style.transform = 'scale(0.95)';
            setTimeout(() => {
                this.style.transform = '';
            }, 150);
        });
    });
    
    // Add route chip selection
    const routeChips = document.querySelectorAll('.route-chip');
    routeChips.forEach((chip, index) => {
        chip.addEventListener('click', function() {
            routeChips.forEach(c => c.classList.remove('selected'));
            this.classList.add('selected');
            selectRoute(index);
        });
    });
    
    // Add search input focus effects
    const searchInputs = document.querySelectorAll('input[type="text"]');
    searchInputs.forEach(input => {
        input.addEventListener('focus', function() {
            this.parentElement.style.transform = 'scale(1.02)';
        });
        input.addEventListener('blur', function() {
            this.parentElement.style.transform = 'scale(1)';
        });
    });
    
    // Add smooth scrolling for mobile
    if (window.innerWidth <= 768) {
        document.body.style.overflow = 'hidden';
    }
});

// Handle window resize
window.addEventListener('resize', function() {
    if (window.innerWidth <= 768) {
        document.body.style.overflow = 'hidden';
    } else {
        document.body.style.overflow = 'auto';
    }
});
