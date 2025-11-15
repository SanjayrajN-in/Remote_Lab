/**
 * Custom Notification System
 * Provides beautiful, non-intrusive notifications for various events
 */

const NotificationSystem = {
    notificationQueue: [],
    maxNotifications: 5,
    defaultDuration: 5000, // 5 seconds

    /**
     * Show a notification
     * @param {string} message - The notification message
     * @param {string} type - 'success', 'error', 'warning', 'info'
     * @param {number} duration - How long to show (ms). 0 for persistent
     * @param {object} options - Additional options
     */
    show(message, type = 'info', duration = null, options = {}) {
        if (duration === null) {
            duration = this.defaultDuration;
        }

        const notification = {
            id: `notify_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            message,
            type,
            duration,
            options
        };

        // Create notification element
        const container = this.getContainer();
        const element = this.createNotificationElement(notification);
        
        container.appendChild(element);
        this.notificationQueue.push(notification);

        // Remove oldest notification if max reached
        if (container.children.length > this.maxNotifications) {
            const oldest = container.children[0];
            oldest.remove();
            this.notificationQueue.shift();
        }

        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                this.hide(notification.id);
            }, duration);
        }

        return notification.id;
    },

    /**
     * Create notification DOM element
     */
    createNotificationElement(notification) {
        const div = document.createElement('div');
        div.id = notification.id;
        div.className = `notification notification-${notification.type}`;
        
        // Icon and colors based on type
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };

        const colors = {
            success: '#10B981',
            error: '#EF4444',
            warning: '#F59E0B',
            info: '#3B82F6'
        };

        const colors2 = {
            success: 'rgba(16, 185, 129, 0.1)',
            error: 'rgba(239, 68, 68, 0.1)',
            warning: 'rgba(245, 158, 11, 0.1)',
            info: 'rgba(59, 130, 246, 0.1)'
        };

        div.innerHTML = `
            <div class="notification-content">
                <div class="notification-icon" style="color: ${colors[notification.type]};">
                    ${icons[notification.type]}
                </div>
                <div class="notification-text">
                    <div class="notification-message">${this.escapeHtml(notification.message)}</div>
                    ${notification.options.details ? `<div class="notification-details">${this.escapeHtml(notification.options.details)}</div>` : ''}
                </div>
            </div>
            <div class="notification-close" onclick="NotificationSystem.hide('${notification.id}')">×</div>
        `;

        // Apply styles
        div.style.cssText = `
            position: relative;
            margin-bottom: 12px;
            padding: 16px;
            background: ${colors2[notification.type]};
            border-left: 4px solid ${colors[notification.type]};
            border-radius: 8px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            animation: slideInNotification 0.3s ease-out;
            color: white;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        `;

        // Add close button styling
        const closeBtn = div.querySelector('.notification-close');
        if (closeBtn) {
            closeBtn.style.cssText = `
                cursor: pointer;
                font-size: 24px;
                line-height: 1;
                color: rgba(255, 255, 255, 0.6);
                transition: color 0.2s ease;
                flex-shrink: 0;
                user-select: none;
            `;
            closeBtn.onmouseover = () => closeBtn.style.color = 'rgba(255, 255, 255, 1)';
            closeBtn.onmouseout = () => closeBtn.style.color = 'rgba(255, 255, 255, 0.6)';
        }

        // Style the content wrapper
        const content = div.querySelector('.notification-content');
        if (content) {
            content.style.cssText = `
                display: flex;
                align-items: flex-start;
                gap: 12px;
                flex: 1;
            `;
        }

        // Style icon
        const icon = div.querySelector('.notification-icon');
        if (icon) {
            icon.style.cssText = `
                font-size: 20px;
                font-weight: bold;
                flex-shrink: 0;
                margin-top: 2px;
            `;
        }

        // Style text container
        const text = div.querySelector('.notification-text');
        if (text) {
            text.style.cssText = `
                flex: 1;
            `;
        }

        // Style message
        const message = div.querySelector('.notification-message');
        if (message) {
            message.style.cssText = `
                font-size: 14px;
                font-weight: 500;
                line-height: 1.4;
                margin: 0;
            `;
        }

        // Style details if present
        const details = div.querySelector('.notification-details');
        if (details) {
            details.style.cssText = `
                font-size: 12px;
                opacity: 0.8;
                margin-top: 6px;
                line-height: 1.3;
            `;
        }

        return div;
    },

    /**
     * Get or create notification container
     */
    getContainer() {
        let container = document.getElementById('notificationContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notificationContainer';
            container.style.cssText = `
                position: fixed;
                bottom: 20px;
                right: 20px;
                z-index: 9999;
                max-width: 450px;
                width: auto;
            `;
            document.body.appendChild(container);

            // Add CSS animations
            const style = document.createElement('style');
            style.textContent = `
                @keyframes slideInNotification {
                    from {
                        opacity: 0;
                        transform: translateX(100%);
                    }
                    to {
                        opacity: 1;
                        transform: translateX(0);
                    }
                }

                @keyframes slideOutNotification {
                    from {
                        opacity: 1;
                        transform: translateX(0);
                    }
                    to {
                        opacity: 0;
                        transform: translateX(100%);
                    }
                }

                .notification-exit {
                    animation: slideOutNotification 0.3s ease-out forwards !important;
                }
            `;
            document.head.appendChild(style);
        }
        return container;
    },

    /**
     * Hide and remove a notification
     */
    hide(id) {
        const element = document.getElementById(id);
        if (element) {
            element.classList.add('notification-exit');
            setTimeout(() => {
                element.remove();
                // Remove from queue
                this.notificationQueue = this.notificationQueue.filter(n => n.id !== id);
            }, 300);
        }
    },

    /**
     * Clear all notifications
     */
    clearAll() {
        const container = document.getElementById('notificationContainer');
        if (container) {
            container.innerHTML = '';
            this.notificationQueue = [];
        }
    },

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    // Convenience methods
    success(message, duration, details) {
        return this.show(message, 'success', duration, { details });
    },

    error(message, duration, details) {
        return this.show(message, 'error', duration || 7000, { details });
    },

    warning(message, duration, details) {
        return this.show(message, 'warning', duration || 6000, { details });
    },

    info(message, duration, details) {
        return this.show(message, 'info', duration, { details });
    }
};

// Event-specific notification helpers
const Notifications = {
    // Firmware flashing notifications
    flashingStarted() {
        return NotificationSystem.info('⚡ Flashing firmware...', 2000);
    },

    flashingProgress(percent) {
        // Update or show progress (can be enhanced for progress notifications)
        return NotificationSystem.info(`⚡ Flashing: ${percent}% complete`, 2000);
    },

    flashingFinished() {
        return NotificationSystem.success('✓ Firmware flashed successfully!', 5000, 'Device ready for use');
    },

    flashingFailed(error) {
        return NotificationSystem.error('✕ Firmware flashing failed', 0, error);
    },

    // Serial monitor notifications
    serialMonitorConnected(port) {
        return NotificationSystem.success(`✓ Serial monitor connected`, 4000, `Port: ${port}`);
    },

    serialMonitorDisconnected() {
        return NotificationSystem.warning('⚠ Serial monitor disconnected', 3000);
    },

    serialMonitorError(error) {
        return NotificationSystem.error('✕ Serial monitor error', 0, error);
    },

    // Video streaming notifications
    videoStreamingStarted() {
        return NotificationSystem.success('✓ Video streaming started', 3000, 'Live video is now active');
    },

    videoStreamingStopped() {
        return NotificationSystem.info('⊙ Video streaming stopped', 3000);
    },

    videoStreamingError(error) {
        return NotificationSystem.error('✕ Video streaming error', 0, error);
    },

    // Audio streaming notifications
    audioStreamingStarted() {
        return NotificationSystem.success('✓ Audio streaming started', 3000, '🔊 Audio is now active');
    },

    audioStreamingStopped() {
        return NotificationSystem.info('⊙ Audio streaming stopped', 3000);
    },

    audioStreamingError(error) {
        return NotificationSystem.error('✕ Audio streaming error', 0, error);
    },

    // Device connection notifications
    deviceConnected(deviceName, deviceType) {
        return NotificationSystem.success(`✓ Device connected`, 4000, `${deviceName} (${deviceType})`);
    },

    deviceDisconnected(deviceName) {
        return NotificationSystem.warning(`⚠ Device disconnected`, 3000, deviceName);
    },

    deviceError(error) {
        return NotificationSystem.error('✕ Device error', 0, error);
    },

    // Hub control notifications
    controlCommandSent(controlName, value) {
        return NotificationSystem.info(`✓ Command sent: ${controlName} = ${value}`, 2000);
    },

    controlCommandFailed(controlName, error) {
        return NotificationSystem.error(`✕ Failed to send command to ${controlName}`, 0, error);
    },

    controlCreated(controlName, controlType) {
        return NotificationSystem.info(`✓ Control created: ${controlName} (${controlType})`, 3000);
    },

    controlDeleted(controlName) {
        return NotificationSystem.info(`✓ Control deleted: ${controlName}`, 2000);
    },

    // Logic analyzer notifications
    logicAnalyzerStarted() {
        return NotificationSystem.success('✓ Logic analyzer started', 3000, 'Capturing data...');
    },

    logicAnalyzerStopped() {
        return NotificationSystem.info('⊙ Logic analyzer stopped', 3000);
    },

    logicAnalyzerError(error) {
        return NotificationSystem.error('✕ Logic analyzer error', 0, error);
    },

    triggerArmed(channel, edge) {
        return NotificationSystem.info(`✓ Trigger armed`, 2000, `Waiting for ${edge} edge on ${channel}`);
    },

    triggerFired(channel, edge) {
        return NotificationSystem.success(`✓ Trigger fired on ${channel}`, 3000, `${edge} edge detected`);
    },

    // Generic notifications
    success(message, details) {
        return NotificationSystem.success(message, 5000, details);
    },

    error(message, details) {
        return NotificationSystem.error(message, 0, details);
    },

    warning(message, details) {
        return NotificationSystem.warning(message, 0, details);
    },

    info(message, details) {
        return NotificationSystem.info(message, 4000, details);
    }
};

// Make available globally
window.NotificationSystem = NotificationSystem;
window.Notifications = Notifications;
