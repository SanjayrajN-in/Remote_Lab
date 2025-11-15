# Custom Notification System Guide

## Overview

A beautiful, non-intrusive notification system has been implemented to replace browser alerts. Notifications appear in the bottom-right corner with visual indicators and auto-dismiss functionality.

## Features

- **Visual Notifications**: Color-coded messages for different event types (success, error, warning, info)
- **Auto-Dismiss**: Notifications automatically disappear after a configurable duration
- **Queue Management**: Multiple notifications can be displayed simultaneously with automatic cleanup
- **Persistent Mode**: Error notifications stay visible until manually closed
- **Smooth Animations**: Slide-in and slide-out animations for better UX
- **Accessibility**: Clear icons and color schemes for different notification types

## Notification Types

### Success Notifications (Green)
Shown for successful operations:
- ✓ Firmware flashed successfully
- ✓ Serial monitor connected
- ✓ Video streaming started
- ✓ Control command sent
- ✓ File uploaded

### Error Notifications (Red)
Shown for failed operations (persistent until closed):
- ✕ Firmware flashing failed
- ✕ Serial monitor error
- ✕ Video streaming error
- ✕ Logic analyzer error
- ✕ Upload failed

### Warning Notifications (Orange)
Shown for warnings and information:
- ⚠ Serial monitor disconnected
- ⚠ Device disconnected
- ⚠ Device configuration issues

### Info Notifications (Blue)
Shown for informational messages:
- ℹ Connected to server
- ℹ Flashing progress updates
- ℹ Device detected

## Usage in Code

### Basic Notifications

```javascript
// Success notification (auto-dismisses after 5 seconds)
Notifications.success('Operation completed');

// Error notification (persistent until closed)
Notifications.error('Operation failed', 'Error details here');

// Warning notification
Notifications.warning('Warning message', 'Optional details');

// Info notification
Notifications.info('Information', 'Optional details');
```

### Specific Event Notifications

#### Firmware Flashing
```javascript
Notifications.flashingStarted();        // Shows flashing in progress
Notifications.flashingFinished();       // Shows success with checkmark
Notifications.flashingFailed(error);    // Shows error details
```

#### Serial Monitor
```javascript
Notifications.serialMonitorConnected(port);   // Port: COM3
Notifications.serialMonitorDisconnected();
Notifications.serialMonitorError(error);
```

#### Video/Audio Streaming
```javascript
Notifications.videoStreamingStarted();
Notifications.videoStreamingStopped();
Notifications.videoStreamingError(error);

Notifications.audioStreamingStarted();
Notifications.audioStreamingStopped();
Notifications.audioStreamingError(error);
```

#### Device Operations
```javascript
Notifications.deviceConnected(deviceName, deviceType);
Notifications.deviceDisconnected(deviceName);
Notifications.deviceError(error);
```

#### Hub Controls
```javascript
Notifications.controlCreated(controlName, controlType);
Notifications.controlDeleted(controlName);
Notifications.controlCommandSent(controlName, value);
Notifications.controlCommandFailed(controlName, error);
```

#### Logic Analyzer
```javascript
Notifications.logicAnalyzerStarted();
Notifications.logicAnalyzerStopped();
Notifications.logicAnalyzerError(error);
Notifications.triggerArmed(channel, edge);
Notifications.triggerFired(channel, edge);
```

## Notification Details

