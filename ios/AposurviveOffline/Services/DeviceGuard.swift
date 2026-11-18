import Foundation
import UIKit

/// Decides when the model may run. Below 10% battery or when the phone is hot,
/// the app pauses the AI and serves static field cards instead.
@MainActor
final class DeviceGuard: ObservableObject {
    @Published private(set) var batteryLevel: Float = -1   // -1 = unknown (simulator)
    @Published private(set) var lowPowerMode = false
    @Published private(set) var thermal: ProcessInfo.ThermalState = .nominal
    @Published var userOverride = false

    static let minBattery: Float = 0.10

    private var observers: [NSObjectProtocol] = []

    init() {
        UIDevice.current.isBatteryMonitoringEnabled = true
        refresh()
        let nc = NotificationCenter.default
        for name in [UIDevice.batteryLevelDidChangeNotification,
                     Notification.Name.NSProcessInfoPowerStateDidChange,
                     ProcessInfo.thermalStateDidChangeNotification] {
            observers.append(nc.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.refresh() }
            })
        }
    }

    func refresh() {
        batteryLevel = UIDevice.current.batteryLevel
        lowPowerMode = ProcessInfo.processInfo.isLowPowerModeEnabled
        thermal = ProcessInfo.processInfo.thermalState
    }

    var pauseReason: String? {
        if userOverride { return nil }
        if batteryLevel >= 0 && batteryLevel < Self.minBattery { return "Battery under 10%: AI paused" }
        if thermal == .serious || thermal == .critical { return "Phone too hot: AI paused" }
        return nil
    }

    var aiAllowed: Bool { pauseReason == nil }

    var batteryText: String {
        batteryLevel < 0 ? "n/a" : "\(Int((batteryLevel * 100).rounded()))%"
    }
}