### Success Notifications
- **Duration**: 5 seconds (auto-dismiss)
- **Position**: Bottom-right corner
- **Color**: Green (#10B981)
- **Icon**: ✓

### Error Notifications
- **Duration**: Persistent (manual close required)
- **Position**: Bottom-right corner
- **Color**: Red (#EF4444)
- **Icon**: ✕

### Warning Notifications
- **Duration**: 6 seconds (auto-dismiss)
- **Position**: Bottom-right corner
- **Color**: Orange (#F59E0B)
- **Icon**: ⚠

### Info Notifications
- **Duration**: 4 seconds (auto-dismiss)
- **Position**: Bottom-right corner
- **Color**: Blue (#3B82F6)
- **Icon**: ℹ

## Advanced Usage

### Custom Duration
```javascript
// Show for 10 seconds instead of default
NotificationSystem.show('Custom message', 'success', 10000);

// Persistent (0 duration)
NotificationSystem.show('Important message', 'warning', 0);
```

### Custom Notification
```javascript
NotificationSystem.show('Message', 'success', 5000, {
    details: 'Additional details displayed below the main message'
});
```

### Hide Specific Notification
```javascript
const notificationId = Notifications.success('Some operation');
// Later...
NotificationSystem.hide(notificationId);
```

### Clear All Notifications
```javascript
NotificationSystem.clearAll();
```

## Styling

Notifications use:
- **Background**: Subtle semi-transparent overlay with glassmorphism effect
- **Border**: Left border (4px) matching notification type color
- **Font**: System fonts for optimal readability
- **Animation**: Smooth slide-in from right (0.3s)
- **Responsive**: Adapts to different screen sizes

## Browser Compatibility

- Chrome/Chromium (all versions)
- Firefox (all versions)
- Safari (all versions)
- Edge (all versions)
- Works on desktop and mobile

## Integration Points

The notification system is integrated throughout the application:

1. **Firmware Management**
   - Flash start/progress/complete
   - Upload status
   - Factory reset

2. **Serial Communication**
   - Connection/disconnection
   - Errors
   - Data transfer

3. **Video/Audio Streaming**
   - Stream start/stop
   - Errors
   - Status changes

4. **Device Management**
   - Device detection
   - Connection status
   - Errors

5. **Hub Controls**
   - Control creation/deletion
   - Command sending
   - Errors

6. **Logic Analyzer**
   - Start/stop
   - Trigger events
   - Errors

## Customization

To customize notification appearance, edit the styles in `static/notifications.js`:

- Colors: Modify the `colors` object in `createNotificationElement()`
- Duration: Change `defaultDuration` variable
- Position: Modify the `getContainer()` CSS
- Animation: Edit `@keyframes` in the style section

## Examples

### Flash Firmware Workflow
```javascript
// User clicks flash button
Notifications.flashingStarted();
// During flashing
Notifications.flashingProgress(50);  // Or similar progress indicators
// When complete
Notifications.flashingFinished();
// If error
Notifications.flashingFailed('Timeout during upload');
```

### Serial Monitor Workflow
```javascript
// User connects
Notifications.serialMonitorConnected('COM3');
// Receives data - no notification (happens in background)
// User disconnects
Notifications.serialMonitorDisconnected();
// If error
Notifications.serialMonitorError('Port not found');
```

## Troubleshooting

### Notifications not appearing
1. Ensure `notifications.js` is loaded in the HTML head
2. Check browser console for JavaScript errors
3. Verify z-index isn't being overridden by other CSS

### Notifications disappearing too quickly
- Increase the duration parameter
- Use `0` for persistent notifications

### Style issues
- Check that CSS animations are not disabled in browser settings
- Verify z-index value (default: 9999) isn't conflicting with other elements

## File Structure

```
/home/pi/remotelab/
├── static/
│   └── notifications.js      # Notification system
└── page/
    └── remotelab.html        # Integrated notifications
```

## Implementation Checklist

- [x] Create `notifications.js` library
- [x] Import library in HTML
- [x] Add notifications to socket event handlers
- [x] Add notifications to firmware flashing
- [x] Add notifications to serial monitor
- [x] Add notifications to video/audio streaming
- [x] Add notifications to device operations
- [x] Add notifications to hub controls
- [x] Add notifications to logic analyzer
- [x] Replace all `alert()` calls with notifications
- [x] Test on different browsers
- [x] Test responsive design

## Future Enhancements

- Sound notifications for critical events
- Desktop notifications (with permission)
- Notification history/log
- Customize per-user notification preferences
- Toast notification themes
